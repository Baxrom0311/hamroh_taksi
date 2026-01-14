"""
app/models/transaction.py

TRANSACTION (TRANZAKSIYA) MODEL

To'lov va balans tarixi
"""

from sqlalchemy import (
    Integer,
    BigInteger,
    String,
    Text,
    Numeric,
    Enum as SQLEnum,
    DateTime,
    ForeignKey,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from decimal import Decimal
import enum

from app.core.database import Base

# ============================================
# ENUMS
# ============================================

class TransactionType(str, enum.Enum):
    """Tranzaksiya turi"""
    DEPOSIT = "deposit"          # To'ldirish
    WITHDRAWAL = "withdrawal"    # Yechish
    COMMISSION = "commission"    # Komissiya


class TransactionStatus(str, enum.Enum):
    """Tranzaksiya holati"""
    PENDING = "pending"      # Kutilmoqda (admin tasdiqlashi kerak)
    APPROVED = "approved"    # Tasdiqlangan
    REJECTED = "rejected"    # Rad etilgan


# ============================================
# TRANSACTION MODEL
# ============================================

class Transaction(Base):
    """
    Transaction (Tranzaksiya) model
    
    ISHLATISH:
    - Haydovchi balansni to'ldiradi → PENDING
    - Admin tasdiqlaydi → APPROVED
    - Balansga qo'shiladi
    """
    
    __tablename__ = "transactions"
    
    # PRIMARY KEY
    transaction_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    
    # FOREIGN KEYS
    driver_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("drivers.driver_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    admin_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Admin (tasdiqlagan)"
    )
    
    # TRANZAKSIYA DETALLARI
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Miqdor (so'm)"
    )
    
    type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType, name="transaction_type"),
        nullable=False,
        index=True
    )
    
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(TransactionStatus, name="transaction_status"),
        default=TransactionStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # CHEK (To'ldirish uchun)
    receipt_file_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Chek file ID (Telegram)"
    )
    
    # TAVSIF
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Tavsif"
    )
    
    # TIMESTAMPS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Admin tomonidan ko'rib chiqilgan vaqt"
    )
    
    # RELATIONSHIPS
    driver: Mapped["Driver"] = relationship("Driver", back_populates="transactions")
    admin: Mapped[Optional["User"]] = relationship("User")  # optional: add back_populates if needed
    
    # INDEXES
    __table_args__ = (
        Index('idx_transactions_status_created', 'status', 'created_at'),
        Index('idx_transactions_driver_status', 'driver_id', 'status'),
        {'extend_existing': True}
    )
    
    def to_dict(self) -> dict:
        return {
            'transaction_id': self.transaction_id,
            'driver_id': self.driver_id,
            'amount': float(self.amount),
            'type': self.type.value,
            'status': self.status.value,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }
    
    def __repr__(self) -> str:
        return (
            f"<Transaction(id={self.transaction_id}, "
            f"type={self.type.value}, "
            f"amount={self.amount}, "
            f"status={self.status.value})>"
        )


# ============================================
# TRANSACTION LOGS (Audit trail)
# ============================================

class TransactionLog(Base):
    """
    Transaction log (barcha balans o'zgarishlari)
    
    BU NIMA:
    Har bir balans o'zgarishi shu yerda yoziladi (audit trail)
    """
    
    __tablename__ = "transaction_logs"
    
    log_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    
    driver_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("drivers.driver_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("orders.order_id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Miqdor (musbat/manfiy)"
    )
    
    type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType, name="transaction_type"),
        nullable=False
    )
    
    old_balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Eski balans"
    )
    
    new_balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Yangi balans"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    __table_args__ = (
        Index('idx_transaction_logs_driver_created', 'driver_id', 'created_at'),
        {'extend_existing': True}
    )
    
    def __repr__(self) -> str:
        return (
            f"<TransactionLog(driver_id={self.driver_id}, "
            f"amount={self.amount}, "
            f"balance: {self.old_balance}→{self.new_balance})>"
        )


# ============================================
# HELPER FUNCTIONS
# ============================================

async def create_transaction(
    session,
    driver_id: int,
    amount: Decimal,
    type: TransactionType,
    **kwargs
) -> Transaction:
    """
    Yangi tranzaksiya yaratish
    
    ISHLATISH:
        # To'ldirish so'rovi
        transaction = await create_transaction(
            session,
            driver_id=1,
            amount=50000,
            type=TransactionType.DEPOSIT,
            receipt_file_id="AgACAgIAAxkBAAI...",
            description="Balans to'ldirish"
        )
        await session.commit()
    """
    transaction = Transaction(
        driver_id=driver_id,
        amount=amount,
        type=type,
        **kwargs
    )
    
    session.add(transaction)
    return transaction


async def approve_transaction(
    session,
    transaction_id: int,
    admin_id: int
) -> bool:
    """
    Tranzaksiyani tasdiqlash
    
    Returns:
        True: Tasdiqlandi
        False: Tranzaksiya topilmadi yoki allaqachon ko'rib chiqilgan
    """
    from sqlalchemy import update
    
    result = await session.execute(
        update(Transaction)
        .where(Transaction.transaction_id == transaction_id)
        .where(Transaction.status == TransactionStatus.PENDING)
        .values(
            status=TransactionStatus.APPROVED,
            admin_id=admin_id,
            processed_at=func.now()
        )
    )
    
    return result.rowcount > 0


async def reject_transaction(
    session,
    transaction_id: int,
    admin_id: int,
    reason: Optional[str] = None
) -> bool:
    """Tranzaksiyani rad etish"""
    from sqlalchemy import update
    
    result = await session.execute(
        update(Transaction)
        .where(Transaction.transaction_id == transaction_id)
        .where(Transaction.status == TransactionStatus.PENDING)
        .values(
            status=TransactionStatus.REJECTED,
            admin_id=admin_id,
            description=reason,
            processed_at=func.now()
        )
    )
    
    return result.rowcount > 0


async def log_balance_change(
    session,
    driver_id: int,
    amount: Decimal,
    type: TransactionType,
    old_balance: Decimal,
    new_balance: Decimal,
    **kwargs
) -> TransactionLog:
    """
    Balans o'zgarishini log qilish
    
    ISHLATISH:
        await log_balance_change(
            session,
            driver_id=1,
            amount=-5000,
            type=TransactionType.COMMISSION,
            old_balance=10000,
            new_balance=5000,
            order_id=123,
            description="Safar #123 uchun komissiya"
        )
    """
    log = TransactionLog(
        driver_id=driver_id,
        amount=amount,
        type=type,
        old_balance=old_balance,
        new_balance=new_balance,
        **kwargs
    )
    
    session.add(log)
    return log


async def get_pending_transactions(session) -> list[Transaction]:
    """
    Barcha kutayotgan tranzaksiyalar (admin uchun)
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(Transaction)
        .where(Transaction.status == TransactionStatus.PENDING)
        .order_by(Transaction.created_at)
    )
    
    return result.scalars().all()


async def get_driver_transaction_history(
    session,
    driver_id: int,
    limit: int = 50
) -> list[TransactionLog]:
    """
    Driver'ning tranzaksiya tarixi
    """
    from sqlalchemy import select
    
    result = await session.execute(
        select(TransactionLog)
        .where(TransactionLog.driver_id == driver_id)
        .order_by(TransactionLog.created_at.desc())
        .limit(limit)
    )
    
    return result.scalars().all()