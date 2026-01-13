"""fix_passenger_count_constraint_for_luggage

Revision ID: fix_passenger_count_constraint
Revises: 45ac19888cb1
Create Date: 2026-01-13 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fix_passenger_count_constraint'
down_revision: Union[str, None] = '45ac19888cb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eski constraint ni o'chirish
    op.drop_constraint('check_passenger_count', 'orders', type_='check')
    
    # Yangi constraint ni qo'shish - pochta uchun passenger_count=0 ga ruxsat beradi
    # PostgreSQL sintaksisi: boolean qiymatlar TRUE/FALSE yoki true/false
    op.create_check_constraint(
        'check_passenger_count',
        'orders',
        sa.text("(has_luggage = TRUE AND passenger_count = 0) OR (has_luggage = FALSE AND passenger_count >= 1 AND passenger_count <= 4)")
    )


def downgrade() -> None:
    # Yangi constraint ni o'chirish
    op.drop_constraint('check_passenger_count', 'orders', type_='check')
    
    # Eski constraint ni qaytarish
    op.create_check_constraint(
        'check_passenger_count',
        'orders',
        sa.text('passenger_count >= 1 AND passenger_count <= 4')
    )
