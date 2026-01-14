"""
app/models/route.py

ROUTE (MARSHRUT) MODEL

Gurlan → Vazir
Vazir → Gurlan
Gurlan → Qoratol
Qoratol → Gurlan
"""
from __future__ import annotations
from sqlalchemy import (
    Integer,
    String,
    Numeric,
    Boolean,
    DateTime,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal

from app.core.database import Base

# ============================================
# ROUTE MODEL
# ============================================

class Route(Base):
    """
    Marshrut model
    
    MISOL:
        - Gurlan → Vazir (45 km)
        - Vazir → Gurlan (45 km)
    """
    
    __tablename__ = "routes"
    
    # PRIMARY KEY
    route_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    
    # MARSHRUT NOMLARI
    from_location: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Qayerdan (Gurlan)"
    )
    
    to_location: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Qayerga (Vazir)"
    )
    
    # LOKATSIYA KOORDINATALARI (Boshlanish nuqta)
    from_location_lat: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 8),
        nullable=True,
        comment="Qayerdan - Latitude"
    )
    
    from_location_lon: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(11, 8),
        nullable=True,
        comment="Qayerdan - Longitude"
    )
    
    # LOKATSIYA KOORDINATALARI (Tugash nuqta)
    to_location_lat: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 8),
        nullable=True,
        comment="Qayerga - Latitude"
    )
    
    to_location_lon: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(11, 8),
        nullable=True,
        comment="Qayerga - Longitude"
    )
    
    # MASOFA
    distance_km: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),  # 999.99 km
        nullable=True,
        comment="Masofa (km)"
    )
    
    # HOLAT
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Aktiv marshrut"
    )
    
    # TIMESTAMP
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # RELATIONSHIPS
    # orders: Order'lar shu marshrut bo'yicha
    orders: Mapped[List["Order"]] = relationship( 
        "Order",
        back_populates="route"
    )
    
    # ============================================
    # INDEXES
    # ============================================
    
    __table_args__ = (
        # Unique constraint (bir xil marshrut 2 marta bo'lmasligi)
        Index('idx_routes_unique', 'from_location', 'to_location', unique=True),
        
        # Active routes
        Index('idx_routes_active', 'is_active'),
        
        {'extend_existing': True}
    )
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def route_name(self) -> str:
        """Marshrut nomi"""
        return f"{self.from_location} → {self.to_location}"
    
    @property
    def reverse_route_name(self) -> str:
        """Teskari marshrut nomi"""
        return f"{self.to_location} → {self.from_location}"
    
    def to_dict(self) -> dict:
        return {
            'route_id': self.route_id,
            'from_location': self.from_location,
            'to_location': self.to_location,
            'route_name': self.route_name,
            'distance_km': float(self.distance_km) if self.distance_km else None,
            'is_active': self.is_active
        }
    
    def __repr__(self) -> str:
        return f"<Route(id={self.route_id}, {self.route_name})>"


# ============================================
# HELPER FUNCTIONS
# ============================================

async def get_route_by_id(session, route_id: int) -> Optional[Route]:
    """Route'ni ID bo'yicha olish"""
    from sqlalchemy import select
    result = await session.execute(
        select(Route).where(Route.route_id == route_id)
    )
    return result.scalar_one_or_none()


async def get_all_active_routes(session) -> list[Route]:
    """Barcha aktiv marshrutlar"""
    from sqlalchemy import select
    result = await session.execute(
        select(Route)
        .where(Route.is_active == True)
        .order_by(Route.from_location, Route.to_location)
    )
    return result.scalars().all()


async def get_all_routes(session) -> list[Route]:
    """Barcha marshrutlar (aktiv va nofaol)"""
    from sqlalchemy import select
    result = await session.execute(
        select(Route)
        .order_by(Route.is_active.desc(), Route.from_location, Route.to_location)
    )
    return result.scalars().all()


async def create_route(
    session,
    from_location: str,
    to_location: str,
    distance_km: Optional[float] = None,
    **kwargs
) -> Route:
    """
    Yangi marshrut yaratish
    
    ISHLATISH:
        route = await create_route(
            session,
            from_location="Gurlan",
            to_location="Vazir",
            distance_km=45.5,
            from_location_lat=41.311512,
            from_location_lon=69.249512
        )
        await session.commit()
    """
    route = Route(
        from_location=from_location,
        to_location=to_location,
        distance_km=distance_km,
        **kwargs
    )
    
    session.add(route)
    return route


async def find_route(
    session,
    from_location: str,
    to_location: str
) -> Optional[Route]:
    """
    Marshrut topish
    
    ISHLATISH:
        route = await find_route(session, "Gurlan", "Vazir")
    """
    from sqlalchemy import select
    result = await session.execute(
        select(Route)
        .where(Route.from_location == from_location)
        .where(Route.to_location == to_location)
        .where(Route.is_active == True)
    )
    return result.scalar_one_or_none()


# ============================================
# DEFAULT ROUTES (Seed data)
# ============================================

DEFAULT_ROUTES = [
    {
        'from_location': 'Gurlan',
        'to_location': 'Vazir',
        'distance_km': 45.0,
        'from_location_lat': 41.8453,
        'from_location_lon': 60.4015,
        'to_location_lat': 41.3775,
        'to_location_lon': 60.3614
    },
    {
        'from_location': 'Vazir',
        'to_location': 'Gurlan',
        'distance_km': 45.0,
        'from_location_lat': 41.3775,
        'from_location_lon': 60.3614,
        'to_location_lat': 41.8453,
        'to_location_lon': 60.4015
    },
    {
        'from_location': 'Gurlan',
        'to_location': 'Qoratol',
        'distance_km': 35.0,
        'from_location_lat': 41.8453,
        'from_location_lon': 60.4015,
        'to_location_lat': 41.6667,
        'to_location_lon': 60.3167
    },
    {
        'from_location': 'Qoratol',
        'to_location': 'Gurlan',
        'distance_km': 35.0,
        'from_location_lat': 41.6667,
        'from_location_lon': 60.3167,
        'to_location_lat': 41.8453,
        'to_location_lon': 60.4015
    }
]


async def seed_default_routes(session):
    """
    Default marshrutlarni yaratish
    
    ISHLATISH (scripts/seed_routes.py):
        from app.models.route import seed_default_routes
        
        async with get_session() as session:
            await seed_default_routes(session)
            await session.commit()
    """
    for route_data in DEFAULT_ROUTES:
        # Mavjudligini tekshirish
        existing = await find_route(
            session,
            route_data['from_location'],
            route_data['to_location']
        )
        
        if not existing:
            await create_route(session, **route_data)
            print(f"✅ Created: {route_data['from_location']} → {route_data['to_location']}")