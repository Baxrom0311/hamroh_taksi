"""Update max available seats constraint to 6

Revision ID: 9b7c1d2e3f4a
Revises: c1f3b2a1d2e3
Create Date: 2026-01-27
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "9b7c1d2e3f4a"
down_revision = "c1f3b2a1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clamp existing data to new max
    op.execute("UPDATE drivers SET available_seats = 6 WHERE available_seats > 6")

    # Drop old constraint and add new one
    op.drop_constraint("check_seats_range", "drivers", type_="check")
    op.create_check_constraint(
        "check_seats_range",
        "drivers",
        "available_seats >= 0 AND available_seats <= 6",
    )


def downgrade() -> None:
    # Clamp existing data to old max
    op.execute("UPDATE drivers SET available_seats = 8 WHERE available_seats > 8")

    # Revert constraint back to 8
    op.drop_constraint("check_seats_range", "drivers", type_="check")
    op.create_check_constraint(
        "check_seats_range",
        "drivers",
        "available_seats >= 0 AND available_seats <= 8",
    )
