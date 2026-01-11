"""add_system_settings_and_driver_ban_tables

Revision ID: 45ac19888cb1
Revises: d0de3df238a3
Create Date: 2026-01-11 23:06:45.329435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45ac19888cb1'
down_revision: Union[str, None] = 'd0de3df238a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================
    # SYSTEM SETTINGS TABLE
    # ============================================
    op.create_table('system_settings',
        sa.Column('setting_key', sa.String(length=100), nullable=False, comment='Sozlama kaliti (unique)'),
        sa.Column('setting_value', sa.Text(), nullable=False, comment='Sozlama qiymati (JSON yoki text)'),
        sa.Column('description', sa.Text(), nullable=True, comment='Sozlama tavsifi'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('setting_key')
    )
    op.create_index('idx_settings_key', 'system_settings', ['setting_key'], unique=False)
    
    # ============================================
    # DRIVER BAN RECORDS TABLE
    # ============================================
    op.create_table('driver_ban_records',
        sa.Column('ban_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('driver_id', sa.BigInteger(), nullable=False, comment='Haydovchi ID'),
        sa.Column('passenger_id', sa.BigInteger(), nullable=False, comment="Yo'lovchi ID (ban tashlagan)"),
        sa.Column('order_id', sa.Integer(), nullable=True, comment='Buyurtma ID (qaysi safar uchun)'),
        sa.Column('reason', sa.Text(), nullable=True, comment="Ban sababi (yo'lovchi yozgan)"),
        sa.Column('reviewed_by_admin', sa.Boolean(), nullable=False, server_default='false', comment='Admin ko\'rib chiqdimi?'),
        sa.Column('admin_id', sa.BigInteger(), nullable=True, comment='Admin ID (ko\'rib chiqqan)'),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True, comment='Ko\'rib chiqilgan vaqt'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['admin_id'], ['users.user_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['driver_id'], ['drivers.driver_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.order_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['passenger_id'], ['passengers.passenger_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('ban_id')
    )
    op.create_index('idx_ban_driver_created', 'driver_ban_records', ['driver_id', 'created_at'], unique=False)
    op.create_index('idx_ban_reviewed', 'driver_ban_records', ['reviewed_by_admin'], unique=False)
    op.create_index(op.f('ix_driver_ban_records_admin_id'), 'driver_ban_records', ['admin_id'], unique=False)
    op.create_index(op.f('ix_driver_ban_records_driver_id'), 'driver_ban_records', ['driver_id'], unique=False)
    op.create_index(op.f('ix_driver_ban_records_order_id'), 'driver_ban_records', ['order_id'], unique=False)
    op.create_index(op.f('ix_driver_ban_records_passenger_id'), 'driver_ban_records', ['passenger_id'], unique=False)
    op.create_index(op.f('ix_driver_ban_records_created_at'), 'driver_ban_records', ['created_at'], unique=False)


def downgrade() -> None:
    # ============================================
    # DRIVER BAN RECORDS TABLE (Teskari tartib)
    # ============================================
    op.drop_index(op.f('ix_driver_ban_records_created_at'), table_name='driver_ban_records')
    op.drop_index(op.f('ix_driver_ban_records_passenger_id'), table_name='driver_ban_records')
    op.drop_index(op.f('ix_driver_ban_records_order_id'), table_name='driver_ban_records')
    op.drop_index(op.f('ix_driver_ban_records_driver_id'), table_name='driver_ban_records')
    op.drop_index(op.f('ix_driver_ban_records_admin_id'), table_name='driver_ban_records')
    op.drop_index('idx_ban_reviewed', table_name='driver_ban_records')
    op.drop_index('idx_ban_driver_created', table_name='driver_ban_records')
    op.drop_table('driver_ban_records')
    
    # ============================================
    # SYSTEM SETTINGS TABLE
    # ============================================
    op.drop_index('idx_settings_key', table_name='system_settings')
    op.drop_table('system_settings')
