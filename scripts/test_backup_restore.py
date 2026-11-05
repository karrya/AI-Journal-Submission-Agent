"""Execute one real encrypted backup and isolated BACKUP-01 restore proof."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from scripts.backup import BackupFailed, create_backup  # noqa: E402
from scripts.restore import (  # noqa: E402
    RestoreFailed,
    _create_engine,
    _database_snapshot,
    restore_backup,
)

TARGET_DATABASE = "academic_submission_agent_restore_test"
AGE_DIRECTORY = Path.home() / ".config/academic-submission-agent/age"


def _configure_age() -> tuple[str, Path]:
    recipient = os.environ.get("AGE_RECIPIENT")
    key_file = os.environ.get("AGE_SECRET_KEY_FILE")
    if bool(recipient) != bool(key_file):
        raise RuntimeError("AGE_RECIPIENT and AGE_SECRET_KEY_FILE must be set together")
    if not recipient:
        recipient_path = AGE_DIRECTORY / "recipient.txt"
        default_key = AGE_DIRECTORY / "backup-key.txt"
        if not recipient_path.is_file() or not default_key.is_file():
            raise RuntimeError("dedicated age key configuration is unavailable")
        recipient = recipient_path.read_text(encoding="utf-8").strip()
        key_file = str(default_key)
        os.environ["AGE_RECIPIENT"] = recipient
        os.environ["AGE_SECRET_KEY_FILE"] = key_file
    assert recipient is not None and key_file is not None
    return recipient, Path(key_file)


def _require_application_stopped() -> None:
    for command in (["pgrep", "-x", "uvicorn"], ["pgrep", "-f", "app.main:app"]):
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            raise RuntimeError("stop application writes before BACKUP-01")


@contextmanager
def _temporary_proof_file(storage: Path) -> Iterator[Path]:
    """Add one exclusive proof file only to empty storage, then remove it."""
    if storage.is_symlink():
        raise RuntimeError("development storage must not be a symlink")
    created_root = not storage.exists()
    if created_root:
        storage.mkdir(parents=True)
    elif not storage.is_dir():
        raise RuntimeError("development storage is not a directory")
    elif any(storage.iterdir()):
        raise RuntimeError("development storage is not empty; proof file not created")

    proof = storage / f".backup-01-temporary-proof-{uuid.uuid4().hex}.txt"
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(proof, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        stat = os.fstat(descriptor)
        identity = (stat.st_dev, stat.st_ino)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = None
            output.write("BACKUP-01 temporary proof file; delete after verification.\n")
            output.flush()
            os.fsync(output.fileno())
        yield proof
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if identity is not None:
            current = proof.lstat()
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("temporary proof file changed during BACKUP-01")
            proof.unlink()
        if created_root:
            storage.rmdir()


def _storage_snapshot(storage: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    if not storage.exists():
        return snapshot
    for path in sorted(storage.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("development storage contains a symlink")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            snapshot[path.relative_to(storage).as_posix()] = digest.hexdigest()
    return snapshot


def _development_snapshot(database_url: str, storage: Path) -> tuple[dict, dict]:
    engine = _create_engine(database_url)
    try:
        database_name = make_url(database_url).database
        if not database_name:
            raise RuntimeError("development database name is missing")
        row_counts = _database_snapshot(engine, database_name)
        checksums: dict[str, str] = {}
        schema_hashes: dict[str, str] = {}
        with engine.connect() as connection:
            for table in row_counts:
                row = connection.execute(text(f"CHECKSUM TABLE `{table}`")).one()
                checksums[table] = str(row[1])
                ddl = connection.execute(text(f"SHOW CREATE TABLE `{table}`")).one()[1]
                schema_hashes[table] = hashlib.sha256(
                    str(ddl).encode("utf-8")
                ).hexdigest()
        database = {
            "row_counts": row_counts,
            "table_checksums": checksums,
            "schema_hashes": schema_hashes,
        }
    finally:
        engine.dispose()
    return database, _storage_snapshot(storage)


def _target_url() -> str:
    configured = os.environ.get("RESTORE_DATABASE_URL")
    if configured:
        if make_url(configured).database != TARGET_DATABASE:
            raise RuntimeError("RESTORE_DATABASE_URL has the wrong target")
        return configured
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        raise RuntimeError("TEST_DATABASE_URL or RESTORE_DATABASE_URL is required")
    parsed_test = make_url(test_url)
    admin_url = os.environ.get("RESTORE_ADMIN_URL")
    if admin_url:
        admin_engine = _create_engine(admin_url)
        try:
            with admin_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                connection.execute(
                    text(
                        f"CREATE DATABASE IF NOT EXISTS `{TARGET_DATABASE}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                    )
                )
                table_count = connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = :database"
                    ),
                    {"database": TARGET_DATABASE},
                )
                if table_count:
                    raise RuntimeError("restore database must be empty")
                connection.exec_driver_sql(
                    f"GRANT ALL PRIVILEGES ON `{TARGET_DATABASE}`.* TO %s@%s",
                    (parsed_test.username, parsed_test.host),
                )
        finally:
            admin_engine.dispose()
    return parsed_test.set(database=TARGET_DATABASE).render_as_string(
        hide_password=False
    )


def _remove_restore_directory(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise RuntimeError("restore directory cleanup failed") from exc
    if path.exists():
        raise RuntimeError("restore directory cleanup failed; plaintext remains")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    _require_application_stopped()
    source_url = os.environ.get("DATABASE_URL", "")
    source_database = make_url(source_url).database
    if source_database != "academic_submission_agent":
        raise SystemExit("BACKUP-01 requires the development source database")
    storage = Path(os.environ.get("STORAGE_ROOT", PROJECT_ROOT / "storage")).resolve()
    recipient, key_file = _configure_age()
    target_url = _target_url()

    try:
        before = _development_snapshot(source_url, storage)
        restore_parent = Path(tempfile.mkdtemp(prefix="academic-agent-restore-proof-"))
        try:
            with _temporary_proof_file(storage):
                archive = create_backup(
                    PROJECT_ROOT / "backups",
                    writes_stopped=True,
                    recipient=recipient,
                    database_url=source_url,
                    storage_root=storage,
                    config_example=PROJECT_ROOT / ".env.example",
                )
                print(f"Encrypted backup created: {archive}")
                verification = restore_backup(
                    archive,
                    source_url,
                    target_url,
                    restore_parent / "storage",
                    confirmation="RESTORE",
                    age_secret_key_file=key_file,
                    live_storage=storage,
                )
            after = _development_snapshot(source_url, storage)
            if after != before:
                raise RuntimeError("development data changed during BACKUP-01")
            with archive.open("rb") as encrypted:
                if not encrypted.read(24).startswith(b"age-encryption.org/v1"):
                    raise RuntimeError("final backup is not an age encrypted artifact")
            unencrypted = [
                path
                for pattern in ("*.sql", "*.tar", "*.partial")
                for path in (PROJECT_ROOT / "backups").rglob(pattern)
            ]
            if unencrypted:
                raise RuntimeError("unencrypted or partial backup artifacts remain")
            result = {
                "table_count_after_alembic": verification.table_count,
                "compared_source_tables": verification.compared_row_counts,
                "restored_file_count": verification.file_count,
                "verified_manifest_hashes": verification.verified_hash_count,
                "development_unchanged": after == before,
                "temporary_proof_file_cleaned": True,
                "isolated_restore_directory_removed": True,
            }
        finally:
            _remove_restore_directory(restore_parent)
        print(json.dumps(result, sort_keys=True))
    except (BackupFailed, RestoreFailed, RuntimeError) as exc:
        raise SystemExit(f"BACKUP-01 failed: {exc}") from None


if __name__ == "__main__":
    main()
