import importlib

import pytest
from sqlalchemy import (
    JSON,
    BIGINT,
    CHAR,
    TEXT,
    VARCHAR,
    ForeignKeyConstraint,
    inspect,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.exc import IntegrityError

from app.models import Author, Base


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
    "manuscripts",
    "manuscript_authors",
    "manuscript_versions",
    "file_families",
    "manuscript_files",
    "publishers",
    "journal_platforms",
    "journals",
    "operation_logs",
}

NEW_MODELS = {
    "Manuscript",
    "ManuscriptAuthor",
    "ManuscriptVersion",
    "FileFamily",
    "ManuscriptFile",
    "Publisher",
    "JournalPlatform",
    "Journal",
    "OperationLog",
}

EXPECTED_NEW_COLUMNS = {
    "manuscripts": {
        "id",
        "internal_number",
        "owner_author_id",
        "title",
        "abstract",
        "keywords",
        "article_type",
        "subject_field",
        "language",
        "funding_statement",
        "conflict_of_interest_statement",
        "ethics_statement",
        "data_availability_statement",
        "current_version_id",
        "status",
        "notes",
        "created_at",
        "updated_at",
        "created_by",
        "deleted_at",
    },
    "manuscript_authors": {
        "id",
        "manuscript_id",
        "author_id",
        "position",
        "is_corresponding",
        "created_at",
        "updated_at",
        "created_by",
    },
    "manuscript_versions": {
        "id",
        "manuscript_id",
        "version_number",
        "label",
        "change_note",
        "metadata_snapshot",
        "created_at",
        "created_by",
    },
    "file_families": {
        "id",
        "author_id",
        "manuscript_id",
        "file_type",
        "display_name",
        "created_at",
        "created_by",
        "deleted_at",
    },
    "manuscript_files": {
        "id",
        "file_family_id",
        "manuscript_id",
        "manuscript_version_id",
        "file_version",
        "original_filename",
        "stored_filename",
        "storage_path",
        "mime_type",
        "extension",
        "size_bytes",
        "sha256",
        "scan_status",
        "integrity_status",
        "status",
        "created_at",
        "updated_at",
        "uploaded_by",
        "deleted_at",
    },
    "publishers": {
        "id",
        "name",
        "normalized_name",
        "website_url",
        "notes",
        "created_at",
        "updated_at",
        "created_by",
        "deleted_at",
    },
    "journal_platforms": {
        "id",
        "code",
        "name",
        "description",
        "status",
        "created_at",
        "updated_at",
        "created_by",
        "deleted_at",
    },
    "journals": {
        "id",
        "publisher_id",
        "platform_id",
        "name",
        "issn",
        "eissn",
        "website_url",
        "submission_url",
        "author_guidelines_url",
        "subject_categories",
        "article_types",
        "requirements",
        "requirements_source_url",
        "requirements_verified_at",
        "status",
        "notes",
        "created_at",
        "updated_at",
        "created_by",
        "deleted_at",
    },
    "operation_logs": {
        "id",
        "actor_user_id",
        "actor_type",
        "category",
        "action",
        "target_type",
        "target_id",
        "author_id",
        "request_id",
        "result",
        "before_summary",
        "after_summary",
        "error_code",
        "error_message",
        "created_at",
    },
}

EXPECTED_COMPOSITE_FKS = {
    "manuscripts": {
        (
            ("id", "current_version_id"),
            "manuscript_versions",
            ("manuscript_id", "id"),
        )
    },
    "file_families": {
        (
            ("manuscript_id", "author_id"),
            "manuscripts",
            ("id", "owner_author_id"),
        )
    },
    "manuscript_files": {
        (
            ("file_family_id", "manuscript_id"),
            "file_families",
            ("id", "manuscript_id"),
        ),
        (
            ("manuscript_id", "manuscript_version_id"),
            "manuscript_versions",
            ("manuscript_id", "id"),
        ),
    },
}


