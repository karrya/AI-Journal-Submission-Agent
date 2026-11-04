"""Create identity and author tables.

Revision ID: 0001
Revises:
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001"
down_revision = None
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


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("username", sa.VARCHAR(64), nullable=False),
        sa.Column("normalized_username", sa.VARCHAR(64), nullable=False),
        sa.Column("display_name", sa.VARCHAR(128), nullable=False),
        sa.Column("password_hash", sa.VARCHAR(255), nullable=False),
        sa.Column("status", sa.VARCHAR(32), nullable=False),
        sa.Column("must_change_password", sa.Boolean, nullable=False),
        sa.Column("last_login_at", mysql.DATETIME(fsp=6), nullable=True),
        *mutable_columns(soft_delete=True),
        sa.UniqueConstraint("normalized_username", name="uq_users_normalized_username"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "roles",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("code", sa.VARCHAR(64), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("description", sa.VARCHAR(500), nullable=False),
        *mutable_columns(),
        sa.UniqueConstraint("code", name="uq_roles_code"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.CHAR(36),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "assigned_by",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("csrf_token_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "user_id",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("idle_expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("absolute_expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_auth_sessions_user_revoked",
        "auth_sessions",
        ["user_id", "revoked_at"],
    )
    op.create_index(
        "ix_auth_sessions_absolute_expires",
        "auth_sessions",
        ["absolute_expires_at"],
    )

    op.create_table(
        "authors",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("given_name", sa.VARCHAR(128), nullable=True),
        sa.Column("middle_name", sa.VARCHAR(128), nullable=True),
        sa.Column("family_name", sa.VARCHAR(128), nullable=True),
        sa.Column("display_name", sa.VARCHAR(255), nullable=False),
        sa.Column("alternate_names", sa.JSON, nullable=False),
        sa.Column("orcid", sa.CHAR(19), nullable=True),
        sa.Column("phone_country_code", sa.VARCHAR(16), nullable=True),
        sa.Column("phone_number", sa.VARCHAR(32), nullable=True),
        sa.Column("status", sa.VARCHAR(32), nullable=False),
        sa.Column("notes", sa.TEXT, nullable=True),
        *mutable_columns(soft_delete=True),
        sa.UniqueConstraint("orcid", name="uq_authors_orcid"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "author_emails",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "author_id",
            sa.CHAR(36),
            sa.ForeignKey("authors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.VARCHAR(254), nullable=False),
        sa.Column("normalized_email", sa.VARCHAR(254), nullable=False),
        sa.Column("purpose", sa.VARCHAR(32), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False),
        sa.Column("verification_status", sa.VARCHAR(32), nullable=False),
        sa.Column("authorization_status", sa.VARCHAR(32), nullable=False),
        sa.Column(
            "active_primary_author_id",
            sa.CHAR(36),
            sa.Computed(
                "IF(is_primary = 1 AND deleted_at IS NULL, author_id, NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
        *mutable_columns(soft_delete=True),
        sa.UniqueConstraint(
            "author_id",
            "normalized_email",
            name="uq_author_emails_author_normalized",
        ),
        sa.UniqueConstraint(
            "active_primary_author_id",
            name="uq_author_emails_active_primary_author",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_author_emails_normalized", "author_emails", ["normalized_email"]
    )

    op.create_table(
        "institutions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("normalized_name", sa.VARCHAR(255), nullable=False),
        sa.Column("institution_type", sa.VARCHAR(32), nullable=True),
        sa.Column("website_url", sa.VARCHAR(1024), nullable=True),
        sa.Column("address_line1", sa.VARCHAR(255), nullable=True),
        sa.Column("address_line2", sa.VARCHAR(255), nullable=True),
        sa.Column("city", sa.VARCHAR(128), nullable=True),
        sa.Column("region", sa.VARCHAR(128), nullable=True),
        sa.Column("postal_code", sa.VARCHAR(32), nullable=True),
        sa.Column("country_code", sa.CHAR(2), nullable=True),
        *mutable_columns(soft_delete=True),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_institutions_normalized_location",
        "institutions",
        ["normalized_name", "country_code", "city"],
    )

    op.create_table(
        "author_institutions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "author_id",
            sa.CHAR(36),
            sa.ForeignKey("authors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.CHAR(36),
            sa.ForeignKey("institutions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("department", sa.VARCHAR(255), nullable=True),
        sa.Column("position_title", sa.VARCHAR(255), nullable=True),
        sa.Column("valid_from", sa.DATE, nullable=True),
        sa.Column("valid_to", sa.DATE, nullable=True),
        sa.Column("is_current", sa.Boolean, nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False),
        *mutable_columns(soft_delete=True),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="valid_date_order",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_author_institutions_author_order",
        "author_institutions",
        ["author_id", "display_order"],
    )
    op.create_index(
        "ix_author_institutions_institution",
        "author_institutions",
        ["institution_id"],
    )

    op.create_table(
        "author_authorizations",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "author_id",
            sa.CHAR(36),
            sa.ForeignKey("authors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("permissions", sa.JSON, nullable=False),
        sa.Column("valid_from", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("valid_to", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("evidence_ref", sa.VARCHAR(1024), nullable=True),
        sa.Column("notes", sa.TEXT, nullable=True),
        sa.Column(
            "reviewed_by",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("reviewed_at", mysql.DATETIME(fsp=6), nullable=True),
        *mutable_columns(),
        sa.CheckConstraint(
            "valid_to > valid_from",
            name="finite_validity_order",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_author_authorizations_author_user",
        "author_authorizations",
        ["author_id", "user_id"],
    )
    op.create_index(
        "ix_author_authorizations_validity",
        "author_authorizations",
        ["valid_from", "valid_to"],
    )
    op.create_index(
        "ix_author_authorizations_revoked",
        "author_authorizations",
        ["revoked_at"],
    )


def downgrade() -> None:
    for table in (
        "author_authorizations",
        "author_institutions",
        "institutions",
        "author_emails",
        "authors",
        "auth_sessions",
        "user_roles",
        "roles",
        "users",
    ):
        op.drop_table(table)
