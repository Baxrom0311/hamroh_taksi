"""fix constraints from audit

Revision ID: b1c2d3e4f5g6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-10 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5g6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Fix order check_passenger_count constraint
    op.drop_constraint('check_passenger_count', 'orders', type_='check')
    op.create_check_constraint(
        'check_passenger_count',
        'orders',
        'passenger_count >= 0 AND passenger_count <= 6 AND (passenger_count > 0 OR has_luggage = true)'
    )
    
    # 2. Add trip constraints
    op.create_check_constraint(
        'check_trip_seats_non_negative',
        'trips',
        'available_seats >= 0'
    )
    op.create_check_constraint(
        'check_trip_seats_max',
        'trips',
        'available_seats <= total_seats'
    )
    op.create_check_constraint(
        'check_trip_total_seats',
        'trips',
        'total_seats >= 1 AND total_seats <= 6'
    )


def downgrade() -> None:
    # Revert trip constraints
    op.drop_constraint('check_trip_total_seats', 'trips', type_='check')
    op.drop_constraint('check_trip_seats_max', 'trips', type_='check')
    op.drop_constraint('check_trip_seats_non_negative', 'trips', type_='check')
    
    # Revert order constraint
    op.drop_constraint('check_passenger_count', 'orders', type_='check')
    op.create_check_constraint(
        'check_passenger_count',
        'orders',
        '(has_luggage = true AND passenger_count = 0) OR (has_luggage = false AND passenger_count >= 1 AND passenger_count <= 4)'
    )
