"""
app/models/driver.py

BU FAYL NIMA QILADI:
- Driver (Haydovchi) model'i
- Haydovchi ma'lumotlari
- Balans, reyting, lokatsiya

JADVAL STRUKTURASI:
    drivers
    ├── driver_id (PK)
    ├── user_id (FK → users)
    ├── full_name
    ├── phone_number (telefon raqam)
    ├── car_model, car_color, car_number
    ├── license_number
    ├── balance (balans)
    ├── rating (reyting)
    ├── total_trips (jami safarlar)
    ├── current_route_id (hozirgi marshrut)
    ├── available_seats (bo'sh o'rinlar)
    ├── location (PostGIS geometry)
    ├── is_active, is_on_trip, is_blocked
    └── timestamps

ISHLATISH:
    from app.models.driver import Driver
    
    driver = await get_driver_by_id(session, driver_id)
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    BigInteger, Integer, String, Boolean, DateTime, Numeric,
    ForeignKey, CheckConstraint, Index, func, select, update, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from geoalchemy2 import Geometry

from app.core.database import Base

if TYPE_CHECKING:
    from .user import User
    from .route import Route
    from .order import Order
    from .trip import Trip
    from .transaction import Transaction


# ============================================
# DRIVER MODEL
# ============================================

class Driver(Base):
    """
    Driver (Haydovchi) model
    
    RELATIONSHIPS:
    - user: User model (1-to-1)
    - orders: Order model (1-to-many) - haydovchi qabul qilgan buyurtmalar
    - transactions: Transaction model (1-to-many)
    """
    
    __tablename__ = "drivers"
    
    # ============================================
    # PRIMARY KEY
    # ============================================
    
    driver_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Driver ID (auto increment)"
    )
    
    # ============================================
    # FOREIGN KEY (User bilan bog'lanish)
    # ============================================
    
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,  # Har bir user faqat 1 marta driver bo'lishi mumkin
        nullable=False,
        index=True,
        comment="User ID (Telegram)"
    )
    
    # ============================================
    # SHAXSIY MA'LUMOTLAR
    # ============================================
    
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="To'liq ism"
    )
    
    phone_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Telefon raqam (+998901234567)"
    )
    
    # ============================================
    # MASHINA MA'LUMOTLARI
    # ============================================
    
    car_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Mashina markasi (Nexia, Cobalt, etc)"
    )
    
    car_color: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Mashina rangi"
    )
    
    car_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,  # Har bir mashina raqami unique
        nullable=False,
        index=True,
        comment="Mashina raqami (01 A 123 BC)"
    )
    
    license_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Haydovchilik guvohnomasi"
    )
    
    # ============================================
    # MOLIYAVIY MA'LUMOTLAR
    # ============================================
    
    balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),  # 10 raqam, 2 ta decimal (99999999.99)
        default=0.00,
        nullable=False,
        comment="Balans (so'm)"
    )
    
    # ============================================
    # STATISTIKA
    # ============================================
    
    total_trips: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Jami safarlar soni"
    )
    
    rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),  # 5.00 format
        default=5.00,
        nullable=False,
        comment="Reyting (1.00 - 5.00)"
    )
    
    ban_count_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Bugungi ban soni"
    )
    
    total_ban_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Jami ban soni"
    )
    
    # ============================================
    # HOLAT
    # ============================================
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Aktiv (online)"
    )
    
    is_on_trip: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Safardaligi"
    )
    
    is_blocked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Bloklangan"
    )

    is_priority: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Priority (Navbatda ustunlik)"
    )
    
    blocked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Qachongacha bloklangan"
    )
    
    block_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Bloklash sababi"
    )
    
    # ============================================
    # MARSHRUT VA O'RINLAR
    # ============================================
    
    current_route_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("routes.route_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Hozirgi marshrut"
    )
    
    available_seats: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Bo'sh o'rinlar soni (0-6)"
    )
    
    # ============================================
    # LOKATSIYA (PostGIS)
    # ============================================
    
    last_location_lat: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 8),  # Latitude: 41.31151200
        nullable=True,
        comment="Oxirgi lokatsiya - Latitude"
    )
    
    last_location_lon: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(11, 8),  # Longitude: 69.24951200
        nullable=True,
        comment="Oxirgi lokatsiya - Longitude"
    )
    
    # PostGIS geometry (POINT)
    location: Mapped[Optional[bytes]] = mapped_column(
        Geometry('POINT', srid=4326, spatial_index=False),  # spatial_index=False → qo'lda indeks qo'yamiz
        nullable=True,
        comment="Lokatsiya (PostGIS geometry)"
    )
    
    # ============================================
    # TIMESTAMPS
    # ============================================
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Yaratilgan sana"
    )
    
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Yangilangan sana"
    )
    
    last_trip_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Oxirgi safar vaqti"
    )
    
    # ============================================
    # RELATIONSHIPS
    # ============================================
    
    user: Mapped["User"] = relationship("User", back_populates="driver")
    current_route: Mapped[Optional["Route"]] = relationship("Route")
    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="driver"
    )
    
    trips: Mapped[list["Trip"]] = relationship(
        "Trip",
        back_populates="driver"
    )
    
    # Transactions bilan
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="driver"
    )
    
    # ============================================
    # INDEXES
    # ============================================
    
    __table_args__ = (
        # Composite indexes (tez qidiruv)
        Index('idx_drivers_active_route', 'is_active', 'current_route_id'),
        Index('idx_drivers_active_blocked', 'is_active', 'is_blocked'),
        Index('idx_drivers_route_seats', 'current_route_id', 'available_seats'),
        
        # Spatial index (PostGIS)
        Index('idx_drivers_location', 'location', postgresql_using='gist'),
        
        # Check constraints
        CheckConstraint('rating >= 1.00 AND rating <= 5.00', name='check_rating_range'),
        CheckConstraint('available_seats >= 0 AND available_seats <= 6', name='check_seats_range'),
        CheckConstraint('balance >= 0', name='check_balance_positive'),
        
        {'extend_existing': True}
    )
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def has_sufficient_balance(self) -> bool:
        """Balans yetarlimi? (komissiya uchun)"""
        from config.settings import settings
        return self.balance >= settings.COMMISSION_AMOUNT
    
    @property
    def is_available(self) -> bool:
        """Buyurtma qabul qilishi mumkinmi?"""
        return (
            self.is_active and
            not self.is_on_trip and
            not self.is_blocked and
            self.available_seats > 0 and
            self.has_sufficient_balance
        )
    
    @property
    def location_tuple(self) -> Optional[tuple]:
        """Lokatsiya tuple (lat, lon)"""
        if self.last_location_lat and self.last_location_lon:
            return (float(self.last_location_lat), float(self.last_location_lon))
        return None
    
    # ============================================
    # METHODS
    # ============================================
    
    def to_dict(self) -> dict:
        """Dictionary'ga aylantirish"""
        return {
            'driver_id': self.driver_id,
            'user_id': self.user_id,
            'full_name': self.full_name,
            'phone_number': self.phone_number,
            'car_model': self.car_model,
            'car_color': self.car_color,
            'car_number': self.car_number,
            'balance': float(self.balance),
            'rating': float(self.rating),
            'total_trips': self.total_trips,
            'is_active': self.is_active,
            'is_on_trip': self.is_on_trip,
            'is_blocked': self.is_blocked,
            'available_seats': self.available_seats,
            'location': self.location_tuple
        }
    
    def __repr__(self) -> str:
        return (
            f"<Driver(id={self.driver_id}, "
            f"name='{self.full_name}', "
            f"car={self.car_model}, "
            f"rating={self.rating})>"
        )


