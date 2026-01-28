"""Add password_hash to users

Revision ID: 4c2a1b0d9e7f
Revises: 9b7c1d2e3f4a
Create Date: 2026-01-27
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "4c2a1b0d9e7f"
down_revision = "9b7c1d2e3f4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
