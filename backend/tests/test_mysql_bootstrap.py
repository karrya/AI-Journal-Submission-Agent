import os
from pathlib import Path
from urllib.parse import quote

import pytest

from scripts.bootstrap_mysql import build_grants, validate_database_name, write_env_file
from app.core.config import PROJECT_ROOT
from conftest import validate_test_database_url, validate_test_storage_root


def test_database_names_are_fixed_and_test_is_distinct():
    assert validate_database_name("academic_submission_agent")
    assert validate_database_name("academic_submission_agent_test")
    assert not validate_database_name("academic_submission_agent; DROP DATABASE mysql")
    assert not validate_database_name("other_test")


def test_runtime_user_has_no_ddl_grants():
    grants = build_grants("asa_app", "academic_submission_agent")
    assert "SELECT" in grants and "INSERT" in grants and "UPDATE" in grants
    assert "DELETE" in grants
    assert "DROP" not in grants and "ALTER" not in grants
    assert "CREATE" not in grants and "REFERENCES" not in grants


def test_migration_and_test_accounts_are_scoped_to_their_own_databases():
    migration_grants = build_grants("asa_migrate", "academic_submission_agent")
    test_grants = build_grants("asa_test", "academic_submission_agent_test")
    assert all(
        privilege in migration_grants
        for privilege in ("CREATE", "ALTER", "INDEX", "DROP", "REFERENCES")
    )
    assert "ALL PRIVILEGES" in test_grants
    assert "academic_submission_agent_test" in test_grants

    for user, database in (
        ("asa_app", "academic_submission_agent_test"),
        ("asa_migrate", "academic_submission_agent_test"),
        ("asa_test", "academic_submission_agent"),
        ("unknown", "academic_submission_agent"),
    ):
        with pytest.raises(ValueError, match="不支持的数据库标识"):
            build_grants(user, database)


def test_env_file_is_0600_and_contains_only_the_expected_settings(tmp_path: Path):
    env_path = tmp_path / ".env"
    passwords = {
        "asa_app": "app-secret/with:symbols@",
        "asa_migrate": "migrate-secret",
        "asa_test": "test-secret",
    }

    write_env_file(env_path, passwords, csrf_secret="csrf-secret")

    assert os.stat(env_path).st_mode & 0o777 == 0o600
    values = dict(
        line.split("=", 1) for line in env_path.read_text(encoding="utf-8").splitlines()
    )
    assert set(values) == {
        "DATABASE_URL",
        "ALEMBIC_DATABASE_URL",
        "TEST_DATABASE_URL",
        "CSRF_SECRET_KEY",
        "ENVIRONMENT",
    }
    assert values["ENVIRONMENT"] == "development"
    assert values["CSRF_SECRET_KEY"] == "csrf-secret"
    assert quote("app-secret/with:symbols@", safe="") in values["DATABASE_URL"]
    assert "academic_submission_agent_test" in values["TEST_DATABASE_URL"]
    assert "asa_test" in values["TEST_DATABASE_URL"]


def test_test_fixtures_reject_non_test_databases_and_live_storage(tmp_path: Path):
    development_url = "mysql+pymysql://asa_test@127.0.0.1/academic_submission_agent"
    test_url = development_url + "_test"
    assert validate_test_database_url(test_url) == test_url
    with pytest.raises(RuntimeError, match="_test"):
        validate_test_database_url(development_url)
    with pytest.raises(RuntimeError, match="MySQL"):
        validate_test_database_url("sqlite:///academic_submission_agent_test")

    temporary_storage = tmp_path / "isolated-test-storage"
    assert validate_test_storage_root(temporary_storage) == temporary_storage
    with pytest.raises(RuntimeError, match="正式存储目录"):
        validate_test_storage_root(PROJECT_ROOT / "storage")


def test_pymysql_caching_sha2_password_dependency_is_available():
    import cryptography  # noqa: F401
