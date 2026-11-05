from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import traceback
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from scripts.backup import BackupFailed, create_backup
from scripts.restore import (
    RestoreFailed,
    _recreate_excluded_tables,
    _mysql_restore_arguments,
    _run_mysql_restore,
    _validate_dump,
    extract_verified_backup,
    restore_backup,
    validate_age_key_file,
    validate_restore_target,
)
from scripts.test_backup_restore import _remove_restore_directory, _temporary_proof_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UNIT_PASSWORD = "unit-only-password"


@pytest.fixture
def age_identity(tmp_path):
    key_file = tmp_path / "age-key.txt"
    with key_file.open("wb") as key_output:
        subprocess.run(
            ["age-keygen"],
            stdout=key_output,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    key_file.chmod(0o600)
    recipient = subprocess.check_output(
        ["age-keygen", "-y", str(key_file)], text=True
    ).strip()
    return key_file, recipient


def make_dump_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-mysqldump.py"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
Path(os.environ['DUMP_CAPTURE']).write_text(json.dumps({
    'args': sys.argv[1:],
    'password_in_environment': os.environ.get('MYSQL_PWD') == 'unit-only-password',
    'password_in_arguments': 'unit-only-password' in sys.argv,
}), encoding='utf-8')
print('CREATE TABLE `authors` (`id` INT);')
print('INSERT INTO `authors` VALUES (1);')
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


def backup_arguments(tmp_path: Path, age_identity, **overrides):
    key_file, recipient = age_identity
    config_example = tmp_path / "example.env"
    if not config_example.exists():
        config_example.write_text("DATABASE_URL=\n", encoding="utf-8")
    storage = tmp_path / "source-storage"
    if not storage.exists():
        (storage / "manuscripts").mkdir(parents=True)
        (storage / "manuscripts" / "proof.pdf").write_bytes(b"stored manuscript")
    arguments = {
        "writes_stopped": True,
        "recipient": recipient,
        "database_url": (
            "mysql+pymysql://asa_app:unit-only-password@127.0.0.1:3306/"
            "academic_submission_agent"
        ),
        "storage_root": storage,
        "config_example": config_example,
        "mysqldump_binary": str(make_dump_executable(tmp_path)),
    }
    arguments.update(overrides)
    return key_file, arguments


def decrypt_archive(archive: Path, key_file: Path) -> bytes:
    return subprocess.check_output(["age", "-d", "-i", str(key_file), str(archive)])


def encrypt_archive(plain_archive: Path, encrypted: Path, recipient: str) -> None:
    with plain_archive.open("rb") as source, encrypted.open("wb") as destination:
        subprocess.run(
            ["age", "-r", recipient],
            stdin=source,
            stdout=destination,
            stderr=subprocess.DEVNULL,
            check=True,
        )


def make_sql_archive(tmp_path: Path, age_identity, dump: bytes) -> tuple[Path, Path]:
    key_file, recipient = age_identity
    manifest = {
        "format_version": 1,
        "sessions_excluded": True,
        "source_database": "academic_submission_agent",
        "files": [
            {
                "path": "database.sql",
                "sha256": hashlib.sha256(dump).hexdigest(),
                "size": len(dump),
            }
        ],
    }
    plain_path = tmp_path / "sql-proof.tar"
    with tarfile.open(plain_path, mode="w:") as bundle:
        for name, content in (
            ("database.sql", dump),
            ("manifest.json", json.dumps(manifest).encode("utf-8")),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    archive = tmp_path / "sql-proof.tar.age"
    encrypt_archive(plain_path, archive, recipient)
    plain_path.unlink()
    return archive, key_file


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def scalar(self, query):
        statement = str(query)
        if statement == "SELECT DATABASE()":
            return self.database.name
        if statement.startswith("SELECT COUNT(*) FROM `"):
            table = statement.removeprefix("SELECT COUNT(*) FROM `").removesuffix("`")
            return self.database.tables.get(table)
        raise AssertionError(statement)

    def execute(self, query):
        statement = str(query)
        if statement.startswith("SELECT table_name FROM information_schema.tables"):
            return FakeResult([(name,) for name in sorted(self.database.tables)])
        raise AssertionError(statement)


class FakeEngine:
    def __init__(self, database):
        self.database = database

    def connect(self):
        return FakeConnection(self.database)

    def dispose(self):
        return None


class FakeDatabase:
    def __init__(self, name, tables=None):
        self.name = name
        self.tables = dict(tables or {})


def test_restore_refuses_development_target():
    with pytest.raises(ValueError):
        validate_restore_target("academic_submission_agent", "storage")


@pytest.mark.parametrize(
    "database_name",
    [
        "academic_submission_agent",
        "academic_submission_agent_restore",
        "academic_submission_agent_restore_test;DROP",
        "../academic_submission_agent_test",
    ],
)
def test_restore_rejects_wrong_database_targets(database_name):
    with pytest.raises(ValueError):
        validate_restore_target(database_name, "isolated-restore-test")


@pytest.mark.parametrize("child_path", [False, True])
def test_restore_binds_guard_to_relocated_live_storage(
    tmp_path, age_identity, child_path
):
    live = tmp_path / "relocated-live-storage"
    live.mkdir()
    archive, key_file = make_sql_archive(tmp_path, age_identity, b"")
    target = live / "child" if child_path else live

    with pytest.raises(ValueError, match="正式存储目录之外"):
        restore_backup(
            archive,
            "mysql+pymysql://asa_app:unit-only-password@127.0.0.1/academic_submission_agent",
            "mysql+pymysql://asa_test:target-unit-password@127.0.0.1/academic_submission_agent_restore_test",
            target,
            confirmation="RESTORE",
            age_secret_key_file=key_file,
            live_storage=live,
            engine_factory=lambda url: pytest.fail("database must not be contacted"),
        )


def test_restore_rejects_live_storage_and_nonempty_targets(tmp_path):
    live = tmp_path / "live-storage"
    live.mkdir()
    with pytest.raises(ValueError):
        validate_restore_target(
            "academic_submission_agent_restore_test", live / "copy", live_storage=live
        )
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "existing").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_restore_target(
            "academic_submission_agent_restore_test", nonempty, live_storage=live
        )
    with pytest.raises(ValueError):
        validate_restore_target(
            "academic_submission_agent_restore_test",
            nonempty / "existing",
            live_storage=live,
        )


def test_backup_requires_application_writes_to_be_stopped(tmp_path, age_identity):
    marker = tmp_path / "dump-ran"
    key_file, arguments = backup_arguments(
        tmp_path,
        age_identity,
        writes_stopped=False,
        dump_command=[sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"],
    )
    del key_file
    with pytest.raises(BackupFailed):
        create_backup(tmp_path / "backups", **arguments)
    assert not marker.exists()


def test_interrupted_backup_leaves_no_unencrypted_final_artifact(tmp_path):
    config_example = tmp_path / "example.env"
    config_example.write_text("DATABASE_URL=\n", encoding="utf-8")
    interrupted_dump = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('partial dump'); sys.exit(1)",
    ]

    with pytest.raises(BackupFailed):
        create_backup(
            tmp_path,
            dump_command=interrupted_dump,
            writes_stopped=True,
            recipient="age1unused",
            database_url="mysql+pymysql://user:password@127.0.0.1/example_test",
            storage_root=tmp_path / "storage",
            config_example=config_example,
        )

    assert not list(tmp_path.rglob("*.sql"))
    assert not list(tmp_path.rglob("*.tar"))
    assert not list(tmp_path.rglob("*.tar.age"))
    assert not list(tmp_path.rglob("*.partial"))
    assert list(tmp_path.iterdir()) == [config_example]


def test_backup_streams_only_encrypted_artifacts_with_verified_manifest(
    tmp_path, age_identity, monkeypatch
):
    capture = tmp_path / "dump-capture.json"
    monkeypatch.setenv("DUMP_CAPTURE", str(capture))
    key_file, arguments = backup_arguments(tmp_path, age_identity)
    output = tmp_path / "backups"

    archive = create_backup(output, **arguments)

    assert archive.parent == output
    assert archive.suffixes == [".tar", ".age"]
    assert not list(output.glob("*.partial"))
    assert not list(output.rglob("*.sql"))
    assert not list(output.rglob("*.tar"))
    plaintext = decrypt_archive(archive, key_file)
    assert UNIT_PASSWORD.encode() not in plaintext
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:") as bundle:
        names = set(bundle.getnames())
        assert names == {
            "config/.env.example",
            "database.sql",
            "manifest.json",
            "storage/manuscripts/proof.pdf",
        }
        manifest = json.load(bundle.extractfile("manifest.json"))
        assert manifest["source_database"] == "academic_submission_agent"
        assert len(manifest["files"]) == 3
        for entry in manifest["files"]:
            content = bundle.extractfile(entry["path"]).read()
            assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert b"auth_sessions" not in bundle.extractfile("database.sql").read()

    dump = json.loads(capture.read_text(encoding="utf-8"))
    assert "--single-transaction" in dump["args"]
    assert "--skip-lock-tables" in dump["args"]
    assert "--ignore-table=academic_submission_agent.auth_sessions" in dump["args"]
    assert dump["password_in_environment"] is True
    assert dump["password_in_arguments"] is False


def test_backup_rejects_output_inside_live_storage(tmp_path, age_identity):
    key_file, arguments = backup_arguments(tmp_path, age_identity)
    del key_file
    storage = arguments["storage_root"]

    with pytest.raises(BackupFailed):
        create_backup(storage / "backups", **arguments)
    assert not (storage / "backups").exists()


def test_age_failure_removes_partial_and_unencrypted_data(tmp_path, age_identity):
    failing_age = tmp_path / "failing-age.py"
    failing_age.write_text(
        "#!/usr/bin/env python3\nimport sys; sys.stdin.buffer.read(); sys.exit(1)",
        encoding="utf-8",
    )
    failing_age.chmod(0o700)
    key_file, arguments = backup_arguments(tmp_path, age_identity)
    del key_file
    output = tmp_path / "backups"

    with pytest.raises(BackupFailed):
        create_backup(output, age_binary=str(failing_age), **arguments)

    assert not output.exists() or not any(output.iterdir())


def test_restore_requires_exact_confirmation_and_external_key(tmp_path):
    with pytest.raises(ValueError):
        restore_backup(
            tmp_path / "backup.tar.age",
            "mysql+pymysql://u:p@localhost/academic_submission_agent",
            "mysql+pymysql://u:p@localhost/academic_submission_agent_restore_test",
            tmp_path / "restored",
            confirmation="restore",
            age_secret_key_file=tmp_path / "key",
            live_storage=tmp_path / "live-storage",
        )
    with pytest.raises(ValueError):
        validate_age_key_file(PROJECT_ROOT / "not-an-external-age-key")


def test_extract_verified_backup_detects_manifest_tampering(
    tmp_path, age_identity, monkeypatch
):
    monkeypatch.setenv("DUMP_CAPTURE", str(tmp_path / "dump-capture.json"))
    key_file, arguments = backup_arguments(tmp_path, age_identity)
    archive = create_backup(tmp_path / "backups", **arguments)
    plaintext = decrypt_archive(archive, key_file)
    altered = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:") as source:
        with tarfile.open(fileobj=altered, mode="w:") as destination:
            for member in source.getmembers():
                content = source.extractfile(member).read()
                if member.name == "database.sql":
                    content = b"tampered database dump"
                info = tarfile.TarInfo(member.name)
                info.size = len(content)
                destination.addfile(info, io.BytesIO(content))
    tampered_plaintext = tmp_path / "tampered.tar"
    tampered_plaintext.write_bytes(altered.getvalue())
    tampered_archive = tmp_path / "tampered.tar.age"
    encrypt_archive(tampered_plaintext, tampered_archive, arguments["recipient"])

    with pytest.raises(RestoreFailed):
        extract_verified_backup(
            tampered_archive, key_file, tmp_path / "verified-extraction"
        )
    assert not (tmp_path / "verified-extraction").exists()
    tampered_plaintext.unlink()


def test_extract_verified_backup_rejects_path_traversal(tmp_path, age_identity):
    key_file, recipient = age_identity
    plaintext = io.BytesIO()
    with tarfile.open(fileobj=plaintext, mode="w:") as bundle:
        content = b"not safe"
        info = tarfile.TarInfo("../outside")
        info.size = len(content)
        bundle.addfile(info, io.BytesIO(content))
    plain_path = tmp_path / "traversal.tar"
    plain_path.write_bytes(plaintext.getvalue())
    archive = tmp_path / "traversal.tar.age"
    encrypt_archive(plain_path, archive, recipient)

    with pytest.raises(RestoreFailed):
        extract_verified_backup(archive, key_file, tmp_path / "safe-target")
    assert not (tmp_path / "outside").exists()
    plain_path.unlink()


@pytest.mark.parametrize(
    "statement",
    [
        "DROP TABLE `academic_submission_agent`.`authors`;",
        "INSERT INTO `academic_submission_agent_test`.`authors` VALUES (1);",
        "UPDATE academic_submission_agent.authors SET display_name='changed';",
        "ALTER TABLE `academic_submission_agent` . `authors` ADD COLUMN x INT;",
        "DROP/**/TABLE/**/`academic_submission_agent`/**/./**/`authors`;",
        "/*!50000 DROP TABLE `academic_submission_agent`.`authors` */;",
        "SET @x=1; DROP TABLE `academic_submission_agent`/* trick */./* trick */`authors`;",
        "CREATE TABLE x AS SELECT * FROM academic_submission_agent.authors;",
        'SET sql_mode=\'ANSI_QUOTES\'; DROP TABLE "academic_submission_agent" . "authors";',
        "DROP TABLE 'academic_submission_agent'.'authors';",
        "SET sql_mode=CONCAT('NO_BACKSLASH','_ESCAPES'); DROP TABLE authors;",
        "SET SQL_MODE=@OLD_SQL_MODE; DROP TABLE authors;",
        "SET NAMES latin1; DROP TABLE authors;",
        "SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE=CONCAT('NO_BACKSLASH','_ESCAPES'); DROP TABLE authors;",
    ],
)
def test_hash_valid_cross_database_sql_never_reaches_mysql(
    tmp_path, age_identity, statement
):
    archive, key_file = make_sql_archive(tmp_path, age_identity, statement.encode())
    source = FakeDatabase("academic_submission_agent", {"authors": 1})
    target = FakeDatabase("academic_submission_agent_restore_test")
    engines = {source.name: FakeEngine(source), target.name: FakeEngine(target)}
    executed = []

    def mysql_runner(*args):
        executed.append(True)

    with pytest.raises(RestoreFailed):
        restore_backup(
            archive,
            "mysql+pymysql://asa_app:unit-only-password@127.0.0.1/academic_submission_agent",
            "mysql+pymysql://asa_test:target-unit-password@127.0.0.1/academic_submission_agent_restore_test",
            tmp_path / "restored-storage",
            confirmation="RESTORE",
            age_secret_key_file=key_file,
            live_storage=tmp_path / "live-storage",
            engine_factory=lambda url: engines[make_url(url).database],
            mysql_runner=mysql_runner,
        )

    assert executed == []
    assert source.tables == {"authors": 1}
    assert target.tables == {}
    assert not (tmp_path / "restored-storage").exists()


def test_mysql_runner_prepends_validated_target_for_one_database(tmp_path, monkeypatch):
    capture = tmp_path / "mysql-input.sql"
    monkeypatch.setenv("MYSQL_INPUT_CAPTURE", str(capture))
    executable = tmp_path / "fake-mysql.py"
    executable.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path
Path(os.environ['MYSQL_INPUT_CAPTURE']).write_bytes(sys.stdin.buffer.read())
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    command, environment = _mysql_restore_arguments(
        "mysql+pymysql://asa_test:target-unit-password@127.0.0.1/academic_submission_agent_restore_test"
    )
    command[0] = str(executable)
    dump = tmp_path / "database.sql"
    dump.write_text("CREATE TABLE `authors` (`id` INT);\n", encoding="utf-8")

    _run_mysql_restore(command, environment, dump)

    assert capture.read_text(encoding="utf-8") == (
        "USE `academic_submission_agent_restore_test`;\n"
        "SET SESSION SQL_MODE='NO_AUTO_VALUE_ON_ZERO';\n"
        "CREATE TABLE `authors` (`id` INT);\n"
    )


def test_exact_parser_differential_is_rejected_at_set_statement(tmp_path, age_identity):
    statement = (
        r"SET sql_mode=CONCAT('NO_BACKSLASH','_ESCAPES'); "
        r"SET @x=('\\'); "
        "DROP TABLE academic_submission_agent.authors; -- ');"
    )
    archive, key_file = make_sql_archive(tmp_path, age_identity, statement.encode())

    with pytest.raises(RestoreFailed, match="不支持的 mysqldump SET 语句"):
        extract_verified_backup(archive, key_file, tmp_path / "verified")
    assert not (tmp_path / "verified").exists()


def test_subprocess_failure_diagnostics_are_sanitized(tmp_path, monkeypatch):
    canary = "test-only-environment-canary"
    database_url_canary = (
        "mysql+pymysql://round3-user:round3-password@db.invalid/round3_test"
    )
    token_canary = "round3-test-only-token-canary-7f3c9a"
    monkeypatch.setenv("TASK_16_SECRET_CANARY", canary)
    monkeypatch.setenv("TASK_16_DATABASE_URL_CANARY", database_url_canary)
    monkeypatch.setenv("TASK_16_TOKEN_CANARY", token_canary)
    executable = tmp_path / "failing-mysql.py"
    executable.write_text(
        "#!/usr/bin/env python3\nimport sys; sys.stdin.buffer.read(); sys.exit(1)",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    command, environment = _mysql_restore_arguments(
        "mysql+pymysql://asa_test:target-unit-password@127.0.0.1/academic_submission_agent_restore_test"
    )
    command[0] = str(executable)
    dump = tmp_path / "database.sql"
    dump.write_text("CREATE TABLE `authors` (`id` INT);", encoding="utf-8")

    with pytest.raises(RestoreFailed) as exc_info:
        _run_mysql_restore(command, environment, dump)
    diagnostics = "".join(traceback.format_exception(exc_info.value))
    assert canary not in diagnostics
    assert database_url_canary not in diagnostics
    assert token_canary not in diagnostics
    assert "target-unit-password" not in diagnostics
    assert "MYSQL_PWD" not in diagnostics
    assert "AGE_SECRET_KEY_FILE" not in diagnostics


def test_dump_validator_accepts_unqualified_mysqldump_statements(tmp_path):
    dump = tmp_path / "database.sql"
    dump.write_text(
        """/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
DROP TABLE IF EXISTS `authors`;
/*!40101 SET @SAVED_CS_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_CLIENT=UTF8MB4 */;
CREATE TABLE `authors` (`id` INT, `note` VARCHAR(100));
LOCK TABLES `authors` WRITE;
/*!40000 ALTER TABLE `authors` DISABLE KEYS */;
INSERT INTO `authors` VALUES (1,'literal academic_submission_agent.authors');
/*!40000 ALTER TABLE `authors` ENABLE KEYS */;
/*!40101 SET CHARACTER_SET_CLIENT=@SAVED_CS_CLIENT */;
UNLOCK TABLES;
""",
        encoding="utf-8",
    )
    _validate_dump(dump)


def test_restore_rejects_nonempty_database_before_reading_backup(tmp_path):
    source = FakeDatabase("academic_submission_agent", {"authors": 1})
    target = FakeDatabase("academic_submission_agent_restore_test", {"authors": 1})
    engines = {
        source.name: FakeEngine(source),
        target.name: FakeEngine(target),
    }

    with pytest.raises(RestoreFailed, match="必须为空"):
        restore_backup(
            tmp_path / "missing.tar.age",
            "mysql+pymysql://asa_app:unit-only-password@127.0.0.1/academic_submission_agent",
            "mysql+pymysql://asa_test:target-unit-password@127.0.0.1/academic_submission_agent_restore_test",
            tmp_path / "restored-storage",
            confirmation="RESTORE",
            age_secret_key_file=tmp_path / "unused-key",
            live_storage=tmp_path / "live-storage",
            engine_factory=lambda url: engines[make_url(url).database],
        )

    assert target.tables == {"authors": 1}
    assert not (tmp_path / "restored-storage").exists()


def test_non_utf8_dump_cleans_decrypted_extraction(tmp_path, age_identity):
    archive, key_file = make_sql_archive(tmp_path, age_identity, b"\xff\xfe\x80")
    destination = tmp_path / "non-utf8-extraction"

    with pytest.raises(RestoreFailed):
        extract_verified_backup(archive, key_file, destination)
    assert not destination.exists()


def test_keyboard_interrupt_during_file_copy_cleans_and_propagates(
    tmp_path, age_identity, monkeypatch
):
    monkeypatch.setenv("DUMP_CAPTURE", str(tmp_path / "dump-capture.json"))
    key_file, arguments = backup_arguments(tmp_path, age_identity)
    archive = create_backup(tmp_path / "backups", **arguments)
    source = FakeDatabase(
        "academic_submission_agent",
        {"authors": 1, "auth_sessions": 0, "alembic_version": 1},
    )
    target = FakeDatabase("academic_submission_agent_restore_test")
    engines = {source.name: FakeEngine(source), target.name: FakeEngine(target)}

    def mysql_runner(*args):
        target.tables.update({"authors": 1, "alembic_version": 1})

    def migration_runner(url):
        target.tables["auth_sessions"] = 0

    def interrupted_copy(source_path, destination_path):
        destination_path.write_bytes(b"partial plaintext")
        raise KeyboardInterrupt

    monkeypatch.setattr("scripts.restore.shutil.copyfile", interrupted_copy)
    restored = tmp_path / "restored-storage"
    with pytest.raises(KeyboardInterrupt):
        restore_backup(
            archive,
            "mysql+pymysql://asa_app:unit-only-password@127.0.0.1/academic_submission_agent",
            "mysql+pymysql://asa_test:target-unit-password@127.0.0.1/academic_submission_agent_restore_test",
            restored,
            confirmation="RESTORE",
            age_secret_key_file=key_file,
            live_storage=tmp_path / "live-storage",
            engine_factory=lambda url: engines[make_url(url).database],
            mysql_runner=mysql_runner,
            migration_runner=migration_runner,
        )

    assert not restored.exists()


def test_alembic_recreation_creates_only_excluded_empty_session_table():
    engine = create_engine("sqlite:///:memory:")
    try:
        _recreate_excluded_tables(engine)
        assert inspect(engine).get_table_names() == ["auth_sessions"]
        indexes = {
            index["name"] for index in inspect(engine).get_indexes("auth_sessions")
        }
        assert indexes == {
            "ix_auth_sessions_absolute_expires",
            "ix_auth_sessions_user_revoked",
        }
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM auth_sessions")) == 0
    finally:
        engine.dispose()


def test_temporary_proof_file_is_exclusive_and_fully_cleaned(tmp_path):
    storage = tmp_path / "storage"
    with _temporary_proof_file(storage) as proof:
        assert proof.name.startswith(".backup-01-temporary-proof-")
        assert "BACKUP-01 临时验证文件" in proof.read_text(encoding="utf-8")
        assert storage.is_dir()
    assert not storage.exists()


def test_temporary_proof_file_preserves_existing_storage_content(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    existing = storage / "existing.pdf"
    existing.write_bytes(b"pre-existing content")

    with pytest.raises(RuntimeError, match="非空"):
        with _temporary_proof_file(storage):
            pass

    assert existing.read_bytes() == b"pre-existing content"
    assert list(storage.iterdir()) == [existing]


def test_restore_directory_cleanup_failure_blocks_success(tmp_path, monkeypatch):
    restored = tmp_path / "decrypted-restore"
    restored.mkdir()
    remnant = restored / "plaintext.sql"
    remnant.write_text("plaintext", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.test_backup_restore.shutil.rmtree", lambda *args, **kwargs: None
    )

    with pytest.raises(RuntimeError, match="清理失败"):
        _remove_restore_directory(restored)
    assert remnant.exists()


def test_restore_compares_database_files_hashes_and_source_snapshot(
    tmp_path, age_identity, monkeypatch
):
    monkeypatch.setenv("DUMP_CAPTURE", str(tmp_path / "dump-capture.json"))
    key_file, arguments = backup_arguments(tmp_path, age_identity)
    archive = create_backup(tmp_path / "backups", **arguments)
    source = FakeDatabase(
        "academic_submission_agent",
        {"authors": 1, "auth_sessions": 2, "alembic_version": 1},
    )
    target = FakeDatabase("academic_submission_agent_restore_test")
    engines = {
        source.name: FakeEngine(source),
        target.name: FakeEngine(target),
    }
    migration_calls = []

    def engine_factory(url):
        return engines[make_url(url).database]

    def mysql_runner(command, environment, dump_path):
        assert "--database=academic_submission_agent_restore_test" in command
        assert "--one-database" in command
        password_is_expected = environment.get("MYSQL_PWD") == "target-unit-password"
        assert password_is_expected
        assert "target-unit-password" not in command
        assert dump_path.read_bytes().startswith(b"CREATE TABLE `authors`")
        target.tables.update({"authors": 1, "alembic_version": 1})

    def migration_runner(database_url):
        migration_calls.append(make_url(database_url).database)
        target.tables["auth_sessions"] = 0
        target.tables["journals"] = 0

    target_url = (
        "mysql+pymysql://asa_test:target-unit-password@127.0.0.1/"
        "academic_submission_agent_restore_test"
    )
    verification = restore_backup(
        archive,
        "mysql+pymysql://asa_app:unit-only-password@127.0.0.1/academic_submission_agent",
        target_url,
        tmp_path / "restored-storage",
        confirmation="RESTORE",
        age_secret_key_file=key_file,
        live_storage=tmp_path / "live-storage",
        engine_factory=engine_factory,
        mysql_runner=mysql_runner,
        migration_runner=migration_runner,
    )

    assert migration_calls == ["academic_submission_agent_restore_test"]
    assert verification.table_count == 4
    assert verification.compared_row_counts == 2
    assert verification.file_count == 1
    assert verification.verified_hash_count == 3
    assert verification.source_table_counts_unchanged is True
    assert source.tables == {
        "authors": 1,
        "auth_sessions": 2,
        "alembic_version": 1,
    }
    assert target.tables["auth_sessions"] == 0
    restored_file = tmp_path / "restored-storage/manuscripts/proof.pdf"
    assert restored_file.read_bytes() == b"stored manuscript"
    assert hashlib.sha256(restored_file.read_bytes()).hexdigest() == next(
        entry["sha256"]
        for entry in verification.manifest["files"]
        if entry["path"] == "storage/manuscripts/proof.pdf"
    )
