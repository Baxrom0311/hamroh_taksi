"""
app/admin/routes/broadcast.py
BROADCAST MESSAGES (XABAR YUBORISH)
ENDPOINTS:
- GET /broadcast - Xabar yuborish sahifasi
- POST /api/broadcast/send - Xabar yuborish
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from loguru import logger
from app.admin.auth import get_current_user
from app.core.database import get_session
from app.models.user import User, UserRole
from sqlalchemy import select
router = APIRouter(prefix="/broadcast", tags=["broadcast"])
# ============================================
# SCHEMAS
# ============================================
class BroadcastRequest(BaseModel):
    """Xabar yuborish so'rovi"""
    message: str
    target: str  # "all", "admins", "drivers", "passengers"
# ============================================
# PERMISSION CHECK
# ============================================
def check_glavni_admin(current_user: dict):
    """Faqat Glavni Admin uchun"""
    if current_user.get('role') != 'glavni_admin':
        raise HTTPException(
            status_code=403,
            detail="Bu funksiya faqat Glavni Admin uchun"
        )
# ============================================
# SEND BROADCAST MESSAGE
# ============================================
@router.post("/send")
async def send_broadcast(
    request: BroadcastRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Xabar yuborish
    TARGETS:
    - all: Barcha foydalanuvchilar
    - admins: Faqat adminlar
    - drivers: Faqat haydovchilar
    - passengers: Faqat yo'lovchilar
    """
    check_glavni_admin(current_user)
    if not request.message or len(request.message.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="Xabar bo'sh bo'lishi mumkin emas"
        )
    if request.target not in ["all", "admins", "drivers", "passengers"]:
        raise HTTPException(
            status_code=400,
            detail="Noto'g'ri target. Qabul qilinadigan: all, admins, drivers, passengers"
        )
    try:
        from app.bot.main import bot
        async with get_session() as session:
            # Foydalanuvchilarni olish
            query = select(User)
            if request.target == "admins":
                query = query.where(
                    User.role.in_([UserRole.ADMIN, UserRole.GLAVNI_ADMIN])
                )
            elif request.target == "drivers":
                query = query.where(User.role == UserRole.DRIVER)
            elif request.target == "passengers":
                query = query.where(User.role == UserRole.PASSENGER)
            # Bloklangan foydalanuvchilarni o'chirish
            query = query.where(User.is_blocked == False)
            result = await session.execute(query)
            users = result.scalars().all()
            # Xabar yuborish
            success_count = 0
            failed_count = 0
            failed_users = []
            for user in users:
                try:
                    await bot.send_message(
                        chat_id=user.user_id,
                        text=request.message,
                        parse_mode="HTML"
                    )
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    failed_users.append({
                        'user_id': user.user_id,
                        'username': user.username or user.phone_number,
                        'error': str(e)
                    })
                    logger.warning(f"Failed to send message to {user.user_id}: {e}")
            logger.info(
                f"Broadcast sent by {current_user['username']}: "
                f"target={request.target}, success={success_count}, failed={failed_count}"
            )
            return {
                'success': True,
                'message': 'Xabar yuborildi',
                'stats': {
                    'total': len(users),
                    'success': success_count,
                    'failed': failed_count
                },
                'failed_users': failed_users[:10]  # Faqat birinchi 10 tasi
            }
    except Exception as e:
        logger.error(f"Failed to send broadcast: {e}")
        raise HTTPException(status_code=500, detail=str(e))
__all__ = ['router']
