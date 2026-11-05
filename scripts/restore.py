"""仅将加密备份恢复到空的隔离测试目标。"""

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
    """备份或隔离恢复未通过验证。"""


@dataclass
class RestoreVerification:
    table_count: int
    compared_row_counts: int
    file_count: int
    verified_hash_count: int
    source_table_counts_unchanged: bool
    manifest: dict


def validate_restore_target(
    database_name: str,
    target_directory: str | Path,
    *,
    live_storage: Path = PROJECT_ROOT / "storage",
) -> Path:
    """要求使用名称以 _test 结尾的数据库，以及正式存储目录之外的空目录。"""
    if database_name == DEVELOPMENT_DATABASE or not DATABASE_NAME.fullmatch(
        database_name
    ):
        raise ValueError("恢复数据库必须使用以 _test 结尾的隔离名称")
    raw_target = Path(target_directory).expanduser()
    if raw_target.is_symlink():
        raise ValueError("恢复目录不得是符号链接")
    if not raw_target.is_absolute():
        raw_target = PROJECT_ROOT / raw_target
    target = raw_target.resolve()
    live = Path(live_storage).resolve()
    if target == live or live in target.parents:
        raise ValueError("恢复目录必须位于正式存储目录之外")
    if target.exists():
        if not target.is_dir():
            raise ValueError("恢复目标路径必须是目录")
        if any(target.iterdir()):
            raise ValueError("恢复目录必须为空")
    return target


def validate_age_key_file(key_file: str | Path) -> Path:
    """要求使用项目外权限受限的私钥文件。"""
    raw_path = Path(key_file).expanduser()
    if raw_path.is_symlink():
        raise ValueError("age 私钥不得是符号链接")
    path = raw_path.resolve()
    if path == PROJECT_ROOT or PROJECT_ROOT in path.parents:
        raise ValueError("age 私钥必须位于项目目录之外")
    if not path.is_file():
        raise ValueError("缺少 age 私钥文件")
    if path.stat().st_mode & 0o077:
        raise ValueError(
            "age 私钥权限不得允许用户组或其他用户访问"
        )
    return path


def _validate_member_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not name or ".." in path.parts or "." in path.parts:
        raise RestoreFailed("归档文件包含不安全路径")
    return path


