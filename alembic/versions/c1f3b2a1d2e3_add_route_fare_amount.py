"""add route fare amount

Revision ID: c1f3b2a1d2e3
Revises: f6f2cdffbcdc
Create Date: 2026-01-22
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c1f3b2a1d2e3'
down_revision = 'f6f2cdffbcdc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'routes',
        sa.Column('fare_amount', sa.Numeric(12, 2), nullable=True, comment="Yo'l haqi (so'm)")
    )


def downgrade() -> None:
    op.drop_column('routes', 'fare_amount')
