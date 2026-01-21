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
from typing import Callable, Dict, Any, Awaitable, Optional
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
        state: Optional[FSMContext] = data.get("state")  # type: ignore[assignment]
        if not state:
            # State yo'q - handler'ga o'tkazamiz
            return await handler(event, data)
        
        try:
            # 1. Check FSM (Cache)
            data_context = await state.get_data()
            user_role = data_context.get("role")
            
            if user_role:
                # Cache hit - use stored role
                logger.debug(f"StateGuard: Role hit from cache for {user_id}: {user_role}")
            else:
                # Cache miss - fetch from DB
                async with get_session() as session:
                    user = await get_user_by_id(session, user_id)
                    
                    if not user:
                        # User ro'yxatdan o'tmagan - state tozalash
                        current_state = await state.get_state()
                        if current_state:
                            logger.info(f"Clearing state for unregistered user {user_id}")
                            await state.clear()
                        return await handler(event, data)
                    
                    # Store in FSM
                    user_role = user.role
                    await state.update_data(role=user_role)
            
            # Current state'ni tekshirish
            current_state = await state.get_state()
            
            if current_state:
                # State pollution tekshiruvi
                should_clear = False
                reason = ""
                
                # Driver user uchun Passenger state
                if user_role == UserRole.DRIVER and "Passenger" in current_state:
                    should_clear = True
                    reason = f"Driver user {user_id} had Passenger state"
                
                # Passenger user uchun Driver state
                elif user_role == UserRole.PASSENGER and "Driver" in current_state:
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
            # ✅ CRITICAL FIX: Fail-safe exception handling
            # Don't silently swallow errors - clear state and notify user
            logger.error(f"StateGuardMiddleware error: {e}", exc_info=True)
            
            # Clear potentially corrupted state
            try:
                await state.clear()
            except Exception as clear_error:
                logger.error(f"Failed to clear state after error: {clear_error}")
            
            # Notify user of the issue
            if isinstance(event, Message):
                try:
                    await event.answer(
                        "⚠️ Tizim xatosi yuz berdi. State tozalandi.\n"
                        "Iltimos, /start dan qayta boshlang."
                    )
                except Exception:
                    pass  # Can't notify, but we tried
            
            # Don't proceed to handler with corrupted state - return early
            return
        
        try:
            return await handler(event, data)
        except Exception as exc:
            # ✅ CRITICAL: Don't catch aiogram control flow exceptions
            from aiogram.dispatcher.event.bases import SkipHandler
            
            # Note: CancelHandler doesn't exist in aiogram 3.x, only SkipHandler
            if isinstance(exc, SkipHandler):
                # This is intentional - let it propagate
                raise
            
            # Now we have a real error - log it with full details
            import traceback
            exc_type = type(exc).__name__
            exc_msg = str(exc)
            tb_str = "".join(traceback.format_tb(exc.__traceback__, limit=10))
            
            logger.error(
                f"StateGuardMiddleware handler error:\n"
                f"  Type: {exc_type}\n"
                f"  Message: {exc_msg}\n"
                f"  Traceback:\n{tb_str}"
            )

            if state:
                try:
                    await state.clear()
                    logger.info("State cleared after exception")
                except Exception as clear_error:
                    logger.error(f"Failed to clear state: {clear_error}")

            if isinstance(event, Message):
                try:
                    await event.answer(
                        "⚠️ Tizim xatosi yuz berdi. State tozalandi.\n"
                        "Iltimos, /start dan qayta boshlang."
                    )
                except Exception:
                    pass
            return


__all__ = ['StateGuardMiddleware']
