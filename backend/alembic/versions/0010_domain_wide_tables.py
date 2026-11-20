"""Consolidate catalogs into domain rows and remove unused registration tables.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
DROPPED_TABLES = {
    "publisher_registration_support",
    "publisher_aliases",
    "journal_aliases",
    "journal_identifiers",
    "journal_platforms",
    "platform_adapters",
    "publisher_accounts",
    "email_verification_records",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _scalar(connection, sql: str) -> int:
    return int(connection.scalar(sa.text(sql)) or 0)


def _validate_legacy_data(connection) -> None:
    _require(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM platform_adapters a WHERE NOT EXISTS ("
            "SELECT 1 FROM journal_submission_portals p WHERE p.platform_adapter_id = a.id)",
        )
        == 0,
        "存在未关联投稿入口的适配器，无法无损内联；请先人工核查",
    )
    _require(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM platform_adapters a "
            "JOIN journal_submission_portals p ON p.platform_adapter_id = a.id "
            "WHERE a.platform_type <> p.platform_code",
        )
        == 0,
        "适配器平台类型与投稿入口不一致，停止迁移以保持准入语义",
    )
    _require(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM publisher_registration_support s "
            "JOIN publishers p ON p.id = s.publisher_id WHERE s.display_name <> p.name",
        )
        == 0,
        "publisher_registration_support.display_name 与出版社名称不一致，停止迁移",
    )
    for table in ("publisher_accounts", "email_verification_records", "journal_platforms"):
        _require(
            _scalar(connection, f"SELECT COUNT(*) FROM {table}") == 0,
            f"{table} 已产生数据，不能按空功能表删除；请先人工核查",
        )
    _require(
        _scalar(connection, "SELECT COUNT(*) FROM journals WHERE platform_id IS NOT NULL") == 0,
        "journals.platform_id 存在引用，不能直接删除平台目录",
    )
    _require(
        _scalar(
            connection, "SELECT COUNT(*) FROM registration_tasks WHERE account_id IS NOT NULL"
        )
        == 0,
        "注册任务仍关联出版社账号，不能删除账号目录",
    )
    _require(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM journal_identifiers ji "
            "JOIN journals j ON j.id = ji.journal_id "
            "WHERE NOT ((ji.identifier_type = 'ISSN' AND ji.identifier_value = j.issn) "
            "OR (ji.identifier_type = 'EISSN' AND ji.identifier_value = j.eissn))",
        )
        == 0,
        "journal_identifiers 存在期刊宽表之外的标识，停止迁移以避免数据丢失",
    )
    _require(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM journal_identifiers ji "
            "JOIN journals j ON j.id = ji.journal_id "
            "WHERE (ji.source_url IS NOT NULL AND NOT (ji.source_url <=> j.source_url)) "
            "OR (ji.verified_at IS NOT NULL AND NOT (ji.verified_at <=> j.verified_at))",
        )
        == 0,
        "journal_identifiers 存在独立证据元数据，停止迁移以避免数据丢失",
    )


def _add_wide_columns() -> None:
    op.add_column("publishers", sa.Column("aliases", sa.JSON(), nullable=True))
    for column in (
        sa.Column("registration_code", sa.VARCHAR(64), nullable=True),
        sa.Column("registration_support_status", sa.VARCHAR(32), nullable=True),
        sa.Column("registration_support_level", sa.VARCHAR(32), nullable=True),
        sa.Column("registration_official_domains", sa.JSON(), nullable=True),
        sa.Column("registration_notes", sa.TEXT(), nullable=True),
        sa.Column("registration_updated_by", sa.CHAR(36), nullable=True),
    ):
        op.add_column("publishers", column)
    op.create_unique_constraint(
        "uq_publishers_registration_code", "publishers", ["registration_code"]
    )
    op.create_index(
        "ix_publishers_registration_status", "publishers", ["registration_support_status"]
    )
    op.create_foreign_key(
        "fk_publishers_registration_updated_by_users",
        "publishers",
        "users",
        ["registration_updated_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column("journals", sa.Column("platform_code", sa.VARCHAR(64), nullable=True))
    op.add_column("journals", sa.Column("aliases", sa.JSON(), nullable=True))
    op.drop_constraint(
        "fk_journals_platform_id_journal_platforms", "journals", type_="foreignkey"
    )
    op.drop_index("ix_journals_platform", table_name="journals")
    op.create_index("ix_journals_platform", "journals", ["platform_code"])

    for column in (
        sa.Column("adapter_code", sa.VARCHAR(100), nullable=True),
        sa.Column("adapter_name", sa.VARCHAR(255), nullable=True),
        sa.Column("adapter_version", sa.VARCHAR(64), nullable=True),
        sa.Column("adapter_support_status", sa.VARCHAR(32), nullable=True),
        sa.Column("adapter_allowed_domains", sa.JSON(), nullable=True),
        sa.Column("adapter_capability_config", sa.JSON(), nullable=True),
        sa.Column("adapter_last_verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("adapter_verification_notes", sa.TEXT(), nullable=True),
    ):
        op.add_column("journal_submission_portals", column)


def _copy_legacy_data(connection) -> None:
    connection.execute(
        sa.text(
            "UPDATE publishers p JOIN publisher_registration_support s "
            "ON s.publisher_id = p.id SET "
            "p.registration_code = s.publisher_code, "
            "p.registration_support_status = s.support_status, "
            "p.registration_support_level = s.support_level, "
            "p.registration_official_domains = s.official_domains, "
            "p.registration_notes = s.notes, "
            "p.registration_updated_by = s.updated_by"
        )
    )
    for table, parent_table, parent_id in (
        ("publisher_aliases", "publishers", "publisher_id"),
        ("journal_aliases", "journals", "journal_id"),
    ):
        connection.execute(
            sa.text(
                f"UPDATE {parent_table} p SET aliases = COALESCE(("
                f"SELECT JSON_ARRAYAGG(JSON_OBJECT("
                f"'alias', a.alias, 'normalized_alias', a.normalized_alias, "
                f"'source_url', a.source_url, 'verified_at', a.verified_at)) "
                f"FROM {table} a WHERE a.{parent_id} = p.id), JSON_ARRAY())"
            )
        )
    connection.execute(
        sa.text(
            "UPDATE journal_submission_portals p "
            "LEFT JOIN platform_adapters a ON a.id = p.platform_adapter_id SET "
            "p.adapter_code = a.adapter_code, p.adapter_name = a.adapter_name, "
            "p.adapter_version = a.adapter_version, "
            "p.adapter_support_status = a.support_status, "
            "p.adapter_allowed_domains = a.allowed_domains, "
            "p.adapter_capability_config = a.capability_config, "
            "p.adapter_last_verified_at = a.last_verified_at, "
            "p.adapter_verification_notes = a.verification_notes"
        )
    )


def _validate_copied_data(connection) -> None:
    _require(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM publisher_registration_support s "
            "JOIN publishers p ON p.id = s.publisher_id "
            "WHERE NOT (p.registration_code <=> s.publisher_code) "
            "OR NOT (p.registration_support_status <=> s.support_status) "
            "OR NOT (p.registration_support_level <=> s.support_level) "
            "OR NOT (p.registration_official_domains <=> s.official_domains) "
            "OR NOT (p.registration_notes <=> s.notes) "
            "OR NOT (p.registration_updated_by <=> s.updated_by)",
        )
        == 0,
        "出版社注册支持复制校验失败，原表尚未删除",
    )
    for table, parent_table, parent_id in (
        ("publisher_aliases", "publishers", "publisher_id"),
        ("journal_aliases", "journals", "journal_id"),
    ):
        _require(
            _scalar(
                connection,
                f"SELECT COUNT(*) FROM {table} a JOIN {parent_table} p "
                f"ON p.id = a.{parent_id} "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM JSON_TABLE(p.aliases, '$[*]' COLUMNS ("
                "normalized_alias VARCHAR(500) PATH '$.normalized_alias')) jt "
                "WHERE jt.normalized_alias = a.normalized_alias)",
            )
            == 0,
            f"{table} 别名复制校验失败，原表尚未删除",
        )
    _require(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM platform_adapters a "
            "JOIN journal_submission_portals p ON p.platform_adapter_id = a.id "
            "WHERE NOT (p.adapter_code <=> a.adapter_code) "
            "OR NOT (p.adapter_name <=> a.adapter_name) "
            "OR NOT (p.adapter_version <=> a.adapter_version) "
            "OR NOT (p.adapter_support_status <=> a.support_status) "
            "OR NOT (p.adapter_allowed_domains <=> a.allowed_domains) "
            "OR NOT (p.adapter_capability_config <=> a.capability_config) "
            "OR NOT (p.adapter_last_verified_at <=> a.last_verified_at) "
            "OR NOT (p.adapter_verification_notes <=> a.verification_notes)",
        )
        == 0,
        "平台适配器复制校验失败，原表尚未删除",
    )


def _drop_legacy_structures() -> None:
    op.alter_column("publishers", "aliases", existing_type=sa.JSON(), nullable=False)
    op.alter_column("journals", "aliases", existing_type=sa.JSON(), nullable=False)
    op.drop_constraint(
        "fk_registration_tasks_account_id_publisher_accounts",
        "registration_tasks",
        type_="foreignkey",
    )
    op.drop_index("idx_registration_account", table_name="registration_tasks")
    op.drop_column("registration_tasks", "account_id")
    op.drop_constraint("fk_portal_adapter", "journal_submission_portals", type_="foreignkey")
    op.drop_column("journal_submission_portals", "platform_adapter_id")
    op.drop_column("journals", "platform_id")
    for table in (
        "email_verification_records",
        "publisher_accounts",
        "publisher_registration_support",
        "publisher_aliases",
        "journal_aliases",
        "journal_identifiers",
        "platform_adapters",
        "journal_platforms",
    ):
        op.drop_table(table)


def upgrade() -> None:
    connection = op.get_bind()
    _validate_legacy_data(connection)
    _add_wide_columns()
    _copy_legacy_data(connection)
    _validate_copied_data(connection)
    _drop_legacy_structures()


def _mutable_columns(*, updated_by: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        sa.Column(
            "created_by",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    ]
    if updated_by:
        columns.append(
            sa.Column(
                "updated_by",
                sa.CHAR(36),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
    return columns


def _recreate_legacy_tables() -> None:
    op.create_table(
        "publisher_registration_support",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("publisher_id", sa.CHAR(36), nullable=False),
        sa.Column("publisher_code", sa.VARCHAR(64), nullable=False),
        sa.Column("display_name", sa.VARCHAR(255), nullable=False),
        sa.Column("support_status", sa.VARCHAR(32), nullable=False),
        sa.Column("support_level", sa.VARCHAR(32), nullable=False),
        sa.Column("official_domains", sa.JSON(), nullable=True),
        sa.Column("notes", sa.TEXT(), nullable=True),
        *_mutable_columns(updated_by=True),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("publisher_id", name="uk_publisher_support_id"),
        sa.UniqueConstraint("publisher_code", name="uk_publisher_code"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_publisher_status", "publisher_registration_support", ["support_status"]
    )
    op.create_table(
        "journal_platforms",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("code", sa.VARCHAR(64), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("status", sa.VARCHAR(32), nullable=False),
        *_mutable_columns(),
        sa.Column("deleted_at", DATETIME(fsp=6), nullable=True),
        sa.UniqueConstraint("code", name="uq_journal_platforms_code"),
        **TABLE_OPTIONS,
    )
    op.create_table(
        "platform_adapters",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("adapter_code", sa.VARCHAR(100), nullable=False),
        sa.Column("adapter_name", sa.VARCHAR(255), nullable=False),
        sa.Column("platform_type", sa.VARCHAR(100), nullable=False),
        sa.Column("adapter_version", sa.VARCHAR(64), nullable=False),
        sa.Column("support_status", sa.VARCHAR(32), nullable=False),
        sa.Column("allowed_domains", sa.JSON(), nullable=False),
        sa.Column("capability_config", sa.JSON(), nullable=True),
        sa.Column("last_verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("verification_notes", sa.TEXT(), nullable=True),
        *_mutable_columns(),
        sa.UniqueConstraint("adapter_code", "adapter_version", name="uk_adapter_version"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_adapter_platform_status", "platform_adapters", ["platform_type", "support_status"]
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
        sa.Column("account_status", sa.VARCHAR(32), nullable=False),
        sa.Column("email_verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("registered_at", DATETIME(fsp=6), nullable=True),
        sa.Column("last_checked_at", DATETIME(fsp=6), nullable=True),
        sa.Column(
            "active_account_email",
            sa.VARCHAR(255),
            sa.Computed("IF(deleted_at IS NULL, normalized_email, NULL)", persisted=True),
            nullable=True,
        ),
        *_mutable_columns(),
        sa.Column("deleted_at", DATETIME(fsp=6), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["authors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "platform_code", "account_namespace", "active_account_email", name="uk_platform_account"
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
    for table, parent_table, parent_id, unique_name in (
        ("publisher_aliases", "publishers", "publisher_id", "uq_publisher_alias"),
        ("journal_aliases", "journals", "journal_id", "uq_journal_alias"),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.CHAR(36), primary_key=True),
            sa.Column(parent_id, sa.CHAR(36), nullable=False),
            sa.Column("alias", sa.VARCHAR(500), nullable=False),
            sa.Column("normalized_alias", sa.VARCHAR(500), nullable=False),
            sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
            sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
            sa.Column("created_at", DATETIME(fsp=6), nullable=False),
            sa.ForeignKeyConstraint([parent_id], [f"{parent_table}.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint(parent_id, "normalized_alias", name=unique_name),
            **TABLE_OPTIONS,
        )
        op.create_index(f"ix_{table[:-1]}_normalized", table, ["normalized_alias"])
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
        **TABLE_OPTIONS,
    )
    op.create_index("ix_journal_identifiers_journal", "journal_identifiers", ["journal_id"])
    op.create_index(
        "ix_identifiers_type_value_journal",
        "journal_identifiers",
        ["identifier_type", "identifier_value", "journal_id"],
    )
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
        sa.Column("verification_status", sa.VARCHAR(32), nullable=False),
        sa.Column("confirmed_by", sa.CHAR(36), nullable=True),
        sa.Column("confirmed_at", DATETIME(fsp=6), nullable=True),
        sa.Column("verified_at", DATETIME(fsp=6), nullable=True),
        sa.Column("expires_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["publisher_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["registration_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("task_id", "email_message_id", name="uk_task_message"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_verification_account", "email_verification_records", ["account_id"])
    op.create_index(
        "idx_verification_status", "email_verification_records", ["verification_status"]
    )


def _restore_legacy_data(connection) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO publisher_registration_support "
            "(id, publisher_id, publisher_code, display_name, support_status, support_level, "
            "official_domains, notes, created_at, updated_at, created_by, updated_by) "
            "SELECT UUID(), id, registration_code, name, registration_support_status, "
            "registration_support_level, registration_official_domains, registration_notes, "
            "created_at, updated_at, created_by, registration_updated_by FROM publishers "
            "WHERE registration_code IS NOT NULL"
        )
    )
    for table, parent_table, parent_id in (
        ("publisher_aliases", "publishers", "publisher_id"),
        ("journal_aliases", "journals", "journal_id"),
    ):
        connection.execute(
            sa.text(
                f"INSERT INTO {table} "
                f"(id, {parent_id}, alias, normalized_alias, source_url, verified_at, created_at) "
                f"SELECT UUID(), p.id, jt.alias, jt.normalized_alias, jt.source_url, "
                f"jt.verified_at, p.created_at FROM {parent_table} p "
                "JOIN JSON_TABLE(p.aliases, '$[*]' COLUMNS ("
                "alias VARCHAR(500) PATH '$.alias', "
                "normalized_alias VARCHAR(500) PATH '$.normalized_alias', "
                "source_url VARCHAR(2048) PATH '$.source_url', "
                "verified_at DATETIME PATH '$.verified_at')) jt"
            )
        )
    connection.execute(
        sa.text(
            "INSERT INTO journal_identifiers "
            "(id, journal_id, identifier_type, identifier_value, source_url, verified_at, created_at) "
            "SELECT UUID(), id, 'ISSN', issn, source_url, verified_at, created_at "
            "FROM journals WHERE issn IS NOT NULL"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO journal_identifiers "
            "(id, journal_id, identifier_type, identifier_value, source_url, verified_at, created_at) "
            "SELECT UUID(), id, 'EISSN', eissn, source_url, verified_at, created_at "
            "FROM journals WHERE eissn IS NOT NULL"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO platform_adapters "
            "(id, adapter_code, adapter_name, platform_type, adapter_version, support_status, "
            "allowed_domains, capability_config, last_verified_at, verification_notes, "
            "created_at, updated_at, created_by) "
            "SELECT UUID(), adapter_code, adapter_name, platform_code, adapter_version, "
            "adapter_support_status, adapter_allowed_domains, adapter_capability_config, "
            "adapter_last_verified_at, adapter_verification_notes, "
            "MIN(created_at), MAX(updated_at), MIN(created_by) "
            "FROM journal_submission_portals WHERE adapter_code IS NOT NULL "
            "GROUP BY adapter_code, adapter_name, platform_code, adapter_version, "
            "adapter_support_status, adapter_allowed_domains, adapter_capability_config, "
            "adapter_last_verified_at, adapter_verification_notes"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE journal_submission_portals p JOIN platform_adapters a "
            "ON a.adapter_code = p.adapter_code AND a.adapter_version = p.adapter_version "
            "AND a.platform_type = p.platform_code SET p.platform_adapter_id = a.id"
        )
    )


def downgrade() -> None:
    _recreate_legacy_tables()
    op.add_column("registration_tasks", sa.Column("account_id", sa.CHAR(36), nullable=True))
    op.create_foreign_key(
        "fk_registration_tasks_account_id_publisher_accounts",
        "registration_tasks",
        "publisher_accounts",
        ["account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("idx_registration_account", "registration_tasks", ["account_id"])
    op.add_column(
        "journal_submission_portals", sa.Column("platform_adapter_id", sa.CHAR(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_portal_adapter",
        "journal_submission_portals",
        "platform_adapters",
        ["platform_adapter_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("journals", sa.Column("platform_id", sa.CHAR(36), nullable=True))
    op.create_foreign_key(
        "fk_journals_platform_id_journal_platforms",
        "journals",
        "journal_platforms",
        ["platform_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    _restore_legacy_data(op.get_bind())

    op.drop_constraint(
        "fk_publishers_registration_updated_by_users", "publishers", type_="foreignkey"
    )
    op.drop_constraint("uq_publishers_registration_code", "publishers", type_="unique")
    op.drop_index("ix_publishers_registration_status", table_name="publishers")
    for column in (
        "registration_updated_by",
        "registration_notes",
        "registration_official_domains",
        "registration_support_level",
        "registration_support_status",
        "registration_code",
        "aliases",
    ):
        op.drop_column("publishers", column)
    op.drop_index("ix_journals_platform", table_name="journals")
    op.create_index("ix_journals_platform", "journals", ["platform_id"])
    op.drop_column("journals", "aliases")
    op.drop_column("journals", "platform_code")
    for column in (
        "adapter_verification_notes",
        "adapter_last_verified_at",
        "adapter_capability_config",
        "adapter_allowed_domains",
        "adapter_support_status",
        "adapter_version",
        "adapter_name",
        "adapter_code",
    ):
        op.drop_column("journal_submission_portals", column)
