import os
import runpy

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CHAR, inspect, text
from sqlalchemy.exc import IntegrityError

from app.models import Base, utc_now
from conftest import BACKEND_DIR


CANONICAL_PUBLISHERS = {
    "SPRINGER_NATURE": ("Springer Nature", "springer nature"),
    "ELSEVIER": ("Elsevier", "elsevier"),
    "WILEY": ("John Wiley & Sons", "john wiley & sons"),
    "TAYLOR_FRANCIS": ("Taylor & Francis", "taylor & francis"),
    "SAGE": ("SAGE Publishing", "sage publishing"),
}


@pytest.fixture
def migration_config():
    previous_url = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    try:
        yield config
    finally:
        command.upgrade(config, "head")
        if previous_url is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = previous_url


def unique_column_sets(table):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


def test_registration_schema_is_at_0007(db_engine):
    from sqlalchemy import inspect, text

    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
    expected = {
        "publisher_registration_support",
        "platform_adapters",
        "publisher_accounts",
        "registration_tasks",
        "email_verification_records",
        "registration_confirmations",
    }
    assert expected <= set(inspect(db_engine).get_table_names())


def test_completed_registration_preserves_account_namespace_and_active_email():
    from app.models import PublisherAccount

    columns = PublisherAccount.__table__.c
    assert columns.account_namespace.nullable is False
    assert columns.normalized_email.nullable is False
    assert columns.active_account_email.computed is not None


def test_registration_uniqueness_and_generated_column_match_the_contract():
    from app.models import (
        PlatformAdapter,
        PublisherAccount,
        PublisherRegistrationSupport,
        RegistrationConfirmation,
        RegistrationTask,
    )

    assert ("publisher_id",) in unique_column_sets(PublisherRegistrationSupport.__table__)
    assert ("publisher_code",) in unique_column_sets(PublisherRegistrationSupport.__table__)
    assert ("adapter_code", "adapter_version") in unique_column_sets(
        PlatformAdapter.__table__
    )
    assert (
        "platform_code",
        "account_namespace",
        "active_account_email",
    ) in unique_column_sets(PublisherAccount.__table__)
    active_email = PublisherAccount.__table__.c.active_account_email
    assert active_email.computed.persisted is True
    assert active_email.computed.sqltext.text == (
        "IF(deleted_at IS NULL, normalized_email, NULL)"
    )
    assert ("idempotency_key",) in unique_column_sets(RegistrationTask.__table__)
    assert ("token_hash",) in unique_column_sets(RegistrationConfirmation.__table__)
    assert isinstance(RegistrationConfirmation.__table__.c.summary_hash.type, CHAR)
    assert RegistrationConfirmation.__table__.c.summary_hash.type.length == 64
    assert isinstance(RegistrationConfirmation.__table__.c.token_hash.type, CHAR)
    assert RegistrationConfirmation.__table__.c.token_hash.type.length == 64
    assert "registration_audit_logs" not in Base.metadata.tables


def test_registration_task_reuses_verified_submission_portal(db_engine):
    from app.models import RegistrationTask

    table = RegistrationTask.__table__
    assert "registration_url" not in table.c
    portal_id = table.c.get("portal_id")
    assert portal_id is not None
    assert isinstance(portal_id.type, CHAR)
    assert portal_id.type.length == 36
    assert portal_id.nullable is False
    foreign_key = next(iter(portal_id.foreign_keys))
    assert foreign_key.column.table.name == "journal_submission_portals"
    assert foreign_key.column.name == "id"
    assert foreign_key.ondelete == "RESTRICT"
    assert any(
        foreign_key["constrained_columns"] == ["portal_id"]
        and foreign_key["referred_table"] == "journal_submission_portals"
        and foreign_key["referred_columns"] == ["id"]
        and foreign_key["options"].get("ondelete") == "RESTRICT"
        for foreign_key in inspect(db_engine).get_foreign_keys("registration_tasks")
    )