# ============================================
# HELPER FUNCTIONS
# ============================================

async def get_driver_by_id(session, driver_id: int, eager_load_user: bool = False) -> Optional[Driver]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    stmt = select(Driver).where(Driver.driver_id == driver_id)
    
    # Agar kerak bo'lsa, Userni ham bitta so'rovda qo'shib yuklaymiz
    if eager_load_user:
        stmt = stmt.options(selectinload(Driver.user))
        
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_driver_by_user_id(session, user_id: int) -> Optional[Driver]:
    """Driver'ni User ID bo'yicha olish"""
    from sqlalchemy import select
    
    result = await session.execute(
        select(Driver).where(Driver.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_driver(
    session,
    user_id: int,
    full_name: str,
    phone_number: str,
    car_model: str,
    car_color: str,
    car_number: str,
    **kwargs
) -> Driver:
    """
    Yangi driver yaratish
    
    ISHLATISH:
        driver = await create_driver(
            session,
            user_id=123456789,
            full_name="Alisher Karimov",
            car_model="Chevrolet Cobalt",
            car_color="Oq",
            car_number="01 A 123 BC"
        )
        await session.commit()
    """
    # Validatsiyadan o'tgan kwargs'larni tozalash (duplication oldini olish)
    kwargs.pop('is_active', None)
    available_seats = kwargs.pop('available_seats', None)

    driver = Driver(
        user_id=user_id,
        full_name=full_name,
        phone_number=phone_number,
        car_model=car_model,
        car_color=car_color,
        car_number=car_number,
        is_active=False,          # Ro'yxatdan keyin qo'lda yoqadi
        available_seats=available_seats if available_seats is not None else 0,
        **kwargs
    )
    
    session.add(driver)
    return driver


async def update_driver_location(
    session,
    driver_id: int,
    latitude: float,
    longitude: float
):
    """
    Driver lokatsiyasini yangilash
    
    ✅ FIX: Parameterized query — SQL injection oldini olish
    """
    from sqlalchemy import update, text
    
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver_id)
        .values(
            last_location_lat=latitude,
            last_location_lon=longitude,
            location=text("ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)").bindparams(lon=longitude, lat=latitude)
        )
    )


