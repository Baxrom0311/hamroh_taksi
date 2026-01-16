"""
app/bot/decorators.py

BOT HANDLER DECORATORS

Bu fayl handler'lar uchun utility decorator'larni o'z ichiga oladi.
Session management va user fetching'ni avtomatlashtiradi.

DECORATORS:
- @with_driver_session - Driver handler'lar uchun (session + driver auto-fetch)
- @with_passenger_session - Passenger handler'lar uchun (session + passenger auto-fetch)
- @with_user_session - Umumiy handler'lar uchun (faqat session)
"""

from functools import wraps
from typing import Callable, Optional
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher.event.bases import SkipHandler
from loguru import logger

from app.core.database import get_session
from app.models.driver import get_driver_by_user_id
from app.models.passenger import get_passenger_by_user_id
from app.bot.keyboards.driver import get_driver_main_menu
from app.bot.keyboards.passenger import get_passenger_main_menu


# ============================================
# DRIVER SESSION DECORATOR
# ============================================

def with_driver_session(func: Callable):
    """
    Driver handler'lar uchun session va driver'ni avtomatik olish
    
    ISHLATISH:
        @with_driver_session
        async def my_handler(message: Message, session, driver):
            # session va driver allaqachon mavjud
            await message.answer(f"Haydovchi: {driver.full_name}")
    
    NIMA QILADI:
    1. Session ochadi
    2. Driver'ni user_id bo'yicha topadi
    3. Agar driver yo'q bo'lsa - xato qaytaradi
    4. Session va driver'ni handler'ga beradi
    5. Xato bo'lsa - session'ni yopadi
    
    Args:
        func: Handler function (message/callback, session, driver)
    
    Returns:
        Wrapped function
    """
    
    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user_id = event.from_user.id if event.from_user else None
        
        if not user_id:
            logger.error("User ID not found in event")
            return
        
        async with get_session() as session:
            try:
                # Driver'ni olish
                driver = await get_driver_by_user_id(session, user_id)
                
                if not driver:
                    # Driver topilmadi — boshqa handlerlarga o'tkazamiz
                    logger.debug(f"Driver not found for user_id={user_id}, skipping driver handler")
                    raise SkipHandler()
                
                # Handler'ni chaqirish (session va driver bilan)
                return await func(event, session, driver, *args, **kwargs)
            
            except SkipHandler:
                # Shartga to'g'ri kelmadi, boshqa handlerlar ishlashini davom ettiramiz
                return
            except Exception as e:
                logger.error(f"Error in handler {func.__name__}: {e}")
                
                error_msg = "⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                
                if isinstance(event, Message):
                    await event.answer(error_msg)
                else:
                    await event.answer(error_msg, show_alert=True)
                
                raise
    
    return wrapper


# ============================================
# PASSENGER SESSION DECORATOR
# ============================================

def with_passenger_session(func: Callable):
    """
    Passenger handler'lar uchun session va passenger'ni avtomatik olish
    
    ISHLATISH:
        @with_passenger_session
        async def my_handler(message: Message, session, passenger):
            # session va passenger allaqachon mavjud
            await message.answer(f"Yo'lovchi: {passenger.full_name}")
    
    Args:
        func: Handler function (message/callback, session, passenger)
    
    Returns:
        Wrapped function
    """
    
    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user_id = event.from_user.id if event.from_user else None
        
        if not user_id:
            logger.error("User ID not found in event")
            return
        
        async with get_session() as session:
            try:
                # Passenger'ni olish
                passenger = await get_passenger_by_user_id(session, user_id)
                
                if not passenger:
                    # Passenger topilmadi
                    error_msg = (
                        "❌ <b>Xatolik</b>\n\n"
                        "Siz yo'lovchi sifatida ro'yxatdan o'tmagansiz.\n\n"
                        "Iltimos, /start buyrug'ini yuboring va ro'yxatdan o'ting."
                    )
                    
                    if isinstance(event, Message):
                        await event.answer(
                            error_msg,
                            reply_markup=get_passenger_main_menu(),
                            parse_mode="HTML"
                        )
                    else:
                        await event.answer(
                            "Yo'lovchi topilmadi",
                            show_alert=True
                        )
                    
                    logger.warning(f"Passenger not found for user_id={user_id}")
                    return
                
                # Handler'ni chaqirish (session va passenger bilan)
                return await func(event, session, passenger, *args, **kwargs)
            
            except Exception as e:
                logger.error(f"Error in handler {func.__name__}: {e}")
                
                error_msg = "⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                
                if isinstance(event, Message):
                    await event.answer(error_msg)
                else:
                    await event.answer(error_msg, show_alert=True)
                
                raise
    
    return wrapper


# ============================================
# GENERIC SESSION DECORATOR
# ============================================

def with_session(func: Callable):
    """
    Umumiy handler'lar uchun faqat session
    
    ISHLATISH:
        @with_session
        async def my_handler(message: Message, session):
            # session mavjud, custom logic yozish mumkin
            result = await session.execute(...)
    
    Args:
        func: Handler function (message/callback, session)
    
    Returns:
        Wrapped function
    """
    
    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        async with get_session() as session:
            try:
                return await func(event, session, *args, **kwargs)
            
            except Exception as e:
                logger.error(f"Error in handler {func.__name__}: {e}")
                
                error_msg = "⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                
                if isinstance(event, Message):
                    await event.answer(error_msg)
                else:
                    await event.answer(error_msg, show_alert=True)
                
                raise
    
    return wrapper


# ============================================
# ADMIN SESSION DECORATOR
# ============================================

def with_admin_session(func: Callable):
    """
    Admin handler'lar uchun session va admin-user'ni avtomatik olish
    
    Args:
        func: Handler function (message/callback, session, user)
    
    Returns:
        Wrapped function
    """
    
    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user_id = event.from_user.id if event.from_user else None
        
        if not user_id:
            return
        
        async with get_session() as session:
            try:
                from app.models.user import get_user_by_id
                user = await get_user_by_id(session, user_id)
                
                if not user or not user.is_admin:
                    # Shunchaki ignore (admin bo'lmaganlar uchun handler ishlamaydi)
                    return
                
                # Handler'ni chaqirish
                return await func(event, session, user, *args, **kwargs)
            
            except Exception as e:
                logger.error(f"Error in admin handler {func.__name__}: {e}")
                raise
    
    return wrapper


__all__ = [
    'with_driver_session',
    'with_passenger_session',
    'with_admin_session',
    'with_session'
]