def test_registration_initialization_is_idempotent_and_preserves_publisher_ids(
    db_engine, db_session, migration_config
):
    existing_id = "00000000-0000-0000-0000-000000000001"
    command.downgrade(migration_config, "0006")
    db_session.execute(
        text(
            "INSERT INTO publishers "
            "(id, name, normalized_name, created_at, updated_at) "
            "VALUES (:id, :name, :normalized_name, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
        ),
        {
            "id": existing_id,
            "name": "Existing Elsevier",
            "normalized_name": "elsevier",
        },
    )
    db_session.commit()

    command.upgrade(migration_config, "0007")
    query = text(
        "SELECT s.publisher_code, s.display_name, s.support_status, s.support_level, "
        "s.publisher_id, p.normalized_name "
        "FROM publisher_registration_support s "
        "JOIN publishers p ON p.id = s.publisher_id"
    )
    with db_engine.connect() as connection:
        first_rows = connection.execute(query).mappings().all()
    assert len(first_rows) == 5
    assert {row["publisher_code"] for row in first_rows} == set(CANONICAL_PUBLISHERS)
    first_ids = {}
    for row in first_rows:
        display_name, normalized_name = CANONICAL_PUBLISHERS[row["publisher_code"]]
        assert row["display_name"] == display_name
        assert row["normalized_name"] == normalized_name
        assert row["support_status"] == "SUPPORTED"
        assert row["support_level"] == "V0_1"
        first_ids[row["publisher_code"]] = row["publisher_id"]
    assert first_ids["ELSEVIER"] == existing_id

    migration = runpy.run_path(
        str(BACKEND_DIR / "alembic" / "versions" / "0007_registration_foundation.py")
    )
    with db_engine.begin() as connection:
        migration["initialize_registration_support"](connection)
        migration["initialize_registration_support"](connection)
    with db_engine.connect() as connection:
        repeated_rows = connection.execute(query).mappings().all()
    assert len(repeated_rows) == 5
    assert {row["publisher_code"] for row in repeated_rows} == set(CANONICAL_PUBLISHERS)
    assert {
        row["publisher_code"]: row["publisher_id"] for row in repeated_rows
    } == first_ids

    command.downgrade(migration_config, "0006")
    inspector = inspect(db_engine)
    assert "publisher_registration_support" not in inspector.get_table_names()
    assert "normalized_host" not in {
        column["name"] for column in inspector.get_columns("journal_submission_portals")
    }
    command.upgrade(migration_config, "0007")
    with db_engine.connect() as connection:
        second_rows = connection.execute(query).mappings().all()
    assert len(second_rows) == 5
    assert {
        row["publisher_code"]: row["publisher_id"] for row in second_rows
    } == first_ids


def test_soft_deleted_account_releases_active_email_uniqueness(db_session):
    from app.models import Author, Publisher, PublisherAccount

    author = Author(display_name="Registration Schema Author", alternate_names=[])
    publisher = Publisher(
        name="Registration Schema Publisher",
        normalized_name="registration schema publisher",
    )
    db_session.add_all([author, publisher])
    db_session.flush()
    account = PublisherAccount(
        author_id=author.id,
        publisher_id=publisher.id,
        platform_code="TEST_PLATFORM",
        account_namespace="test.example",
        account_email="Author@Example.com",
        normalized_email="author@example.com",
    )
    db_session.add(account)
    db_session.commit()
    account_id = account.id
    db_session.refresh(account)
    assert account.active_account_email == "author@example.com"

    db_session.add(
        PublisherAccount(
            author_id=author.id,
            publisher_id=publisher.id,
            platform_code="TEST_PLATFORM",
            account_namespace="test.example",
            account_email="author@example.com",
            normalized_email="author@example.com",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    account = db_session.get(PublisherAccount, account_id)
    account.deleted_at = utc_now()
    replacement = PublisherAccount(
        author_id=author.id,
        publisher_id=publisher.id,
        platform_code="TEST_PLATFORM",
        account_namespace="test.example",
        account_email="author@example.com",
        normalized_email="author@example.com",
    )
    db_session.add(replacement)
    db_session.commit()
    db_session.refresh(account)
    db_session.refresh(replacement)
    assert account.active_account_email is None
    assert replacement.active_account_email == "author@example.com"
