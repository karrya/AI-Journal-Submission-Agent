"""Add extended manuscript metadata fields.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manuscripts", sa.Column("funding_number", sa.VARCHAR(255), nullable=True))
    op.add_column("manuscripts", sa.Column("funding_name", sa.VARCHAR(255), nullable=True))
    op.add_column("manuscripts", sa.Column("publication_statement", sa.TEXT(), nullable=True))
    op.add_column("manuscripts", sa.Column("acknowledgements", sa.TEXT(), nullable=True))
    op.add_column("manuscripts", sa.Column("author_contributions", sa.TEXT(), nullable=True))
    op.add_column("manuscripts", sa.Column("clinical_trial_number", sa.VARCHAR(255), nullable=True))


def downgrade() -> None:
    op.drop_column("manuscripts", "clinical_trial_number")
    op.drop_column("manuscripts", "author_contributions")
    op.drop_column("manuscripts", "acknowledgements")
    op.drop_column("manuscripts", "publication_statement")
    op.drop_column("manuscripts", "funding_name")
    op.drop_column("manuscripts", "funding_number")
