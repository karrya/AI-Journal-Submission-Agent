import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import inspect, select, text
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


@pytest.fixture
def frozen_now():
    return datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def user_factory(db_session):
    from app.models import Role, User, UserRole

    def create(username: str, *, roles: tuple[str, ...], status: str = "active"):
        user = User(
            username=username,
            normalized_username=username,
            display_name=username,
            password_hash="test-only-password-hash",
            status=status,
            must_change_password=False,
        )
        db_session.add(user)
        db_session.flush()
        for code in roles:
            role = db_session.scalar(select(Role).where(Role.code == code))
            if role is None:
                role = Role(code=code, name=code, description=f"Test {code} role")
                db_session.add(role)
                db_session.flush()
            db_session.add(UserRole(user_id=user.id, role_id=role.id))
        db_session.commit()
        return user

    return create


@pytest.fixture
def operator(user_factory):
    return user_factory("operator", roles=("submission_operator",))


@pytest.fixture
def reviewer(user_factory):
    return user_factory("reviewer", roles=("reviewer",))


@pytest.fixture
def auditor(user_factory):
    return user_factory("auditor", roles=("auditor",))


@pytest.fixture
def admin(user_factory):
    return user_factory("admin", roles=("system_admin",))


@pytest.fixture
def disabled_admin(user_factory):
    return user_factory(
        "disabled-admin", roles=("system_admin", "reviewer"), status="disabled"
    )


@pytest.fixture
def author(db_session):
    from app.models import Author

    record = Author(display_name="Permission Test Author", alternate_names=[])
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def grant_factory(db_session, frozen_now):
    from app.models import AuthorAuthorization

    def create(
        *,
        user,
        author,
        permission=None,
        permissions=None,
        valid_from=None,
        valid_to=None,
        revoked_at=None,
    ):
        if permission is not None and permissions is not None:
            raise ValueError("pass permission or permissions, not both")
        codes = permissions if permissions is not None else [permission]
        values = [getattr(code, "value", code) for code in codes]
        start = valid_from or frozen_now - timedelta(hours=1)
        end = valid_to or frozen_now + timedelta(hours=1)
        if start.tzinfo is not None:
            start = start.astimezone(UTC).replace(tzinfo=None)
        if end.tzinfo is not None:
            end = end.astimezone(UTC).replace(tzinfo=None)
        if revoked_at is not None and revoked_at.tzinfo is not None:
            revoked_at = revoked_at.astimezone(UTC).replace(tzinfo=None)
        grant = AuthorAuthorization(
            user_id=user.id,
            author_id=author.id,
            permissions=values,
            valid_from=start,
            valid_to=end,
            revoked_at=revoked_at,
        )
        db_session.add(grant)
        db_session.commit()
        return grant

    return create


@pytest.fixture
def auth_context_factory(client, db_session):
    from secrets import token_urlsafe
    from types import SimpleNamespace

    from app.core.config import get_settings
    from app.models import AuthSession, utc_now
    from app.security.csrf import csrf_token, token_hash

    def authenticate(user, target_client=None):
        target = target_client or client
        raw_token = token_urlsafe(32)
        hashed_token = token_hash(raw_token)
        csrf = csrf_token(hashed_token, get_settings().csrf_secret_key)
        now = utc_now()
        session = AuthSession(
            token_hash=hashed_token,
            csrf_token_hash=token_hash(csrf),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=now + timedelta(hours=1),
            absolute_expires_at=now + timedelta(hours=8),
        )
        db_session.add(session)
        db_session.commit()
        target.cookies.set("asa_session", raw_token, path="/")
        target.headers.update({"Origin": "http://localhost:5173", "X-CSRF-Token": csrf})
        return SimpleNamespace(user=user, session=session, csrf_token=csrf)

    return authenticate


@pytest.fixture
def admin_context(admin, auth_context_factory):
    return auth_context_factory(admin)


@pytest.fixture
def operator_context(operator, auth_context_factory):
    return auth_context_factory(operator)


@pytest.fixture
def institution(db_session):
    from app.models import Institution

    record = Institution(
        name="Test University",
        normalized_name="test university",
        institution_type="university",
        address_line1="1 Test Road",
        city="Test City",
        region="Test Region",
        postal_code="123456",
        country_code="CN",
    )
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def owner(db_session):
    from app.models import Author

    record = Author(display_name="File Owner", alternate_names=[])
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def owner_permissions(grant_factory, operator, owner):
    now = datetime.now(UTC)
    return grant_factory(
        user=operator,
        author=owner,
        permissions=[
            "manuscript:create",
            "manuscript:read",
            "manuscript:update",
            "manuscript:file:manage",
        ],
        valid_from=now - timedelta(minutes=5),
        valid_to=now + timedelta(hours=1),
    )


@pytest.fixture
def manuscript(client, db_session, operator_context, owner_permissions, owner):
    from app.models import Manuscript

    response = client.post(
        "/api/v1/manuscripts",
        json={
            "owner_author_id": owner.id,
            "title": "File study",
            "abstract": "Abstract",
            "keywords": ["files"],
            "article_type": "research",
            "language": "en",
        },
    )
    assert response.status_code == 201, response.text
    db_session.expire_all()
    record = db_session.get(Manuscript, response.json()["id"])
    db_session.commit()
    return record
