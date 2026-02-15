"""Add is_priority to drivers

Revision ID: a1b2c3d4e5f6
Revises: 9b7c1d2e3f4a
Create Date: 2026-02-15 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '4c2a1b0d9e7f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_priority column with default value false
    op.add_column('drivers', sa.Column('is_priority', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # Create index for performance
    op.create_index(op.f('ix_drivers_is_priority'), 'drivers', ['is_priority'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_drivers_is_priority'), table_name='drivers')
    op.drop_column('drivers', 'is_priority')
