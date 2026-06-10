"""
app/core/celery_app.py

CELERY NIMA?
- Distributed task queue (async vazifalar uchun)
- Background jobs (Telegram xabar yuborish, email, etc)
- Scheduled tasks (Celery Beat)

NIMAGA KERAK:
- Telegram rate limiting (30 msg/sec)
- Heavy tasks (Database query, AI, etc)
- Cron jobs (Kunlik tozalash, statistika)

ISHLATISH:
    from app.core.celery_app import celery_app
    
    @celery_app.task
    def my_task(arg):
        # Code...
        pass
    
    # Task'ni chaqirish
    my_task.delay(arg)  # Async
"""
import functools
from celery.signals import worker_process_init
import asyncio
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue
from loguru import logger

from config.settings import settings
import threading
_thread_locals = threading.local()

def get_worker_loop():
    if not hasattr(_thread_locals, 'loop'):
        _thread_locals.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_thread_locals.loop)
    return _thread_locals.loop
_worker_loop = get_worker_loop()

# ============================================
# CELERY APP YARATISH
# ============================================

    
celery_app = Celery(
    'hamroh_bot',
    broker=settings.celery_broker,        # Redis (task queue)
    backend=settings.celery_backend,      # Redis (results)
    include=[
        'app.tasks.notifications',  # Notification tasks
        'app.tasks.matching',       # Order matching tasks
        'app.tasks.cleanup'         # Cleanup tasks
    ]
)

