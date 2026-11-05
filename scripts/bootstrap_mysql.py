"""配置固定的本地 MySQL 数据库和最小权限账户。"""

import getpass
import os
import re
import secrets
import tempfile
from pathlib import Path
from urllib.parse import quote

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_DATABASE = "academic_submission_agent"
TEST_DATABASE = "academic_submission_agent_test"
ACCOUNTS = ("asa_app", "asa_migrate", "asa_test")
ACCOUNT_HOST = "127.0.0.1"
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 3306


def validate_database_name(name: str) -> bool:
    return bool(re.fullmatch(r"academic_submission_agent(?:_test)?", name))


def build_grants(user: str, database: str) -> str:
    expected_database = {
        "asa_app": DEVELOPMENT_DATABASE,
        "asa_migrate": DEVELOPMENT_DATABASE,
        "asa_test": TEST_DATABASE,
    }.get(user)
    if not validate_database_name(database) or database != expected_database:
        raise ValueError("不支持的数据库标识")

    privileges = {
        "asa_app": "SELECT, INSERT, UPDATE, DELETE",
        "asa_migrate": (
            "SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES"
        ),
        "asa_test": "ALL PRIVILEGES",
    }[user]
    return f"GRANT {privileges} ON `{database}`.* TO %s@%s"


def database_url(user: str, password: str, database: str) -> str:
    if user not in ACCOUNTS or not validate_database_name(database):
        raise ValueError("不支持的数据库标识")
    return (
        f"mysql+pymysql://{user}:{quote(password, safe='')}@"
        f"{DATABASE_HOST}:{DATABASE_PORT}/{database}"
    )


def write_env_file(env_path: Path, passwords: dict[str, str], csrf_secret: str) -> None:
    if set(passwords) != set(ACCOUNTS):
        raise ValueError("必须提供恰好三个已生成的账户密码")

    values = {
        "DATABASE_URL": database_url(
            "asa_app", passwords["asa_app"], DEVELOPMENT_DATABASE
        ),
        "ALEMBIC_DATABASE_URL": database_url(
            "asa_migrate", passwords["asa_migrate"], DEVELOPMENT_DATABASE
        ),
        "TEST_DATABASE_URL": database_url(
            "asa_test", passwords["asa_test"], TEST_DATABASE
        ),
        "CSRF_SECRET_KEY": csrf_secret,
        "ENVIRONMENT": "development",
    }
    content = "".join(f"{key}={value}\n" for key, value in values.items())

    descriptor, temporary_name = tempfile.mkstemp(
        dir=env_path.parent, prefix=".env.", text=True
    )
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as env_file:
            env_file.write(content)
            env_file.flush()
            os.fsync(env_file.fileno())
        os.replace(temporary_path, env_path)
        os.chmod(env_path, 0o600)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def bootstrap_mysql(
    administrative_password: str,
    *,
    administrative_user: str = "root",
    administrative_host: str = "localhost",
    administrative_port: int = DATABASE_PORT,
    env_path: Path = PROJECT_ROOT / ".env",
) -> None:
    passwords = {user: secrets.token_urlsafe(32) for user in ACCOUNTS}
    csrf_secret = secrets.token_urlsafe(48)

    connection = pymysql.connect(
        host=administrative_host,
        port=administrative_port,
        user=administrative_user,
        password=administrative_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            for database in (DEVELOPMENT_DATABASE, TEST_DATABASE):
                if not validate_database_name(database):
                    raise ValueError("不支持的数据库标识")
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )

            for user in ACCOUNTS:
                cursor.execute(
                    "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
                    (user, ACCOUNT_HOST, passwords[user]),
                )
                cursor.execute(
                    "ALTER USER %s@%s IDENTIFIED BY %s",
                    (user, ACCOUNT_HOST, passwords[user]),
                )
                cursor.execute(
                    "REVOKE ALL PRIVILEGES, GRANT OPTION FROM %s@%s",
                    (user, ACCOUNT_HOST),
                )

            for user, database in (
                ("asa_app", DEVELOPMENT_DATABASE),
                ("asa_migrate", DEVELOPMENT_DATABASE),
                ("asa_test", TEST_DATABASE),
            ):
                cursor.execute(build_grants(user, database), (user, ACCOUNT_HOST))
    finally:
        connection.close()

    write_env_file(env_path, passwords, csrf_secret)


def main() -> None:
    administrative_password = getpass.getpass("MySQL 管理员密码：")
    administrative_user = os.environ.get("MYSQL_ADMIN_USER", "root")
    administrative_host = os.environ.get("MYSQL_ADMIN_HOST", "localhost")
    administrative_port = int(os.environ.get("MYSQL_ADMIN_PORT", DATABASE_PORT))
    try:
        bootstrap_mysql(
            administrative_password,
            administrative_user=administrative_user,
            administrative_host=administrative_host,
            administrative_port=administrative_port,
        )
    except Exception as exc:
        raise SystemExit(
            "MySQL 初始化失败，未写入凭据；"
            "请检查本地管理员连接后重试。"
        ) from exc
    print("MySQL 初始化完成，.env 已写入并设置为 0600 权限。")


if __name__ == "__main__":
    main()
