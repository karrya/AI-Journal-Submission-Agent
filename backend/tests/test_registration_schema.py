import os
import runpy

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CHAR, inspect, text
from app.models import Base
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


def test_registration_schema_is_at_0010(db_engine):
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0010"
    table_names = set(inspect(db_engine).get_table_names())
    assert len(table_names - {"alembic_version"}) == 23
    assert {"registration_tasks", "registration_confirmations"} <= table_names
    assert {
        "publisher_registration_support",
        "platform_adapters",
        "publisher_accounts",
        "email_verification_records",
    }.isdisjoint(table_names)


def test_registration_uniqueness_and_generated_column_match_the_contract():
    from app.models import Publisher, RegistrationConfirmation, RegistrationTask

    assert ("registration_code",) in unique_column_sets(Publisher.__table__)
    assert ("idempotency_key",) in unique_column_sets(RegistrationTask.__table__)
    assert (
        "author_id",
        "portal_id",
        "blocking_scope",
    ) in unique_column_sets(RegistrationTask.__table__)
    blocking_scope = RegistrationTask.__table__.c.blocking_scope
    assert blocking_scope.computed is not None
    assert blocking_scope.computed.persisted is True
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
            "name": "Elsevier",
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
