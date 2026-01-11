"""
app/models/driver_ban.py

DRIVER BAN RECORDS MODEL

Yo'lovchilar haydovchini ban qilganda yoziladi
"""

from sqlalchemy import (
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

from app.core.database import Base


class DriverBanRecord(Base):
    """
    Driver Ban Record model
    
    BU MODEL NIMA QILADI:
    - Yo'lovchi haydovchini ban qilganda yoziladi
    - Admin ko'rib chiqadi
    - 50% yoki 5 ta ban = haydovchi blok
    """
    
    __tablename__ = "driver_ban_records"
    
    # PRIMARY KEY
    ban_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    
    # FOREIGN KEYS
    driver_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("drivers.driver_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Haydovchi ID"
    )
    
    passenger_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("passengers.passenger_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Yo'lovchi ID (ban tashlagan)"
    )
    
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("orders.order_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Buyurtma ID (qaysi safar uchun)"
    )
    
    # BAN SABABI
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Ban sababi (yo'lovchi yozgan)"
    )
    
    # ADMIN KO'RIB CHIQISHI
    reviewed_by_admin: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Admin ko'rib chiqdimi?"
    )
    
    admin_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin ID (ko'rib chiqqan)"
    )
    
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Ko'rib chiqilgan vaqt"
    )
    
    # TIMESTAMPS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    # RELATIONSHIPS
    driver: Mapped["Driver"] = relationship("Driver")
    passenger: Mapped["Passenger"] = relationship("Passenger")
    order: Mapped[Optional["Order"]] = relationship("Order")
    admin: Mapped[Optional["User"]] = relationship("User")
    
    # INDEXES
    __table_args__ = (
        Index('idx_ban_driver_created', 'driver_id', 'created_at'),
        Index('idx_ban_reviewed', 'reviewed_by_admin'),
    )
    
    def to_dict(self) -> dict:
        return {
            'ban_id': self.ban_id,
            'driver_id': self.driver_id,
            'passenger_id': self.passenger_id,
            'order_id': self.order_id,
            'reason': self.reason,
            'reviewed_by_admin': self.reviewed_by_admin,
            'created_at': self.created_at.isoformat()
        }


# ============================================
# HELPER FUNCTIONS
# ============================================

async def create_ban_record(
    session,
    driver_id: int,
    passenger_id: int,
    order_id: Optional[int] = None,
    reason: Optional[str] = None
) -> DriverBanRecord:
    """
    Yangi ban record yaratish
    
    ISHLATISH:
        ban = await create_ban_record(
            session,
            driver_id=1,
            passenger_id=2,
            order_id=123,
            reason="Narx ortiqcha oldi"
        )
        await session.commit()
    """
    ban = DriverBanRecord(
        driver_id=driver_id,
        passenger_id=passenger_id,
        order_id=order_id,
        reason=reason
    )
    
    session.add(ban)
    return ban


async def check_driver_should_be_blocked(
    session,
    driver_id: int
) -> dict:
    """
    Haydovchi bloklanishi kerakmi tekshirish
    
    QOIDALAR:
    - 50% yoki undan ko'p ban = blok
    - Kunlik 5 ta yoki undan ko'p ban = blok
    
    Returns:
        {
            'should_block': bool,
            'reason': str,
            'ban_percentage': float,
            'today_ban_count': int,
            'total_ban_count': int,
            'total_orders': int
        }
    """
    from sqlalchemy import select, func
    from datetime import datetime, timedelta
    from app.models.order import Order, OrderStatus
    from app.models.system_settings import get_setting_int
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0)
    
    # 1. Bugungi ban soni
    today_bans_result = await session.execute(
        select(func.count(DriverBanRecord.ban_id))
        .where(DriverBanRecord.driver_id == driver_id)
        .where(DriverBanRecord.created_at >= today_start)
    )
    today_ban_count = today_bans_result.scalar() or 0
    
    # 2. Jami ban soni
    total_bans_result = await session.execute(
        select(func.count(DriverBanRecord.ban_id))
        .where(DriverBanRecord.driver_id == driver_id)
    )
    total_ban_count = total_bans_result.scalar() or 0
    
    # 3. Jami safarlar soni
    total_orders_result = await session.execute(
        select(func.count(Order.order_id))
        .where(Order.driver_id == driver_id)
        .where(Order.status == OrderStatus.COMPLETED)
    )
    total_orders = total_orders_result.scalar() or 0
    
    # 4. Ban foizi
    ban_percentage = 0.0
    if total_orders > 0:
        ban_percentage = (total_ban_count / total_orders) * 100
    
    # 5. Sozlamalarni olish
    ban_percentage_threshold = await get_setting_int(session, 'ban_percentage_threshold', 50)
    ban_count_threshold = await get_setting_int(session, 'ban_count_threshold', 5)
    
    # 6. Bloklanishi kerakmi?
    should_block = False
    reason = None
    
    if today_ban_count >= ban_count_threshold:
        should_block = True
        reason = f"Kunlik ban limiti yetdi ({today_ban_count}/{ban_count_threshold})"
    
    if ban_percentage >= ban_percentage_threshold and total_orders >= 10:
        should_block = True
        reason = f"Ban foizi yuqori ({ban_percentage:.1f}%/{ban_percentage_threshold}%)"
    
    return {
        'should_block': should_block,
        'reason': reason,
        'ban_percentage': ban_percentage,
        'today_ban_count': today_ban_count,
        'total_ban_count': total_ban_count,
        'total_orders': total_orders,
        'ban_percentage_threshold': ban_percentage_threshold,
        'ban_count_threshold': ban_count_threshold
    }
