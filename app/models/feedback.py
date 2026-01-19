"""
app/models/feedback.py
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from datetime import datetime
import enum

from sqlalchemy import (
    BigInteger, Text, Enum as SQLEnum, DateTime, ForeignKey, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from .user import User
# ============================================
# ENUMS
# ============================================
class FeedbackType(str, enum.Enum):
    """Fikr turi"""
    COMPLAINT = "complaint"    # Shikoyat
    SUGGESTION = "suggestion"  # Taklif

class FeedbackStatus(str, enum.Enum):
    """Fikr holati"""
    OPEN = "open"          # Ochiq (ko'rilmagan)
    IN_PROGRESS = "in_progress" # Ko'rilmoqda
    RESOLVED = "resolved"  # Hal qilingan
    IGNORED = "ignored"    # Bekor qilingan
# ============================================
# FEEDBACK MODEL
# ============================================
class Feedback(Base):
    """
    Feedback (Shikoyat va Takliflar) modeli
    """
    __tablename__ = "feedbacks"
    
    # PRIMARY KEY
    feedback_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )
    
    # FOREIGN KEYS
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    resolved_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="Kim tomonidan hal qilindi (Admin ID)"
    )
    
    # MA'LUMOTLAR
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    type: Mapped[FeedbackType] = mapped_column(
        SQLEnum(FeedbackType, name="feedback_type_enum"),
        default=FeedbackType.COMPLAINT,
        nullable=False
    )
    
    status: Mapped[FeedbackStatus] = mapped_column(
        SQLEnum(FeedbackStatus, name="feedback_status_enum"),
        default=FeedbackStatus.OPEN,
        nullable=False,
        index=True
    )
    
    admin_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # TIMESTAMPS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )
    
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # RELATIONSHIPS
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        backref="feedbacks"
    )
    
    resolver: Mapped["User"] = relationship(
        "User",
        foreign_keys=[resolved_by],
        backref="resolved_feedbacks"
    )
    
    def __repr__(self):
        return f"<Feedback(id={self.feedback_id}, type={self.type}, status={self.status})>"


# ============================================
# HELPER FUNCTIONS
# ============================================

async def create_feedback(
    session,
    user_id: int,
    message: str,
    type: FeedbackType = FeedbackType.COMPLAINT
) -> Feedback:
    """Yangi feedback yaratish"""
    feedback = Feedback(
        user_id=user_id,
        message=message,
        type=type
    )
    session.add(feedback)
    return feedback


async def get_feedback_by_id(session, feedback_id: int) -> Optional[Feedback]:
    """ID bo'yicha olish"""
    from sqlalchemy import select
    result = await session.execute(
        select(Feedback).where(Feedback.feedback_id == feedback_id)
    )
    return result.scalar_one_or_none()