def async_to_sync(func):
    """
    Senior Stable Wrapper:
    Faqat worker jarayoni uchun yaratilgan yagona loopdan foydalanadi.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        global _worker_loop
        
        # Agar loop bo'lmasa yoki yopilgan bo'lsa
        if _worker_loop is None or _worker_loop.is_closed():
            _worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_worker_loop)
            
        # Vazifani asyncio.Task ichida yurgizamiz (aiohttp/timeout uchun shart)
        async def task_wrapper():
            return await asyncio.create_task(func(*args, **kwargs))
            
        return _worker_loop.run_until_complete(task_wrapper())
    return wrapper

@worker_process_init.connect
def init_worker_process(*args, **kwargs):
    """
    Worker jarayoni ochilishi bilan loop va ulanishlarni bir marta yaratadi.
    """
    global _worker_loop
    # Yangi loop yaratamiz
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)

    from app.core.database import init_database
    from app.core.redis_client import init_redis
    
    # Bazani va Redisni aynan shu loop ichida o't oldiramiz
    _worker_loop.run_until_complete(init_database())
    _worker_loop.run_until_complete(init_redis())
    
    logger.success("⚙️ Celery Worker: Persistent Loop and DB connections locked to this process.")

# ============================================
# CELERY CONFIG
# ============================================

celery_app.conf.update(
    broker_connection_retry_on_startup=True,

    # ============================================
    # SERIALIZATION (Ma'lumot formati)
    # ============================================
    task_serializer='json',          # Task'lar JSON formatda
    accept_content=['json'],         # Faqat JSON qabul qilish
    result_serializer='json',        # Natijalar JSON formatda
    
    # ============================================
    # TIMEZONE
    # ============================================
    timezone='Asia/Tashkent',        # O'zbekiston vaqti
    enable_utc=False,                # UTC o'chirish
    
    # ============================================
    # TASK ROUTING (Queue'lar)
    # ============================================
    task_default_queue='default',   # Default queue nomi
    task_default_exchange='default',
    task_default_routing_key='default',
    
    # Queue'lar
    task_queues=(
        # Default queue (barcha task'lar)
        Queue(
            'default',
            Exchange('default'),
            routing_key='default'
        ),
        
        # High priority queue (muhim task'lar)
        Queue(
            'high_priority',
            Exchange('high_priority'),
            routing_key='high_priority'
        ),
        
        # Low priority queue (kam muhim)
        Queue(
            'low_priority',
            Exchange('low_priority'),
            routing_key='low_priority'
        ),
    ),
    
    # ============================================
    # RATE LIMITING
    # ============================================
    task_default_rate_limit='30/s',  # 30 ta task/soniya (Telegram limit)
    
    # ============================================
    # RETRY SETTINGS
    # ============================================
    task_acks_late=True,              # Task bajarilgandan keyin ACK
    task_reject_on_worker_lost=True,  # Worker o'chsa - retry qilish
    
    # ============================================
    # WORKER SETTINGS
    # ============================================
    worker_prefetch_multiplier=4,     # Har bir worker 4 ta task oladi
    worker_max_tasks_per_child=1000,  # 1000 ta task'dan keyin restart
    
    # ============================================
    # RESULT BACKEND (Natijalar)
    # ============================================
    result_expires=3600,              # Natijalar 1 soat saqlanadi
    result_persistent=False,          # Natijalarni saqlamaslik (tez)
    
    # ============================================
    # ERROR HANDLING
    # ============================================
    task_soft_time_limit=300,         # 5 daqiqa (soft limit)
    task_time_limit=600,              # 10 daqiqa (hard limit)
    
    # ============================================
    # LOGGING
    # ============================================
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s',
)


# ============================================
# CELERY BEAT SCHEDULE (Cron jobs)
# ============================================

celery_app.conf.beat_schedule = {
    # ============================================
    # Kunlik cleanup (har kuni 03:00 da)
    # ============================================
    'daily-cleanup': {
        'task': 'app.tasks.cleanup.daily_cleanup',
        'schedule': crontab(hour="3", minute="0"),  # 03:00
        'options': {'queue': 'low_priority'}
    },
    
    # ============================================
    # Ban count reset (har kuni 00:00 da)
    # ============================================
    'reset-daily-ban-counts': {
        'task': 'app.tasks.cleanup.reset_daily_ban_counts',
        'schedule': crontab(hour="0", minute="0"),  # 00:00
        'options': {'queue': 'low_priority'}
    },
    
    # ============================================
    # Kunlik statistika (har kuni 23:55 da)
    # ============================================
    'generate-daily-stats': {
        'task': 'app.tasks.cleanup.generate_daily_statistics',
        'schedule': crontab(hour="23", minute="55"),  # 23:55
        'options': {'queue': 'low_priority'}
    },
    
    # ============================================
    # Driver cancellation count reset (har soat)
    # ============================================
    'reset-hourly-cancellation': {
        'task': 'app.tasks.cleanup.reset_hourly_cancellation_counts',
        'schedule': crontab(minute="0"),  # Har soat 00 daqiqada
        'options': {'queue': 'low_priority'}
    },
    
    # ============================================
    # Monitoring health check (har 5 daqiqada)
    # ============================================
    'health-check': {
        'task': 'app.tasks.cleanup.health_check',
        'schedule': 300.0,  # 5 daqiqa (soniya)
        'options': {'queue': 'high_priority'}
    },
    
    # ============================================
    # Nightly driver reset (har kuni 03:00 da)
    # ============================================
    'nightly-driver-reset': {
        'task': 'app.tasks.cleanup.nightly_driver_reset',
        'schedule': crontab(hour="3", minute="0"),  # 03:00
        'options': {'queue': 'low_priority'}
    },

    # ============================================
    # Ghost driver cleanup (har 30 daqiqada)
    # ============================================
    'ghost-driver-cleanup': {
        'task': 'app.tasks.cleanup.cleanup_ghost_drivers',
        'schedule': 1800.0,  # 30 daqiqa
        'options': {'queue': 'low_priority'}
    },
}


# ============================================
# CELERY SIGNALS (Events)
# ============================================

@celery_app.on_after_configure.connect # type: ignore
def setup_periodic_tasks(sender, **kwargs):
    """
    Celery ishga tushgandan keyin
    
    BU YERDA:
    - Periodic task'larni qo'shish mumkin
    - Initialization kod
    """
    logger.info("✅ Celery periodic tasks configured")


@celery_app.task(bind=True)
def debug_task(self):
    """
    Debug task (test qilish uchun)
    
    ISHLATISH:
        from app.core.celery_app import debug_task
        debug_task.delay()
    """
    logger.info(f'Request: {self.request!r}')
    return 'Debug task completed!'


# ============================================
# TASK BASE CLASS (Custom behavior)
# ============================================

class CallbackTask(celery_app.Task):
    """
    Custom task class
    
    BU NIMA:
    - Har bir task uchun custom behavior
    - Error handling
    - Logging
    - Retry logic
    """
    
    def on_success(self, retval, task_id, args, kwargs):
        """Task muvaffaqiyatli tugaganda"""
        logger.info(f'✅ Task {self.name}[{task_id}] succeeded: {retval}')
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Task xato berganda"""
        logger.error(f'❌ Task {self.name}[{task_id}] failed: {exc}')
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Task retry qilganda"""
        logger.warning(f'⚠️ Task {self.name}[{task_id}] retrying: {exc}')


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_celery_stats() -> dict:
    """
    Celery statistikasi
    
    Returns:
        {
            'active_tasks': int,
            'scheduled_tasks': int,
            'workers': list
        }
    
    ISHLATISH:
        stats = get_celery_stats()
        print(f"Active tasks: {stats['active_tasks']}")
    """
    try:
        inspect = celery_app.control.inspect()
        
        # Active tasks
        active = inspect.active()
        active_count = sum(len(tasks) for tasks in (active or {}).values())
        
        # Scheduled tasks
        scheduled = inspect.scheduled()
        scheduled_count = sum(len(tasks) for tasks in (scheduled or {}).values())
        
        # Workers
        stats = inspect.stats()
        workers = list(stats.keys()) if stats else []
        
        return {
            'active_tasks': active_count,
            'scheduled_tasks': scheduled_count,
            'workers': workers,
            'worker_count': len(workers)
        }
    
    except Exception as e:
        logger.error(f"Failed to get Celery stats: {e}")
        return {
            'active_tasks': 0,
            'scheduled_tasks': 0,
            'workers': [],
            'worker_count': 0
        }


def purge_all_tasks():
    """
    Barcha task'larni o'chirish (XAVFLI!)
    
    DIQQAT: Faqat development'da ishlatish!
    """
    if not settings.is_production:
        celery_app.control.purge()
        logger.warning("⚠️ All tasks purged!")
    else:
        logger.error("❌ Cannot purge tasks in production!")


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.core.celery_app
    """
    print("\n🧪 Testing Celery App...\n")
    
    # Debug task
    result = debug_task.delay() # type: ignore
    print(f"Task ID: {result.id}")
    print(f"Task status: {result.status}")
    
    # Stats
    stats = get_celery_stats()
    print(f"\nCelery Stats:")
    print(f"  Workers: {stats['worker_count']}")
    print(f"  Active tasks: {stats['active_tasks']}")
    print(f"  Scheduled tasks: {stats['scheduled_tasks']}")
    
    print("\n✅ Celery test completed!\n")
    
    print("""
    ========================================
    CELERY WORKER ISHGA TUSHIRISH:
    ========================================
    
    # Worker ishga tushirish
    celery -A app.core.celery_app worker --loglevel=info
    
    # Beat ishga tushirish (cron jobs)
    celery -A app.core.celery_app beat --loglevel=info
    
    # Worker + Beat (bitta jarayon)
    celery -A app.core.celery_app worker --beat --loglevel=info
    
    # Flower (monitoring UI)
    celery -A app.core.celery_app flower
    
    # Stats
    celery -A app.core.celery_app inspect active
    celery -A app.core.celery_app inspect scheduled
    celery -A app.core.celery_app inspect stats
    
    ========================================
    """)