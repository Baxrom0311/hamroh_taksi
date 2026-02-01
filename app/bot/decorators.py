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
from app.models.user import UserRole
from app.bot.keyboards.driver import get_driver_main_menu
from app.bot.keyboards.passenger import get_passenger_main_menu


# ============================================
# GENERIC DECORATOR FACTORY (DRY Pattern)
# ============================================

def _create_role_session_decorator(
    role: "UserRole",
    entity_getter: Callable,
    entity_name: str
):
    """
    Generic decorator factory for role-based session management
    
    ✅ CODE QUALITY: Eliminates 70+ lines of duplicate code
    
    Args:
        role: UserRole enum (DRIVER, PASSENGER, ADMIN)
        entity_getter: Function to get entity (get_driver_by_user_id, etc.)
        entity_name: Entity name for error messages ("haydovchi", "yo'lovchi")
    
    Returns:
        Decorator function
    """
    def decorator(func: Callable):
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
                    
                    if user.role != role:
                        # Noto'g'ri role -> Skip to other handlers
                        raise SkipHandler()
                        
                    # 2. Entity (driver/passenger) record olish
                    entity = await entity_getter(session, user_id)
                    
                        # DATA INTEGRITY ERROR: Role mavjud, profil yo'q
                        logger.warning(
                            f"Data integrity error: User {user_id} is {role.value} "
                            f"but has no {entity_name} profile!"
                        )
                        
                        warning_msg = (
                            f"⚠️ <b>Sizning profilingiz topilmadi</b> (ehtimol o'chirilgan).\n\n"
                            f"Iltimos, qayta ro'yxatdan o'tish uchun /start ni bosing."
                        )
                        
                        if isinstance(event, Message):
                            await event.answer(warning_msg)
                        else:
                            await event.answer(warning_msg, show_alert=True)
                        return  # Stop propagation
                    
                    # Handler'ni chaqirish
                    return await func(event, session, entity, *args, **kwargs)
                
                except SkipHandler:
                    raise
                except Exception as e:
                    logger.error(f"Error in {entity_name} handler {func.__name__}: {e}")
                    err_text = "⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                    if isinstance(event, Message):
                        await event.answer(err_text)
                    else:
                        await event.answer(err_text, show_alert=True)
                    raise
        
        return wrapper
    return decorator


# ============================================
# DRIVER SESSION DECORATOR
# ============================================

def with_driver_session(func: Callable):
    """
    Driver handler'lar uchun session va driver'ni avtomatik olish
    
    ✅ REFACTORED: Uses generic factory to eliminate code duplication
    
    STRICT MODE:
    1. User borligini tekshiradi
    2. User.role == DRIVER ekanligini tekshiradi
    3. Agar role != DRIVER -> SkipHandler (Passenger handlerlariga o'tkazish)
    4. Agar role == DRIVER va driver record yo'q -> ERROR (Stop propagation)
    """
    from app.models.user import UserRole
    return _create_role_session_decorator(
        role=UserRole.DRIVER,
        entity_getter=get_driver_by_user_id,
        entity_name="haydovchi"
    )(func)


# ============================================
# PASSENGER SESSION DECORATOR
# ============================================

def with_passenger_session(func: Callable):
    """
    Passenger handler'lar uchun session va passenger'ni avtomatik olish
    
    ✅ REFACTORED: Uses generic factory to eliminate code duplication
    """
    from app.models.user import UserRole
    return _create_role_session_decorator(
        role=UserRole.PASSENGER,
        entity_getter=get_passenger_by_user_id,
        entity_name="yo'lovchi"
    )(func)


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
