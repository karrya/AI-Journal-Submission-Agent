"""Create encrypted, write-quiesced database and storage backups."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class BackupFailed(RuntimeError):
    """A backup failed without producing a final artifact."""


def _database_settings(database_url: str) -> tuple[URL, dict[str, str]]:
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise BackupFailed("invalid database configuration") from exc
    if (
        not url.drivername.startswith("mysql+")
        or not url.database
        or not DATABASE_NAME.fullmatch(url.database)
        or not url.username
    ):
        raise BackupFailed("a valid MySQL database URL is required")
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = url.password or ""
    return url, environment


def _dump_arguments(binary: str, url: URL) -> list[str]:
    assert url.database is not None
    return [
        binary,
        "--single-transaction",
        "--skip-lock-tables",
        "--no-tablespaces",
        f"--host={url.host or '127.0.0.1'}",
        f"--port={url.port or 3306}",
        f"--user={url.username}",
        f"--ignore-table={url.database}.auth_sessions",
        url.database,
    ]


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _add_file(bundle: tarfile.TarFile, path: Path, archive_name: str) -> None:
    stat = path.stat()
    info = tarfile.TarInfo(archive_name)
    info.size = stat.st_size
    info.mode = 0o600
    info.mtime = int(stat.st_mtime)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    with path.open("rb") as source:
        bundle.addfile(info, source)


def create_backup(
    output_dir: Path,
    *,
    dump_command: Sequence[str] | None = None,
    writes_stopped: bool = False,
    recipient: str | None = None,
    database_url: str | None = None,
    storage_root: Path | None = None,
    config_example: Path | None = None,
    mysqldump_binary: str = "mysqldump",
    age_binary: str = "age",
) -> Path:
    """Stream a tar archive directly to age and atomically publish it."""
    if not writes_stopped:
        raise BackupFailed("application writes must be stopped before backup")
    if not recipient:
        raise BackupFailed("AGE_RECIPIENT is required")
    if not database_url:
        raise BackupFailed("DATABASE_URL is required")

    url, environment = _database_settings(database_url)
    storage = Path(storage_root or PROJECT_ROOT / "storage").resolve()
    example = Path(config_example or PROJECT_ROOT / ".env.example").resolve()
    if not example.is_file():
        raise BackupFailed("the configuration example is missing")
    if storage.exists() and not storage.is_dir():
        raise BackupFailed("STORAGE_ROOT must be a directory")

    destination = Path(output_dir).resolve()
    if (
        destination == storage
        or destination in storage.parents
        or storage in destination.parents
    ):
        raise BackupFailed("backup output must be outside live storage")
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise BackupFailed("backup output must be a directory")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_path = destination / (
        f"academic-submission-agent-{timestamp}-{uuid.uuid4().hex[:8]}.tar.age"
    )
    partial_path = final_path.with_name(final_path.name + ".partial")
    age_process: subprocess.Popen[bytes] | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="academic-agent-backup-") as temp:
            temporary = Path(temp)
            dump_path = temporary / "database.sql"
            command = list(dump_command or _dump_arguments(mysqldump_binary, url))
            with dump_path.open("wb") as dump_file:
                dump_result = subprocess.run(
                    command,
                    stdout=dump_file,
                    stderr=subprocess.DEVNULL,
                    env=environment,
                    check=False,
                )
            if dump_result.returncode != 0:
                raise BackupFailed("database dump failed; temporary data removed")

            archived_files: list[tuple[Path, str]] = [
                (dump_path, "database.sql"),
                (example, "config/.env.example"),
            ]
            if storage.exists():
                for path in sorted(storage.rglob("*")):
                    if path.is_symlink():
                        raise BackupFailed("live storage must not contain symlinks")
                    if path.is_file():
                        archived_files.append(
                            (path, f"storage/{path.relative_to(storage).as_posix()}")
                        )
                    elif not path.is_dir():
                        raise BackupFailed("live storage contains an unsupported file")

            manifest_files = []
            for path, archive_name in archived_files:
                sha256, size = _hash_file(path)
                manifest_files.append(
                    {"path": archive_name, "sha256": sha256, "size": size}
                )
            manifest = {
                "format_version": 1,
                "created_at": datetime.now(UTC).isoformat(),
                "source_database": url.database,
                "sessions_excluded": True,
                "files": manifest_files,
            }
            manifest_bytes = json.dumps(
                manifest, indent=2, sort_keys=True, ensure_ascii=True
            ).encode("utf-8")

            descriptor = os.open(
                partial_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as encrypted_output:
                age_process = subprocess.Popen(
                    [age_binary, "-r", recipient],
                    stdin=subprocess.PIPE,
                    stdout=encrypted_output,
                    stderr=subprocess.DEVNULL,
                )
                assert age_process.stdin is not None
                try:
                    with tarfile.open(fileobj=age_process.stdin, mode="w|") as bundle:
                        for path, archive_name in archived_files:
                            _add_file(bundle, path, archive_name)
                        info = tarfile.TarInfo("manifest.json")
                        info.size = len(manifest_bytes)
                        info.mode = 0o600
                        info.mtime = int(datetime.now(UTC).timestamp())
                        bundle.addfile(info, io.BytesIO(manifest_bytes))
                    age_process.stdin.close()
                except Exception:
                    age_process.stdin.close()
                    age_process.kill()
                    age_process.wait()
                    raise
                if age_process.wait() != 0:
                    raise BackupFailed("age encryption failed; temporary data removed")
            age_process = None

        os.replace(partial_path, final_path)
        return final_path
    except BackupFailed:
        raise
    except Exception as exc:
        raise BackupFailed("backup failed; temporary data removed") from exc
    finally:
        if age_process is not None and age_process.poll() is None:
            age_process.kill()
            age_process.wait()
        partial_path.unlink(missing_ok=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "backups")
    parser.add_argument("--confirm-writes-stopped", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    if not args.confirm_writes_stopped:
        raise SystemExit("stop application writes and pass --confirm-writes-stopped")
    try:
        archive = create_backup(
            args.output_dir,
            writes_stopped=args.confirm_writes_stopped,
            recipient=os.environ.get("AGE_RECIPIENT"),
            database_url=os.environ.get("DATABASE_URL"),
            storage_root=Path(os.environ.get("STORAGE_ROOT", PROJECT_ROOT / "storage")),
            config_example=PROJECT_ROOT / ".env.example",
        )
    except BackupFailed as exc:
        raise SystemExit(str(exc)) from None
    print(f"Encrypted backup created: {archive}")


if __name__ == "__main__":
    main()
