"""
app/models/order.py

ORDER (BUYURTMA) MODEL - ENG MUHIM!

Bu model yo'lovchi va haydovchini bog'laydi
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from datetime import datetime
import enum

from sqlalchemy import (
    Integer, BigInteger, Text, Numeric, Boolean, String, DateTime,
    ForeignKey, CheckConstraint, Index, Enum as SQLEnum, func,
    select, update
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from app.core.database import Base

if TYPE_CHECKING:
    from .passenger import Passenger
    from .driver import Driver
    from .route import Route
    from .trip import Trip


# ============================================
# ENUM
# ============================================

class OrderStatus(str, enum.Enum):
    """
    Buyurtma holati
    
    LIFECYCLE:
    pending → accepted → in_progress → completed
                      ↘ cancelled
    """
    PENDING = "pending"              # Kutilmoqda (haydovchi topilmagan)
    ACCEPTED = "accepted"            # Haydovchi qabul qildi
    IN_PROGRESS = "in_progress"      # Safar davom etmoqda
    COMPLETED = "completed"          # Yakunlandi
    CANCELLED = "cancelled"          # Bekor qilindi


# ============================================
# ORDER MODEL
# ============================================

class Order(Base):
    """
    Order (Buyurtma) model
    
    BU MODEL NIMA QILADI:
    - Yo'lovchi buyurtma beradi → PENDING
    - Haydovchi qabul qiladi → ACCEPTED
    - Safar boshlandi → IN_PROGRESS
    - Safar yakunlandi → COMPLETED
    """
    
    __tablename__ = "orders"
    
    # ============================================
    # PRIMARY KEY
    # ============================================
    
    order_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Buyurtma ID"
    )
    
    # ============================================
    # FOREIGN KEYS
    # ============================================
    
    passenger_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("passengers.passenger_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Yo'lovchi ID"
    )
    
    driver_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("drivers.driver_id", ondelete="SET NULL"),
        nullable=True,  # NULL = hali haydovchi topilmagan
        index=True,
        comment="Haydovchi ID (NULL = topilmagan)"
    )
    
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.route_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Marshrut ID"
    )
    
    trip_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trips.trip_id", ondelete="SET NULL"),
        nullable=True,  # NULL = hali trip'ga qo'shilmagan
        index=True,
        comment="Trip ID (NULL = trip yo'q)"
    )
    
    # ============================================
    # PICKUP LOCATION (Qayerdan olish)
    # ============================================
    
    pickup_location: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Olish joyi (matn)"
    )
    
    # ✅ CRITICAL FIX: Made nullable to support text-only addresses
    pickup_lat: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 8),
        nullable=True,  # ✅ Changed from False - text-only addresses have no GPS
        comment="Olish joyi - Latitude (None for text-only)"
    )
    
    pickup_lon: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(11, 8),
        nullable=True,  # ✅ Changed from False - text-only addresses have no GPS
        comment="Olish joyi - Longitude (None for text-only)"
    )
    
    # ============================================
    # BUYURTMA DETALLARI
    # ============================================
    
    passenger_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Yo'lovchilar soni"
    )
    
    has_luggage: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Pochta bor/yo'q"
    )
    
    luggage_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Pochta soni"
    )
    
    luggage_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Pochta tavsifi"
    )
    
    # ============================================
    # STATUS
    # ============================================
    
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, name="order_status"),
        default=OrderStatus.PENDING,
        nullable=False,
        index=True,
        comment="Buyurtma holati"
    )
    
    # ============================================
    # TO'LOV
    # ============================================
    
    commission_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Komissiya miqdori (so'm)"
    )
    
    # ============================================
    # TIMESTAMPS (Muhim!)
    # ============================================
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="Buyurtma berilgan vaqt"
    )
    
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Haydovchi qabul qilgan vaqt"
    )
    
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Safar boshlangan vaqt"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Safar yakunlangan vaqt"
    )
    
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Bekor qilingan vaqt"
    )
    
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Bekor qilish sababi"
    )

    # ============================================
    # IDEMPOTENCY
    # ============================================
    
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
        comment="Idempotency key to prevent duplicates"
    )
    
    # ============================================
    # ADDITIONAL FLAGS
    # ============================================
    
    auto_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Avtomatik tasdiqlangan (2 daqiqadan keyin)"
    )
    
    driver_arrived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Haydovchi yetib keldi"
    )
    
    # ============================================
    # PROPERTIES & HELPERS
    # ============================================

    @property
    def type_text(self) -> str:
        """Buyurtma turi matni (👥 3 kishi yoki 📦 Pochta)"""
        if self.passenger_count == 0 and self.has_luggage:
            text = "📦 Pochta"
            if (self.luggage_count or 0) > 1:
                text += f" ({self.luggage_count} dona)"
            if getattr(self, 'luggage_description', None):
                text += f"\n 📝 {self.luggage_description}"
            return text
        
        elif self.has_luggage and self.passenger_count > 0:
            text = f"👥 {self.passenger_count} kishi"
            if (self.luggage_count or 0) > 0:
                text += f" + 📦 Pochta ({self.luggage_count} dona)"
                if getattr(self, 'luggage_description', None):
                    text += f"\n 📝 {self.luggage_description}"
            return text
        
        return f"👥 {self.passenger_count} kishi"

    
    # ============================================
    # RELATIONSHIPS
    # ============================================
    
    passenger: Mapped["Passenger"] = relationship(
        "Passenger",
        back_populates="orders",
        foreign_keys=[passenger_id]
    )

    driver: Mapped[Optional["Driver"]] = relationship(
        "Driver",
        back_populates="orders",
        foreign_keys=[driver_id]
    )

    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="orders"
    )
    
    trip: Mapped[Optional["Trip"]] = relationship(
        "Trip",
        back_populates="orders",
        foreign_keys=[trip_id]
    )
    
    # ============================================
    # INDEXES
    # ============================================
    
    __table_args__ = (
        # Composite indexes (tez qidiruv)
        Index('idx_orders_status_created', 'status', 'created_at'),
        Index('idx_orders_driver_status', 'driver_id', 'status'),
        Index('idx_orders_passenger_status', 'passenger_id', 'status'),
        Index('idx_orders_route_status', 'route_id', 'status'),
        
        # Check constraints
        # Pochta uchun passenger_count=0 bo'lishi mumkin, yo'lovchi uchun 1-4 orasida
        CheckConstraint(
            '(has_luggage = true AND passenger_count = 0) OR (has_luggage = false AND passenger_count >= 1 AND passenger_count <= 4)',
            name='check_passenger_count'
        ),
        CheckConstraint('luggage_count >= 0', name='check_luggage_count'),
        
        {'extend_existing': True}
    )
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def is_pending(self) -> bool:
        """Kutilmoqda (haydovchi topilmagan)"""
        return self.status == OrderStatus.PENDING
    
    @property
    def is_accepted(self) -> bool:
        """Haydovchi qabul qildi"""
        return self.status == OrderStatus.ACCEPTED
    
    @property
    def is_in_progress(self) -> bool:
        """Safar davom etmoqda"""
        return self.status == OrderStatus.IN_PROGRESS
    
    @property
    def is_completed(self) -> bool:
        """Yakunlandi"""
        return self.status == OrderStatus.COMPLETED
    
    @property
    def is_cancelled(self) -> bool:
        """Bekor qilindi"""
        return self.status == OrderStatus.CANCELLED
    
    @property
    def is_active(self) -> bool:
        """
        Aktiv buyurtma (ACCEPTED yoki IN_PROGRESS)
        
        ✅ CODE QUALITY: Replaces duplicate checks like:
            if order.status in [OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]
        
        With cleaner:
            if order.is_active
        """
        return self.status in (OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS)
    
    @property
    def duration_minutes(self) -> Optional[int]:
        """Safar davomiyligi (daqiqa)"""
        if self.completed_at and self.started_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() / 60)
        return None
    
    def to_dict(self) -> dict:
        """Dictionary'ga aylantirish"""
        return {
            'order_id': self.order_id,
            'passenger_id': self.passenger_id,
            'driver_id': self.driver_id,
            'route_id': self.route_id,
            'pickup_location': self.pickup_location,
            'pickup_lat': float(self.pickup_lat) if self.pickup_lat is not None else None,
            'pickup_lon': float(self.pickup_lon) if self.pickup_lon is not None else None,
            'passenger_count': self.passenger_count,
            'has_luggage': self.has_luggage,
            'status': self.status.value,
            'commission_amount': float(self.commission_amount) if self.commission_amount else None,
            'created_at': self.created_at.isoformat(),
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
    
    def __repr__(self) -> str:
        return (
            f"<Order(id={self.order_id}, "
            f"status={self.status.value}, "
            f"driver_id={self.driver_id})>"
        )


# ============================================
# HELPER FUNCTIONS
# ============================================
from sqlalchemy import select
from sqlalchemy.orm import selectinload

async def get_order_by_id(
    session,
    order_id: int
) -> Optional[Order]:
    stmt = (
        select(Order)
        .execution_options(populate_existing=True)  # Force refresh even if instance is cached
        .options(selectinload(Order.passenger))
        .where(Order.order_id == order_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_order(
    session,
    passenger_id: int,
    route_id: int,
    pickup_location: str,
    pickup_lat: Optional[float],  # ✅ FIXED: Optional for text-only
    pickup_lon: Optional[float],  # ✅ FIXED: Optional for text-only
    passenger_count: int = 1,
    **kwargs
) -> Order:
    """
    Yangi buyurtma yaratish
    
    ISHLATISH:
        order = await create_order(
            session,
            passenger_id=1,
            route_id=1,
            pickup_location="Gurlan bozori yonida",
            pickup_lat=41.311512,
            pickup_lon=69.249512,
            passenger_count=2,
            has_luggage=True
        )
        await session.commit()
    """
    order = Order(
        passenger_id=passenger_id,
        route_id=route_id,
        pickup_location=pickup_location,
        pickup_lat=pickup_lat,
        pickup_lon=pickup_lon,
        passenger_count=passenger_count,
        **kwargs
    )
    
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order


async def accept_order(
    session,
    order_id: int,
    driver_id: int,
    commission_amount: Decimal
) -> Order:
    """
    Buyurtmani qabul qilish
    
    STATUS: pending → accepted
    """
    from sqlalchemy import update
    
    await session.execute(
        update(Order)
        .where(Order.order_id == order_id)
        .where(Order.status == OrderStatus.PENDING)  # Faqat pending bo'lsa
        .values(
            driver_id=driver_id,
            status=OrderStatus.ACCEPTED,
            commission_amount=commission_amount,
            accepted_at=func.now()
        )
    )
    
    return await get_order_by_id(session, order_id)


async def start_order(session, order_id: int):
    """
    Safar boshlash
    
    STATUS: accepted → in_progress
    """
    from sqlalchemy import update
    
    await session.execute(
        update(Order)
        .where(Order.order_id == order_id)
        .where(Order.status == OrderStatus.ACCEPTED)
        .values(
            status=OrderStatus.IN_PROGRESS,
            started_at=func.now()
        )
    )


async def complete_order(session, order_id: int):
    """
    Safar yakunlash
    
    STATUS: in_progress → completed
    """
    from sqlalchemy import update
    
    await session.execute(
        update(Order)
        .where(Order.order_id == order_id)
        .where(Order.status == OrderStatus.IN_PROGRESS)
        .values(
            status=OrderStatus.COMPLETED,
            completed_at=func.now()
        )
    )


async def cancel_order(
    session,
    order_id: int,
    reason: Optional[str] = None
):
    """
    Buyurtmani bekor qilish
    
    STATUS: any → cancelled
    """
    from sqlalchemy import update
    
    await session.execute(
        update(Order)
        .where(Order.order_id == order_id)
        .values(
            status=OrderStatus.CANCELLED,
            cancellation_reason=reason,
            cancelled_at=func.now()
        )
    )


async def get_pending_orders_for_route(
    session,
    route_id: int
) -> list[Order]:
    """
    Marshrut bo'yicha kutayotgan buyurtmalar
    
    ISHLATISH:
        # Gurlan→Vazir marshrutidagi barcha buyurtmalar
        orders = await get_pending_orders_for_route(session, route_id=1)
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(Order)
        .where(Order.route_id == route_id)
        .where(Order.status == OrderStatus.PENDING)
        .order_by(Order.created_at)  # Eng eski birinchi (FIFO)
    )
    
    return result.scalars().all()


async def get_driver_active_orders(
    session,
    driver_id: int
) -> list[Order]:
    """
    Haydovchining aktiv buyurtmalari
    
    ✅ CODE QUALITY: Uses SQL WHERE for performance
    After fetching, can use order.is_active property in Python
    
    ISHLATISH:
        orders = await get_driver_active_orders(session, driver_id=1)
        # Python tarafda: active = [o for o in all_orders if o.is_active]
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(Order)
        .where(Order.driver_id == driver_id)
        .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))  # is_active equivalent
        .order_by(Order.created_at)
    )
    
    return result.scalars().all()
