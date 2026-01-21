"""
app/models/system_settings.py

SYSTEM SETTINGS MODEL

Bu model tizim sozlamalarini saqlaydi (admin o'zgartira oladi)
"""

from __future__ import annotations
from typing import Optional
from datetime import datetime

from sqlalchemy import (
    String, Text, DateTime, func, Index, select
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base



class SystemSettings(Base):
    """
    System Settings model
    
    BU MODEL NIMA QILADI:
    - Bot sozlamalarini saqlaydi
    - Admin o'zgartira oladi (web panel orqali)
    - Default qiymatlar mavjud
    """
    
    __tablename__ = "system_settings"
    
    # PRIMARY KEY
    setting_key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Sozlama kaliti (unique)"
    )
    
    # QIYMAT
    setting_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Sozlama qiymati (JSON yoki text)"
    )
    
    # TAVSIF
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Sozlama tavsifi"
    )
    
    # TIMESTAMPS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )
    
    # INDEXES
    __table_args__ = (
        Index('idx_settings_key', 'setting_key'),
        {'extend_existing': True}
    )
    
    def to_dict(self) -> dict:
        return {
            'key': self.setting_key,
            'value': self.setting_value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self) -> str:
        return f"<SystemSettings(key='{self.setting_key}', value='{self.setting_value[:50]}...')>"


# ============================================
# HELPER FUNCTIONS
# ============================================

async def get_setting(session, key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Sozlamani olish
    
    ISHLATISH:
        commission = await get_setting(session, 'commission_amount', '5000')
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(SystemSettings).where(SystemSettings.setting_key == key)
    )
    setting = result.scalar_one_or_none()
    
    if setting:
        return setting.setting_value
    return default


async def set_setting(
    session,
    key: str,
    value: str,
    description: Optional[str] = None
) -> SystemSettings:
    """
    Sozlamani o'rnatish yoki yangilash
    
    ISHLATISH:
        await set_setting(session, 'commission_amount', '5000', 'Komissiya miqdori')
        await session.commit()
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(SystemSettings).where(SystemSettings.setting_key == key)
    )
    setting = result.scalar_one_or_none()
    
    if setting:
        # Yangilash
        setting.setting_value = value
        if description:
            setting.description = description
        setting.updated_at = func.now()
    else:
        # Yangi yaratish
        setting = SystemSettings(
            setting_key=key,
            setting_value=value,
            description=description
        )
        session.add(setting)
    
    return setting


async def get_setting_int(session, key: str, default: int = 0) -> int:
    """Sozlamani int sifatida olish"""
    value = await get_setting(session, key)
    if value:
        try:
            return int(value)
        except ValueError:
            return default
    return default


async def get_setting_bool(session, key: str, default: bool = False) -> bool:
    """Sozlamani bool sifatida olish"""
    value = await get_setting(session, key)
    if value:
        return value.lower() in ('true', '1', 'yes', 'on')
    return default


async def get_all_settings(session) -> dict:
    """
    Barcha sozlamalarni olish
    
    Returns:
        dict: {key: value} formatida
    """
    result = await session.execute(select(SystemSettings))
    settings = result.scalars().all()
    
    return {setting.setting_key: setting.setting_value for setting in settings}


async def update_setting(session, key: str, value: str, description: Optional[str] = None) -> SystemSettings:
    """
    Sozlamani yangilash
    
    ISHLATISH:
        await update_setting(session, 'commission_amount', '6000')
        await session.commit()
    """
    from sqlalchemy import update
    
    # Mavjudligini tekshirish
    existing = await get_setting(session, key)
    
    if existing:
        # Yangilash
        await session.execute(
            update(SystemSettings)
            .where(SystemSettings.setting_key == key)
            .values(
                setting_value=value,
                description=description,
                updated_at=func.now()
            )
        )
    else:
        # Yangi yaratish
        new_setting = SystemSettings(
            setting_key=key,
            setting_value=value,
            description=description
        )
        session.add(new_setting)
        return new_setting
    
    # Yangilangan sozlamani qaytarish
    result = await session.execute(
        select(SystemSettings).where(SystemSettings.setting_key == key)
    )
    return result.scalar_one()


# ============================================
# PRICING HELPERS
# ============================================

async def get_pricing_settings(session) -> dict:
    """
    Bot rejimi va komissiya miqdorini olish (DB -> fallback .env)
    
    Returns:
        {
            'bot_is_free': bool,
            'commission_amount': int
        }
    """
    from config.settings import settings as config_settings

    bot_is_free = await get_setting_bool(session, 'bot_is_free', default=True)
    commission_amount = await get_setting_int(
        session,
        'commission_amount',
        default=config_settings.COMMISSION_AMOUNT
    )

    if bot_is_free:
        commission_amount = 0

    return {
        'bot_is_free': bot_is_free,
        'commission_amount': commission_amount
    }


# ============================================
# DEFAULT SETTINGS
# ============================================

DEFAULT_SETTINGS = [
    {
        'key': 'commission_amount',
        'value': '5000',
        'description': 'Har bir safar uchun komissiya (so\'m)'
    },
    {
        'key': 'bot_is_free',
        'value': 'true',
        'description': 'Bot tekin/pullik (true/false)'
    },
    {
        'key': 'ban_percentage_threshold',
        'value': '50',
        'description': 'Ban foizi (50% = haydovchi blok)'
    },
    {
        'key': 'ban_count_threshold',
        'value': '5',
        'description': 'Kunlik ban soni (5 ta = haydovchi blok)'
    },
    {
        'key': 'max_driver_change_per_hour',
        'value': '3',
        'description': 'Mashina o\'zgartirish limiti (1 soatda)'
    },
    {
        'key': 'max_pickup_distance_km',
        'value': '50',
        'description': 'Maksimal masofa (km)'
    },
    {
        'key': 'auto_confirm_delay_seconds',
        'value': '120',
        'description': 'Avtomatik tasdiqlash vaqti (soniya)'
    },
]


async def seed_default_settings(session):
    """
    Default sozlamalarni yaratish
    
    ISHLATISH:
        async with get_session() as session:
            await seed_default_settings(session)
            await session.commit()
    """
    for setting_data in DEFAULT_SETTINGS:
        existing = await get_setting(session, setting_data['key'])
        if not existing:
            await set_setting(
                session,
                key=setting_data['key'],
                value=setting_data['value'],
                description=setting_data['description']
            )
            print(f"✅ Created setting: {setting_data['key']}")
