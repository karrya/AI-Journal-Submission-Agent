"""Allow identifier reuse after journal soft deletion.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _duplicate_exists(connection, query: str) -> bool:
    return connection.execute(sa.text(query)).first() is not None


def upgrade() -> None:
    op.drop_constraint("uq_journals_issn", "journals", type_="unique")
    op.drop_constraint("uq_journals_eissn", "journals", type_="unique")
    op.drop_constraint("uq_journal_identifier", "journal_identifiers", type_="unique")
    op.add_column(
        "journals",
        sa.Column(
            "active_issn",
            sa.CHAR(8),
            sa.Computed("CASE WHEN deleted_at IS NULL THEN issn ELSE NULL END", persisted=True),
            nullable=True,
        ),
    )
    op.add_column(
        "journals",
        sa.Column(
            "active_eissn",
            sa.CHAR(8),
            sa.Computed("CASE WHEN deleted_at IS NULL THEN eissn ELSE NULL END", persisted=True),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_journals_active_issn", "journals", ["active_issn"])
    op.create_unique_constraint("uq_journals_active_eissn", "journals", ["active_eissn"])
    op.create_index(
        "ix_identifiers_type_value_journal",
        "journal_identifiers",
        ["identifier_type", "identifier_value", "journal_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for query in (
        "SELECT issn FROM journals WHERE issn IS NOT NULL GROUP BY issn HAVING COUNT(*) > 1 LIMIT 1",
        "SELECT eissn FROM journals WHERE eissn IS NOT NULL GROUP BY eissn HAVING COUNT(*) > 1 LIMIT 1",
        "SELECT identifier_type, identifier_value FROM journal_identifiers "
        "GROUP BY identifier_type, identifier_value HAVING COUNT(*) > 1 LIMIT 1",
    ):
        if _duplicate_exists(connection, query):
            raise RuntimeError("存在历史复用标识，无法自动降级到全局唯一约束")
    op.drop_index("ix_identifiers_type_value_journal", table_name="journal_identifiers")
    op.drop_constraint("uq_journals_active_eissn", "journals", type_="unique")
    op.drop_constraint("uq_journals_active_issn", "journals", type_="unique")
    op.drop_column("journals", "active_eissn")
    op.drop_column("journals", "active_issn")
    op.create_unique_constraint("uq_journals_issn", "journals", ["issn"])
    op.create_unique_constraint("uq_journals_eissn", "journals", ["eissn"])
    op.create_unique_constraint(
        "uq_journal_identifier", "journal_identifiers", ["identifier_type", "identifier_value"]
    )
