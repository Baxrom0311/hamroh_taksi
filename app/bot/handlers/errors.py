"""
app/bot/handlers/errors.py

GLOBAL ERROR HANDLER

BU MODULE NIMA QILADI:
- Bot'dagi barcha ushlanmagan xatoliklarni (Exception) tutadi
- Adminga xabar beradi (agar sozlangan bo'lsa)
- Userga tushunarli xabar qaytaradi (Silent fail bo'lmaydi)

ISHLATISH:
Dispatcherga 'dp.errors.register(global_error_handler)' orqali ulanadi.
"""
import traceback
from loguru import logger
from aiogram import Router, F
from aiogram.types import ErrorEvent, Message, CallbackQuery
from aiogram.filters import ExceptionTypeFilter
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

router = Router()

@router.error(ExceptionTypeFilter(TelegramBadRequest))
async def handle_bad_request(event: ErrorEvent):
    """
    Osilib qolgan (old) callback query'larni indamay o'tkazib yuborish
    """
    logger.warning(f"⚠️ Bad Request (likely old query): {event.exception}")
    return True # Prevent crash

@router.error(ExceptionTypeFilter(Exception))
async def global_error_handler(event: ErrorEvent):
    """
    Global xatolik ushlagich
    """
    # Xatolik haqida log
    logger.error(f"🚨 Unhandled exception in bot: {event.exception}")
    logger.debug(traceback.format_exc())
    
    # Update obyektini olish
    if event.update.message:
        message = event.update.message
        user = message.from_user
        
        try:
            await message.answer(
                "😔 <b>Kechirasiz, texnik xatolik yuz berdi.</b>\n\n"
                "Bizning dasturchilar bu haqida xabardor qilindi.\n"
                "Iltimos, birozdan so'ng qayta urinib ko'ring yoki /start ni bosing.",
                parse_mode="HTML"
            )
        except TelegramAPIError:
            pass  # Agar javob qaytarish ham o'xshamasa (masalan user bloklagan)

    elif event.update.callback_query:
        callback = event.update.callback_query
        try:
            await callback.answer(
                "❌ Xatolik yuz berdi. Iltimos qayta urinib ko'ring.",
                show_alert=True
            )
        except TelegramAPIError:
            pass
    
    # TODO: Notify Admins
    # from config.settings import settings
    # if settings.ADMIN_IDS: ...
    
    return True  # Xatolik "ushlandi", dastur qulamaydi.
