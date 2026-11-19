"""Prevent conflicting registration tasks for one author and portal.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_BLOCKING_SCOPE_EXPRESSION = (
    "CASE WHEN task_status NOT IN ('CANCELLED', 'FAILED', 'EXPIRED') "
    "OR last_external_action IS NOT NULL THEN 'BLOCKED' ELSE NULL END"
)


def upgrade() -> None:
    connection = op.get_bind()
    conflict = connection.execute(
        sa.text(
            "SELECT author_id, portal_id FROM registration_tasks "
            "WHERE task_status NOT IN ('CANCELLED', 'FAILED', 'EXPIRED') "
            "OR last_external_action IS NOT NULL "
            "GROUP BY author_id, portal_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if conflict is not None:
        raise ValueError(
            "Existing conflicting registration tasks must be reconciled before 0008"
        )
    op.add_column(
        "registration_tasks",
        sa.Column(
            "blocking_scope",
            sa.VARCHAR(7),
            sa.Computed(_BLOCKING_SCOPE_EXPRESSION, persisted=True),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uk_registration_blocking_scope",
        "registration_tasks",
        ["author_id", "portal_id", "blocking_scope"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uk_registration_blocking_scope", "registration_tasks", type_="unique"
    )
    op.drop_column("registration_tasks", "blocking_scope")
