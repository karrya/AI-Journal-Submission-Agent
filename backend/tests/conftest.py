import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
TEST_DATABASE = "academic_submission_agent_test"
LIVE_STORAGE_ROOT = PROJECT_ROOT / "storage"

sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=False)


def validate_test_database_url(url: str) -> str:
    parsed = make_url(url)
    if not parsed.drivername.startswith("mysql+"):
        raise RuntimeError("tests require a MySQL TEST_DATABASE_URL")
    if parsed.database != TEST_DATABASE:
        raise RuntimeError(
            "TEST_DATABASE_URL must target the fixed academic_submission_agent_test "
            "database ending in _test"
        )
    return url


def validate_test_storage_root(root: Path) -> Path:
    resolved = root.resolve()
    live = LIVE_STORAGE_ROOT.resolve()
    if resolved == live or live in resolved.parents:
        raise RuntimeError("tests cannot use the live storage directory")
    return root


@pytest.fixture(scope="session")
def db_engine():
    if os.environ.get("ENVIRONMENT") != "test":
        raise RuntimeError("MySQL integration tests require ENVIRONMENT=test")
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("TEST_DATABASE_URL is required for MySQL integration tests")
    validate_test_database_url(url)

    from app.core.database import create_mysql_engine

    engine = create_mysql_engine(url)
    try:
        with engine.connect() as connection:
            actual_database = connection.scalar(text("SELECT DATABASE()"))
        if actual_database != TEST_DATABASE:
            raise RuntimeError("connected test session is not on the _test database")

        missing = object()
        previous_url = os.environ.get("ALEMBIC_DATABASE_URL", missing)
        os.environ["ALEMBIC_DATABASE_URL"] = url
        try:
            alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
            command.upgrade(alembic_config, "head")
        finally:
            if previous_url is missing:
                os.environ.pop("ALEMBIC_DATABASE_URL", None)
            else:
                os.environ["ALEMBIC_DATABASE_URL"] = previous_url

        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def test_storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = validate_test_storage_root(tmp_path / "isolated-test-storage")
    root.mkdir()
    monkeypatch.setenv("STORAGE_ROOT", str(root))

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture
def db_session(db_engine, test_storage_root):
    session = Session(bind=db_engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with db_engine.begin() as connection:
            table_names = set(inspect(connection).get_table_names())
            if "manuscripts" in table_names:
                connection.execute(
                    text("UPDATE manuscripts SET current_version_id = NULL")
                )
            for table in (
                "operation_logs",
                "manuscript_files",
                "file_families",
                "manuscript_authors",
                "manuscript_versions",
                "manuscripts",
                "journals",
                "journal_platforms",
                "publishers",
                "author_authorizations",
                "author_institutions",
                "author_emails",
                "auth_sessions",
                "user_roles",
                "authors",
                "institutions",
                "roles",
                "users",
            ):
                if table in table_names:
                    connection.execute(text(f"DELETE FROM `{table}`"))


@pytest.fixture
def client(db_engine, db_session, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.core.config import get_settings
    from app.core.database import get_db
    from app.main import app

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv(
        "CSRF_SECRET_KEY", "test-only-csrf-secret-key-with-at-least-32-bytes"
    )
    monkeypatch.setenv("ALLOWED_ORIGINS", '["http://localhost:5173"]')
    get_settings.cache_clear()

    testing_session_local = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    from app.core import database

    monkeypatch.setattr(database, "SessionLocal", testing_session_local)
    app.dependency_overrides[get_db] = override_get_db

    if hasattr(app.state, "login_rate_limiter"):
        app.state.login_rate_limiter = type(app.state.login_rate_limiter)()

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def second_client(client):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_with_initial_password(db_session):
    from argon2 import PasswordHasher

    from app.models import Role, User, UserRole

    password = "Test-Initial-Passphrase-2026!"
    role = Role(
        code="system_admin",
        name="System Administrator",
        description="Test administrator role",
    )
    user = User(
        username="initial-admin",
        normalized_username="initial-admin",
        display_name="Initial Administrator",
        password_hash=PasswordHasher().hash(password),
        status="active",
        must_change_password=True,
    )
    db_session.add_all([role, user])
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    return {"username": "initial-admin", "password": password}


@pytest.fixture
def login_initial_admin(client, admin_with_initial_password):
    response = client.post(
        "/api/v1/auth/login",
        json=admin_with_initial_password,
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    return response.json()