def models():
    return importlib.import_module("app.models")


def model_foreign_keys(table):
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.elements[0].column.table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def model_unique_columns(table):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


@pytest.fixture
def manuscript_graph(db_session):
    orm = models()
    owner = Author(display_name="Manuscript Owner", alternate_names=[])
    other_author = Author(display_name="Other Author", alternate_names=[])
    db_session.add_all([owner, other_author])
    db_session.flush()
    first = orm.Manuscript(
        internal_number="MS-SCHEMA-001",
        owner_author_id=owner.id,
        title="First manuscript",
        abstract="First abstract",
        keywords=[],
        article_type="research",
        language="en",
    )
    second = orm.Manuscript(
        internal_number="MS-SCHEMA-002",
        owner_author_id=owner.id,
        title="Second manuscript",
        abstract="Second abstract",
        keywords=[],
        article_type="research",
        language="en",
    )
    db_session.add_all([first, second])
    db_session.flush()
    first_version = orm.ManuscriptVersion(
        manuscript_id=first.id,
        version_number=1,
        metadata_snapshot={"title": first.title, "authors": []},
    )
    second_version = orm.ManuscriptVersion(
        manuscript_id=second.id,
        version_number=1,
        metadata_snapshot={"title": second.title, "authors": []},
    )
    db_session.add_all([first_version, second_version])
    db_session.commit()
    return {
        "owner_id": owner.id,
        "other_author_id": other_author.id,
        "manuscript_id": first.id,
        "other_manuscript_id": second.id,
        "version_id": first_version.id,
        "other_version_id": second_version.id,
    }


@pytest.fixture
def two_manuscript_versions(manuscript_graph):
    return (
        manuscript_graph["manuscript_id"],
        manuscript_graph["other_version_id"],
    )


def test_remaining_models_export_the_complete_eighteen_table_contract():
    orm = models()
    assert NEW_MODELS.issubset(set(orm.__all__))
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert {getattr(orm, name).__tablename__ for name in NEW_MODELS} == set(
        EXPECTED_NEW_COLUMNS
    )
    for table_name, expected_columns in EXPECTED_NEW_COLUMNS.items():
        assert set(Base.metadata.tables[table_name].columns.keys()) == expected_columns


def test_column_types_json_and_immutable_timestamps_match_the_contract():
    models()
    for table_name in EXPECTED_NEW_COLUMNS:
        table = Base.metadata.tables[table_name]
        assert table.dialect_options["mysql"]["engine"] == "InnoDB"
        assert table.dialect_options["mysql"]["charset"] == "utf8mb4"
        for column in table.columns:
            if column.primary_key or column.name.endswith("_id"):
                assert isinstance(column.type, CHAR)
                assert column.type.length == 36
            if column.name.endswith("_at"):
                assert isinstance(column.type, DATETIME)
                assert column.type.fsp == 6

    json_columns = {
        ("manuscripts", "keywords"),
        ("manuscript_versions", "metadata_snapshot"),
        ("journals", "subject_categories"),
        ("journals", "article_types"),
        ("journals", "requirements"),
        ("operation_logs", "before_summary"),
        ("operation_logs", "after_summary"),
    }
    actual_json_columns = {
        (table_name, column.name)
        for table_name in EXPECTED_NEW_COLUMNS
        for column in Base.metadata.tables[table_name].columns
        if isinstance(column.type, JSON)
    }
    assert actual_json_columns == json_columns

    files = Base.metadata.tables["manuscript_files"]
    assert isinstance(files.c.size_bytes.type, BIGINT)
    assert files.c.size_bytes.type.unsigned is True
    assert isinstance(files.c.sha256.type, CHAR)
    assert files.c.sha256.type.length == 64
    assert files.c.storage_path.type.collation == "ascii_bin"
    assert isinstance(Base.metadata.tables["manuscripts"].c.abstract.type, TEXT)
    assert Base.metadata.tables["manuscripts"].c.title.type.length == 1000
    assert Base.metadata.tables["journals"].c.name.type.length == 500
    assert "updated_at" not in Base.metadata.tables["manuscript_versions"].columns
    assert "updated_at" not in Base.metadata.tables["file_families"].columns
    assert "updated_at" not in Base.metadata.tables["operation_logs"].columns
    assert "deleted_at" not in Base.metadata.tables["operation_logs"].columns


