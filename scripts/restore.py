"""Restore encrypted backups only to an empty, isolated test target."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEVELOPMENT_DATABASE = "academic_submission_agent"
DATABASE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*_test$")
SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class RestoreFailed(RuntimeError):
    """The backup or isolated restore failed verification."""


@dataclass
class RestoreVerification:
    table_count: int
    compared_row_counts: int
    file_count: int
    verified_hash_count: int
    source_unchanged: bool
    manifest: dict


def validate_restore_target(
    database_name: str,
    target_directory: str | Path,
    *,
    live_storage: Path = PROJECT_ROOT / "storage",
) -> Path:
    """Require a _test database and an empty directory outside live storage."""
    if database_name == DEVELOPMENT_DATABASE or not DATABASE_NAME.fullmatch(
        database_name
    ):
        raise ValueError("restore database must be an isolated name ending in _test")
    raw_target = Path(target_directory).expanduser()
    if raw_target.is_symlink():
        raise ValueError("restore directory must not be a symlink")
    if not raw_target.is_absolute():
        raw_target = PROJECT_ROOT / raw_target
    target = raw_target.resolve()
    live = Path(live_storage).resolve()
    if target == live or live in target.parents:
        raise ValueError("restore directory must be outside live storage")
    if target.exists():
        if not target.is_dir():
            raise ValueError("restore target must be a directory")
        if any(target.iterdir()):
            raise ValueError("restore directory must be empty")
    return target


def validate_age_key_file(key_file: str | Path) -> Path:
    """Require a restrictive private-key file outside the project."""
    raw_path = Path(key_file).expanduser()
    if raw_path.is_symlink():
        raise ValueError("age private key must not be a symlink")
    path = raw_path.resolve()
    if path == PROJECT_ROOT or PROJECT_ROOT in path.parents:
        raise ValueError("age private key must be outside the project")
    if not path.is_file():
        raise ValueError("age private key file is missing")
    if path.stat().st_mode & 0o077:
        raise ValueError(
            "age private key permissions must not allow group/other access"
        )
    return path


def _validate_member_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not name or ".." in path.parts or "." in path.parts:
        raise RestoreFailed("archive contains an unsafe path")
    return path


def _read_manifest(
    bundle: tarfile.TarFile, members: dict[str, tarfile.TarInfo]
) -> dict:
    if "manifest.json" not in members:
        raise RestoreFailed("archive manifest is missing")
    manifest_file = bundle.extractfile(members["manifest.json"])
    if manifest_file is None:
        raise RestoreFailed("archive manifest is unreadable")
    try:
        manifest = json.load(manifest_file)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestoreFailed("archive manifest is invalid") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != 1
        or manifest.get("sessions_excluded") is not True
        or not isinstance(manifest.get("source_database"), str)
        or not SAFE_NAME.fullmatch(manifest["source_database"])
        or not isinstance(manifest.get("files"), list)
    ):
        raise RestoreFailed("archive manifest has an unsupported format")

    archived_paths = set(members) - {"manifest.json"}
    manifest_paths: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise RestoreFailed("archive manifest contains an invalid entry")
        path = entry["path"]
        if (
            not isinstance(path, str)
            or path in manifest_paths
            or not isinstance(entry["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
            or type(entry["size"]) is not int
            or entry["size"] < 0
        ):
            raise RestoreFailed("archive manifest contains an invalid entry")
        _validate_member_name(path)
        manifest_paths.add(path)
    if manifest_paths != archived_paths:
        raise RestoreFailed("archive files do not match the manifest")

    for entry in manifest["files"]:
        extracted = bundle.extractfile(members[entry["path"]])
        if extracted is None:
            raise RestoreFailed("archive member is unreadable")
        digest = hashlib.sha256()
        size = 0
        while chunk := extracted.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise RestoreFailed("archive SHA-256 verification failed")
    return manifest


def _validate_dump(dump_path: Path) -> None:
    dump = dump_path.read_text(encoding="utf-8")
    if re.search(r"^\s*USE\s+", dump, flags=re.IGNORECASE | re.MULTILINE) or re.search(
        r"\b(?:CREATE|DROP|ALTER)\s+(?:SCHEMA|DATABASE)\b",
        dump,
        flags=re.IGNORECASE,
    ):
        raise RestoreFailed("database dump contains unsafe database selection or DDL")


def extract_verified_backup(
    backup_path: str | Path,
    age_secret_key_file: str | Path,
    destination: str | Path,
    *,
    age_binary: str = "age",
) -> dict:
    """Decrypt to temporary storage, verify every hash, then extract safely."""
    key_file = validate_age_key_file(age_secret_key_file)
    archive = Path(backup_path).resolve()
    if not archive.is_file():
        raise RestoreFailed("encrypted backup is missing")
    target = Path(destination).resolve()
    if target.exists():
        raise RestoreFailed("verified extraction target must not already exist")

    try:
        with tempfile.TemporaryDirectory(prefix="academic-agent-restore-") as temp:
            plaintext_tar = Path(temp) / "verified.tar"
            with plaintext_tar.open("wb") as output:
                result = subprocess.run(
                    [age_binary, "-d", "-i", str(key_file), str(archive)],
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            if result.returncode != 0:
                raise RestoreFailed("age decryption failed")

            with tarfile.open(plaintext_tar, mode="r:") as bundle:
                members: dict[str, tarfile.TarInfo] = {}
                for member in bundle.getmembers():
                    name = _validate_member_name(member.name).as_posix()
                    if name in members or not member.isreg():
                        raise RestoreFailed("archive contains an unsupported member")
                    members[name] = member
                manifest = _read_manifest(bundle, members)
                for name, member in members.items():
                    relative = PurePosixPath(name)
                    output_path = target.joinpath(*relative.parts)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(member)
                    if source is None:
                        raise RestoreFailed("archive member is unreadable")
                    descriptor = os.open(
                        output_path,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                    with os.fdopen(descriptor, "wb") as output:
                        shutil.copyfileobj(source, output)
            _validate_dump(target / "database.sql")
        return manifest
    except RestoreFailed:
        shutil.rmtree(target, ignore_errors=True)
        raise
    except (OSError, tarfile.TarError) as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise RestoreFailed("encrypted backup could not be verified") from exc


def _create_engine(database_url: str) -> Engine:
    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.database import create_mysql_engine

    return create_mysql_engine(database_url)


def _database_snapshot(engine: Engine, expected_database: str) -> dict[str, int]:
    with engine.connect() as connection:
        actual_database = connection.scalar(text("SELECT DATABASE()"))
        if actual_database != expected_database:
            raise RestoreFailed(
                "connected database does not match the requested target"
            )
        rows = connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() ORDER BY table_name"
            )
        )
        tables = [row[0] for row in rows]
        snapshot: dict[str, int] = {}
        for table in tables:
            if not SAFE_NAME.fullmatch(table):
                raise RestoreFailed("database contains an unsupported table name")
            count = connection.scalar(text(f"SELECT COUNT(*) FROM `{table}`"))
            snapshot[table] = int(count)
        return snapshot


def _run_mysql_restore(
    command: Sequence[str], environment: dict[str, str], dump_path: Path
) -> None:
    with dump_path.open("rb") as dump:
        result = subprocess.run(
            command,
            stdin=dump,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            check=False,
        )
    if result.returncode != 0:
        raise RestoreFailed("isolated database import failed")


def _recreate_excluded_tables(engine: Engine) -> None:
    """Recreate only intentionally omitted tables, without stamping revisions."""
    sys.path.insert(0, str(BACKEND_DIR))
    from app.models import Base

    Base.metadata.tables["auth_sessions"].create(bind=engine, checkfirst=True)


def _run_alembic(database_url: str) -> None:
    engine = _create_engine(database_url)
    try:
        _recreate_excluded_tables(engine)
    except Exception as exc:
        raise RestoreFailed("Alembic verification failed") from exc
    finally:
        engine.dispose()
    environment = os.environ.copy()
    environment["ALEMBIC_DATABASE_URL"] = database_url
    for arguments in (("upgrade", "head"), ("check",)):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(BACKEND_DIR / "alembic.ini"),
                *arguments,
            ],
            cwd=BACKEND_DIR,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            raise RestoreFailed("Alembic verification failed")


def _mysql_restore_arguments(database_url: str) -> tuple[list[str], dict[str, str]]:
    url = make_url(database_url)
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = url.password or ""
    command = [
        "mysql",
        f"--host={url.host or '127.0.0.1'}",
        f"--port={url.port or 3306}",
        f"--user={url.username}",
        f"--database={url.database}",
    ]
    return command, environment


def _clear_restore_directory(target: Path, existed: bool) -> None:
    if existed:
        if target.exists():
            for child in target.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    else:
        shutil.rmtree(target, ignore_errors=True)


def restore_backup(
    backup_path: str | Path,
    source_database_url: str,
    target_database_url: str,
    target_directory: str | Path,
    *,
    confirmation: str,
    age_secret_key_file: str | Path,
    engine_factory: Callable[[str], Engine] = _create_engine,
    mysql_runner: Callable[
        [Sequence[str], dict[str, str], Path], None
    ] = _run_mysql_restore,
    migration_runner: Callable[[str], None] = _run_alembic,
) -> RestoreVerification:
    """Restore and compare tables, rows, files, hashes, and source immutability."""
    if confirmation != "RESTORE":
        raise ValueError("restore requires explicit --confirm RESTORE")
    source_url = make_url(source_database_url)
    target_url = make_url(target_database_url)
    if (
        not source_url.drivername.startswith("mysql+")
        or not target_url.drivername.startswith("mysql+")
        or not source_url.database
        or not target_url.database
        or not source_url.username
        or not target_url.username
    ):
        raise ValueError("valid source and target MySQL URLs are required")
    if source_url.database == target_url.database:
        raise ValueError("restore target must differ from the development database")
    target = validate_restore_target(target_url.database, target_directory)
    target_existed = target.exists()
    source_engine: Engine | None = None
    target_engine: Engine | None = None

    try:
        source_engine = engine_factory(source_database_url)
        target_engine = engine_factory(target_database_url)
        source_before = _database_snapshot(source_engine, source_url.database)
        if _database_snapshot(target_engine, target_url.database):
            raise RestoreFailed("restore database must be empty")

        with tempfile.TemporaryDirectory(prefix="academic-agent-verified-") as temp:
            verified = Path(temp) / "verified"
            manifest = extract_verified_backup(
                backup_path, age_secret_key_file, verified
            )
            if manifest["source_database"] != source_url.database:
                raise RestoreFailed(
                    "backup source does not match the development database"
                )
            command, environment = _mysql_restore_arguments(target_database_url)
            mysql_runner(command, environment, verified / "database.sql")
            dumped_tables = _database_snapshot(target_engine, target_url.database)
            expected_dump = {
                table: count
                for table, count in source_before.items()
                if table != "auth_sessions"
            }
            if dumped_tables != expected_dump:
                raise RestoreFailed(
                    "restored dump tables or rows do not match the source"
                )
            migration_runner(target_database_url)

            if target.exists() and any(target.iterdir()):
                raise RestoreFailed("restore directory became non-empty")
            storage_source = verified / "storage"
            storage_entries = [
                entry
                for entry in manifest["files"]
                if entry["path"].startswith("storage/")
            ]
            for entry in storage_entries:
                relative = PurePosixPath(entry["path"]).relative_to("storage")
                output_path = target.joinpath(*relative.parts)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(storage_source.joinpath(*relative.parts), output_path)

        source_after = _database_snapshot(source_engine, source_url.database)
        if source_after != source_before:
            raise RestoreFailed("development database changed during restore")
        target_after = _database_snapshot(target_engine, target_url.database)
        if not set(source_before).issubset(target_after):
            raise RestoreFailed("post-migration source tables are missing")
        compared = 0
        for table, source_count in source_before.items():
            if table == "auth_sessions":
                if target_after[table] != 0:
                    raise RestoreFailed("sessions must not be restored")
                continue
            if target_after[table] != source_count:
                raise RestoreFailed("restored row counts do not match the source")
            compared += 1

        expected_files = {
            entry["path"].removeprefix("storage/"): entry["sha256"]
            for entry in manifest["files"]
            if entry["path"].startswith("storage/")
        }
        actual_files: dict[str, str] = {}
        if target.exists():
            for path in target.rglob("*"):
                if path.is_symlink() or not path.is_file() and not path.is_dir():
                    raise RestoreFailed("restored storage contains an unsupported file")
                if path.is_file():
                    digest = hashlib.sha256()
                    with path.open("rb") as restored:
                        while chunk := restored.read(1024 * 1024):
                            digest.update(chunk)
                    actual_files[path.relative_to(target).as_posix()] = (
                        digest.hexdigest()
                    )
        if actual_files != expected_files:
            raise RestoreFailed("restored file counts or hashes do not match")
        return RestoreVerification(
            table_count=len(target_after),
            compared_row_counts=compared,
            file_count=len(actual_files),
            verified_hash_count=len(manifest["files"]),
            source_unchanged=True,
            manifest=manifest,
        )
    except RestoreFailed:
        _clear_restore_directory(target, target_existed)
        raise
    except Exception as exc:
        _clear_restore_directory(target, target_existed)
        raise RestoreFailed(
            "isolated restore failed; development data was not targeted"
        ) from exc
    finally:
        if source_engine is not None:
            source_engine.dispose()
        if target_engine is not None:
            target_engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--database", default=f"{DEVELOPMENT_DATABASE}_restore_test")
    parser.add_argument("--target-directory", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    source_url = os.environ.get("DATABASE_URL", "")
    configured_target = os.environ.get("RESTORE_DATABASE_URL")
    if configured_target:
        target_url = configured_target
    else:
        test_url = os.environ.get("TEST_DATABASE_URL")
        if not test_url:
            raise SystemExit("RESTORE_DATABASE_URL or TEST_DATABASE_URL is required")
        target_url = (
            make_url(test_url)
            .set(database=args.database)
            .render_as_string(hide_password=False)
        )
    if make_url(target_url).database != args.database:
        raise SystemExit("RESTORE_DATABASE_URL must match --database")
    key_file = os.environ.get("AGE_SECRET_KEY_FILE")
    if not key_file:
        raise SystemExit("AGE_SECRET_KEY_FILE is required")
    try:
        verification = restore_backup(
            args.backup,
            source_url,
            target_url,
            args.target_directory,
            confirmation=args.confirm,
            age_secret_key_file=key_file,
        )
    except (ValueError, RestoreFailed) as exc:
        raise SystemExit(str(exc)) from None
    print(
        json.dumps(
            {
                "table_count": verification.table_count,
                "compared_row_counts": verification.compared_row_counts,
                "file_count": verification.file_count,
                "verified_hash_count": verification.verified_hash_count,
                "source_unchanged": verification.source_unchanged,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
