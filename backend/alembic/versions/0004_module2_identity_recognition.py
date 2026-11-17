"""Add publisher and journal identity recognition structures.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, TINYINT

from app.schemas.journals import normalize_issn

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rows = op.get_bind().execute(sa.text("SELECT id, issn, eissn FROM journals")).mappings()
    normalized_identifiers = []
    for row in rows:
        for identifier_type, column in (("ISSN", "issn"), ("EISSN", "eissn")):
            if row[column] is not None:
                normalized_identifiers.append(
                    (row["id"], identifier_type, normalize_issn(row[column]))
                )

    for column in (
        sa.Column("publisher_name_en", sa.VARCHAR(255), nullable=True),
        sa.Column("primary_domain", sa.VARCHAR(255), nullable=True),
        sa.Column("country", sa.VARCHAR(100), nullable=True),
        sa.Column("publisher_type", sa.VARCHAR(50), nullable=True),
        sa.Column("parent_organization_id", sa.CHAR(36), nullable=True),
        sa.Column("status", sa.VARCHAR(30), nullable=False, server_default="ACTIVE"),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
    ):
        op.add_column("publishers", column)
    op.create_foreign_key(
        "fk_publishers_parent",
        "publishers",
        "publishers",
        ["parent_organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_publishers_domain", "publishers", ["primary_domain"])
    for column in (
        sa.Column("journal_name_en", sa.VARCHAR(500), nullable=True),
        sa.Column("aims_scope", sa.TEXT(), nullable=True),
        sa.Column("open_access_status", sa.VARCHAR(50), nullable=True),
        sa.Column(
            "identity_status",
            sa.VARCHAR(30),
            nullable=False,
            server_default="UNVERIFIED",
        ),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
    ):
        op.add_column("journals", column)
    op.create_index("ix_journals_identity_status", "journals", ["identity_status"])
    op.create_table(
        "publisher_aliases",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("publisher_id", sa.CHAR(36), nullable=False),
        sa.Column("alias", sa.VARCHAR(500), nullable=False),
        sa.Column("normalized_alias", sa.VARCHAR(500), nullable=False),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("publisher_id", "normalized_alias", name="uq_publisher_alias"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "ix_publisher_alias_normalized", "publisher_aliases", ["normalized_alias"]
    )
    op.create_table(
        "journal_aliases",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("journal_id", sa.CHAR(36), nullable=False),
        sa.Column("alias", sa.VARCHAR(500), nullable=False),
        sa.Column("normalized_alias", sa.VARCHAR(500), nullable=False),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("journal_id", "normalized_alias", name="uq_journal_alias"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_journal_alias_normalized", "journal_aliases", ["normalized_alias"])
    op.create_table(
        "journal_identifiers",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("journal_id", sa.CHAR(36), nullable=False),
        sa.Column("identifier_type", sa.VARCHAR(30), nullable=False),
        sa.Column("identifier_value", sa.VARCHAR(50), nullable=False),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("identifier_type", "identifier_value", name="uq_journal_identifier"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_journal_identifiers_journal", "journal_identifiers", ["journal_id"])
    op.create_table(
        "discovery_tasks",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("task_type", sa.VARCHAR(50), nullable=False),
        sa.Column("journal_id", sa.CHAR(36), nullable=True),
        sa.Column("owner_author_id", sa.CHAR(36), nullable=True),
        sa.Column("idempotency_key", sa.VARCHAR(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.VARCHAR(30), nullable=False, server_default="PENDING"),
        sa.Column("progress", TINYINT(unsigned=True), nullable=False, server_default="0"),
        sa.Column("attempt_count", INTEGER(unsigned=True), nullable=False, server_default="0"),
        sa.Column("max_attempts", INTEGER(unsigned=True), nullable=False, server_default="3"),
        sa.Column("checkpoint", sa.JSON(), nullable=True),
        sa.Column("last_error_code", sa.VARCHAR(64), nullable=True),
        sa.Column("last_error_message", sa.TEXT(), nullable=True),
        sa.Column("created_by", sa.CHAR(36), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", DATETIME(fsp=6), nullable=True),
        sa.Column("completed_at", DATETIME(fsp=6), nullable=True),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_author_id"], ["authors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("task_type", "idempotency_key", name="uq_discovery_task_idempotency"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_discovery_progress"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_discovery_status_updated", "discovery_tasks", ["status", "updated_at"])
    op.create_index("ix_discovery_owner", "discovery_tasks", ["owner_author_id", "created_at"])
    for journal_id, identifier_type, value in normalized_identifiers:
        op.execute(
            "INSERT INTO journal_identifiers "
            "(id, journal_id, identifier_type, identifier_value, created_at) "
            f"VALUES (UUID(), '{journal_id}', '{identifier_type}', "
            f"'{value}', CURRENT_TIMESTAMP(6))"
        )


def downgrade() -> None:
    op.drop_table("discovery_tasks")
    op.drop_table("journal_identifiers")
    op.drop_table("journal_aliases")
    op.drop_table("publisher_aliases")
    op.drop_index("ix_journals_identity_status", table_name="journals")
    for column in (
        "verified_at",
        "source_url",
        "identity_status",
        "open_access_status",
        "aims_scope",
        "journal_name_en",
    ):
        op.drop_column("journals", column)
    op.drop_constraint("fk_publishers_parent", "publishers", type_="foreignkey")
    op.drop_index("ix_publishers_domain", table_name="publishers")
    for column in (
        "verified_at",
        "source_url",
        "status",
        "parent_organization_id",
        "publisher_type",
        "country",
        "primary_domain",
        "publisher_name_en",
    ):
        op.drop_column("publishers", column)
