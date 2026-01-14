"""
app/models/user.py

BU FAYL NIMA QILADI:
- User (foydalanuvchi) model'i
- SQLAlchemy ORM model
- users jadvali uchun

JADVAL STRUKTURASI:
    users
    ├── user_id (PK) - Telegram user ID
    ├── username - Telegram username
    ├── first_name - Ism
    ├── last_name - Familiya
    ├── phone_number - Telefon raqam (unique)
    ├── role - Rol (glavni_admin, admin, driver, passenger)
    ├── is_blocked - Bloklangan
    ├── registration_date - Ro'yxatdan o'tgan sana
    └── last_active - Oxirgi faollik

ISHLATISH:
    from app.models.user import User
    from app.core.database import get_session
    
    async with get_session() as session:
        user = await session.get(User, user_id)
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    String,
    Boolean,
    Enum as SQLEnum,
    DateTime,
    Index
)
from typing import TYPE_CHECKING, Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import enum
from app.core.database import Base
# ============================================
# ENUM (Rol turlari)
# ============================================

class UserRole(str, enum.Enum):
    """
    Foydalanuvchi rollari
    
    QIYMATLAR:
    - GLAVNI_ADMIN: Bosh admin (barcha huquqlar)
    - ADMIN: Admin (cheklangan huquqlar)
    - DRIVER: Haydovchi
    - PASSENGER: Yo'lovchi
    """
    GLAVNI_ADMIN = "glavni_admin"
    ADMIN = "admin"
    DRIVER = "driver"
    PASSENGER = "passenger"


# ============================================
# USER MODEL
# ============================================

class User(Base):
    """
    User (Foydalanuvchi) model
    
    BU MODEL NIMA UCHUN:
    - Barcha foydalanuvchilar (admin, driver, passenger) shu jadvalda
    - Role orqali farqlanadi
    - Telegram ma'lumotlari saqlanadi
    
    RELATIONSHIPS:
    - driver: Driver model bilan (1-to-1) agar role=driver
    - passenger: Passenger model bilan (1-to-1) agar role=passenger
    """
    
    __tablename__ = "users"
    
    # ============================================
    # COLUMNS (Ustunlar)
    # ============================================
    
    # Primary Key - Telegram user ID
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        comment="Telegram user ID"
    )
    # DIQQAT: autoincrement=False chunki Telegram ID ishlatamiz
    
    # Telegram ma'lumotlari
    username: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Telegram username (@username)"
    )
    
    first_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Ism"
    )
    
    last_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Familiya"
    )
    
    # Telefon raqam (unique!)
    phone_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,  # Tez qidiruv uchun
        comment="Telefon raqam (+998901234567)"
    )
    
    # Rol
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.PASSENGER,
        index=True,  # Role bo'yicha qidiruv
        comment="Foydalanuvchi roli"
    )
    
    # Holat
    is_blocked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,  # Bloklangan foydalanuvchilar
        comment="Bloklangan"
    )
    
    # Sanalar
    registration_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Ro'yxatdan o'tgan sana"
    )
    
    last_active: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),  # Har update'da yangilanadi
        comment="Oxirgi faollik"
    )
    
    # ============================================
    # RELATIONSHIPS (Bog'lanishlar)
    # ============================================
    
    # Driver model bilan (agar role=driver)
    driver: Mapped[Optional["Driver"]] = relationship(
        "Driver",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # 1-to-1 relationship with Passenger
    passenger: Mapped[Optional["Passenger"]] = relationship(
        "Passenger",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # ============================================
    # INDEXES (Qidiruv tezligi uchun)
    # ============================================
    
    __table_args__ = (
        # Composite index (role + is_blocked)
        Index('idx_users_role_blocked', 'role', 'is_blocked'),
        
        # Phone number index (allaqachon unique=True'da bor)
        # Index('idx_users_phone', 'phone_number'),
        
        {'extend_existing': True}
    )
    
    # ============================================
    # METHODS (Yordamchi funksiyalar)
    # ============================================
    
    @property
    def full_name(self) -> str:
        """
        To'liq ism
        
        Returns:
            "Ism Familiya" yoki faqat "Ism"
        """
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name
    
    @property
    def is_admin(self) -> bool:
        """Admin yoki Bosh admin?"""
        return self.role in [UserRole.GLAVNI_ADMIN, UserRole.ADMIN]
    
    @property
    def is_driver(self) -> bool:
        """Haydovchi?"""
        return self.role == UserRole.DRIVER
    
    @property
    def is_passenger(self) -> bool:
        """Yo'lovchi?"""
        return self.role == UserRole.PASSENGER
    
    @property
    def is_glavni_admin(self) -> bool:
        """Bosh admin?"""
        return self.role == UserRole.GLAVNI_ADMIN
    
    def to_dict(self) -> dict:
        """
        Dictionary'ga aylantirish
        
        Returns:
            {
                'user_id': int,
                'username': str,
                'full_name': str,
                'phone_number': str,
                'role': str,
                'is_blocked': bool,
                'registration_date': str
            }
        """
        return {
            'user_id': self.user_id,
            'username': self.username,
            'full_name': self.full_name,
            'phone_number': self.phone_number,
            'role': self.role.value,
            'is_blocked': self.is_blocked,
            'registration_date': self.registration_date.isoformat() if self.registration_date else None,
            'last_active': self.last_active.isoformat() if self.last_active else None
        }
    
    def __repr__(self) -> str:
        """String representation"""
        return (
            f"<User(user_id={self.user_id}, "
            f"full_name='{self.full_name}', "
            f"role={self.role.value})>"
        )


