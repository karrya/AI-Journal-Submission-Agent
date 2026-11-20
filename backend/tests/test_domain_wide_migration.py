import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from conftest import BACKEND_DIR


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


def test_0010_merges_existing_data_before_dropping_redundant_tables(
    db_engine, db_session, migration_config
):
    command.downgrade(migration_config, "0009")
    publisher_id = "00000000-0000-0000-0000-000000000101"
    journal_id = "00000000-0000-0000-0000-000000000102"
    adapter_id = "00000000-0000-0000-0000-000000000103"
    portal_id = "00000000-0000-0000-0000-000000000104"
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO publishers "
                "(id, name, normalized_name, created_at, updated_at) "
                "VALUES (:id, 'Elsevier', 'elsevier', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
            ),
            {"id": publisher_id},
        )
        connection.execute(
            text(
                "INSERT INTO publisher_registration_support "
                "(id, publisher_id, publisher_code, display_name, support_status, "
                "support_level, official_domains, notes, created_at, updated_at) "
                "VALUES (UUID(), :publisher_id, 'ELSEVIER', 'Elsevier', 'SUPPORTED', "
                "'V0_1', JSON_ARRAY('register.example'), 'migration fixture', "
                "CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
            ),
            {"publisher_id": publisher_id},
        )
        connection.execute(
            text(
                "INSERT INTO publisher_aliases "
                "(id, publisher_id, alias, normalized_alias, created_at) "
                "VALUES (UUID(), :publisher_id, 'Elsevier BV', 'elsevier bv', CURRENT_TIMESTAMP(6))"
            ),
            {"publisher_id": publisher_id},
        )
        connection.execute(
            text(
                "INSERT INTO journals "
                "(id, publisher_id, name, issn, eissn, subject_categories, article_types, "
                "requirements, status, created_at, updated_at) "
                "VALUES (:id, :publisher_id, 'Migration Journal', '12345679', '87654321', "
                "JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY(), 'active', "
                "CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
            ),
            {"id": journal_id, "publisher_id": publisher_id},
        )
        connection.execute(
            text(
                "INSERT INTO journal_aliases "
                "(id, journal_id, alias, normalized_alias, created_at) "
                "VALUES (UUID(), :journal_id, 'Migration J', 'migration j', CURRENT_TIMESTAMP(6))"
            ),
            {"journal_id": journal_id},
        )
        for identifier_type, value in (("ISSN", "12345679"), ("EISSN", "87654321")):
            connection.execute(
                text(
                    "INSERT INTO journal_identifiers "
                    "(id, journal_id, identifier_type, identifier_value, created_at) "
                    "VALUES (UUID(), :journal_id, :identifier_type, :value, CURRENT_TIMESTAMP(6))"
                ),
                {
                    "journal_id": journal_id,
                    "identifier_type": identifier_type,
                    "value": value,
                },
            )
        connection.execute(
            text(
                "INSERT INTO platform_adapters "
                "(id, adapter_code, adapter_name, platform_type, adapter_version, "
                "support_status, allowed_domains, capability_config, created_at, updated_at) "
                "VALUES (:id, 'TEST_ADAPTER', 'Test Adapter', 'TEST_PLATFORM', '1.0.0', "
                "'SUPPORTED', JSON_ARRAY('register.example'), JSON_OBJECT('form', 'v1'), "
                "CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
            ),
            {"id": adapter_id},
        )
        connection.execute(
            text(
                "INSERT INTO journal_submission_portals "
                "(id, journal_id, original_url, final_url, redirect_chain, verification_status, "
                "access_status, platform_code, confidence, evidence_summary, normalized_host, "
                "platform_adapter_id, support_status, created_at, updated_at) "
                "VALUES (:id, :journal_id, 'https://register.example/start', "
                "'https://register.example/register', JSON_ARRAY(), 'VERIFIED', 'ACCESSIBLE', "
                "'TEST_PLATFORM', 1, JSON_ARRAY(), 'register.example', :adapter_id, "
                "'SUPPORTED', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
            ),
            {"id": portal_id, "journal_id": journal_id, "adapter_id": adapter_id},
        )
        connection.execute(
            text(
                "INSERT INTO journal_submission_portals "
                "(id, journal_id, original_url, final_url, redirect_chain, verification_status, "
                "access_status, platform_code, confidence, evidence_summary, normalized_host, "
                "platform_adapter_id, support_status, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000105', :journal_id, "
                "'https://register.example/second', 'https://register.example/second', "
                "JSON_ARRAY(), 'VERIFIED', 'ACCESSIBLE', 'TEST_PLATFORM', 1, JSON_ARRAY(), "
                "'register.example', :adapter_id, 'SUPPORTED', "
                "'2026-01-01 00:00:00', '2026-01-02 00:00:00')"
            ),
            {"journal_id": journal_id, "adapter_id": adapter_id},
        )

    command.upgrade(migration_config, "head")

    inspector = inspect(db_engine)
    table_names = set(inspector.get_table_names())
    assert len(table_names - {"alembic_version"}) == 23
    assert {
        "publisher_registration_support",
        "publisher_aliases",
        "journal_aliases",
        "journal_identifiers",
        "journal_platforms",
        "platform_adapters",
        "publisher_accounts",
        "email_verification_records",
    }.isdisjoint(table_names)
    with db_engine.connect() as connection:
        publisher = connection.execute(
            text(
                "SELECT registration_code, registration_support_status, "
                "registration_support_level, registration_notes, "
                "JSON_UNQUOTE(JSON_EXTRACT(registration_official_domains, '$[0]')) AS domain, "
                "JSON_UNQUOTE(JSON_EXTRACT(aliases, '$[0].normalized_alias')) AS alias "
                "FROM publishers WHERE id = :id"
            ),
            {"id": publisher_id},
        ).mappings().one()
        assert dict(publisher) == {
            "registration_code": "ELSEVIER",
            "registration_support_status": "SUPPORTED",
            "registration_support_level": "V0_1",
            "registration_notes": "migration fixture",
            "domain": "register.example",
            "alias": "elsevier bv",
        }
        journal = connection.execute(
            text(
                "SELECT issn, eissn, "
                "JSON_UNQUOTE(JSON_EXTRACT(aliases, '$[0].normalized_alias')) AS alias "
                "FROM journals WHERE id = :id"
            ),
            {"id": journal_id},
        ).mappings().one()
        assert dict(journal) == {
            "issn": "12345679",
            "eissn": "87654321",
            "alias": "migration j",
        }
        portal = connection.execute(
            text(
                "SELECT adapter_code, adapter_name, adapter_version, "
                "adapter_support_status, "
                "JSON_UNQUOTE(JSON_EXTRACT(adapter_allowed_domains, '$[0]')) AS domain, "
                "JSON_UNQUOTE(JSON_EXTRACT(adapter_capability_config, '$.form')) AS form "
                "FROM journal_submission_portals WHERE id = :id"
            ),
            {"id": portal_id},
        ).mappings().one()
        assert dict(portal) == {
            "adapter_code": "TEST_ADAPTER",
            "adapter_name": "Test Adapter",
            "adapter_version": "1.0.0",
            "adapter_support_status": "SUPPORTED",
            "domain": "register.example",
            "form": "v1",
        }

    command.downgrade(migration_config, "0009")
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM platform_adapters")) == 1
        adapter_ids = connection.execute(
            text(
                "SELECT platform_adapter_id FROM journal_submission_portals "
                "WHERE id IN ('00000000-0000-0000-0000-000000000104', "
                "'00000000-0000-0000-0000-000000000105') ORDER BY id"
            )
        ).scalars().all()
        assert len(adapter_ids) == 2
        assert adapter_ids[0] == adapter_ids[1]
    command.upgrade(migration_config, "head")


