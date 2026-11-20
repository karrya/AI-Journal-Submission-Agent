"""Allow publisher name reuse after soft deletion.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_publishers_normalized_name", "publishers", type_="unique"
    )
    op.add_column(
        "publishers",
        sa.Column(
            "active_normalized_name",
            sa.VARCHAR(255),
            sa.Computed(
                "IF(deleted_at IS NULL, normalized_name, NULL)", persisted=True
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_publishers_active_normalized_name",
        "publishers",
        ["active_normalized_name"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            "SELECT normalized_name FROM publishers "
            "GROUP BY normalized_name HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError("存在历史复用出版社名称，无法恢复全局唯一约束")
    op.drop_constraint(
        "uq_publishers_active_normalized_name", "publishers", type_="unique"
    )
    op.drop_column("publishers", "active_normalized_name")
    op.create_unique_constraint(
        "uq_publishers_normalized_name", "publishers", ["normalized_name"]
    )
