from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, CHAR, Computed, inspect, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1.readiness import get_db
from app.main import app
from app.models import (
    Author,
    AuthorAuthorization,
    AuthorEmail,
    AuthorInstitution,
    AuthSession,
    Base,
    Institution,
    Role,
    User,
    UserRole,
    utc_now,
)

EXPECTED_TABLES = {
    "users",
    "roles",
    "user_roles",
    "auth_sessions",
    "authors",
    "author_emails",
    "institutions",
    "author_institutions",
    "author_authorizations",
}


def test_first_stage_exports_exactly_nine_models_and_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert {
        User.__tablename__,
        Role.__tablename__,
        UserRole.__tablename__,
        AuthSession.__tablename__,
        Author.__tablename__,
        AuthorEmail.__tablename__,
        Institution.__tablename__,
        AuthorInstitution.__tablename__,
        AuthorAuthorization.__tablename__,
    } == EXPECTED_TABLES


def test_uuid_datetime_and_json_columns_match_the_database_contract():
    for table in Base.metadata.tables.values():
        assert table.dialect_options["mysql"]["engine"] == "InnoDB"
        assert table.dialect_options["mysql"]["charset"] == "utf8mb4"
        for column in table.columns:
            if column.primary_key and column.name != "role_id":
                assert isinstance(column.type, CHAR)
                assert column.type.length == 36
            if column.name.endswith("_at") or column.name in {
                "valid_from",
                "valid_to",
                "idle_expires_at",
                "absolute_expires_at",
            }:
                if table.name != "author_institutions":
                    assert isinstance(column.type, DATETIME)
                    assert column.type.fsp == 6

    assert isinstance(Author.__table__.c.alternate_names.type, JSON)
    assert isinstance(AuthorAuthorization.__table__.c.permissions.type, JSON)
    assert AuthorAuthorization.__table__.c.valid_from.nullable is False
    assert AuthorAuthorization.__table__.c.valid_to.nullable is False
    assert "deleted_at" not in AuthorAuthorization.__table__.c


def test_orcid_and_primary_email_uniqueness_are_database_constraints():
    orcid = Author.__table__.c.orcid
    assert orcid.nullable is True
    assert any(
        tuple(constraint.columns) == (orcid,)
        for constraint in Author.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )

    generated = AuthorEmail.__table__.c.active_primary_author_id
    assert isinstance(generated.computed, Computed)
    assert generated.computed.persisted is True
    assert generated.computed.sqltext.text == (
        "IF(is_primary = 1 AND deleted_at IS NULL, author_id, NULL)"
    )
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in AuthorEmail.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("author_id", "normalized_email") in unique_column_sets
    assert ("active_primary_author_id",) in unique_column_sets


def test_date_order_and_foreign_key_delete_rules_are_enforced_in_schema():
    institution_checks = {
        constraint.sqltext.text
        for constraint in AuthorInstitution.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    authorization_checks = {
        constraint.sqltext.text
        for constraint in AuthorAuthorization.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert any("valid_to >=" in check for check in institution_checks)
    assert any("valid_to > valid_from" in check for check in authorization_checks)

    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.ondelete == "RESTRICT"


def test_utc_helper_returns_naive_utc_for_mysql_datetime_columns():
    before = datetime.now(UTC).replace(tzinfo=None)
    value = utc_now()
    after = datetime.now(UTC).replace(tzinfo=None)
    assert value.tzinfo is None
    assert before <= value <= after


def test_readiness_executes_select_one_and_returns_public_health_status():
    class RecordingSession:
        def __init__(self):
            self.statement = None

        def execute(self, statement):
            self.statement = statement
            return object()

    session = RecordingSession()
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = TestClient(app).get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert str(session.statement) == "SELECT 1"


def test_readiness_failure_does_not_expose_connection_details():
    secret_detail = "mysql://asa_app:secret@database.internal/private"

    class BrokenSession:
        def execute(self, statement):
            raise SQLAlchemyError(secret_detail)

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = TestClient(app).get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert response.json()["details"] is None
    assert secret_detail not in response.text
    assert "secret" not in response.text
    assert "database.internal" not in response.text


def test_integration_first_migration_has_nine_tables(db_engine):
    names = set(inspect(db_engine).get_table_names())
    assert EXPECTED_TABLES.issubset(names)


def test_integration_orcid_is_unique_but_allows_multiple_nulls(db_session):
    db_session.add_all(
        [
            Author(display_name="Single Name One", alternate_names=[], orcid=None),
            Author(display_name="Single Name Two", alternate_names=[], orcid=None),
            Author(
                display_name="ORCID Author",
                alternate_names=[],
                orcid="0000-0002-1825-0097",
            ),
        ]
    )
    db_session.commit()
    db_session.add(
        Author(
            display_name="Duplicate ORCID",
            alternate_names=[],
            orcid="0000-0002-1825-0097",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_integration_generated_column_allows_only_one_active_primary_email(db_session):
    domain = "@example.com"
    author = Author(display_name="Primary Email Author", alternate_names=[])
    db_session.add(author)
    db_session.flush()
    first = AuthorEmail(
        author_id=author.id,
        email="first" + domain,
        normalized_email="first" + domain,
        purpose="communication",
        is_primary=True,
        verification_status="unverified",
        authorization_status="unconfirmed",
    )
    db_session.add(first)
    db_session.commit()
    assert first.active_primary_author_id == author.id

    db_session.add(
        AuthorEmail(
            author_id=author.id,
            email="second" + domain,
            normalized_email="second" + domain,
            purpose="communication",
            is_primary=True,
            verification_status="unverified",
            authorization_status="unconfirmed",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    first.deleted_at = utc_now()
    replacement = AuthorEmail(
        author_id=author.id,
        email="replacement" + domain,
        normalized_email="replacement" + domain,
        purpose="backup",
        is_primary=True,
        verification_status="verified",
        authorization_status="authorized",
    )
    db_session.add(replacement)
    db_session.commit()
    db_session.refresh(first)
    assert first.active_primary_author_id is None
    assert replacement.active_primary_author_id == author.id


def test_integration_authorization_requires_a_strictly_later_end(db_session):
    user = User(
        username="schema-test",
        normalized_username="schema-test",
        display_name="Schema Test",
        password_hash="not-a-real-password-hash",
        status="active",
        must_change_password=True,
    )
    author = Author(display_name="Authorization Author", alternate_names=[])
    db_session.add_all([user, author])
    db_session.flush()
    now = utc_now()
    db_session.add(
        AuthorAuthorization(
            author_id=author.id,
            user_id=user.id,
            permissions=["manuscript:read"],
            valid_from=now,
            valid_to=now - timedelta(microseconds=1),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_integration_migrated_session_uses_utc(db_engine):
    with db_engine.connect() as connection:
        session_timezone = connection.scalar(text("SELECT @@session.time_zone"))
    assert session_timezone == "+00:00"
