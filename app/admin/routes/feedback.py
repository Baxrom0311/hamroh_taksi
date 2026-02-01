"""
app/admin/routes/feedback.py
"""

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, desc, func
from datetime import datetime

from app.core.database import get_session
from app.admin.auth import get_current_user
from app.models.feedback import Feedback, FeedbackStatus
from app.bot.main import bot

router = APIRouter()

@router.post("/feedback/reply")
async def reply_feedback(
    feedback_id: int = Form(...),
    reply_text: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Feedbackga javob berish
    """
    admin_id = current_user['user_id']
    
    async with get_session() as session:
        # Update Feedback
        query = (
            update(Feedback)
            .where(Feedback.feedback_id == feedback_id)
            .values(
                status=FeedbackStatus.RESOLVED,
                admin_reply=reply_text,
                resolved_by=admin_id,
                resolved_at=func.now()
            )
            .returning(Feedback.user_id)
        )
        
        result = await session.execute(query)
        user_id = result.scalar_one_or_none()
        await session.commit()
        
        if user_id:
            # User'ga xabar yuborish
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"📨 <b>Sizning murojaatingizga javob (#{feedback_id})</b>\n\n"
                        f"📝 <b>Javob:</b>\n{reply_text}"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                # Log error but don't fail request
                from loguru import logger
                logger.error(f"Failed to send feedback reply to user {user_id}: {e}")
                pass
                
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail="Feedback topilmadi")


@router.get("/feedback/stats")
async def get_feedback_stats(
    current_user: dict = Depends(get_current_user)
):
    """
    Feedback statistic
    """
    try:
        async with get_session() as session:
            # Total
            total = (await session.execute(select(func.count(Feedback.feedback_id)))).scalar() or 0
            
            # Unread (OPEN status)
            unread = (await session.execute(
                select(func.count(Feedback.feedback_id)).where(Feedback.status == FeedbackStatus.OPEN)
            )).scalar() or 0
            
            # Today
            today_start = datetime.now().replace(hour=0, minute=0, second=0)
            today = (await session.execute(
                select(func.count(Feedback.feedback_id)).where(Feedback.created_at >= today_start)
            )).scalar() or 0
            
            return {
                "total": total,
                "unread": unread,
                "today": today
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/")
async def get_feedback_list(
    limit: int = 20,
    offset: int = 0,
    status: str = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Feedback list with pagination
    """
    try:
        async with get_session() as session:
            stmt = select(Feedback).options(selectinload(Feedback.user)).order_by(desc(Feedback.created_at))
            
            if status == 'unread':
                stmt = stmt.where(Feedback.status == FeedbackStatus.OPEN)
            elif status == 'read':
                stmt = stmt.where(Feedback.status.in_([FeedbackStatus.RESOLVED, FeedbackStatus.CLOSED]))
                
            stmt = stmt.limit(limit).offset(offset)
            
            result = await session.execute(stmt)
            feedbacks = result.scalars().all()
            
            items = []
            for fb in feedbacks:
                items.append({
                    "id": fb.feedback_id,
                    "message": fb.message,
                    "is_read": fb.status != FeedbackStatus.OPEN,
                    "created_at": fb.created_at.isoformat() if fb.created_at else None,
                    "status": fb.status.value,
                    "user_type": fb.user.role.value if fb.user else "unknown",
                    "user": {
                        "full_name": fb.user.full_name if fb.user else "Noma'lum",
                        "phone": fb.user.phone_number if fb.user else "N/A"
                    }
                })
            
            return {"items": items}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/feedback/{feedback_id}/read")
async def mark_feedback_read(
    feedback_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Mark feedback as read (RESOLVED/IN_PROGRESS)
    """
    try:
        async with get_session() as session:
            # Check current status
            fb = await session.get(Feedback, feedback_id)
            if not fb:
                raise HTTPException(status_code=404, detail="Feedback not found")
                
            if fb.status == FeedbackStatus.OPEN:
                fb.status = FeedbackStatus.IN_PROGRESS
                await session.commit()
                
            return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

