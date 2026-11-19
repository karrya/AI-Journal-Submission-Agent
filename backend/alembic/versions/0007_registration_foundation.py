"""Add module 3 registration support, accounts, tasks, and confirmations.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME, INTEGER

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
CANONICAL_PUBLISHERS = (
    ("SPRINGER_NATURE", "Springer Nature", "springer nature"),
    ("ELSEVIER", "Elsevier", "elsevier"),
    ("WILEY", "John Wiley & Sons", "john wiley & sons"),
    ("TAYLOR_FRANCIS", "Taylor & Francis", "taylor & francis"),
    ("SAGE", "SAGE Publishing", "sage publishing"),
)


def mutable_columns(
    *, created_by: bool = True, updated_by: bool = False, soft_delete: bool = False
) -> list[sa.Column]:
    columns = [
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
    ]
    if created_by:
        columns.append(
            sa.Column(
                "created_by",
                sa.CHAR(36),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
    if updated_by:
        columns.append(
            sa.Column(
                "updated_by",
                sa.CHAR(36),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
    if soft_delete:
        columns.append(sa.Column("deleted_at", DATETIME(fsp=6), nullable=True))
    return columns


def initialize_registration_support() -> None:
    connection = op.get_bind()
    for publisher_code, display_name, normalized_name in CANONICAL_PUBLISHERS:
        publisher_id = connection.scalar(
            sa.text("SELECT id FROM publishers WHERE normalized_name = :normalized_name"),
            {"normalized_name": normalized_name},
        )
        if publisher_id is None:
            connection.execute(
                sa.text(
                    "INSERT INTO publishers "
                    "(id, name, normalized_name, status, created_at, updated_at) "
                    "VALUES (UUID(), :name, :normalized_name, 'ACTIVE', "
                    "CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))"
                ),
                {"name": display_name, "normalized_name": normalized_name},
            )
            publisher_id = connection.scalar(
                sa.text("SELECT id FROM publishers WHERE normalized_name = :normalized_name"),
                {"normalized_name": normalized_name},
            )
        connection.execute(
            sa.text(
                "INSERT INTO publisher_registration_support "
                "(id, publisher_id, publisher_code, display_name, support_status, "
                "support_level, official_domains, created_at, updated_at) "
                "VALUES (UUID(), :publisher_id, :publisher_code, :display_name, "
                "'SUPPORTED', 'V0_1', NULL, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)) "
                "ON DUPLICATE KEY UPDATE "
                "publisher_id = publisher_registration_support.publisher_id"
            ),
            {
                "publisher_id": publisher_id,
                "publisher_code": publisher_code,
                "display_name": display_name,
            },
        )


def upgrade() -> None:
    op.create_table(
        "publisher_registration_support",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("publisher_id", sa.CHAR(36), nullable=False),
        sa.Column("publisher_code", sa.VARCHAR(64), nullable=False),
        sa.Column("display_name", sa.VARCHAR(255), nullable=False),
        sa.Column("support_status", sa.VARCHAR(32), nullable=False, server_default="SUPPORTED"),
        sa.Column("support_level", sa.VARCHAR(32), nullable=False, server_default="V0_1"),
        sa.Column("official_domains", sa.JSON(), nullable=True),
        sa.Column("notes", sa.TEXT(), nullable=True),
        *mutable_columns(updated_by=True),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("publisher_id", name="uk_publisher_support_id"),
        sa.UniqueConstraint("publisher_code", name="uk_publisher_code"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_publisher_status", "publisher_registration_support", ["support_status"]
    )
    op.create_table(
        "platform_adapters",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("adapter_code", sa.VARCHAR(100), nullable=False),
        sa.Column("adapter_name", sa.VARCHAR(255), nullable=False),
        sa.Column("platform_type", sa.VARCHAR(100), nullable=False),
        sa.Column("adapter_version", sa.VARCHAR(64), nullable=False),
        sa.Column("support_status", sa.VARCHAR(32), nullable=False, server_default="TESTING"),
        sa.Column("allowed_domains", sa.JSON(), nullable=False),
        sa.Column("capability_config", sa.JSON(), nullable=True),
        sa.Column("last_verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("verification_notes", sa.TEXT(), nullable=True),
        *mutable_columns(),
        sa.UniqueConstraint("adapter_code", "adapter_version", name="uk_adapter_version"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_adapter_platform_status",
        "platform_adapters",
        ["platform_type", "support_status"],
    )
    for column in (
        sa.Column("normalized_host", sa.VARCHAR(255), nullable=True),
        sa.Column("platform_adapter_id", sa.CHAR(36), nullable=True),
        sa.Column("support_status", sa.VARCHAR(32), nullable=False, server_default="TESTING"),
        sa.Column("verified_by", sa.CHAR(36), nullable=True),
        sa.Column("verification_evidence_ref", sa.VARCHAR(255), nullable=True),
        sa.Column("last_checked_at", DATETIME(fsp=6), nullable=True),
        sa.Column("disabled_reason", sa.VARCHAR(1000), nullable=True),
    ):
        op.add_column("journal_submission_portals", column)
    op.create_index(
        "idx_portal_status",
        "journal_submission_portals",
        ["support_status", "verification_status"],
    )
    op.create_index(
        "idx_portal_host", "journal_submission_portals", ["normalized_host"]
    )
    op.create_foreign_key(
        "fk_portal_adapter",
        "journal_submission_portals",
        "platform_adapters",
        ["platform_adapter_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_portal_verifier",
        "journal_submission_portals",
        "users",
        ["verified_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "publisher_accounts",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("author_id", sa.CHAR(36), nullable=False),
        sa.Column("publisher_id", sa.CHAR(36), nullable=False),
        sa.Column("journal_id", sa.CHAR(36), nullable=True),
        sa.Column("platform_code", sa.VARCHAR(64), nullable=False),
        sa.Column("account_namespace", sa.VARCHAR(255), nullable=False),
        sa.Column("account_email", sa.VARCHAR(255), nullable=False),
        sa.Column("normalized_email", sa.VARCHAR(255), nullable=False),
        sa.Column("platform_account_id", sa.VARCHAR(255), nullable=True),
        sa.Column("username", sa.VARCHAR(255), nullable=True),
        sa.Column("credential_ref", sa.VARCHAR(255), nullable=True),
        sa.Column("account_status", sa.VARCHAR(32), nullable=False, server_default="PENDING"),
        sa.Column("email_verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("registered_at", DATETIME(fsp=6), nullable=True),
        sa.Column("last_checked_at", DATETIME(fsp=6), nullable=True),
        sa.Column(
            "active_account_email",
            sa.VARCHAR(255),
            sa.Computed("IF(deleted_at IS NULL, normalized_email, NULL)", persisted=True),
            nullable=True,
        ),
        *mutable_columns(soft_delete=True),
        sa.ForeignKeyConstraint(["author_id"], ["authors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "platform_code",
            "account_namespace",
            "active_account_email",
            name="uk_platform_account",
        ),
        **TABLE_OPTIONS,
    )
    for name, columns in (
        ("idx_account_author", ["author_id"]),
        ("idx_account_publisher", ["publisher_id"]),
        ("idx_account_journal", ["journal_id"]),
        ("idx_account_status", ["account_status"]),
    ):
        op.create_index(name, "publisher_accounts", columns)
    op.create_table(
        "registration_tasks",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("account_id", sa.CHAR(36), nullable=True),
        sa.Column("author_id", sa.CHAR(36), nullable=False),
        sa.Column("publisher_id", sa.CHAR(36), nullable=False),
        sa.Column("journal_id", sa.CHAR(36), nullable=True),
        sa.Column("authorization_id", sa.CHAR(36), nullable=False),
        sa.Column("platform_code", sa.VARCHAR(64), nullable=False),
        sa.Column("registration_url", sa.TEXT(), nullable=False),
        sa.Column("adapter_code", sa.VARCHAR(64), nullable=True),
        sa.Column("adapter_version", sa.VARCHAR(32), nullable=True),
        sa.Column("task_status", sa.VARCHAR(40), nullable=False, server_default="PENDING"),
        sa.Column("current_step", sa.VARCHAR(100), nullable=True),
        sa.Column("retry_count", INTEGER(unsigned=True), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.VARCHAR(64), nullable=True),
        sa.Column("lease_expires_at", DATETIME(fsp=6), nullable=True),
        sa.Column("available_at", DATETIME(fsp=6), nullable=True),
        sa.Column("last_heartbeat_at", DATETIME(fsp=6), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_external_action", sa.VARCHAR(100), nullable=True),
        sa.Column("external_evidence_ref", sa.VARCHAR(255), nullable=True),
        sa.Column("browser_handoff_id", sa.VARCHAR(64), nullable=True),
        sa.Column("idempotency_key", sa.VARCHAR(128), nullable=False),
        sa.Column("error_code", sa.VARCHAR(64), nullable=True),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.Column("started_at", DATETIME(fsp=6), nullable=True),
        sa.Column("last_activity_at", DATETIME(fsp=6), nullable=True),
        sa.Column("completed_at", DATETIME(fsp=6), nullable=True),
        *mutable_columns(),
        sa.ForeignKeyConstraint(["account_id"], ["publisher_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["authors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["authorization_id"], ["author_authorizations.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("idempotency_key", name="uk_registration_idempotency"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_registration_author_status",
        "registration_tasks",
        ["author_id", "task_status"],
    )
    op.create_index("idx_registration_account", "registration_tasks", ["account_id"])
    op.create_index("idx_registration_created", "registration_tasks", ["created_at"])
    op.create_table(
        "email_verification_records",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("account_id", sa.CHAR(36), nullable=False),
        sa.Column("task_id", sa.CHAR(36), nullable=False),
        sa.Column("email_address", sa.VARCHAR(255), nullable=False),
        sa.Column("email_message_id", sa.VARCHAR(255), nullable=True),
        sa.Column("sender_address", sa.VARCHAR(255), nullable=True),
        sa.Column("subject", sa.VARCHAR(500), nullable=True),
        sa.Column("received_at", DATETIME(fsp=6), nullable=True),
        sa.Column("link_domain", sa.VARCHAR(255), nullable=True),
        sa.Column("verification_ref", sa.VARCHAR(255), nullable=True),
        sa.Column(
            "verification_status", sa.VARCHAR(32), nullable=False, server_default="PENDING"
        ),
        sa.Column("confirmed_by", sa.CHAR(36), nullable=True),
        sa.Column("confirmed_at", DATETIME(fsp=6), nullable=True),
        sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("expires_at", DATETIME(fsp=6), nullable=True),
        *mutable_columns(created_by=False),
        sa.ForeignKeyConstraint(["account_id"], ["publisher_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["registration_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("task_id", "email_message_id", name="uk_task_message"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_verification_account", "email_verification_records", ["account_id"]
    )
    op.create_index(
        "idx_verification_status", "email_verification_records", ["verification_status"]
    )
    op.create_table(
        "registration_confirmations",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("task_id", sa.CHAR(36), nullable=False),
        sa.Column("action_type", sa.VARCHAR(64), nullable=False),
        sa.Column("summary_hash", sa.CHAR(64), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("requested_by", sa.CHAR(36), nullable=False),
        sa.Column("expires_at", DATETIME(fsp=6), nullable=False),
        sa.Column("consumed_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["registration_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("token_hash", name="uk_confirmation_token"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_confirmation_task",
        "registration_confirmations",
        ["task_id", "action_type", "created_at"],
    )
    initialize_registration_support()


def downgrade() -> None:
    op.drop_table("registration_confirmations")
    op.drop_table("email_verification_records")
    op.drop_table("registration_tasks")
    op.drop_table("publisher_accounts")
    op.drop_constraint(
        "fk_portal_verifier", "journal_submission_portals", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_portal_adapter", "journal_submission_portals", type_="foreignkey"
    )
    op.drop_index("idx_portal_host", table_name="journal_submission_portals")
    op.drop_index("idx_portal_status", table_name="journal_submission_portals")
    for column in (
        "disabled_reason",
        "last_checked_at",
        "verification_evidence_ref",
        "verified_by",
        "support_status",
        "platform_adapter_id",
        "normalized_host",
    ):
        op.drop_column("journal_submission_portals", column)
    op.drop_table("platform_adapters")
    op.drop_table("publisher_registration_support")
