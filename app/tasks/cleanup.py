"""
app/tasks/cleanup.py

CLEANUP TASKS - Kunlik va soatlik tozalash

BU TASK'LAR NIMA QILADI:
- Eski ma'lumotlarni tozalash
- Ban count'larni reset qilish
- Statistika generatsiya qilish
- Health check

QACHON ISHGA TUSHADI:
- Celery Beat orqali avtomatik (cron)
"""

from datetime import datetime, timedelta
from sqlalchemy import delete, update, select, func
from loguru import logger

from app.core.celery_app import celery_app
from app.core.database import get_session
from app.models.driver import Driver
from app.models.passenger import Passenger
from app.models.order import Order, OrderStatus
from app.models.transaction import TransactionLog
from app.core.redis_client import redis_client
from app.core.celery_app import celery_app, async_to_sync # <--- import


# ============================================
# KUNLIK CLEANUP (har kuni 03:00)
# ============================================

@celery_app.task
@async_to_sync # <--- Decorator qo'shildi
async def daily_cleanup():
    """
    Kunlik tozalash
    
    NIMA QILADI:
    1. 30 kundan eski transaction log'larni o'chirish
    2. Bekor qilingan va 7 kundan eski buyurtmalarni o'chirish
    3. Eski Redis key'larni tozalash
    """
    logger.info("🧹 Starting daily cleanup...")
    
    async with get_session() as session:
        # 1. Eski transaction log'lar (30 kun)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        result = await session.execute(
            delete(TransactionLog)
            .where(TransactionLog.created_at < thirty_days_ago)
        )
        
        deleted_logs = result.rowcount
        logger.info(f"🗑️ Deleted {deleted_logs} old transaction logs")
        
        # 2. Bekor qilingan buyurtmalar (7 kun)
        seven_days_ago = datetime.now() - timedelta(days=7)
        
        result = await session.execute(
            delete(Order)
            .where(Order.status == OrderStatus.CANCELLED)
            .where(Order.cancelled_at < seven_days_ago)

        )
        
        deleted_orders = result.rowcount
        logger.info(f"🗑️ Deleted {deleted_orders} old cancelled orders")
        
        await session.commit()
    
    # 3. Redis tozalash
    await cleanup_redis_keys()
    
    logger.success("✅ Daily cleanup completed!")
    
    return {
        'deleted_logs': deleted_logs,
        'deleted_orders': deleted_orders
    }


# ============================================
# NIGHTLY DRIVER RESET (har kuni 03:00)
# ============================================

@celery_app.task
@async_to_sync
async def nightly_driver_reset():
    """
    Tungi 3:00 da barcha driverlarni reset qilish
    
    NIMA QILADI:
    1. is_active = False (agar is_on_trip=False bo'lsa)
    2. Navbatdan o'chirish
    3. Inactivity counter tozalash
    
    MAQSAD:
    - Eskirgan sessiyalarni tozalash
    - Navbatni kattalashishini oldini olish
    """
    logger.info("🌙 Starting nightly driver reset...")
    
    async with get_session() as session:
        # 1. Safardalik bo'lmagan driverlarni deactivate qilish
        result = await session.execute(
            update(Driver)
            .where(Driver.is_active == True)
            .where(Driver.is_on_trip == False)  # Safarda bo'lganlarni o'zgartirmaymiz
            .values(
                is_active=False,
                current_route_id=None,
                available_seats=0
            )
        )
        deactivated = result.rowcount
        await session.commit()
    
    # 2. Barcha navbatlarni tozalash
    from app.services.queue_service import driver_queue
    queues_cleared = await driver_queue.remove_all_drivers_from_queues()
    
    logger.success(
        f"✅ Nightly reset: {deactivated} drivers deactivated, "
        f"{queues_cleared} queues cleared"
    )
    
    return {
        'deactivated_drivers': deactivated,
        'queues_cleared': queues_cleared
    }


# ============================================
# BAN COUNT RESET (har kuni 00:00)
# ============================================

@celery_app.task
@async_to_sync # <--- Decorator qo'shildi
async def reset_daily_ban_counts():
    """
    Kunlik ban count'larni reset qilish
    
    NIMA QILADI:
    - Barcha driver'larning ban_count_today = 0
    - Vaqti o'tgan block'larni ochish
    """

    logger.info("🔄 Resetting daily ban counts...")
    
    async with get_session() as session:
        # 1. Ban count reset
        await session.execute(
            update(Driver)
            .values(ban_count_today=0)
        )
        
        # 2. Vaqti o'tgan block'larni ochish
        now = datetime.now()
        
        result = await session.execute(
            update(Driver)
            .where(Driver.is_blocked == True)
            .where(Driver.blocked_until <= now)
            .values(
                is_blocked=False,
                blocked_until=None,
                block_reason=None
            )
        )
        
        unblocked_count = result.rowcount
        
        await session.commit()
        
        logger.success(f"✅ Ban counts reset, {unblocked_count} drivers unblocked")
        
        return {'unblocked': unblocked_count}



# ============================================
# CANCELLATION COUNT RESET (har soat)
# ============================================

@celery_app.task
@async_to_sync # <--- Decorator qo'shildi
async def reset_hourly_cancellation_counts():
    """
    Soatlik bekor qilish count'larni reset qilish
    
    Passenger'larning cancellation_count_hour'ni tozalash
    """
    
    logger.info("🔄 Resetting hourly cancellation counts...")
    
    async with get_session() as session:
        # 1 soat oldin
        one_hour_ago = datetime.now() - timedelta(hours=1)
        
        await session.execute(
            update(Passenger)
            .where(Passenger.last_cancellation_time < one_hour_ago)
            .values(cancellation_count_hour=0)
        )
        
        await session.commit()
        
        logger.success("✅ Hourly cancellation counts reset")
    