def _read_manifest(
    bundle: tarfile.TarFile, members: dict[str, tarfile.TarInfo]
) -> dict:
    if "manifest.json" not in members:
        raise RestoreFailed("缺少归档清单")
    manifest_file = bundle.extractfile(members["manifest.json"])
    if manifest_file is None:
        raise RestoreFailed("归档清单无法读取")
    try:
        manifest = json.load(manifest_file)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestoreFailed("归档清单无效") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != 1
        or manifest.get("sessions_excluded") is not True
        or not isinstance(manifest.get("source_database"), str)
        or not SAFE_NAME.fullmatch(manifest["source_database"])
        or not isinstance(manifest.get("files"), list)
    ):
        raise RestoreFailed("归档清单格式不受支持")

    archived_paths = set(members) - {"manifest.json"}
    manifest_paths: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise RestoreFailed("归档清单包含无效条目")
        path = entry["path"]
        if (
            not isinstance(path, str)
            or path in manifest_paths
            or not isinstance(entry["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
            or type(entry["size"]) is not int
            or entry["size"] < 0
        ):
            raise RestoreFailed("归档清单包含无效条目")
        _validate_member_name(path)
        manifest_paths.add(path)
    if manifest_paths != archived_paths:
        raise RestoreFailed("归档文件与清单不一致")

    for entry in manifest["files"]:
        extracted = bundle.extractfile(members[entry["path"]])
        if extracted is None:
            raise RestoreFailed("归档成员无法读取")
        digest = hashlib.sha256()
        size = 0
        while chunk := extracted.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise RestoreFailed("归档文件 SHA-256（安全散列算法 256 位）校验失败")
    return manifest


def _quoted_token(dump: str, start: int, quote: str) -> tuple[str, int]:
    content: list[str] = []
    index = start + 1
    while index < len(dump):
        char = dump[index]
        if char == "\\":
            if index + 1 >= len(dump):
                raise RestoreFailed("数据库导出文件包含未终止的转义序列")
            if quote != "`":
                content.append(dump[index + 1])
            index += 2
            continue
        if char == quote:
            if index + 1 < len(dump) and dump[index + 1] == quote:
                content.append(quote)
                index += 2
                continue
            return "".join(content), index + 1
        content.append(char)
        index += 1
    raise RestoreFailed("数据库导出文件包含未终止的引用值")


def _mysql_tokens(dump: str) -> list[tuple[str, str]]:
    """将可执行的 MySQL SQL 分词，忽略注释和字面量内容。"""
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(dump):
        char = dump[index]
        if char.isspace():
            index += 1
            continue
        if char == "#" or (
            dump.startswith("--", index)
            and index + 2 < len(dump)
            and dump[index + 2].isspace()
        ):
            newline = dump.find("\n", index)
            index = len(dump) if newline < 0 else newline + 1
            continue
        if dump.startswith("/*", index):
            end = dump.find("*/", index + 2)
            if end < 0:
                raise RestoreFailed("数据库导出文件包含未终止的注释")
            if dump.startswith("/*!", index):
                executable = dump[index + 3 : end]
                if len(executable) >= 5 and executable[:5].isdigit():
                    executable = executable[5:]
                tokens.extend(_mysql_tokens(executable))
            index = end + 2
            continue
        if char in "'\"`":
            content, index = _quoted_token(dump, index, char)
            tokens.append(("ident" if char in '"`' else "string", content))
            continue
        if char.isdigit():
            end = index + 1
            while end < len(dump) and (dump[end].isalnum() or dump[end] in "xX_"):
                end += 1
            tokens.append(("number", dump[index:end]))
            index = end
            continue
        if char.isalpha() or char in "_$" or ord(char) > 127:
            end = index + 1
            while end < len(dump) and (
                dump[end].isalnum() or dump[end] in "_$" or ord(dump[end]) > 127
            ):
                end += 1
            tokens.append(("ident", dump[index:end]))
            index = end
            continue
        tokens.append(("punct", char))
        index += 1
    return tokens


def _canonical_statement(
    statement: list[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (kind, value.upper() if kind == "ident" else value) for kind, value in statement
    )


_INITIAL_MYSQLDUMP_SETS = (
    "SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT",
    "SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS",
    "SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION",
    "SET NAMES utf8mb4",
    "SET @SAVED_CS_CLIENT=@@CHARACTER_SET_CLIENT",
    "SET CHARACTER_SET_CLIENT=UTF8MB4",
    "SET CHARACTER_SET_CLIENT=@SAVED_CS_CLIENT",
    "SET @OLD_TIME_ZONE=@@TIME_ZONE",
    "SET TIME_ZONE='+00:00'",
    "SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0",
    "SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0",
    "SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO'",
    "SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO'",
    "SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0",
)
_CLOSING_MYSQLDUMP_SETS = (
    "SET TIME_ZONE=@OLD_TIME_ZONE",
    "SET SQL_MODE=@OLD_SQL_MODE",
    "SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS",
    "SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS",
    "SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT",
    "SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS",
    "SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION",
    "SET SQL_NOTES=@OLD_SQL_NOTES",
)
_INITIAL_SET_SIGNATURES = {
    _canonical_statement(_mysql_tokens(statement))
    for statement in _INITIAL_MYSQLDUMP_SETS
}
_CLOSING_SET_SIGNATURES = {
    _canonical_statement(_mysql_tokens(statement))
    for statement in _CLOSING_MYSQLDUMP_SETS
}


def _validate_dump(dump_path: Path) -> None:
    dump = dump_path.read_text(encoding="utf-8")
    tokens = _mysql_tokens(dump)
    statements: list[list[tuple[str, str]]] = []
    statement: list[tuple[str, str]] = []
    for token in tokens:
        if token == ("punct", ";"):
            if statement:
                statements.append(statement)
                statement = []
        else:
            statement.append(token)
    if statement:
        statements.append(statement)

    allowed_second_keywords = {
        "DROP": {"TABLE"},
        "CREATE": {"TABLE"},
        "ALTER": {"TABLE"},
        "INSERT": {"INTO"},
        "LOCK": {"TABLES"},
        "UNLOCK": {"TABLES"},
    }
    closing_seen = False
    for statement in statements:
        if statement[0][0] != "ident":
            raise RestoreFailed("数据库导出文件包含不支持的语句")
        keyword = statement[0][1].upper()
        if keyword == "SET":
            signature = _canonical_statement(statement)
            if signature in _CLOSING_SET_SIGNATURES:
                closing_seen = True
            elif signature in _INITIAL_SET_SIGNATURES and not closing_seen:
                pass
            else:
                raise RestoreFailed(
                    "数据库导出文件包含不支持的 mysqldump SET 语句"
                )
            continue
        if closing_seen:
            raise RestoreFailed(
                "数据库导出文件在 mysqldump 清理语句后仍包含其他语句"
            )
        if keyword not in allowed_second_keywords:
            raise RestoreFailed("数据库导出文件包含不支持的语句")
        if len(statement) < 2 or statement[1][0] != "ident":
            raise RestoreFailed("数据库导出文件包含不支持的语句")
        if statement[1][1].upper() not in allowed_second_keywords[keyword]:
            raise RestoreFailed("数据库导出文件包含不支持的语句")

    for index in range(len(tokens) - 2):
        left, dot, right = tokens[index : index + 3]
        if (
            left[0] in {"ident", "string"}
            and dot == ("punct", ".")
            and right[0] in {"ident", "string"}
            and not (
                left[0] == "ident" and index > 0 and tokens[index - 1] == ("punct", "@")
            )
        ):
            raise RestoreFailed("数据库导出文件包含带数据库限定的引用")


def extract_verified_backup(
    backup_path: str | Path,
    age_secret_key_file: str | Path,
    destination: str | Path,
    *,
    age_binary: str = "age",
) -> dict:
    """先解密到临时存储并校验所有哈希，再安全解压。"""
    key_file = validate_age_key_file(age_secret_key_file)
    archive = Path(backup_path).resolve()
    if not archive.is_file():
        raise RestoreFailed("缺少加密备份文件")
    target = Path(destination).resolve()
    if target.exists():
        raise RestoreFailed("已验证解压目标不得事先存在")

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
                raise RestoreFailed("age 解密失败")

            with tarfile.open(plaintext_tar, mode="r:") as bundle:
                members: dict[str, tarfile.TarInfo] = {}
                for member in bundle.getmembers():
                    name = _validate_member_name(member.name).as_posix()
                    if name in members or not member.isreg():
                        raise RestoreFailed("归档文件包含不支持的成员")
                    members[name] = member
                manifest = _read_manifest(bundle, members)
                for name, member in members.items():
                    relative = PurePosixPath(name)
                    output_path = target.joinpath(*relative.parts)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(member)
                    if source is None:
                        raise RestoreFailed("归档成员无法读取")
                    descriptor = os.open(
                        output_path,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                    with os.fdopen(descriptor, "wb") as output:
                        shutil.copyfileobj(source, output)
            _validate_dump(target / "database.sql")
        return manifest
    except BaseException as exc:
        if target.exists():
            shutil.rmtree(target)
        if isinstance(exc, RestoreFailed):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            raise
        raise RestoreFailed("加密备份无法通过验证") from exc


def _create_engine(database_url: str) -> Engine:
    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.database import create_mysql_engine

    return create_mysql_engine(database_url)


def _database_snapshot(engine: Engine, expected_database: str) -> dict[str, int]:
    with engine.connect() as connection:
        actual_database = connection.scalar(text("SELECT DATABASE()"))
        if actual_database != expected_database:
            raise RestoreFailed(
                "已连接数据库与请求的目标不一致"
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
                raise RestoreFailed("数据库包含不支持的表名")
            count = connection.scalar(text(f"SELECT COUNT(*) FROM `{table}`"))
            snapshot[table] = int(count)
        return snapshot


def _run_mysql_restore(
    command: Sequence[str], environment: dict[str, str], dump_path: Path
) -> None:
    database_arguments = [
        argument for argument in command if argument.startswith("--database=")
    ]
    if len(database_arguments) != 1:
        raise RestoreFailed("隔离数据库导入配置无效")
    database = database_arguments[0].removeprefix("--database=")
    if not DATABASE_NAME.fullmatch(database):
        raise RestoreFailed("隔离数据库导入配置无效")
    with dump_path.open("rb") as dump:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        try:
            assert process.stdin is not None
            with process.stdin as stdin:
                stdin.write(f"USE `{database}`;\n".encode("ascii"))
                stdin.write(b"SET SESSION SQL_MODE='NO_AUTO_VALUE_ON_ZERO';\n")
                shutil.copyfileobj(dump, stdin)
            return_code = process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
    if return_code != 0:
        raise RestoreFailed("隔离数据库导入失败")


def _recreate_excluded_tables(engine: Engine) -> None:
    """仅重建有意排除的表，不写入迁移版本标记。"""
    sys.path.insert(0, str(BACKEND_DIR))
    from app.models import Base

    Base.metadata.tables["auth_sessions"].create(bind=engine, checkfirst=True)


def _run_alembic(database_url: str) -> None:
    engine = _create_engine(database_url)
    try:
        _recreate_excluded_tables(engine)
    except Exception as exc:
        raise RestoreFailed("Alembic 验证失败") from exc
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
            raise RestoreFailed("Alembic 验证失败")


def _mysql_restore_arguments(database_url: str) -> tuple[list[str], dict[str, str]]:
    url = make_url(database_url)
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = url.password or ""
    command = [
        "mysql",
        "--one-database",
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
        if target.exists():
            shutil.rmtree(target)


def restore_backup(
    backup_path: str | Path,
    source_database_url: str,
    target_database_url: str,
    target_directory: str | Path,
    *,
    confirmation: str,
    age_secret_key_file: str | Path,
    live_storage: str | Path,
    engine_factory: Callable[[str], Engine] = _create_engine,
    mysql_runner: Callable[
        [Sequence[str], dict[str, str], Path], None
    ] = _run_mysql_restore,
    migration_runner: Callable[[str], None] = _run_alembic,
) -> RestoreVerification:
    """恢复并比对表、行、文件和哈希，同时确认源表数量稳定。"""
    if confirmation != "RESTORE":
        raise ValueError("恢复操作必须显式传入 --confirm RESTORE")
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
        raise ValueError("必须提供有效的源和目标 MySQL URL")
    if source_url.database == target_url.database:
        raise ValueError("恢复目标必须不同于开发数据库")
    target = validate_restore_target(
        target_url.database, target_directory, live_storage=Path(live_storage)
    )
    target_existed = target.exists()
    source_engine: Engine | None = None
    target_engine: Engine | None = None

    try:
        source_engine = engine_factory(source_database_url)
        target_engine = engine_factory(target_database_url)
        source_before = _database_snapshot(source_engine, source_url.database)
        if _database_snapshot(target_engine, target_url.database):
            raise RestoreFailed("恢复目标数据库必须为空")

        with tempfile.TemporaryDirectory(prefix="academic-agent-verified-") as temp:
            verified = Path(temp) / "verified"
            manifest = extract_verified_backup(
                backup_path, age_secret_key_file, verified
            )
            if manifest["source_database"] != source_url.database:
                raise RestoreFailed(
                    "备份来源与开发数据库不一致"
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
                    "恢复后的导出表或数据行与源数据库不一致"
                )
            migration_runner(target_database_url)

            if target.exists() and any(target.iterdir()):
                raise RestoreFailed("恢复目录变为非空")
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
            raise RestoreFailed(
                "恢复期间开发数据库的表名或行数发生变化"
            )
        target_after = _database_snapshot(target_engine, target_url.database)
        if not set(source_before).issubset(target_after):
            raise RestoreFailed("迁移后缺少源数据库中的表")
        compared = 0
        for table, source_count in source_before.items():
            if table == "auth_sessions":
                if target_after[table] != 0:
                    raise RestoreFailed("不得恢复会话数据")
                continue
            if target_after[table] != source_count:
                raise RestoreFailed("恢复后的行数与源数据库不一致")
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
                    raise RestoreFailed("恢复后的存储目录包含不支持的文件")
                if path.is_file():
                    digest = hashlib.sha256()
                    with path.open("rb") as restored:
                        while chunk := restored.read(1024 * 1024):
                            digest.update(chunk)
                    actual_files[path.relative_to(target).as_posix()] = (
                        digest.hexdigest()
                    )
        if actual_files != expected_files:
            raise RestoreFailed("恢复后的文件数量或哈希不一致")
        return RestoreVerification(
            table_count=len(target_after),
            compared_row_counts=compared,
            file_count=len(actual_files),
            verified_hash_count=len(manifest["files"]),
            source_table_counts_unchanged=True,
            manifest=manifest,
        )
    except BaseException as exc:
        _clear_restore_directory(target, target_existed)
        if isinstance(exc, RestoreFailed):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            raise
        raise RestoreFailed(
            "隔离恢复失败，未将开发数据作为操作目标"
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
            raise SystemExit("必须设置 RESTORE_DATABASE_URL 或 TEST_DATABASE_URL")
        target_url = (
            make_url(test_url)
            .set(database=args.database)
            .render_as_string(hide_password=False)
        )
    if make_url(target_url).database != args.database:
        raise SystemExit("RESTORE_DATABASE_URL 必须与 --database 一致")
    key_file = os.environ.get("AGE_SECRET_KEY_FILE")
    if not key_file:
        raise SystemExit("必须设置 AGE_SECRET_KEY_FILE")
    try:
        verification = restore_backup(
            args.backup,
            source_url,
            target_url,
            args.target_directory,
            confirmation=args.confirm,
            age_secret_key_file=key_file,
            live_storage=Path(os.environ.get("STORAGE_ROOT", PROJECT_ROOT / "storage")),
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
                "source_table_counts_unchanged": verification.source_table_counts_unchanged,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