async def update_driver_balance(
    session,
    driver_id: int,
    amount: Decimal
) -> Decimal:
    """
    Driver balansini yangilash (atomic)
    
    Args:
        amount: Miqdor (musbat = qo'shish, manfiy = yechish)
    
    Returns:
        Yangi balans
    
    ISHLATISH:
        # Balansdan 5000 yechish
        new_balance = await update_driver_balance(session, driver_id, -5000)
    """
    from sqlalchemy import update
    
    result = await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver_id)
        .values(balance=Driver.balance + amount)
        .returning(Driver.balance)
    )
    
    return result.scalar_one()


async def get_available_drivers_for_route(
    session,
    route_id: int,
    min_seats: int = 1
) -> list[Driver]:
    """
    Marshrut uchun bo'sh haydovchilar
    
    ISHLATISH:
        drivers = await get_available_drivers_for_route(session, route_id=1, min_seats=2)
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(Driver)
        .where(Driver.current_route_id == route_id)
        .where(Driver.is_active == True)
        .where(Driver.is_on_trip == False)
        .where(Driver.is_blocked == False)
        .where(Driver.available_seats >= min_seats)
        .order_by(Driver.rating.desc(), Driver.total_trips.desc())
    )
    
    return result.scalars().all()


# ============================================
# QUERY EXAMPLES
# ============================================

"""
# Driver olish
driver = await get_driver_by_id(session, 1)
driver = await get_driver_by_user_id(session, 123456789)

# Yangi driver yaratish
driver = await create_driver(
    session,
    user_id=123456789,
    full_name="Alisher Karimov",
    phone_number="+998901234567",
    car_model="Cobalt",
    car_color="Oq",
    car_number="01 A 123 BC"
)
await session.commit()

# Lokatsiyani yangilash
await update_driver_location(session, driver_id=1, latitude=41.311512, longitude=69.249512)
await session.commit()

# Balansni yangilash
new_balance = await update_driver_balance(session, driver_id=1, amount=-5000)
await session.commit()

# Bo'sh haydovchilar
drivers = await get_available_drivers_for_route(session, route_id=1, min_seats=2)
"""