def insert_adapter(connection, platform_type="TEST_PLATFORM"):
    connection.execute(
        text(
            "INSERT INTO platform_adapters "
            "(id, adapter_code, adapter_name, platform_type, adapter_version, "
            "support_status, allowed_domains, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000103', 'TEST_ADAPTER', "
            "'Test Adapter', :platform_type, '1.0.0', 'SUPPORTED', "
            "JSON_ARRAY('register.example'), CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
        ),
        {"platform_type": platform_type},
    )


def insert_publisher_and_journal(connection):
    connection.execute(
        text(
            "INSERT INTO publishers (id, name, normalized_name, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000101', 'Elsevier', 'elsevier', "
            "CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
        )
    )
    connection.execute(
        text(
            "INSERT INTO journals (id, publisher_id, name, subject_categories, article_types, "
            "requirements, status, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000102', "
            "'00000000-0000-0000-0000-000000000101', 'Migration Journal', "
            "JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY(), 'active', "
            "CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
        )
    )


def assert_upgrade_aborts_before_ddl(db_engine, migration_config, match):
    with pytest.raises(RuntimeError, match=match):
        command.upgrade(migration_config, "head")
    inspector = inspect(db_engine)
    assert "registration_code" not in {
        column["name"] for column in inspector.get_columns("publishers")
    }
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009"


def test_0010_rejects_unreferenced_adapter_before_ddl(db_engine, db_session, migration_config):
    command.downgrade(migration_config, "0009")
    with db_engine.begin() as connection:
        insert_adapter(connection)

    assert_upgrade_aborts_before_ddl(db_engine, migration_config, "未关联")
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM platform_adapters"))


def test_0010_rejects_adapter_platform_mismatch_before_ddl(
    db_engine, db_session, migration_config
):
    command.downgrade(migration_config, "0009")
    with db_engine.begin() as connection:
        insert_publisher_and_journal(connection)
        insert_adapter(connection, platform_type="OTHER_PLATFORM")
        connection.execute(
            text(
                "INSERT INTO journal_submission_portals "
                "(id, journal_id, original_url, final_url, redirect_chain, verification_status, "
                "access_status, platform_code, confidence, evidence_summary, normalized_host, "
                "platform_adapter_id, support_status, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000104', "
                "'00000000-0000-0000-0000-000000000102', 'https://register.example/start', "
                "'https://register.example/register', JSON_ARRAY(), 'VERIFIED', 'ACCESSIBLE', "
                "'TEST_PLATFORM', 1, JSON_ARRAY(), 'register.example', "
                "'00000000-0000-0000-0000-000000000103', 'SUPPORTED', "
                "CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
            )
        )

    assert_upgrade_aborts_before_ddl(db_engine, migration_config, "平台类型")
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE journal_submission_portals SET platform_adapter_id = NULL"))
        connection.execute(text("DELETE FROM platform_adapters"))


def test_0010_rejects_distinct_registration_display_name_before_ddl(
    db_engine, db_session, migration_config
):
    command.downgrade(migration_config, "0009")
    with db_engine.begin() as connection:
        insert_publisher_and_journal(connection)
        connection.execute(
            text(
                "INSERT INTO publisher_registration_support "
                "(id, publisher_id, publisher_code, display_name, support_status, support_level, "
                "created_at, updated_at) VALUES (UUID(), "
                "'00000000-0000-0000-0000-000000000101', 'ELSEVIER', 'Different Name', "
                "'SUPPORTED', 'V0_1', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
            )
        )

    assert_upgrade_aborts_before_ddl(db_engine, migration_config, "display_name")
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM publisher_registration_support"))
