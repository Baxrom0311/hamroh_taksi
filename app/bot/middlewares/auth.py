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
            async with get_session() as session:
                await update_last_active(session, user_id)
        
        return await handler(event, data)
