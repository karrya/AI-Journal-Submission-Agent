"""Add persistent network discovery workers, portals, and evidence.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME, INTEGER

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("stage", sa.VARCHAR(50), nullable=True),
        sa.Column("worker_id", sa.VARCHAR(64), nullable=True),
        sa.Column("lease_expires_at", DATETIME(fsp=6), nullable=True),
        sa.Column("available_at", DATETIME(fsp=6), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        op.add_column("discovery_tasks", column)
    op.create_index(
        "ix_discovery_available",
        "discovery_tasks",
        ["status", "available_at", "lease_expires_at"],
    )
    op.alter_column(
        "discovery_tasks",
        "created_by",
        existing_type=sa.CHAR(36),
        nullable=True,
    )
    op.create_table(
        "journal_submission_portals",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("journal_id", sa.CHAR(36), nullable=False),
        sa.Column("task_id", sa.CHAR(36), nullable=True),
        sa.Column("original_url", sa.VARCHAR(2048), nullable=False),
        sa.Column("final_url", sa.VARCHAR(2048), nullable=False),
        sa.Column("redirect_chain", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.VARCHAR(30), nullable=False),
        sa.Column("access_status", sa.VARCHAR(30), nullable=False),
        sa.Column("platform_code", sa.VARCHAR(50), nullable=False, server_default="UNKNOWN"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_summary", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.CHAR(36), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["discovery_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "ix_submission_portal_journal",
        "journal_submission_portals",
        ["journal_id", "created_at"],
    )
    op.create_table(
        "journal_source_snapshots",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("task_id", sa.CHAR(36), nullable=False),
        sa.Column("journal_id", sa.CHAR(36), nullable=True),
        sa.Column("source_type", sa.VARCHAR(30), nullable=False),
        sa.Column("original_url", sa.VARCHAR(2048), nullable=False),
        sa.Column("final_url", sa.VARCHAR(2048), nullable=False),
        sa.Column("http_status", INTEGER(unsigned=True), nullable=True),
        sa.Column("title", sa.VARCHAR(500), nullable=False, server_default=""),
        sa.Column("text_excerpt", sa.TEXT(), nullable=False),
        sa.Column("content_sha256", sa.CHAR(64), nullable=False),
        sa.Column("storage_path", sa.VARCHAR(1024), nullable=True),
        sa.Column("parser_version", sa.VARCHAR(50), nullable=False),
        sa.Column("fetched_at", DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["discovery_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "ix_source_snapshot_task", "journal_source_snapshots", ["task_id", "created_at"]
    )
    op.create_index(
        "ix_source_snapshot_journal", "journal_source_snapshots", ["journal_id", "created_at"]
    )
    op.create_table(
        "journal_discovery_logs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("task_id", sa.CHAR(36), nullable=True),
        sa.Column("journal_id", sa.CHAR(36), nullable=True),
        sa.Column("actor_user_id", sa.CHAR(36), nullable=True),
        sa.Column("event_type", sa.VARCHAR(50), nullable=False),
        sa.Column("message", sa.TEXT(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["discovery_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "ix_discovery_logs_task", "journal_discovery_logs", ["task_id", "created_at"]
    )
    op.create_index(
        "ix_discovery_logs_journal", "journal_discovery_logs", ["journal_id", "created_at"]
    )


def downgrade() -> None:
    if op.get_bind().execute(
        sa.text("SELECT created_by FROM discovery_tasks WHERE created_by IS NULL LIMIT 1")
    ).first() is not None:
        raise RuntimeError("存在无创建用户的识别任务，无法恢复 created_by 非空约束")
    op.drop_table("journal_discovery_logs")
    op.drop_table("journal_source_snapshots")
    op.drop_table("journal_submission_portals")
    op.alter_column(
        "discovery_tasks",
        "created_by",
        existing_type=sa.CHAR(36),
        nullable=False,
    )
    op.drop_index("ix_discovery_available", table_name="discovery_tasks")
    for column in (
        "cancel_requested",
        "retryable",
        "available_at",
        "lease_expires_at",
        "worker_id",
        "stage",
    ):
        op.drop_column("discovery_tasks", column)
