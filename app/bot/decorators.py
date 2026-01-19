"""
app/bot/decorators.py - FIXED VERSION

BOT HANDLER DECORATORS

Bu fayl handler'lar uchun utility decorator'larni o'z ichiga oladi.
Session management va user fetching'ni avtomatlashtiradi.

DECORATORS:
- @with_driver_session - Driver handler'lar uchun (session + driver auto-fetch)
- @with_passenger_session - Passenger handler'lar uchun (session + passenger auto-fetch)
- @with_user_session - Umumiy handler'lar uchun (faqat session)

CRITICAL: SkipHandler raise qilish kerak, return qilmaslik kerak!
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
    
    STRICT MODE:
    1. User borligini tekshiradi
    2. User.role == DRIVER ekanligini tekshiradi
    3. Agar role != DRIVER -> SkipHandler (Passenger handlerlariga o'tkazish)
    4. Agar role == DRIVER va driver record yo'q -> ERROR (Stop propagation)
    """
    
    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user_id = event.from_user.id if event.from_user else None
        
        if not user_id:
            logger.error("User ID not found in event")
            raise SkipHandler()
        
        async with get_session() as session:
            try:
                # 1. User va Role tekshirish
                from app.models.user import get_user_by_id, UserRole
                user = await get_user_by_id(session, user_id)
                
                if not user:
                    # Ro'yxatdan o'tmagan -> Skip
                    raise SkipHandler()
                
                if user.role != UserRole.DRIVER:
                    # Haydovchi emas (demak passenger yoki admin) -> Skip
                    raise SkipHandler()
                    
                # 2. Driver record olish
                driver = await get_driver_by_user_id(session, user_id)
                
                if not driver:
                    # DATA INTEGRITY ERROR: Role driver, lekin profil yo'q
                    logger.critical(f"Data integrity error: User {user_id} is DRIVER but has no driver profile!")
                    error_msg = "❌ Tizim xatoligi: Haydovchi profili topilmadi. Iltimos @support'ga murojaat qiling."
                    if isinstance(event, Message):
                        await event.answer(error_msg)
                    else:
                        await event.answer(error_msg, show_alert=True)
                    return # Stop propagation (SkipHandler EMAS!)
                
                # Handler'ni chaqirish
                return await func(event, session, driver, *args, **kwargs)
            
            except SkipHandler:
                raise
            except Exception as e:
                logger.error(f"Error in driver handler {func.__name__}: {e}")
                err_text = "⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                if isinstance(event, Message):
                    await event.answer(err_text)
                else:
                    await event.answer(err_text, show_alert=True)
                raise
    
    return wrapper


# ============================================
# PASSENGER SESSION DECORATOR
# ============================================

def with_passenger_session(func: Callable):
    """
    Passenger handler'lar uchun session va passenger'ni avtomatik olish
    """
    
    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user_id = event.from_user.id if event.from_user else None
        
        if not user_id:
            logger.error("User ID not found in event")
            raise SkipHandler()
        
        async with get_session() as session:
            try:
                # 1. User va Role tekshirish
                from app.models.user import get_user_by_id, UserRole
                user = await get_user_by_id(session, user_id)
                
                if not user:
                    raise SkipHandler()
                
                if user.role != UserRole.PASSENGER:
                    # Passenger emas -> Skip
                    raise SkipHandler()

                # 2. Passenger record olish
                passenger = await get_passenger_by_user_id(session, user_id)
                
                if not passenger:
                    # DATA INTEGRITY ERROR
                    logger.critical(f"Data integrity error: User {user_id} is PASSENGER but has no profile!")
                    error_msg = "❌ Tizim xatoligi: Yo'lovchi profili topilmadi. @support"
                    if isinstance(event, Message):
                        await event.answer(error_msg)
                    else:
                        await event.answer(error_msg, show_alert=True)
                    return # Stop propagation
                
                # Handler'ni chaqirish
                return await func(event, session, passenger, *args, **kwargs)
            
            except SkipHandler:
                raise
            except Exception as e:
                logger.error(f"Error in passenger handler {func.__name__}: {e}")
                err_text = "⚠️ Xatolik yuz berdi."
                if isinstance(event, Message):
                    await event.answer(err_text)
                else:
                    await event.answer(err_text, show_alert=True)
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
            raise SkipHandler()
        
        async with get_session() as session:
            try:
                from app.models.user import get_user_by_id
                user = await get_user_by_id(session, user_id)
                
                if not user or not user.is_admin:
                    # Shunchaki ignore (admin bo'lmaganlar uchun handler ishlamaydi)
                    raise SkipHandler()
                
                # Handler'ni chaqirish
                return await func(event, session, user, *args, **kwargs)
            
            except SkipHandler:
                raise
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
