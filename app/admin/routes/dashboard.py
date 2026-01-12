
"""
app/admin/routes/dashboard.py

DASHBOARD - Asosiy statistika va monitoring

ENDPOINTS:
- GET /dashboard/stats - Asosiy statistika
- GET /dashboard/realtime - Real-time ma'lumotlar
- GET /dashboard/charts/trips - Safarlar grafigi
- GET /dashboard/charts/revenue - Daromad grafigi
"""

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
from fastapi import HTTPException

from app.admin.auth import get_current_user
from app.core.database import get_session
from app.core.redis_client import redis_client
from sqlalchemy import select, func, and_


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ============================================
# MAIN STATS
# ============================================

@router.get("/stats")
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_user)
):
    """
    Asosiy dashboard statistika
    """
    try:
        async with get_session() as session:
            from app.models.driver import Driver
            from app.models.passenger import Passenger
            from app.models.user import User
            from app.models.order import Order, OrderStatus
            from app.models.transaction import Transaction, TransactionStatus
            from app.models.route import Route
            
            # Bugungi sanalar
            today_start = datetime.now().replace(hour=0, minute=0, second=0)
            yesterday_start = today_start - timedelta(days=1)
            week_start = today_start - timedelta(days=7)
            month_start = today_start - timedelta(days=30)
            
            # ========================================
            # DRIVERS
            # ========================================
            
            # Total drivers
            total_drivers_query = select(func.count(Driver.driver_id))
            total_drivers = (await session.execute(total_drivers_query)).scalar()
            
            # Active drivers (online hozir)
            active_drivers_query = select(func.count(Driver.driver_id)).where(
                Driver.is_active == True
            )
            active_drivers = (await session.execute(active_drivers_query)).scalar()
            
            # Blocked drivers
            blocked_drivers_query = select(func.count(Driver.driver_id)).where(
                Driver.is_blocked == True
            )
            blocked_drivers = (await session.execute(blocked_drivers_query)).scalar()
            
            # Drivers on trip
            on_trip_query = select(func.count(Driver.driver_id)).where(
                Driver.is_on_trip == True
            )
            drivers_on_trip = (await session.execute(on_trip_query)).scalar()
            
            # ========================================
            # PASSENGERS
            # ========================================
            
            # Total passengers
            total_passengers_query = select(func.count(Passenger.passenger_id))
            total_passengers = (await session.execute(total_passengers_query)).scalar()
            
            # Blocked passengers (User.is_blocked)
            blocked_passengers_query = select(func.count(Passenger.passenger_id)).join(User).where(
                User.is_blocked == True
            )
            blocked_passengers = (await session.execute(blocked_passengers_query)).scalar()
            
            # ========================================
            # ORDERS/TRIPS
            # ========================================
            
            # Today's completed trips
            today_trips_query = select(func.count(Order.order_id)).where(
                and_(
                    Order.status == OrderStatus.COMPLETED,
                    Order.completed_at >= today_start
                )
            )
            today_trips = (await session.execute(today_trips_query)).scalar()
            
            # Yesterday's trips
            yesterday_trips_query = select(func.count(Order.order_id)).where(
                and_(
                    Order.status == OrderStatus.COMPLETED,
                    Order.completed_at >= yesterday_start,
                    Order.completed_at < today_start
                )
            )
            yesterday_trips = (await session.execute(yesterday_trips_query)).scalar()
            
            # Week's trips
            week_trips_query = select(func.count(Order.order_id)).where(
                and_(
                    Order.status == OrderStatus.COMPLETED,
                    Order.completed_at >= week_start
                )
            )
            week_trips = (await session.execute(week_trips_query)).scalar()
            
            # Pending orders
            pending_orders_query = select(func.count(Order.order_id)).where(
                Order.status == OrderStatus.PENDING
            )
            pending_orders = (await session.execute(pending_orders_query)).scalar()
            
            # ========================================
            # REVENUE (COMMISSION)
            # ========================================
            
            # Today's revenue
            today_revenue_query = select(func.sum(Order.commission_amount)).where(
                and_(
                    Order.status == OrderStatus.COMPLETED,
                    Order.completed_at >= today_start
                )
            )
            today_revenue = (await session.execute(today_revenue_query)).scalar() or 0
            
            # Week's revenue
            week_revenue_query = select(func.sum(Order.commission_amount)).where(
                and_(
                    Order.status == OrderStatus.COMPLETED,
                    Order.completed_at >= week_start
                )
            )
            week_revenue = (await session.execute(week_revenue_query)).scalar() or 0
            
            # Month's revenue
            month_revenue_query = select(func.sum(Order.commission_amount)).where(
                and_(
                    Order.status == OrderStatus.COMPLETED,
                    Order.completed_at >= month_start
                )
            )
            month_revenue = (await session.execute(month_revenue_query)).scalar() or 0
            
            # ========================================
            # TRANSACTIONS
            # ========================================
            
            # Pending transactions
            pending_trans_query = select(func.count(Transaction.transaction_id)).where(
                Transaction.status == TransactionStatus.PENDING
            )
            pending_transactions = (await session.execute(pending_trans_query)).scalar()
            
            # ========================================
            # ROUTES
            # ========================================
            total_routes_query = select(func.count(Route.route_id)).where(Route.is_active == True)
            total_routes = (await session.execute(total_routes_query)).scalar() or 0
            
            # ========================================
            # GROWTH (vs yesterday)
            # ========================================
            
            trips_growth = 0
            if yesterday_trips > 0: # type: ignore
                trips_growth = ((today_trips - yesterday_trips) / yesterday_trips) * 100 # type: ignore
            
            return {
                'success': True,
                'stats': {
                    'drivers': {
                        'total': total_drivers or 0,
                        'active': active_drivers or 0,
                        'on_trip': drivers_on_trip or 0,
                        'blocked': blocked_drivers or 0
                    },
                    'passengers': {
                        'total': total_passengers or 0,
                        'blocked': blocked_passengers or 0
                    },
                    'routes': {
                        'total': total_routes
                    },
                    'trips': {
                        'today': today_trips or 0,
                        'yesterday': yesterday_trips or 0,
                        'week': week_trips or 0,
                        'pending': pending_orders or 0,
                        'growth_percentage': round(trips_growth, 1)
                    },
                    'revenue': {
                        'today': float(today_revenue),
                        'week': float(week_revenue),
                        'month': float(month_revenue)
                    },
                    'transactions': {
                        'pending': pending_transactions or 0
                    }
                }
            }
    
    except Exception as e:
        logger.error(f"Failed to get dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime")
