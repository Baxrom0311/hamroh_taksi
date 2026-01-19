"""
app/bot/middlewares/state_guard.py

STATE POLLUTION GUARD MIDDLEWARE

BU MIDDLEWARE NIMA QILADI:
- Driver va Passenger state'larini ajratadi
- Noto'g'ri state'ni avtomatik tozalaydi
- State corruption'ni oldini oladi

MUAMMO:
Agar bitta user ham driver, ham passenger bo'lsa, 
state'lar aralashib ketadi va bug'lar paydo bo'ladi.

YECHIM:
User rolini tekshirib, noto'g'ri state'ni tozalash
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.models.user import get_user_by_id, UserRole
from app.core.database import get_session


class StateGuardMiddleware(BaseMiddleware):
    """
    State pollution'ni oldini oluvchi middleware
    
    NIMA QILADI:
    1. User rolini database'dan oladi
    2. Current state'ni tekshiradi
    3. Agar noto'g'ri role'ning state'i bo'lsa, tozalaydi
    
    ISHLATISH:
        dp.message.middleware(StateGuardMiddleware())
        dp.callback_query.middleware(StateGuardMiddleware())
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Middleware asosiy logikasi
        """
        # User ID olish
        user_id = None
        if isinstance(event, Message):
            if event.from_user:
                user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        
        if not user_id:
            # User yo'q - handler'ga o'tkazamiz
            return await handler(event, data)
        
        # State context olish
        state: FSMContext = data.get("state")
        if not state:
            # State yo'q - handler'ga o'tkazamiz
            return await handler(event, data)
        
        try:
            # Database'dan user rolini olish
            async with get_session() as session:
                user = await get_user_by_id(session, user_id)
                
                if not user:
                    # User ro'yxatdan o'tmagan - state tozalash
                    current_state = await state.get_state()
                    if current_state:
                        logger.info(f"Clearing state for unregistered user {user_id}")
                        await state.clear()
                    return await handler(event, data)
                
                # Current state'ni tekshirish
                current_state = await state.get_state()
                
                if current_state:
                    # State pollution tekshiruvi
                    should_clear = False
                    reason = ""
                    
                    # Driver user uchun Passenger state
                    if user.role == UserRole.DRIVER and "Passenger" in current_state:
                        should_clear = True
                        reason = f"Driver user {user_id} had Passenger state"
                    
                    # Passenger user uchun Driver state
                    elif user.role == UserRole.PASSENGER and "Driver" in current_state:
                        should_clear = True
                        reason = f"Passenger user {user_id} had Driver state"
                    
                    # Agar noto'g'ri state bo'lsa, tozalash
                    if should_clear:
                        logger.warning(
                            f"🚨 STATE POLLUTION DETECTED: {reason} "
                            f"(state: {current_state}). Clearing..."
                        )
                        await state.clear()
                        
                        # User'ga xabar (optional)
                        if isinstance(event, Message):
                            await event.answer(
                                "⚠️ Tizim xatosi aniqlandi va tuzatildi.\n"
                                "Iltimos, jarayonni qaytadan boshlang."
                            )
        
        except Exception as e:
            # Middleware xatosi handler'ni to'xtatmasligi kerak
            logger.error(f"StateGuardMiddleware error: {e}")
        
        # Handler'ni chaqirish
        return await handler(event, data)


__all__ = ['StateGuardMiddleware']
