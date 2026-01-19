"""add_balance_check_constraints

Revision ID: bc5f7e892a10
Revises: perf_indexes_001
Create Date: 2026-01-19 17:26:00

CRITICAL FIX:
- Driver balance negative bo'lishini oldini olish
- CHECK constraint qo'shish
- Existing data validation

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc5f7e892a10'
down_revision = 'perf_indexes_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade: Balance CHECK constraint qo'shish
    
    NIMA BO'LADI:
    1. Existing data validation (negative balance'lar tekshiriladi)
    2. CHECK constraint qo'shiladi
    3. Agar negative balance bo'lsa, 0 ga o'zgartiriladi
    """
    
    # 1. Existing negative balance'larni tekshirish va tuzatish
    op.execute("""
        UPDATE drivers 
        SET balance = 0 
        WHERE balance < 0;
    """)
    
    # 2. CHECK constraint qo'shish
    # Yangi balance manfiy bo'lolmaydi
    op.create_check_constraint(
        'check_driver_balance_positive',
        'drivers',
        'balance >= 0'
    )
    
    # 3. Available seats ham manfiy bo'lolmasligi kerak
    op.execute("""
        UPDATE drivers 
        SET available_seats = 0 
        WHERE available_seats < 0;
    """)
    
    op.create_check_constraint(
        'check_driver_available_seats_positive',
        'drivers',
        'available_seats >= 0'
    )
    
    # 4. Passenger balance ham (agar bor bo'lsa)
    # Yo'lovchilar ham to'lov qilishlari mumkin (prepaid system)
    # Hozircha comment, lekin kelajakda kerak bo'lishi mumkin
    # op.create_check_constraint(
    #     'check_passenger_balance_positive',
    #     'passengers',
    #     'balance >= 0'
    # )


def downgrade() -> None:
    """
    Downgrade: CHECK constraint'larni o'chirish
    """
    op.drop_constraint('check_driver_balance_positive', 'drivers', type_='check')
    op.drop_constraint('check_driver_available_seats_positive', 'drivers', type_='check')
    
    # If passenger balance constraint was added:
    # op.drop_constraint('check_passenger_balance_positive', 'passengers', type_='check')
