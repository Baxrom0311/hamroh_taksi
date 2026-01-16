"""
app/bot/main.py

TELEGRAM BOT - ASOSIY FAYL

BU FAYL NIMA QILADI:
- Bot'ni ishga tushiradi
- Dispatcher sozlaydi
- Handler'larni ro'yxatga oladi
- Database va Redis'ga ulanadi

ISHLATISH:
    python -m app.bot.main
"""

import asyncio
import sys
from loguru import logger

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.settings import settings
from app.core.database import init_database, close_database
from app.core.redis_client import init_redis, close_redis, redis_client


# ============================================
# BOT VA DISPATCHER YARATISH
# ============================================

# Bot instance
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML  # HTML formatting
    )
)

# FSM Storage (Redis)
dp: Dispatcher | None = None

# ============================================
# HANDLER'LARNI RO'YXATGA OLISH
# ============================================

# Handlers are now registered via dispatcher.py


# ============================================
# STARTUP / SHUTDOWN
# ============================================

async def on_startup():
    """
    Bot ishga tushganda
    """
    global dp
    logger.info("🚀 Starting bot...")
    
    # Database
    await init_database()
    
    # Redis & Dispatcher
    await init_redis()
    from app.bot.dispatcher import setup_dispatcher
    storage = RedisStorage(redis=redis_client.client)
    dp = setup_dispatcher(storage=storage)
    
    # Bot ma'lumotlarini olish
    bot_info = await bot.get_me()
    logger.success(f"✅ Bot started: @{bot_info.username}")
    
    # Adminlarga xabar (opsional)
    if settings.admin_ids_list:
        for admin_id in settings.admin_ids_list:
            try:
                await bot.send_message(
                    admin_id,
                    "🚀 <b>Bot ishga tushdi!</b>\n\n"
                    f"Username: @{bot_info.username}\n"
                    f"Environment: {settings.ENVIRONMENT}",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")


async def on_shutdown():
    """
    Bot o'chganda
    """
    logger.info("🔄 Shutting down bot...")
    
    # Adminlarga xabar
    if settings.admin_ids_list:
        for admin_id in settings.admin_ids_list:
            try:
                await bot.send_message(
                    admin_id,
                    "🔴 <b>Bot to'xtatildi!</b>",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    # Database
    await close_database()
    
    # Redis
    await close_redis()
    
    # Bot session
    await bot.session.close()
    
    logger.info("✅ Bot stopped")


# ============================================
# MAIN FUNCTION
# ============================================

async def main():
    """
    Asosiy funksiya
    """
    try:
        # Startup
        await on_startup()
        
        # Polling
        logger.info("📡 Starting polling...")
        if dp is None:
            raise ValueError("Dispatcher is not initialized")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    
    except KeyboardInterrupt:
        logger.info("⚠️ Bot stopped by user (Ctrl+C)")
    
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        raise
    
    finally:
        await on_shutdown()


# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    """
    Bot'ni ishga tushirish:
    python -m app.bot.main
    """
    
    # Logging sozlash
    logger.remove()  # Default handler'ni o'chirish
    
    # Console'ga yozish
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=settings.LOG_LEVEL
    )
    
    # Faylga yozish
    logger.add(
        settings.LOG_FILE_PATH,
        rotation="00:00",  # Har kuni yangi fayl
        retention="30 days",  # 30 kun saqlash
        compression="zip",  # Eski loglarni zip qilish
        level=settings.LOG_LEVEL
    )
    
    # Bot'ni ishga tushirish
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Bot gracefully stopped")