def test_composite_foreign_keys_use_the_referenced_unique_index_order():
    models()
    for table_name, expected in EXPECTED_COMPOSITE_FKS.items():
        table = Base.metadata.tables[table_name]
        assert expected.issubset(model_foreign_keys(table))
        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                assert all(
                    element.ondelete == "RESTRICT" for element in constraint.elements
                )


def test_unique_constraints_checks_and_indexes_match_the_spec():
    models()
    manuscripts = Base.metadata.tables["manuscripts"]
    versions = Base.metadata.tables["manuscript_versions"]
    families = Base.metadata.tables["file_families"]
    files = Base.metadata.tables["manuscript_files"]
    authorship = Base.metadata.tables["manuscript_authors"]

    assert {
        ("internal_number",),
        ("id", "owner_author_id"),
    }.issubset(model_unique_columns(manuscripts))
    assert {
        ("manuscript_id", "version_number"),
        ("manuscript_id", "id"),
    }.issubset(model_unique_columns(versions))
    assert ("id", "manuscript_id") in model_unique_columns(families)
    assert {
        ("file_family_id", "file_version"),
        ("storage_path",),
    }.issubset(model_unique_columns(files))
    assert {
        ("manuscript_id", "author_id"),
        ("manuscript_id", "position"),
    }.issubset(model_unique_columns(authorship))
    assert any(
        constraint.__class__.__name__ == "CheckConstraint"
        and "position > 0" in constraint.sqltext.text
        for constraint in authorship.constraints
    )
    assert any(
        tuple(column.name for column in index.columns) == ("sha256",)
        for index in files.indexes
    )


def test_journal_issn_provenance_and_audit_read_only_contract():
    models()
    journals = Base.metadata.tables["journals"]
    for name in ("issn", "eissn"):
        column = journals.c[name]
        assert isinstance(column.type, CHAR)
        assert column.type.length == 8
        assert column.nullable is True
        assert (name,) in model_unique_columns(journals)
    assert isinstance(journals.c.requirements_source_url.type, VARCHAR)
    assert journals.c.requirements_source_url.type.length == 1024
    assert isinstance(journals.c.requirements_verified_at.type, DATETIME)
    assert journals.c.requirements_verified_at.type.fsp == 6
    assert journals.c.requirements.nullable is False

    from app.api.v1.contract_manifest import CONTRACTS

    audit_methods = {
        contract.method
        for contract in CONTRACTS
        if contract.path.startswith("/audit-logs")
    }
    assert audit_methods == {"GET"}
    assert "updated_at" not in Base.metadata.tables["operation_logs"].columns


def test_all_eighteen_tables_exist(db_engine):
    core_tables = set(inspect(db_engine).get_table_names()) - {"alembic_version"}
    assert core_tables == EXPECTED_TABLES


def test_migrated_columns_and_composite_foreign_keys_match_models(db_engine):
    inspector = inspect(db_engine)
    for table_name, table in Base.metadata.tables.items():
        columns = inspector.get_columns(table_name)
        assert {column["name"] for column in columns} == set(table.columns.keys())
        for column in columns:
            if column["name"].endswith("_at"):
                assert isinstance(column["type"], DATETIME)
                assert column["type"].fsp == 6

    for table_name, expected in EXPECTED_COMPOSITE_FKS.items():
        actual = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        assert expected.issubset(actual)


