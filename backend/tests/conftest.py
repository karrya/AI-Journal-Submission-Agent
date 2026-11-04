import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import text
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
            for table in (
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
                connection.execute(text(f"DELETE FROM `{table}`"))