# ============================================
# HELPER FUNCTIONS (Qulaylik uchun)
# ============================================

async def get_user_by_id(session, user_id: int) -> Optional[User]:
    """
    User'ni ID bo'yicha olish
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        User yoki None
    
    ISHLATISH:
        async with get_session() as session:
            user = await get_user_by_id(session, 123456789)
            if user:
                print(user.full_name)
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_phone(session, phone_number: str) -> Optional[User]:
    """
    User'ni telefon raqam bo'yicha olish
    
    ISHLATISH:
        user = await get_user_by_phone(session, "+998901234567")
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(User).where(User.phone_number == phone_number)
    )
    return result.scalar_one_or_none()


async def create_user(
    session,
    user_id: int,
    phone_number: str,
    first_name: str,
    role: UserRole = UserRole.PASSENGER,
    **kwargs
) -> User:
    """
    Yangi user yaratish
    
    Args:
        session: Database session
        user_id: Telegram user ID
        phone_number: Telefon raqam
        first_name: Ism
        role: Rol (default: passenger)
        **kwargs: Qo'shimcha parametrlar (username, last_name)
    
    Returns:
        Yangi User object
    
    ISHLATISH:
        async with get_session() as session:
            user = await create_user(
                session,
                user_id=123456789,
                phone_number="+998901234567",
                first_name="Alisher",
                last_name="Karimov",
                role=UserRole.DRIVER
            )
            await session.commit()
    """
    user = User(
        user_id=user_id,
        phone_number=phone_number,
        first_name=first_name,
        role=role,
        **kwargs
    )
    
    session.add(user)
    return user


async def block_user(session, user_id: int, reason: Optional[str] = None) -> bool:
    """
    User'ni bloklash
    
    Returns:
        True: Bloklandi
        False: User topilmadi
    """
    from sqlalchemy import update
    
    result = await session.execute(
        update(User)
        .where(User.user_id == user_id)
        .values(is_blocked=True)
    )
    
    return result.rowcount > 0


async def unblock_user(session, user_id: int) -> bool:
    """
    User'ni blokdan ochish
    
    Returns:
        True: Ochildi
        False: User topilmadi
    """
    from sqlalchemy import update
    
    result = await session.execute(
        update(User)
        .where(User.user_id == user_id)
        .values(is_blocked=False)
    )
    
    return result.rowcount > 0


async def update_last_active(session, user_id: int):
    """
    Oxirgi faollik vaqtini yangilash
    
    QACHON: Har safar user biror narsa qilganda
    """
    from sqlalchemy import update
    
    await session.execute(
        update(User)
        .where(User.user_id == user_id)
        .values(last_active=func.now())
    )


# ============================================
# QUERY EXAMPLES (Misol query'lar)
# ============================================

"""
# User'ni olish
user = await get_user_by_id(session, 123456789)

# Telefon bo'yicha qidirish
user = await get_user_by_phone(session, "+998901234567")

# Yangi user yaratish
user = await create_user(
    session,
    user_id=123456789,
    phone_number="+998901234567",
    first_name="Alisher",
    role=UserRole.DRIVER
)
await session.commit()

# User'ni bloklash
await block_user(session, 123456789)
await session.commit()

# Barcha haydovchilar
from sqlalchemy import select

result = await session.execute(
    select(User)
    .where(User.role == UserRole.DRIVER)
    .where(User.is_blocked == False)
)
drivers = result.scalars().all()

# Oxirgi 10 ta ro'yxatdan o'tgan user
result = await session.execute(
    select(User)
    .order_by(User.registration_date.desc())
    .limit(10)
)
recent_users = result.scalars().all()
"""