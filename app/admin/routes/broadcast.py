"""
app/admin/routes/broadcast.py
BROADCAST MESSAGES (XABAR YUBORISH)
ENDPOINTS:
- GET /broadcast - Xabar yuborish sahifasi
- POST /api/broadcast/send - Xabar yuborish
"""
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from typing import Optional
from loguru import logger
from aiogram.types import BufferedInputFile
from app.admin.auth import get_current_user
from app.core.database import get_session
from app.models.user import User, UserRole
from sqlalchemy import select

router = APIRouter(prefix="/broadcast", tags=["broadcast"])

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
    message: str = Form(...),
    target: str = Form(...),
    photo_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    file_type: Optional[str] = Form(None), # 'photo' or 'video'
    current_user: dict = Depends(get_current_user)
):
    """
    Xabar yuborish (Matn, Rasm yoki Video)
    """
    check_glavni_admin(current_user)
    
    if not message or len(message.strip()) == 0:
        raise HTTPException(status_code=400, detail="Xabar bo'sh bo'lishi mumkin emas")
        
    if target not in ["all", "admins", "drivers", "passengers"]:
        raise HTTPException(status_code=400, detail="Noto'g'ri target")

    try:
        from app.bot.main import bot
        
        async with get_session() as session:
            # 1. Foydalanuvchilarni olish
            query = select(User)
            if target == "admins":
                query = query.where(User.role.in_([UserRole.ADMIN, UserRole.GLAVNI_ADMIN]))
            elif target == "drivers":
                query = query.where(User.role == UserRole.DRIVER)
            elif target == "passengers":
                query = query.where(User.role == UserRole.PASSENGER)
            
            query = query.where(User.is_blocked == False)
            result = await session.execute(query)
            users = result.scalars().all()
            
            if not users:
                return {'success': True, 'message': 'Foydalanuvchilar topilmadi', 'stats': {'total': 0}}

            # 2. Faylni tayyorlash (agar bo'lsa)
            uploaded_file_id = None
            input_file = None
            
            # Agar fayl yuklangan bo'lsa
            if file and file_type in ['photo', 'video']:
                file_content = await file.read()
                filename = file.filename or f"file.{'jpg' if file_type == 'photo' else 'mp4'}"
                input_file = BufferedInputFile(file_content, filename=filename)
            
            # 3. Xabar yuborish loop
            success_count = 0
            failed_count = 0
            failed_users = []
            
            # Birinchi userga yuborib ko'ramiz (to get file_id)
            first_user = users[0]
            remaining_users = users[1:]
            
            try:
                sent_msg = None
                if input_file:
                    if file_type == 'photo':
                        sent_msg = await bot.send_photo(chat_id=first_user.user_id, photo=input_file, caption=message, parse_mode="HTML")
                        if sent_msg.photo:
                            uploaded_file_id = sent_msg.photo[-1].file_id
                    elif file_type == 'video':
                        sent_msg = await bot.send_video(chat_id=first_user.user_id, video=input_file, caption=message, parse_mode="HTML")
                        if sent_msg.video:
                            uploaded_file_id = sent_msg.video.file_id
                elif photo_url:
                    sent_msg = await bot.send_photo(chat_id=first_user.user_id, photo=photo_url, caption=message, parse_mode="HTML")
                else:
                    sent_msg = await bot.send_message(chat_id=first_user.user_id, text=message, parse_mode="HTML")
                
                success_count += 1
            except Exception as e:
                failed_count += 1
                failed_users.append({'user_id': first_user.user_id, 'error': str(e)})
                logger.error(f"Failed to send to first user {first_user.user_id}: {e}")
                # Don't stop, try others (but without file_id optimization if failed)

            # Qolganlarga yuborish
            for user in remaining_users:
                try:
                    if uploaded_file_id:
                        # Use file_id (Fast!)
                        if file_type == 'photo':
                            await bot.send_photo(chat_id=user.user_id, photo=uploaded_file_id, caption=message, parse_mode="HTML")
                        elif file_type == 'video':
                            await bot.send_video(chat_id=user.user_id, video=uploaded_file_id, caption=message, parse_mode="HTML")
                    elif photo_url:
                        await bot.send_photo(chat_id=user.user_id, photo=photo_url, caption=message, parse_mode="HTML")
                    elif input_file:
                        # Fallback if first failed (Re-upload - Slow but works)
                        # We need to create NEW BufferedInputFile for each request or reset pointer? 
                        # BufferedInputFile holds bytes, reusable? Yes.
                        if file_type == 'photo':
                            await bot.send_photo(chat_id=user.user_id, photo=input_file, caption=message, parse_mode="HTML")
                        elif file_type == 'video':
                            await bot.send_video(chat_id=user.user_id, video=input_file, caption=message, parse_mode="HTML")
                    else:
                        await bot.send_message(chat_id=user.user_id, text=message, parse_mode="HTML")
                    
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    failed_users.append({'user_id': user.user_id, 'error': str(e)})
            
            logger.info(
                f"Broadcast finished: success={success_count}, failed={failed_count}"
            )
            
            return {
                'success': True,
                'message': 'Xabar yuborildi',
                'stats': {
                    'total': len(users),
                    'success': success_count,
                    'failed': failed_count
                },
                'failed_users': failed_users[:10]
            }

    except Exception as e:
        logger.error(f"Failed to send broadcast: {e}")
        raise HTTPException(status_code=500, detail=str(e))

__all__ = ['router']

