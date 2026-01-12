"""
app/models/passenger.py

PASSENGER (YO'LOVCHI) MODEL
"""

from sqlalchemy import (
    BigInteger,
    Integer,
    String,
    Enum as SQLEnum,
    DateTime,
    ForeignKey,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import enum
from sqlalchemy.orm import selectinload # Buni tepaga qo'shing
from typing import Optional
from app.core.database import Base
# ============================================
# ENUM
# ============================================

class Gender(str, enum.Enum):
    """Jins"""
    MALE = "male"      # Erkak
    FEMALE = "female"  # Ayol


# ============================================
# PASSENGER MODEL
# ============================================

class Passenger(Base):
    """Yo'lovchi model"""
    
    __tablename__ = "passengers"
    
    # PRIMARY KEY
    passenger_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )
    
    # FOREIGN KEY
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    
    # MA'LUMOTLAR
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    gender: Mapped[Gender] = mapped_column(
        SQLEnum(Gender, name="gender_enum"),
        nullable=False
    )
    
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    
    phone_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True
    )
    
    # STATISTIKA
    total_trips: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Jami safarlar"
    )
    
    cancellation_count_hour: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Soatdagi bekor qilish soni"
    )
    
    last_cancellation_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Oxirgi bekor qilish vaqti"
    )
    
    # TIMESTAMPS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # RELATIONSHIPS
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="passenger",
        uselist=False  # 1-to-1
    )

    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="passenger",
        foreign_keys="Order.passenger_id"
    )
    
    def to_dict(self) -> dict:
        return {
            'passenger_id': self.passenger_id,
            'user_id': self.user_id,
            'full_name': self.full_name,
            'gender': self.gender.value,
            'age': self.age,
            'phone_number': self.phone_number,
            'total_trips': self.total_trips
        }
    
    def __repr__(self) -> str:
        return f"<Passenger(id={self.passenger_id}, name='{self.full_name}')>"


# ============================================
# HELPER FUNCTIONS
# ============================================

async def get_passenger_by_id(session, passenger_id: int) -> Optional[Passenger]:
    """Passenger'ni ID bo'yicha olish (User ma'lumotlari bilan birga)"""
    from sqlalchemy import select
    
    # .options(selectinload(Passenger.user)) qismi User modelini ham darhol yuklab beradi
    query = (
        select(Passenger)
        .options(selectinload(Passenger.user)) 
        .where(Passenger.passenger_id == passenger_id)
    )
    
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_passenger_by_user_id(session, user_id: int) -> Optional[Passenger]:
    """Passenger'ni User ID bo'yicha olish"""
    from sqlalchemy import select
    result = await session.execute(
        select(Passenger).where(Passenger.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_passenger(
    session,
    user_id: int,
    full_name: str,
    gender: Gender,
    age: int,
    phone_number: str
) -> Passenger:
    """
    Yangi passenger yaratish
    
    ISHLATISH:
        passenger = await create_passenger(
            session,
            user_id=123456789,
            full_name="Alisher Karimov",
            gender=Gender.MALE,
            age=25,
            phone_number="+998901234567"
        )
        await session.commit()
    """
    passenger = Passenger(
        user_id=user_id,
        full_name=full_name,
        gender=gender,
        age=age,
        phone_number=phone_number
    )
    
    session.add(passenger)
    return passenger


async def increment_cancellation_count(session, passenger_id: int):
    """Bekor qilish sonini oshirish"""
    from sqlalchemy import update
    
    await session.execute(
        update(Passenger)
        .where(Passenger.passenger_id == passenger_id)
        .values(
            cancellation_count_hour=Passenger.cancellation_count_hour + 1,
            last_cancellation_time=func.now()
        )
    )


async def reset_cancellation_count(session, passenger_id: int):
    """Bekor qilish sonini reset qilish (1 soatdan keyin)"""
    from sqlalchemy import update
    
    await session.execute(
        update(Passenger)
        .where(Passenger.passenger_id == passenger_id)
        .values(cancellation_count_hour=0)
    )