async def get_realtime_data(
    current_user: dict = Depends(get_current_user)
):
    """
    Real-time ma'lumotlar (Redis'dan)
    """
    try:
        # Health status
        health_data = await redis_client.get('health:latest')
        
        # Queue statistics
        from app.services.queue_service import driver_queue
        
        queue_stats = {}
        for route_id in range(1, 5):  # 1-4 marshrutlar
            stats = await driver_queue.get_queue_stats(route_id)
            if stats['total_drivers'] > 0:
                queue_stats[f'route_{route_id}'] = stats
        
        # Celery stats
        from app.core.celery_app import get_celery_stats
        celery_stats = get_celery_stats()
        
        return {
            'success': True,
            'realtime': {
                'health': health_data or {},
                'queues': queue_stats,
                'celery': celery_stats,
                'timestamp': datetime.now().isoformat()
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get realtime data: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@router.get("/charts/trips")
async def get_trips_chart_data(
    days: int = Query(7, ge=1, le=30),
    current_user: dict = Depends(get_current_user)
):
    """
    Safarlar grafigi (kunlik)
    """
    try:
        async with get_session() as session:
            from app.models.order import Order, OrderStatus
            
            data = []
            
            for i in range(days):
                day_start = datetime.now().replace(hour=0, minute=0, second=0) - timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                # Day's trips
                query = select(func.count(Order.order_id)).where(
                    and_(
                        Order.status == OrderStatus.COMPLETED,
                        Order.completed_at >= day_start,
                        Order.completed_at < day_end
                    )
                )
                
                result = await session.execute(query)
                count = result.scalar() or 0
                
                data.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'trips': count
                })
            
            # Reverse (oldest first)
            data.reverse()
            
            return {
                'success': True,
                'chart_data': data
            }
    
    except Exception as e:
        logger.error(f"Failed to get trips chart data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/charts/revenue")
