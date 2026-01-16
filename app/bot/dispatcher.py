"""
app/bot/dispatcher.py

BOT DISPATCHER - Handler'larni ro'yxatga olish

BU FAYL NIMA QILADI:
- Barcha handler router'larini yig'ish
- Middleware'larni qo'shish
- Dispatcher'ni konfiguratsiya qilish

ISHLATISH:
    from app.bot.dispatcher import setup_dispatcher
    
    dp = Dispatcher(storage=storage)
    setup_dispatcher(dp)
"""

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger
from typing import Optional
from app.core.redis_client import redis_client


# ============================================
# DISPATCHER SETUP
# ============================================

def setup_dispatcher(storage: Optional[RedisStorage] = None) -> Dispatcher:
    """
    Dispatcher'ni sozlash va handler'larni ro'yxatga olish
    
    Args:
        storage: FSM storage (Redis)
    
    Returns:
        Configured Dispatcher
    """
    
    # Storage
    if storage is None:
        storage = RedisStorage(redis=redis_client.client)
    
    # Dispatcher
    dp = Dispatcher(storage=storage)
    
    logger.info("🔄 Setting up dispatcher...")
    
    # ============================================
    # MIDDLEWARE'LAR
    # ============================================
    
    from app.bot.middlewares.auth import AuthMiddleware
    from app.bot.middlewares.logging import LoggingMiddleware
    from app.bot.middlewares.rate_limit import RateLimitMiddleware  # ✅ Yangi
    
    # Rate limiting (BIRINCHI!) - Spam protection
    dp.message.middleware(RateLimitMiddleware(
        rate_limit=10,  # 10 requests per minute
        time_window=60,
        ban_threshold=5,
        ban_duration=300  # 5 min ban
    ))
    dp.callback_query.middleware(RateLimitMiddleware())  # ✅
    
    # Message middleware'lar
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(AuthMiddleware())
    
    # Callback query middleware'lar
    dp.callback_query.middleware(AuthMiddleware())
    
    logger.info("✅ Middlewares registered")
    
    # ============================================
    # HANDLER ROUTER'LAR
    # ============================================
    
    # Start va Registration
    from app.bot.handlers.start import router as start_router
    from app.bot.handlers.registration import router as registration_router
    
    # Driver handlers
    from app.bot.handlers.driver.main_menu import router as driver_menu_router
    from app.bot.handlers.driver.orders import router as driver_orders_router
    from app.bot.handlers.driver.trip_handlers import router as driver_trip_router  # ✅ Yangi
    from app.bot.handlers.driver.balance import router as driver_balance_router
    from app.bot.handlers.driver.support import router as driver_support_router
    from app.bot.handlers.driver.location import router as driver_location_router
    
    # Passenger handlers
    from app.bot.handlers.passenger.main_menu import router as passenger_menu_router
    from app.bot.handlers.passenger.booking import router as passenger_booking_router
    from app.bot.handlers.passenger.driver_info import router as passenger_driver_info_router
    from app.bot.handlers.passenger.active_orders import router as passenger_active_orders_router  # ✅ Yangi
    from app.bot.handlers.passenger.history import router as passenger_history_router  # ✅ Yangi
    from app.bot.handlers.passenger.rating import router as passenger_rating_router
    from app.bot.handlers.passenger.support import router as passenger_support_router
    
    # Router'larni qo'shish (TARTIB MUHIM!)
    # Birinchi qo'shilgan router'lar birinchi tekshiriladi
    
    dp.include_router(start_router)
    dp.include_router(registration_router)
    
    # Driver router'lar
    dp.include_router(driver_menu_router)
    dp.include_router(driver_orders_router)
    dp.include_router(driver_trip_router)  # ✅ Yangi
    dp.include_router(driver_balance_router)
    dp.include_router(driver_support_router)
    dp.include_router(driver_location_router)
    
    # Passenger router'lar
    dp.include_router(passenger_menu_router)
    dp.include_router(passenger_booking_router)
    dp.include_router(passenger_active_orders_router)  # ✅ Yangi
    dp.include_router(passenger_history_router)  # ✅ Yangi
    dp.include_router(passenger_rating_router)
    dp.include_router(passenger_support_router)
    dp.include_router(passenger_driver_info_router)
    
    logger.success("✅ All handlers registered")
    
    # Handler'lar soni
    message_handlers = len(dp.message.handlers)
    callback_handlers = len(dp.callback_query.handlers)
    
    logger.info(
        f"📊 Registered handlers: "
        f"{message_handlers} message, "
        f"{callback_handlers} callback"
    )
    
    return dp


# ============================================
# ERROR HANDLERS
# ============================================

async def on_startup_error(error: Exception):
    """Startup xato"""
    logger.error(f"❌ Startup error: {error}")


async def on_shutdown_error(error: Exception):
    """Shutdown xato"""
    logger.error(f"❌ Shutdown error: {error}")


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.bot.dispatcher
    """
    
    print("\n🧪 Testing Dispatcher Setup...\n")
    
    # Setup
    dp = setup_dispatcher()
    
    print(f"✅ Dispatcher configured!")
    print(f"   Message handlers: {len(dp.message.handlers)}")
    print(f"   Callback handlers: {len(dp.callback_query.handlers)}")
    print(f"   Middlewares: {len(dp.message.middleware)}")
    
    print("\n✅ Dispatcher test completed!\n")


__all__ = ['setup_dispatcher']