def test_migrated_engine_collation_and_every_foreign_key_restrict_match_contract(
    db_engine,
):
    inspector = inspect(db_engine)
    for table_name in EXPECTED_TABLES:
        options = inspector.get_table_options(table_name)
        assert options["mysql_engine"] == "InnoDB"
        assert options["mysql_default charset"] == "utf8mb4"
        assert options["mysql_collate"].startswith("utf8mb4_")
        foreign_keys = inspector.get_foreign_keys(table_name)
        assert foreign_keys
        assert all(
            foreign_key["options"].get("ondelete") == "RESTRICT"
            for foreign_key in foreign_keys
        )
    storage_path = next(
        column
        for column in inspector.get_columns("manuscript_files")
        if column["name"] == "storage_path"
    )
    assert storage_path["type"].collation == "ascii_bin"


def test_mig_01_empty_upgrade_head_is_cleanly_repeatable(db_engine):
    """MIG-01: an empty upgrade and repeated head produce identical schema options."""
    import os

    from alembic import command
    from alembic.config import Config
    from conftest import BACKEND_DIR

    previous_url = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    try:
        command.downgrade(config, "base")
        assert inspect(db_engine).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        first_options = {
            name: inspect(db_engine).get_table_options(name) for name in EXPECTED_TABLES
        }
        command.upgrade(config, "head")
        assert set(inspect(db_engine).get_table_names()) == EXPECTED_TABLES | {
            "alembic_version"
        }
        assert {
            name: inspect(db_engine).get_table_options(name) for name in EXPECTED_TABLES
        } == first_options
        with db_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
            assert connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 1
    finally:
        command.upgrade(config, "head")
        if previous_url is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = previous_url


def test_current_version_must_belong_to_same_manuscript(
    db_session, two_manuscript_versions
):
    manuscript_id, other_version_id = two_manuscript_versions
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE manuscripts SET current_version_id=:version WHERE id=:id"),
            {"version": other_version_id, "id": manuscript_id},
        )
    db_session.rollback()


def test_file_family_owner_must_match_manuscript_owner(db_session, manuscript_graph):
    family = models().FileFamily(
        manuscript_id=manuscript_graph["manuscript_id"],
        author_id=manuscript_graph["other_author_id"],
        file_type="main_manuscript",
        display_name="Wrong owner",
    )
    db_session.add(family)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def add_file(db_session, graph, *, family_id, manuscript_id, version_id):
    file = models().ManuscriptFile(
        file_family_id=family_id,
        manuscript_id=manuscript_id,
        manuscript_version_id=version_id,
        file_version=1,
        original_filename="manuscript.pdf",
        stored_filename="stored.pdf",
        storage_path=f"tests/{family_id}/{version_id}/stored.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=12,
        sha256="0" * 64,
    )
    db_session.add(file)
    return file


def test_file_family_must_belong_to_the_same_manuscript(db_session, manuscript_graph):
    family = models().FileFamily(
        manuscript_id=manuscript_graph["manuscript_id"],
        author_id=manuscript_graph["owner_id"],
        file_type="main_manuscript",
        display_name="First family",
    )
    db_session.add(family)
    db_session.flush()
    add_file(
        db_session,
        manuscript_graph,
        family_id=family.id,
        manuscript_id=manuscript_graph["other_manuscript_id"],
        version_id=manuscript_graph["other_version_id"],
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_file_version_must_belong_to_the_same_manuscript(db_session, manuscript_graph):
    family = models().FileFamily(
        manuscript_id=manuscript_graph["manuscript_id"],
        author_id=manuscript_graph["owner_id"],
        file_type="main_manuscript",
        display_name="First family",
    )
    db_session.add(family)
    db_session.flush()
    add_file(
        db_session,
        manuscript_graph,
        family_id=family.id,
        manuscript_id=manuscript_graph["manuscript_id"],
        version_id=manuscript_graph["other_version_id"],
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
