from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, CallbackQuery
from loguru import logger


class LoggingMiddleware(BaseMiddleware):
    """
    Logging middleware
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        if isinstance(event, Message) or isinstance(event, CallbackQuery):
            user = event.from_user
            text_preview = getattr(event, "text", None)
            logger.info(
                f"Message from user {user.id} (@{user.username}): " # type: ignore
                f"{text_preview[:50] if text_preview else 'NO TEXT'}"
            )
        
        return await handler(event, data)
