"""
app/models/trip.py

TRIP (SAFAR) MODEL

Trip - Haydovchining bir safardagi barcha buyurtmalari

LIFECYCLE:
active → completed / cancelled

EXAMPLE:
Driver Gurlan → Vazir yo'nalishida:
- Trip #1 boshladi  
- Order #5 qabul qildi (2 kishi)
- Order #8 qabul qildi (1 kishi)
- Trip yakunlandi (jami 3 kishi)
"""

from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal
from datetime import datetime
import enum

from sqlalchemy import (
    Integer, BigInteger, ForeignKey, Enum as SQLEnum, DateTime, Numeric,
    Index, func, select, update
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from app.core.database import Base


if TYPE_CHECKING:
    from app.models.driver import Driver
    from app.models.route import Route
    from app.models.order import Order


# ============================================
# ENUM
# ============================================

class TripStatus(str, enum.Enum):
    """
    Trip holati
    
    LIFECYCLE:
    active → completed
          → cancelled
    """
    ACTIVE = "active"          # Aktiv - buyurtmalar qabul qilinmoqda yoki trip davom etmoqda
    COMPLETED = "completed"     # Yakunlandi - barcha order'lar completed
    CANCELLED = "cancelled"     # Bekor qilindi


# ============================================
# TRIP MODEL
# ============================================

class Trip(Base):
    """
    Trip - Haydovchining bir safardagi barcha buyurtmalari
    
    VAZIFASI:
    - Bir necha order'larni guruhlash
    - Driver qaysi yo'lovchilarni olib borayotganini bilishi
    - Statistika uchun trip-level data
    """
    
    __tablename__ = "trips"
    
    # PRIMARY KEY
    trip_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Trip ID"
    )
    
    # FOREIGN KEYS
    driver_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("drivers.driver_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Haydovchi ID"
    )
    
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.route_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Marshrut ID"
    )
    
    # STATUS
    status: Mapped[TripStatus] = mapped_column(
        SQLEnum(TripStatus, name="trip_status"),
        default=TripStatus.ACTIVE,
        nullable=False,
        index=True,
        comment="Trip holati"
    )
    
    # BO'SH JOYLAR
    total_seats: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Jami o'rindiqlar (mashina sig'imi)"
    )
    
    available_seats: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Bo'sh o'rindiqlar"
    )
    
    # TIMESTAMPS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Trip yaratilgan vaqt"
    )
    
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Safar boshlangan vaqt (yo'lga chiqqan)"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Trip yakunlangan vaqt"
    )
    
    # LOCATION (ixtiyoriy - real-time tracking uchun)
    current_lat: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 8),
        nullable=True,
        comment="Joriy lat (GPS tracking)"
    )
    
    current_lon: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(11, 8),
        nullable=True,
        comment="Joriy lon (GPS tracking)"
    )
    
    last_location_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Oxirgi location update vaqti"
    )
    
    # RELATIONSHIPS
    driver: Mapped["Driver"] = relationship(
        "Driver",
        back_populates="trips"
    )
    
    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="trips"
    )
    
    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="trip",
        foreign_keys="Order.trip_id"
    )
    
    # INDEXES
    __table_args__ = (
        Index('idx_trips_driver_status', 'driver_id', 'status'),
        Index('idx_trips_route_status', 'route_id', 'status'),
        Index('idx_trips_created', 'created_at'),
    )
    
    # PROPERTIES
    @property
    def is_active(self) -> bool:
        """Aktiv trip"""
        return self.status == TripStatus.ACTIVE
    
    @property
    def is_completed(self) -> bool:
        """Yakunlangan"""
        return self.status == TripStatus.COMPLETED
    
    @property
    def passenger_count(self) -> int:
        """Jami yo'lovchilar soni (band qilingan o'rindiqlar)"""
        return self.total_seats - self.available_seats
    
    @property
    def duration_minutes(self) -> Optional[int]:
        """Trip davomiyligi (daqiqa)"""
        if self.completed_at and self.started_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() / 60)
        return None
    
    def to_dict(self) -> dict:
        """Dictionary'ga aylantirish"""
        return {
            'trip_id': self.trip_id,
            'driver_id': self.driver_id,
            'route_id': self.route_id,
            'status': self.status.value,
            'total_seats': self.total_seats,
            'available_seats': self.available_seats,
            'passenger_count': self.passenger_count,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
    
    def __repr__(self) -> str:
        return (
            f"<Trip(id={self.trip_id}, "
            f"status={self.status.value}, "
            f"driver_id={self.driver_id}, "
            f"seats={self.available_seats}/{self.total_seats})>"
        )


# ============================================
# HELPER FUNCTIONS
# ============================================

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload


async def create_trip(
    session,
    driver_id: int,
    route_id: int,
    total_seats: int
) -> Trip:
    """
    Yangi trip yaratish
    
    QACHON:
    - Haydovchi birinchi order'ni qabul qilganda
    
    ISHLATISH:
        trip = await create_trip(
            session,
            driver_id=1,
            route_id=1,
            total_seats=4
        )
        await session.commit()
    """
    trip = Trip(
        driver_id=driver_id,
        route_id=route_id,
        total_seats=total_seats,
        available_seats=total_seats,  # Hozircha barcha bo'sh
        status=TripStatus.ACTIVE
    )
    
    session.add(trip)
    await session.flush()  # ID olish uchun
    return trip


async def get_trip_by_id(
    session,
    trip_id: int
) -> Optional[Trip]:
    """Trip'ni ID bo'yicha olish"""
    stmt = (
        select(Trip)
        .options(
            selectinload(Trip.driver),
            selectinload(Trip.route),
            selectinload(Trip.orders)
        )
        .where(Trip.trip_id == trip_id)
    )
    
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_trip_by_driver(
    session,
    driver_id: int
) -> Optional[Trip]:
    """
    Haydovchining aktiv trip'ini olish
    
    QACHON:
    - Yangi order qabul qilishda (trip topish yoki yaratish)
    - Yo'lovchi bilan bog'lanishda (faqat shu trip'dagi order'lar)
    
    ISHLATISH:
        trip = await get_active_trip_by_driver(session, driver_id=1)
        if trip:
            # Trip mavjud - order'ni qo'shish
        else:
            # Yangi trip yaratish
    """
    stmt = (
        select(Trip)
        .options(selectinload(Trip.orders))
        .where(Trip.driver_id == driver_id)
        .where(Trip.status == TripStatus.ACTIVE)
        .order_by(Trip.created_at.desc())  # Eng yangi aktiv trip
    )
    
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def add_order_to_trip(
    session,
    trip_id: int,
    order_id: int,
    passenger_count: int
) -> Trip:
    """
    Order'ni trip'ga qo'shish va available_seats kamay tirish
    
    QACHON:
    - Order qabul qilinganda
    
    ISHLATISH:
        await add_order_to_trip(
            session,
            trip_id=1,
            order_id=5,
            passenger_count=2
        )
    """
    # Trip available_seats'ni kamaytirish
    await session.execute(
        update(Trip)
        .where(Trip.trip_id == trip_id)
        .values(available_seats=Trip.available_seats - passenger_count)
    )
    
    # Order'ga trip_id qo'shish (order_service.py'da)
    
    return await get_trip_by_id(session, trip_id)


async def start_trip(
    session,
    trip_id: int
) -> Trip:
    """
    Trip'ni boshlash (yo'lga chiqqan)
    
    QACHON:
    - Haydovchi "Yo'lga chiqdik" tugmasini bosadi
    
    STATUS: active (lekin started_at set)
    """
    await session.execute(
        update(Trip)
        .where(Trip.trip_id == trip_id)
        .where(Trip.status == TripStatus.ACTIVE)
        .values(started_at=func.now())
    )
    
    return await get_trip_by_id(session, trip_id)


async def complete_trip(
    session,
    trip_id: int
) -> Trip:
    """
    Trip'ni yakunlash
    
    QACHON:
    - Barcha order'lar COMPLETED bo'lganda
    - Haydovchi "To'xtatish" bosadi
    
    STATUS: active → completed
    """
    await session.execute(
        update(Trip)
        .where(Trip.trip_id == trip_id)
        .where(Trip.status == TripStatus.ACTIVE)
        .values(
            status=TripStatus.COMPLETED,
            completed_at=func.now()
        )
    )
    
    return await get_trip_by_id(session, trip_id)


async def cancel_trip(
    session,
    trip_id: int
) -> Trip:
    """
    Trip'ni bekor qilish
    
    QACHON:
    - Haydovchi barcha order'larni bekor qildi
    
    STATUS: active → cancelled
    """
    await session.execute(
        update(Trip)
        .where(Trip.trip_id == trip_id)
        .values(
            status=TripStatus.CANCELLED,
            completed_at=func.now()
        )
    )
    
    return await get_trip_by_id(session, trip_id)


async def update_trip_location(
    session,
    trip_id: int,
    lat: float,
    lon: float
) -> Trip:
    """
    Trip lokatsiyasini yangilash (real-time GPS tracking)
    
    QACHON:
    - Har 30 soniyada (Celery task)
    
    ISHLATISH:
        await update_trip_location(
            session,
            trip_id=1,
            lat=41.311512,
            lon=69.249512
        )
    """
    await session.execute(
        update(Trip)
        .where(Trip.trip_id == trip_id)
        .values(
            current_lat=lat,
            current_lon=lon,
            last_location_update=func.now()
        )
    )
    
    return await get_trip_by_id(session, trip_id)


__all__ = [
    'Trip',
    'TripStatus',
    'create_trip',
    'get_trip_by_id',
    'get_active_trip_by_driver',
    'add_order_to_trip',
    'start_trip',
    'complete_trip',
    'cancel_trip',
    'update_trip_location'
]
