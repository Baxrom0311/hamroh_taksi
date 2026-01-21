"""
app/bot/middlewares/rate_limit.py

RATE LIMITING MIDDLEWARE - Spam va DDoS protection

LIMITS:
- 10 requests per minute per user
- 30 requests per 5 minutes per user
- Auto-ban after excessive violations
"""
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery
from loguru import logger
import time
from typing import Optional

from app.core.redis_client import redis_client


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate limiting middleware
    
    LOGIKA:
    1. Har bir user uchun request count Redis'da saqlanadi
    2. Limit oshsa - warning
    3. Ko'p marta limit oshsa - temp ban
    """
    
    def __init__(
        self,
        rate_limit: int = 20,  # 10 requests
        time_window: int = 60,  # per minute
        ban_threshold: int = 10,  # 5 violations
        ban_duration: int = 300  # 5 minutes ban
    ):
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.ban_threshold = ban_threshold
        self.ban_duration = ban_duration
        super().__init__()
    
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Middleware handler
        """
        # Get user ID and reply target safely (Aiogram v3 passes concrete event like Message/CallbackQuery)
        # Explicit type definition to help Pylance narrowing
        user_id = None
        reply_target: Optional[TelegramObject] = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            reply_target = event
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            reply_target = event.message
        elif isinstance(event, Update):
            if event.message:
                user_id = event.message.from_user.id if event.message.from_user else None
                reply_target = event.message
            elif event.callback_query:
                user_id = event.callback_query.from_user.id if event.callback_query.from_user else None
                reply_target = event.callback_query.message
        
        if not user_id:
            # No user ID - skip rate limiting
            return await handler(event, data)
        try:
            # Check if banned
            ban_key = f"rate_limit:ban:{user_id}"
            is_banned = await redis_client.get(ban_key)
            
            if is_banned:
                logger.warning(f"🚫 Rate limit: User {user_id} is banned")
                
                if reply_target and isinstance(reply_target, (Message, CallbackQuery)):
                     # Note: CallbackQuery.answer sets a toast, Message.answer sends a message
                     # We prefer sending a message if possible
                    if isinstance(reply_target, Message):
                        msg_target: Message = reply_target
                        await msg_target.answer(
                            "⚠️ Siz vaqtincha bloklangansiz.\n\n"
                            "Iltimos, 5 daqiqadan keyin qayta urinib ko'ring."
                        )
                    elif isinstance(reply_target, CallbackQuery):
                        cb_target: CallbackQuery = reply_target
                        await cb_target.answer("⚠️ Siz vaqtincha bloklangansiz (5 daqiqa).",show_alert=True)
                
                return  # Don't call handler
            
            # Rate limit check
            request_key = f"rate_limit:requests:{user_id}"
            violation_key = f"rate_limit:violations:{user_id}"
            
            # Get current request count
            request_count_raw = await redis_client.get(request_key)
            
            if request_count_raw is None:
                # First request in this window
                await redis_client.set(request_key, 1, ex=self.time_window)
                request_count = 1
            else:
                request_count = int(request_count_raw)
                
                if request_count >= self.rate_limit:
                    # Rate limit exceeded
                    logger.warning(
                        f"⚠️ Rate limit exceeded: user_id={user_id}, "
                        f"count={request_count}"
                    )
                    
                    # Increment violations
                    violation_count_raw = await redis_client.get(violation_key)
                    
                    if violation_count_raw is None:
                        violation_count = 1
                    else:
                        violation_count = int(violation_count_raw) + 1
                    
                    await redis_client.set(
                        violation_key,
                        violation_count,
                        ex=300  # 5 minutes
                    )
                    
                    # Ban if too many violations
                    if violation_count >= self.ban_threshold:
                        await redis_client.set(
                            ban_key,
                            1,
                            ex=self.ban_duration
                        )
                        
                        logger.error(
                            f"🚫 User {user_id} banned for {self.ban_duration}s "
                            f"due to {violation_count} violations"
                        )
                        
                        if reply_target and isinstance(reply_target, (Message, CallbackQuery)):
                            if isinstance(reply_target, Message):
                                msg_target: Message = reply_target
                                await msg_target.answer(
                                    "🚫 <b>Siz bloklangansiz!</b>\n\n"
                                    "Sabab: Ko'p marta limit oshirildi\n"
                                    f"Davomiyligi: {self.ban_duration // 60} daqiqa",
                                    parse_mode="HTML"
                                )
                            elif isinstance(reply_target, CallbackQuery):
                                cb_target: CallbackQuery = reply_target
                                await cb_target.answer(
                                "🚫 Siz bloklangansiz! Ko'p limit oshirildi.",
                                show_alert=True
                                )
                        
                        # Track metric
                        from app.core.metrics import ERROR_OCCURRED
                        ERROR_OCCURRED.labels(
                            error_type='rate_limit_ban',
                            handler='middleware'
                        ).inc()
                        
                        return  # Don't call handler
                    
                    # Warning message
                    if reply_target and isinstance(reply_target, (Message, CallbackQuery)):
                        if isinstance(reply_target, Message):
                            msg_target: Message = reply_target
                            await msg_target.answer(
                                f"⚠️ Sekinroq! ({request_count}/{self.rate_limit})\n\n"
                                "Iltimos, biroz kuting."
                            )
                        elif isinstance(reply_target, CallbackQuery):
                            cb_target: CallbackQuery = reply_target
                            await cb_target.answer(
                                "⚠️ Sekinroq! Iltimos, biroz kuting.",
                                show_alert=True
                            )
                    
                    return  # Don't call handler
                
                # Increment request count
                await redis_client.incr(request_key)
        
        except Exception as exc:
            logger.error(f"RateLimitMiddleware fallback (redis issue): {exc}")
            # Fail open: allow handler to proceed on Redis errors
        
        # Call the handler regardless if no early return happened
        return await handler(event, data)


__all__ = ['RateLimitMiddleware']
