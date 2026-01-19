"""add_idempotency_constraints

Revision ID: cd6e8f923b20
Revises: bc5f7e892a10
Create Date: 2026-01-19 17:38:00

IDEMPOTENCY FIX:
- Duplicate order prevention (concurrent button clicks)
- Partial unique index: faqat PENDING orders uchun
- Passenger bir vaqtda faqat 1 ta PENDING order bo'lishi mumkin

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cd6e8f923b20'
down_revision = 'bc5f7e892a10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade: Idempotency uchun partial unique constraint
    
    NIMA BO'LADI:
    1. Passenger bir vaqtda faqat 1 ta PENDING order qo'yishi mumkin
    2. ACCEPTED/IN_PROGRESS/COMPLETED orders'ga ta'sir yo'q
    3. Concurrent button clicks duplicate order yaratmaydi
    """
    
    # PostgreSQL Partial Unique Index
    # Faqat PENDING holatdagi orderlar uchun unique constraint
    op.execute("""
        CREATE UNIQUE INDEX idx_unique_pending_order_per_passenger
        ON orders (passenger_id)
        WHERE status = 'pending';
    """)
    
    # Alternative: Agar multiple PENDING bo'lishi kerak bo'lsa (per route)
    # op.execute("""
    #     CREATE UNIQUE INDEX idx_unique_pending_order_per_route_passenger
    #     ON orders (passenger_id, route_id)
    #     WHERE status = 'pending';
    # """)


def downgrade() -> None:
    """
    Downgrade: Index'ni o'chirish
    """
    op.execute("DROP INDEX IF EXISTS idx_unique_pending_order_per_passenger;")
    
    # If route-based index:
    # op.execute("DROP INDEX IF EXISTS idx_unique_pending_order_per_route_passenger;")
