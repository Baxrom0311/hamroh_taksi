"""merge heads before orders update

Revision ID: 849610523d16
Revises: a45ea8e740a3, fix_passenger_count_constraint
Create Date: 2026-01-13 16:55:22.453782

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '849610523d16'
down_revision: Union[str, None] = ('a45ea8e740a3', 'fix_passenger_count_constraint')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
