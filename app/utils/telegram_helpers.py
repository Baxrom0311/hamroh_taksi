"""
app/utils/telegram_helpers.py

TELEGRAM HELPER UTILITIES

Bu fayl Telegram bot bilan ishlashda kerak bo'ladigan umumiy
yordamchi funksiyalarni o'z ichiga oladi.

✅ PRODUCTION FIX: Specific exception handling for Telegram errors
"""

import asyncio
from typing import Optional, Any
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramAPIError
)
from loguru import logger


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    **kwargs: Any
) -> bool:
    """
    Xavfsiz Telegram xabar yuborish (exception handling bilan)
    
    Args:
        bot: Aiogram Bot instance
        chat_id: Telegram user/chat ID
        text: Xabar matni
        parse_mode: HTML yoki Markdown
        reply_markup: Klaviatura (optional)
        **kwargs: Qo'shimcha aiogram parametrlar
    
    Returns:
        True - Xabar yuborildi
        False - Xabar yuborilmadi (user blocked, chat not found, etc.)
    
    ISHLATISH:
        from app.utils.telegram_helpers import safe_send_message
        from app.bot.main import bot
        
        success = await safe_send_message(
            bot, 
            user_id, 
            "✅ Safar boshlandi!",
            parse_mode="HTML"
        )
        
        if not success:
            logger.warning(f"Could not notify user {user_id}")
    
    ✅ PRODUCTION BENEFIT:
    - User bot'ni block qilsa, retry qilmaydi (Celery worker'ini band qilmaydi)
    - Flood wait holatida avtomatik kutadi va retry qiladi
    - Aniq error log'lar
    """
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            **kwargs
        )
        return True
    
    except TelegramForbiddenError:
        # User blocked the bot - DON'T RETRY
        logger.warning(
            f"❌ User {chat_id} has blocked the bot. "
            f"Message not sent (this is normal)."
        )
        return False
    
    except TelegramBadRequest as e:
        # Invalid request (chat not found, message too long, etc.) - DON'T RETRY
        error_msg = str(e).lower()
        
        if 'chat not found' in error_msg:
            logger.warning(f"❌ Chat {chat_id} not found (user deleted account?)")
        elif 'message is too long' in error_msg:
            logger.error(f"❌ Message too long for {chat_id}. Text length: {len(text)}")
        elif 'wrong file identifier' in error_msg or 'wrong type' in error_msg:
            logger.error(f"❌ Invalid file/media in message to {chat_id}: {e}")
        else:
            logger.warning(f"❌ Bad request to {chat_id}: {e}")
        
        return False
    
    except TelegramRetryAfter as e:
        # Flood wait - WAIT and RETRY
        retry_after = e.retry_after
        logger.warning(
            f"⏳ Flood wait for chat {chat_id}. "
            f"Waiting {retry_after} seconds before retry..."
        )
        
        await asyncio.sleep(retry_after + 1)  # +1 for safety
        
        # Recursive retry (only once)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                **kwargs
            )
            logger.info(f"✅ Message sent to {chat_id} after flood wait")
            return True
        except Exception as retry_error:
            logger.error(f"❌ Failed to send after flood wait: {retry_error}")
            return False
    
    except TelegramAPIError as e:
        # Generic Telegram API error - log and return False
        logger.error(f"❌ Telegram API error for {chat_id}: {e}")
        return False
    
    except Exception as e:
        # Unexpected error (network, etc.)
        logger.error(
            f"❌ Unexpected error sending message to {chat_id}: {e}",
            exc_info=True
        )
        return False


async def safe_edit_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    **kwargs: Any
) -> bool:
    """
    Xavfsiz xabar tahrirlash
    
    Returns:
        True - Tahrirlandi
        False - Tahrirlanmadi (xabar juda eski, o'chirilgan, etc.)
    """
    
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            **kwargs
        )
        return True
    
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        
        if 'message is not modified' in error_msg:
            # Xabar o'zgarmagan - bu xato emas
            logger.debug(f"Message {message_id} in {chat_id} not modified (same content)")
            return True
        elif 'message to edit not found' in error_msg:
            logger.warning(f"Message {message_id} in {chat_id} not found (deleted?)")
            return False
        elif 'message can\'t be edited' in error_msg:
            logger.warning(f"Message {message_id} in {chat_id} too old to edit")
            return False
        else:
            logger.warning(f"Bad request editing message {message_id}: {e}")
            return False
    
    except TelegramForbiddenError:
        logger.warning(f"User {chat_id} blocked bot, cannot edit message")
        return False
    
    except Exception as e:
        logger.error(f"Unexpected error editing message {message_id}: {e}")
        return False


__all__ = ['safe_send_message', 'safe_edit_message']
