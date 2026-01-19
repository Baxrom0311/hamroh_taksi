from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types.base import TelegramObject
from aiogram.types import Message, CallbackQuery

from app.core.database import get_session
from app.models.user import update_last_active


class AuthMiddleware(BaseMiddleware):
    """
    Auth middleware - har bir Telegram event uchun
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        # event turini tekshirish (Message yoki CallbackQuery)
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id
        
        if user_id:
            from app.core.redis_client import redis_client
            
            # Redis throttling (5 minutda 1 marta update)
            throttle_key = f"user:last_active:{user_id}"
            should_update = not await redis_client.exists(throttle_key)
            
            if should_update:
                async with get_session() as session:
                    await update_last_active(session, user_id)
                # Redis key set (5 min TTL)
                await redis_client.set(throttle_key, "1", ex=300)
        
        return await handler(event, data)
