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