async def get_revenue_chart_data(
    days: int = Query(7, ge=1, le=30),
    current_user: dict = Depends(get_current_user)
):
    """
    Daromad grafigi (kunlik)
    """
    try:
        async with get_session() as session:
            from app.models.order import Order, OrderStatus
            
            data = []
            
            for i in range(days):
                day_start = datetime.now().replace(hour=0, minute=0, second=0) - timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                # Day's revenue
                query = select(func.sum(Order.commission_amount)).where(
                    and_(
                        Order.status == OrderStatus.COMPLETED,
                        Order.completed_at >= day_start,
                        Order.completed_at < day_end
                    )
                )
                
                result = await session.execute(query)
                revenue = result.scalar() or 0
                
                data.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'revenue': float(revenue)
                })
            
            # Reverse
            data.reverse()
            
            return {
                'success': True,
                'chart_data': data
            }
    
    except Exception as e:
        logger.error(f"Failed to get revenue chart data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# DAILY/MONTHLY STATISTICS
# ============================================

@router.get("/statistics/daily")
async def get_daily_statistics(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    current_user: dict = Depends(get_current_user)
):
    """
    Kunlik statistika
    
    Args:
        date: Sana (YYYY-MM-DD). Agar berilmasa - bugungi sana
    """
    try:
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        else:
            target_date = datetime.now()
        
        day_start = target_date.replace(hour=0, minute=0, second=0)
        day_end = day_start + timedelta(days=1)
        
        async with get_session() as session:
            from app.models.driver import Driver
            from app.models.passenger import Passenger
            from app.models.order import Order, OrderStatus
            from app.models.transaction import Transaction, TransactionStatus
            
            # Safarlar
            completed_trips = (await session.execute(
                select(func.count(Order.order_id)).where(
                    and_(
                        Order.status == OrderStatus.COMPLETED,
                        Order.completed_at >= day_start,
                        Order.completed_at < day_end
                    )
                )
            )).scalar() or 0
            
            cancelled_trips = (await session.execute(
                select(func.count(Order.order_id)).where(
                    and_(
                        Order.status == OrderStatus.CANCELLED,
                        Order.cancelled_at >= day_start,
                        Order.cancelled_at < day_end
                    )
                )
            )).scalar() or 0
            
            # Daromad
            revenue = (await session.execute(
                select(func.sum(Order.commission_amount)).where(
                    and_(
                        Order.status == OrderStatus.COMPLETED,
                        Order.completed_at >= day_start,
                        Order.completed_at < day_end
                    )
                )
            )).scalar() or 0
            
            # Yangi haydovchilar
            new_drivers = (await session.execute(
                select(func.count(Driver.driver_id)).where(
                    and_(
                        Driver.created_at >= day_start,
                        Driver.created_at < day_end
                    )
                )
            )).scalar() or 0
            
            # Yangi yo'lovchilar
            new_passengers = (await session.execute(
                select(func.count(Passenger.passenger_id)).where(
                    and_(
                        Passenger.created_at >= day_start,
                        Passenger.created_at < day_end
                    )
                )
            )).scalar() or 0
            
            # To'lovlar
            approved_transactions = (await session.execute(
                select(func.count(Transaction.transaction_id)).where(
                    and_(
                        Transaction.status == TransactionStatus.APPROVED,
                        Transaction.approved_at >= day_start,
                        Transaction.approved_at < day_end
                    )
                )
            )).scalar() or 0
            
            return {
                'success': True,
                'date': day_start.strftime('%Y-%m-%d'),
                'statistics': {
                    'trips': {
                        'completed': completed_trips,
                        'cancelled': cancelled_trips,
                        'total': completed_trips + cancelled_trips
                    },
                    'revenue': float(revenue),
                    'users': {
                        'new_drivers': new_drivers,
                        'new_passengers': new_passengers
                    },
                    'transactions': {
                        'approved': approved_transactions
                    }
                }
            }
    
    except Exception as e:
        logger.error(f"Failed to get daily statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/monthly")
async def get_monthly_statistics(
    year: Optional[int] = Query(None, description="Year (e.g., 2024)"),
    month: Optional[int] = Query(None, description="Month (1-12)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Oylik statistika
    
    Args:
        year: Yil. Agar berilmasa - joriy yil
        month: Oy (1-12). Agar berilmasa - joriy oy
    """
    try:
        now = datetime.now()
        target_year = year or now.year
        target_month = month or now.month
        
        month_start = datetime(target_year, target_month, 1)
        if target_month == 12:
            month_end = datetime(target_year + 1, 1, 1)
        else:
            month_end = datetime(target_year, target_month + 1, 1)
        
        async with get_session() as session:
            from app.models.driver import Driver
            from app.models.passenger import Passenger
            from app.models.order import Order, OrderStatus
            from app.models.transaction import Transaction, TransactionStatus
            
            # Safarlar
            completed_trips = (await session.execute(
                select(func.count(Order.order_id)).where(
                    and_(
                        Order.status == OrderStatus.COMPLETED,
                        Order.completed_at >= month_start,
                        Order.completed_at < month_end
                    )
                )
            )).scalar() or 0
            
            cancelled_trips = (await session.execute(
                select(func.count(Order.order_id)).where(
                    and_(
                        Order.status == OrderStatus.CANCELLED,
                        Order.cancelled_at >= month_start,
                        Order.cancelled_at < month_end
                    )
                )
            )).scalar() or 0
            
            # Daromad
            revenue = (await session.execute(
                select(func.sum(Order.commission_amount)).where(
                    and_(
                        Order.status == OrderStatus.COMPLETED,
                        Order.completed_at >= month_start,
                        Order.completed_at < month_end
                    )
                )
            )).scalar() or 0
            
            # Yangi haydovchilar
            new_drivers = (await session.execute(
                select(func.count(Driver.driver_id)).where(
                    and_(
                        Driver.created_at >= month_start,
                        Driver.created_at < month_end
                    )
                )
            )).scalar() or 0
            
            # Yangi yo'lovchilar
            new_passengers = (await session.execute(
                select(func.count(Passenger.passenger_id)).where(
                    and_(
                        Passenger.created_at >= month_start,
                        Passenger.created_at < month_end
                    )
                )
            )).scalar() or 0
            
            # To'lovlar
            approved_transactions = (await session.execute(
                select(func.count(Transaction.transaction_id)).where(
                    and_(
                        Transaction.status == TransactionStatus.APPROVED,
                        Transaction.approved_at >= month_start,
                        Transaction.approved_at < month_end
                    )
                )
            )).scalar() or 0
            
            # Kunlik o'rtacha
            days_in_month = (month_end - month_start).days
            avg_daily_trips = completed_trips / days_in_month if days_in_month > 0 else 0
            avg_daily_revenue = float(revenue) / days_in_month if days_in_month > 0 else 0
            
            return {
                'success': True,
                'year': target_year,
                'month': target_month,
                'statistics': {
                    'trips': {
                        'completed': completed_trips,
                        'cancelled': cancelled_trips,
                        'total': completed_trips + cancelled_trips,
                        'avg_daily': round(avg_daily_trips, 1)
                    },
                    'revenue': {
                        'total': float(revenue),
                        'avg_daily': round(avg_daily_revenue, 2)
                    },
                    'users': {
                        'new_drivers': new_drivers,
                        'new_passengers': new_passengers
                    },
                    'transactions': {
                        'approved': approved_transactions
                    }
                }
            }
    
    except Exception as e:
        logger.error(f"Failed to get monthly statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ['router']