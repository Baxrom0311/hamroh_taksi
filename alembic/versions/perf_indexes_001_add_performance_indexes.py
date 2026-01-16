"""add_performance_indexes

Revision ID: perf_indexes_001
Revises: 4879ee18dbf7
Create Date: 2026-01-16 12:15:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'perf_indexes_001'
down_revision: Union[str, None] = '4879ee18dbf7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Performance indexes qo'shish
    
    MAQSAD:
    - Driver location search tezlashtirish (PostGIS)
    - Order trip_id bo'yicha qidirish
    - Transaction logs sorting
    """
    
    # 1. Driver location index (PostGIS) - Active va blocked bo'lmaganlar
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_drivers_location_active
        ON drivers USING GIST (location)
        WHERE is_active = true AND is_blocked = false;
    """)
    
    # 2. Orders trip_id index - Trip bo'yicha orderlarni topish
    op.create_index(
        'idx_orders_trip_id_composite',
        'orders',
        ['trip_id', 'status'],
        unique=False,
        postgresql_where=sa.text('trip_id IS NOT NULL')
    )
    
    # 3. Transaction logs - Created DESC (yangilar birinchi)
    op.create_index(
        'idx_transaction_logs_created_desc',
        'transaction_logs',
        [sa.text('created_at DESC')]
    )
    
    # 4. Orders - Route + Status + Created (queue optimization)
    op.create_index(
        'idx_orders_route_status_created',
        'orders',
        ['route_id', 'status', 'created_at']
    )
    
    # 5. Drivers - Route + Available Seats (queue optimization)
    op.create_index(
        'idx_drivers_route_seats_active',
        'drivers',
        ['current_route_id', 'available_seats', 'is_active'],
        postgresql_where=sa.text('is_blocked = false')
    )


def downgrade() -> None:
    """
    Performance indexes o'chirish
    """
    op.execute("DROP INDEX IF EXISTS idx_drivers_location_active;")
    op.drop_index('idx_orders_trip_id_composite', table_name='orders')
    op.drop_index('idx_transaction_logs_created_desc', table_name='transaction_logs')
    op.drop_index('idx_orders_route_status_created', table_name='orders')
    op.drop_index('idx_drivers_route_seats_active', table_name='drivers')
