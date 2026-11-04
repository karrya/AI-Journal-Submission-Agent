"""Create manuscript, file, journal, and audit tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def mutable_columns(*, soft_delete: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "created_by",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    ]
    if soft_delete:
        columns.append(sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True))
    return columns


def created_only_columns(*, soft_delete: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "created_by",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    ]
    if soft_delete:
        columns.append(sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True))
    return columns


def upgrade() -> None:
    op.create_table(
        "manuscripts",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("internal_number", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "owner_author_id",
            sa.CHAR(36),
            sa.ForeignKey("authors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.VARCHAR(1000), nullable=False),
        sa.Column("abstract", sa.TEXT, nullable=False),
        sa.Column("keywords", sa.JSON, nullable=False),
        sa.Column("article_type", sa.VARCHAR(100), nullable=False),
        sa.Column("subject_field", sa.VARCHAR(255), nullable=True),
        sa.Column("language", sa.VARCHAR(32), nullable=False),
        sa.Column("funding_statement", sa.TEXT, nullable=True),
        sa.Column("conflict_of_interest_statement", sa.TEXT, nullable=True),
        sa.Column("ethics_statement", sa.TEXT, nullable=True),
        sa.Column("data_availability_statement", sa.TEXT, nullable=True),
        sa.Column("current_version_id", sa.CHAR(36), nullable=True),
        sa.Column("status", sa.VARCHAR(32), nullable=False),
        sa.Column("notes", sa.TEXT, nullable=True),
        *mutable_columns(soft_delete=True),
        sa.UniqueConstraint("internal_number", name="uq_manuscripts_internal_number"),
        sa.UniqueConstraint("id", "owner_author_id", name="uq_manuscripts_id_owner"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_manuscripts_owner", "manuscripts", ["owner_author_id"])
    op.create_index("ix_manuscripts_status", "manuscripts", ["status"])

    op.create_table(
        "manuscript_authors",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "manuscript_id",
            sa.CHAR(36),
            sa.ForeignKey("manuscripts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.CHAR(36),
            sa.ForeignKey("authors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("is_corresponding", sa.Boolean, nullable=False),
        *mutable_columns(),
        sa.UniqueConstraint(
            "manuscript_id",
            "author_id",
            name="uq_manuscript_authors_manuscript_author",
        ),
        sa.UniqueConstraint(
            "manuscript_id",
            "position",
            name="uq_manuscript_authors_manuscript_position",
        ),
        sa.CheckConstraint("position > 0", name="positive_position"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "manuscript_versions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "manuscript_id",
            sa.CHAR(36),
            sa.ForeignKey("manuscripts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("label", sa.VARCHAR(100), nullable=True),
        sa.Column("change_note", sa.TEXT, nullable=True),
        sa.Column("metadata_snapshot", sa.JSON, nullable=False),
        *created_only_columns(),
        sa.UniqueConstraint(
            "manuscript_id",
            "version_number",
            name="uq_manuscript_versions_manuscript_number",
        ),
        sa.UniqueConstraint(
            "manuscript_id", "id", name="uq_manuscript_versions_manuscript_id"
        ),
        **TABLE_OPTIONS,
    )

    op.create_foreign_key(
        "fk_manuscripts_current_version",
        "manuscripts",
        "manuscript_versions",
        ["id", "current_version_id"],
        ["manuscript_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "file_families",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("author_id", sa.CHAR(36), nullable=False),
        sa.Column("manuscript_id", sa.CHAR(36), nullable=False),
        sa.Column("file_type", sa.VARCHAR(32), nullable=False),
        sa.Column("display_name", sa.VARCHAR(255), nullable=False),
        *created_only_columns(soft_delete=True),
        sa.UniqueConstraint(
            "id", "manuscript_id", name="uq_file_families_id_manuscript"
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "author_id"],
            ["manuscripts.id", "manuscripts.owner_author_id"],
            name="fk_file_families_manuscript_owner",
            ondelete="RESTRICT",
        ),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "manuscript_files",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("file_family_id", sa.CHAR(36), nullable=False),
        sa.Column("manuscript_id", sa.CHAR(36), nullable=False),
        sa.Column("manuscript_version_id", sa.CHAR(36), nullable=False),
        sa.Column("file_version", sa.Integer, nullable=False),
        sa.Column("original_filename", sa.VARCHAR(255), nullable=False),
        sa.Column("stored_filename", sa.VARCHAR(255), nullable=False),
        sa.Column(
            "storage_path",
            sa.VARCHAR(1024, collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("mime_type", sa.VARCHAR(255), nullable=False),
        sa.Column("extension", sa.VARCHAR(16), nullable=False),
        sa.Column("size_bytes", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("scan_status", sa.VARCHAR(32), nullable=False),
        sa.Column("integrity_status", sa.VARCHAR(32), nullable=False),
        sa.Column("status", sa.VARCHAR(32), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "uploaded_by",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.UniqueConstraint(
            "file_family_id",
            "file_version",
            name="uq_manuscript_files_family_version",
        ),
        sa.UniqueConstraint("storage_path", name="uq_manuscript_files_storage_path"),
        sa.ForeignKeyConstraint(
            ["file_family_id", "manuscript_id"],
            ["file_families.id", "file_families.manuscript_id"],
            name="fk_manuscript_files_family_manuscript",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "manuscript_version_id"],
            ["manuscript_versions.manuscript_id", "manuscript_versions.id"],
            name="fk_manuscript_files_manuscript_version",
            ondelete="RESTRICT",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_manuscript_files_sha256", "manuscript_files", ["sha256"])

    op.create_table(
        "publishers",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("normalized_name", sa.VARCHAR(255), nullable=False),
        sa.Column("website_url", sa.VARCHAR(1024), nullable=True),
        sa.Column("notes", sa.TEXT, nullable=True),
        *mutable_columns(soft_delete=True),
        sa.UniqueConstraint("normalized_name", name="uq_publishers_normalized_name"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "journal_platforms",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("code", sa.VARCHAR(64), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("description", sa.TEXT, nullable=False),
        sa.Column("status", sa.VARCHAR(32), nullable=False),
        *mutable_columns(soft_delete=True),
        sa.UniqueConstraint("code", name="uq_journal_platforms_code"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "journals",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "publisher_id",
            sa.CHAR(36),
            sa.ForeignKey("publishers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "platform_id",
            sa.CHAR(36),
            sa.ForeignKey("journal_platforms.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.VARCHAR(500), nullable=False),
        sa.Column("issn", sa.CHAR(8), nullable=True),
        sa.Column("eissn", sa.CHAR(8), nullable=True),
        sa.Column("website_url", sa.VARCHAR(1024), nullable=True),
        sa.Column("submission_url", sa.VARCHAR(1024), nullable=True),
        sa.Column("author_guidelines_url", sa.VARCHAR(1024), nullable=True),
        sa.Column("subject_categories", sa.JSON, nullable=False),
        sa.Column("article_types", sa.JSON, nullable=False),
        sa.Column("requirements", sa.JSON, nullable=False),
        sa.Column("requirements_source_url", sa.VARCHAR(1024), nullable=True),
        sa.Column("requirements_verified_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("status", sa.VARCHAR(32), nullable=False),
        sa.Column("notes", sa.TEXT, nullable=True),
        *mutable_columns(soft_delete=True),
        sa.UniqueConstraint("issn", name="uq_journals_issn"),
        sa.UniqueConstraint("eissn", name="uq_journals_eissn"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_journals_publisher_name", "journals", ["publisher_id", "name"])
    op.create_index("ix_journals_platform", "journals", ["platform_id"])

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "actor_user_id",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("actor_type", sa.VARCHAR(32), nullable=False),
        sa.Column("category", sa.VARCHAR(32), nullable=False),
        sa.Column("action", sa.VARCHAR(100), nullable=False),
        sa.Column("target_type", sa.VARCHAR(64), nullable=True),
        sa.Column("target_id", sa.CHAR(36), nullable=True),
        sa.Column(
            "author_id",
            sa.CHAR(36),
            sa.ForeignKey("authors.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("request_id", sa.CHAR(36), nullable=False),
        sa.Column("result", sa.VARCHAR(32), nullable=False),
        sa.Column("before_summary", sa.JSON, nullable=True),
        sa.Column("after_summary", sa.JSON, nullable=True),
        sa.Column("error_code", sa.VARCHAR(64), nullable=True),
        sa.Column("error_message", sa.VARCHAR(1024), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_operation_logs_actor_created",
        "operation_logs",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_operation_logs_author_created",
        "operation_logs",
        ["author_id", "created_at"],
    )
    op.create_index(
        "ix_operation_logs_target",
        "operation_logs",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_operation_logs_action_created",
        "operation_logs",
        ["action", "created_at"],
    )
    op.create_index("ix_operation_logs_request", "operation_logs", ["request_id"])


def downgrade() -> None:
    for table in (
        "operation_logs",
        "journals",
        "journal_platforms",
        "publishers",
        "manuscript_files",
        "file_families",
    ):
        op.drop_table(table)
    op.drop_constraint(
        "fk_manuscripts_current_version", "manuscripts", type_="foreignkey"
    )
    op.drop_table("manuscript_versions")
    op.drop_table("manuscript_authors")
    op.drop_table("manuscripts")
