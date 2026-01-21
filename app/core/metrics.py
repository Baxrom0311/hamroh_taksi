"""
app/core/metrics.py

PROMETHEUS METRICS - Production monitoring

METRICS:
- Orders: created, completed, cancelled
- Trips: active, completed
- Drivers: active count, queue size
- Performance: order duration, response time
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from functools import wraps
import time
from loguru import logger
from typing import Optional
# ============================================
# COUNTERS (Increment only)
# ============================================

# Orders
ORDER_CREATED = Counter(
    'orders_created_total',
    'Total orders created',
    ['route']
)

ORDER_COMPLETED = Counter(
    'orders_completed_total',
    'Total completed orders',
    ['route']
)

ORDER_CANCELLED = Counter(
    'orders_cancelled_total',
    'Total cancelled orders',
    ['reason']
)

ORDER_ACCEPTED = Counter(
    'orders_accepted_total',
    'Total accepted orders'
)

# Trips
TRIP_CREATED = Counter(
    'trips_created_total',
    'Total trips created'
)

TRIP_COMPLETED = Counter(
    'trips_completed_total',
    'Total completed trips'
)

# Drivers
DRIVER_REGISTERED = Counter(
    'drivers_registered_total',
    'Total drivers registered'
)

DRIVER_BLOCKED = Counter(
    'drivers_blocked_total',
    'Total drivers blocked'
)

# Passengers
PASSENGER_REGISTERED = Counter(
    'passengers_registered_total',
    'Total passengers registered'
)

# Transactions
BALANCE_TOPUP = Counter(
    'balance_topup_total',
    'Total balance top-ups',
    ['driver_id']
)

COMMISSION_DEDUCTED = Counter(
    'commission_deducted_total',
    'Total commission deductions'
)

COMMISSION_REFUNDED = Counter(
    'commission_refunded_total',
    'Total commission refunds'
)

# Errors
ERROR_OCCURRED = Counter(
    'errors_total',
    'Total errors',
    ['error_type', 'handler']
)

# ============================================
# HISTOGRAMS (Distributions)
# ============================================

# Order processing time
ORDER_DURATION = Histogram(
    'order_duration_seconds',
    'Order duration from created to completed',
    buckets=[60, 120, 300, 600, 900, 1800, 3600]  # 1min, 2min, 5min, 10min, 15min, 30min, 1h
)

TRIP_DURATION = Histogram(
    'trip_duration_seconds',
    'Trip duration',
    buckets=[300, 600, 900, 1800, 3600, 7200]  # 5min, 10min, 15min, 30min, 1h, 2h
)

# Response times
API_RESPONSE_TIME = Histogram(
    'api_response_time_seconds',
    'API response time',
    ['endpoint', 'method'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5]
)

BOT_HANDLER_TIME = Histogram(
    'bot_handler_time_seconds',
    'Bot handler processing time',
    ['handler_name'],
    buckets=[0.1, 0.5, 1, 2, 5, 10]
)

# Database query time
DB_QUERY_TIME = Histogram(
    'db_query_time_seconds',
    'Database query execution time',
    ['query_type'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2]
)

# ============================================
# GAUGES (Can go up/down)
# ============================================

# Active counts
ACTIVE_DRIVERS = Gauge(
    'active_drivers',
    'Number of active drivers'
)

ACTIVE_TRIPS = Gauge(
    'active_trips',
    'Number of active trips'
)

PENDING_ORDERS = Gauge(
    'pending_orders',
    'Number of pending orders'
)

DRIVER_QUEUE_SIZE = Gauge(
    'driver_queue_size',
    'Driver queue size',
    ['route_id']
)

# System
TOTAL_DRIVERS = Gauge(
    'total_drivers',
    'Total registered drivers'
)

TOTAL_PASSENGERS = Gauge(
    'total_passengers',
    'Total registered passengers'
)

# ============================================
# INFO (Static metadata)
# ============================================

APP_INFO = Info(
    'app_info',
    'Application information'
)

APP_INFO.info({
    'version': '1.0.0',
    'app_name': 'Hamroh Taxi Bot',
    'environment': 'production'
})

# ============================================
# DECORATORS
# ============================================
 
def track_time(metric: Histogram, label: Optional[str] = None):
    """
    Decorator to track function execution time
    
    Usage:
        @track_time(BOT_HANDLER_TIME, 'start_booking')
        async def start_booking(message: Message):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if label:
                    metric.labels(handler_name=label).observe(duration)
                else:
                    metric.observe(duration)
        return wrapper
    return decorator


def count_errors(error_type: str, handler: str = 'unknown'):
    """
    Decorator to count errors
    
    Usage:
        @count_errors('database_error', 'create_order')
        async def create_order():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                ERROR_OCCURRED.labels(
                    error_type=error_type,
                    handler=handler
                ).inc()
                raise
        return wrapper
    return decorator


# ============================================
# HELPER FUNCTIONS
# ============================================

async def update_active_counts():
    """
    Update active metrics (called periodically by Celery Beat)
    """
    from app.core.database import get_session
    from app.models.driver import Driver
    from app.models.trip import Trip, TripStatus
    from app.models.order import Order, OrderStatus
    from sqlalchemy import select, func
    
    async with get_session() as session:
        # Active drivers
        result = await session.execute(
            select(func.count(Driver.driver_id))
            .where(Driver.is_active == True)
        )
        ACTIVE_DRIVERS.set(result.scalar() or 0)
        
        # Active trips
        result = await session.execute(
            select(func.count(Trip.trip_id))
            .where(Trip.status == TripStatus.ACTIVE)
        )
        ACTIVE_TRIPS.set(result.scalar() or 0)
        
        # Pending orders
        result = await session.execute(
            select(func.count(Order.order_id))
            .where(Order.status == OrderStatus.PENDING)
        )
        PENDING_ORDERS.set(result.scalar() or 0)
        
        # Total counts
        result = await session.execute(select(func.count(Driver.driver_id)))
        TOTAL_DRIVERS.set(result.scalar() or 0)
        
        from app.models.passenger import Passenger
        result = await session.execute(select(func.count(Passenger.passenger_id)))
        TOTAL_PASSENGERS.set(result.scalar() or 0)


__all__ = [
    'ORDER_CREATED',
    'ORDER_COMPLETED',
    'ORDER_CANCELLED',
    'TRIP_CREATED',
    'TRIP_COMPLETED',
    'ORDER_DURATION',
    'TRIP_DURATION',
    'track_time',
    'count_errors',
    'update_active_counts',
    'ERROR_OCCURRED'
]