# ============================================
# STATISTIKA (har kuni 23:55)
# ============================================

@celery_app.task
@async_to_sync # <--- Decorator qo'shildi
async def generate_daily_statistics():

    """
    Kunlik statistika generatsiya qilish
    
    NIMA QILADI:
    - Bugungi safarlar soni
    - Bugungi daromad
    - Aktiv driver/passenger soni
    - Redis'ga saqlash
    """
    
    logger.info("📊 Generating daily statistics...")
    
    async with get_session() as session:
        today_start = datetime.now().replace(hour=0, minute=0, second=0)
        
        # Bugungi completed trips
        trips_result = await session.execute(
            select(func.count(Order.order_id))
            .where(Order.status == OrderStatus.COMPLETED)
            .where(Order.completed_at >= today_start)
        )
        trips_count = trips_result.scalar() or 0
        
        # Bugungi daromad (commission'lar)
        revenue_result = await session.execute(
            select(func.sum(Order.commission_amount))
            .where(Order.status == OrderStatus.COMPLETED)
            .where(Order.completed_at >= today_start)
        )
        revenue = float(revenue_result.scalar() or 0)
        
        # Aktiv driver'lar
        active_drivers_result = await session.execute(
            select(func.count(Driver.driver_id))
            .where(Driver.is_active == True)
        )
        active_drivers = active_drivers_result.scalar() or 0
        
        # Jami driver'lar
        total_drivers_result = await session.execute(
            select(func.count(Driver.driver_id))
        )
        total_drivers = total_drivers_result.scalar() or 0
        
        # Jami passenger'lar
        total_passengers_result = await session.execute(
            select(func.count(Passenger.passenger_id))
        )
        total_passengers = total_passengers_result.scalar() or 0
    
    # Statistika
    stats = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'trips_count': trips_count,
        'revenue': revenue,
        'active_drivers': active_drivers,
        'total_drivers': total_drivers,
        'total_passengers': total_passengers
    }
    
    # Redis'ga saqlash (30 kun)
    stats_key = f"stats:daily:{stats['date']}"
    await redis_client.set(stats_key, stats, ex=86400 * 30)
    
    logger.success(f"✅ Daily statistics generated: {trips_count} trips, {revenue:,.0f} so'm")
    
    return stats

# ============================================
# HEALTH CHECK (har 5 daqiqada)
# ============================================

@celery_app.task
@async_to_sync # <--- Decorator qo'shildi
async def health_check():
    """
    Tizim health check
    
    NIMA TEKSHIRADI:
    - Database connection
    - Redis connection
    - Celery worker'lar
    """
    
    health = {
        'timestamp': datetime.now().isoformat(),
        'database': False,
        'redis': False,
        'celery': False
    }
    
    # 1. Database
    try:
        from app.core.database import check_database_health
        db_health = await check_database_health()
        health['database'] = db_health['status'] == 'healthy'
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    # 2. Redis
    try:
        health['redis'] = await redis_client.ping()
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
    
    # 3. Celery
    try:
        from celery import Celery
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        health['celery'] = stats is not None and len(stats) > 0
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
    
    # Health status
    all_healthy = all(
        v for k, v in health.items() if k != 'timestamp'
        )
    
    if all_healthy:
        logger.debug("✅ Health check: All systems operational")
    else:
        logger.warning(f"⚠️ Health check: Some systems down - {health}")
    
    # Redis'ga saqlash
    await redis_client.set('health:latest', health, ex=300)
    
    return health
    

# ============================================
# REDIS KEY'LARNI TOZALASH
# ============================================

async def cleanup_redis_keys():
    """
    Eski Redis key'larni tozalash
    
    PATTERN'LAR:
    - lock:* (eski lock'lar)
    - session:* (1 kundan eski)
    - cache:* (expire bo'lmagan)
    """
    
    logger.info("🧹 Cleaning up Redis keys...")
    
    try:
        # 1. Eski lock'lar (expire yo'q)
        from app.core.locks import clear_expired_locks
        locks_cleared = await clear_expired_locks()
        
        # 2. Eski session'lar
        session_count = 0
        async for key in redis_client.client.scan_iter(match="session:*", count=100):
            ttl = await redis_client.ttl(key)
            if ttl == -1:  # Expire yo'q
                await redis_client.delete(key)
                session_count += 1
        
        logger.info(f"🗑️ Cleaned up {locks_cleared} locks, {session_count} sessions")
        
    except Exception as e:
        logger.error(f"Redis cleanup error: {e}")


# ============================================
# MANUAL CLEANUP (Admin)
# ============================================

@celery_app.task
@async_to_sync # <--- Decorator qo'shildi
async def manual_cleanup_orders(days: int = 30):
    """
    Manual buyurtmalar tozalash (Admin)
    
    Args:
        days: Necha kundan eski buyurtmalar
    """
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    async with get_session() as session:
        result = await session.execute(
            delete(Order)
            .where(Order.status.in_([OrderStatus.COMPLETED, OrderStatus.CANCELLED]))
            .where(Order.created_at < cutoff_date)
        )
        
        deleted = result.rowcount
        await session.commit()
        
        logger.info(f"🗑️ Manual cleanup: deleted {deleted} orders older than {days} days")
        
        return {'deleted': deleted}
    

__all__ = [
    'daily_cleanup',
    'nightly_driver_reset',
    'reset_daily_ban_counts',
    'reset_hourly_cancellation_counts',
    'generate_daily_statistics',
    'health_check',
    'manual_cleanup_orders'
]