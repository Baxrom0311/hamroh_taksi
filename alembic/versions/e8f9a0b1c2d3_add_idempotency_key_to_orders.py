"""add idempotency_key to orders

Revision ID: e8f9a0b1c2d3
Revises: cd6e8f923b20
Create Date: 2026-01-21 22:12:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'cd6e8f923b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add idempotency_key column to orders table
    
    This column prevents duplicate order creation from concurrent button clicks.
    """
    # Add idempotency_key column
    op.add_column('orders', sa.Column(
        'idempotency_key',
        sa.String(length=255),
        nullable=True,
        comment='Idempotency key to prevent duplicates'
    ))
    
    # Add unique constraint
    op.create_unique_constraint(
        'uq_orders_idempotency_key',
        'orders',
        ['idempotency_key']
    )
    
    # Add index for faster lookups
    op.create_index(
        'idx_orders_idempotency_key',
        'orders',
        ['idempotency_key'],
        unique=False
    )


def downgrade() -> None:
    """Remove idempotency_key column and related constraints"""
    op.drop_index('idx_orders_idempotency_key', table_name='orders')
    op.drop_constraint('uq_orders_idempotency_key', 'orders', type_='unique')
    op.drop_column('orders', 'idempotency_key')
