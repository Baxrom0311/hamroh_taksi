"""
app/admin/routes/passengers.py

PASSENGERS MANAGEMENT

ENDPOINTS:
- GET /passengers - Barcha yo'lovchilar
- GET /passengers/{id} - Bitta yo'lovchi
- PUT /passengers/{id}/block - Bloklash
- PUT /passengers/{id}/unblock - Blokdan ochish
- GET /passengers/statistics - Statistika
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from loguru import logger

from app.admin.auth import get_current_user
from app.core.database import get_session
from app.models.passenger import Passenger, get_passenger_by_id
from app.models.user import User, block_user, unblock_user
from sqlalchemy import select, func, or_


router = APIRouter(prefix="/passengers", tags=["passengers"])


# ============================================
# SCHEMAS
# ============================================

class PassengerResponse(BaseModel):
    """Passenger response model"""
    passenger_id: int
    user_id: int
    full_name: str
    phone_number: str
    gender: str
    age: int
    total_trips: int
    is_blocked: bool
    created_at: str


class BlockPassengerRequest(BaseModel):
    """Bloklash so'rovi"""
    reason: str


# ============================================
# ENDPOINTS
# ============================================

@router.get("/")
async def get_passengers_list(
    search: Optional[str] = None,
    is_blocked: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """
    Barcha yo'lovchilar (filtrlash va qidiruv bilan)
    """
    try:
        async with get_session() as session:
            # Base query
            query = select(Passenger).join(User)
            
            # Filters
            if search:
                search_pattern = f"%{search}%"
                query = query.where(
                    or_(
                        Passenger.full_name.ilike(search_pattern),
                        User.phone_number.ilike(search_pattern)
                    )
                )
            
            if is_blocked is not None:
                query = query.where(User.is_blocked == is_blocked)
            
            # Pagination
            query = query.order_by(Passenger.created_at.desc())
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            passengers = result.scalars().all()
            
            # Total count
            count_query = select(func.count(Passenger.passenger_id)).join(User)
            
            if search:
                search_pattern = f"%{search}%"
                count_query = count_query.where(
                    or_(
                        Passenger.full_name.ilike(search_pattern),
                        User.phone_number.ilike(search_pattern)
                    )
                )
            
            if is_blocked is not None:
                count_query = count_query.where(User.is_blocked == is_blocked)
            
            total_result = await session.execute(count_query)
            total = total_result.scalar()
            
            # Response
            passengers_list = []
            for passenger in passengers:
                passengers_list.append({
                    'passenger_id': passenger.passenger_id,
                    'user_id': passenger.user_id,
                    'full_name': passenger.full_name,
                    'phone_number': passenger.phone_number,
                    'gender': passenger.gender.value,
                    'age': passenger.age,
                    'total_trips': passenger.total_trips,
                    'is_blocked': passenger.user.is_blocked,
                    'created_at': passenger.created_at.isoformat()
                })
            
            return {
                'success': True,
                'passengers': passengers_list,
                'total': total,
                'limit': limit,
                'offset': offset
            }
    
    except Exception as e:
        logger.error(f"Failed to get passengers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{passenger_id}")
async def get_passenger_details(
    passenger_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Bitta yo'lovchi ma'lumotlari (to'liq)
    """
    try:
        async with get_session() as session:
            passenger = await get_passenger_by_id(session, passenger_id)
            
            if not passenger:
                raise HTTPException(status_code=404, detail="Passenger topilmadi")
            
            # Recent orders
            from app.models.order import Order
            
            orders_query = select(Order).where(
                Order.passenger_id == passenger_id
            ).order_by(
                Order.created_at.desc()
            ).limit(20)
            
            orders_result = await session.execute(orders_query)
            orders = orders_result.scalars().all()
            # Response
            return {
                'success': True,
                'passenger': {
                    'passenger_id': passenger.passenger_id,
                    'user_id': passenger.user_id,
                    'full_name': passenger.full_name,
                    'phone_number': passenger.phone_number,
                    'gender': passenger.gender.value,
                    'age': passenger.age,
                    'total_trips': passenger.total_trips,
                    'cancellation_count_hour': passenger.cancellation_count_hour,
                    'last_cancellation_time': passenger.last_cancellation_time.isoformat() if passenger.last_cancellation_time else None,
                    'is_blocked': passenger.user.is_blocked,
                    'created_at': passenger.created_at.isoformat()
                },
                'recent_orders': [
                    {
                        'order_id': order.order_id,
                        'route_id': order.route_id,
                        'status': order.status.value,
                        'passenger_count': order.passenger_count,
                        'has_luggage': order.has_luggage,
                        'created_at': order.created_at.isoformat(),
                        'completed_at': order.completed_at.isoformat() if order.completed_at else None
                    }
                    for order in orders
                ]
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to get passenger details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{passenger_id}/block")
async def block_passenger(
    passenger_id: int,
    request: BlockPassengerRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Yo'lovchini bloklash
    """
    try:
        async with get_session() as session:
            passenger = await get_passenger_by_id(session, passenger_id)
            
            if not passenger:
                raise HTTPException(status_code=404, detail="Passenger topilmadi")
            
            if passenger.user.is_blocked:
                raise HTTPException(status_code=400, detail="Passenger allaqachon bloklangan")
            
            # Bloklash
            await block_user(session, passenger.user_id, request.reason)
            await session.commit()
            
            logger.warning(
                f"Passenger {passenger_id} blocked by admin {current_user['username']}: "
                f"{request.reason}"
            )
            
            # Yo'lovchiga xabar
            from app.tasks.notifications import send_telegram_message
            send_telegram_message.delay( # type: ignore
                passenger.user_id,
                f"🚫 <b>Sizning hisobingiz bloklandi!</b>\n\n"
                f"Sabab: {request.reason}\n\n"
                f"Agar bu xato deb hisoblasangiz, admin bilan bog'laning."
            )
            
            return {
                'success': True,
                'message': 'Passenger bloklandi'
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to block passenger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{passenger_id}/unblock")
async def unblock_passenger(
    passenger_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Yo'lovchini blokdan ochish
    """
    try:
        async with get_session() as session:
            passenger = await get_passenger_by_id(session, passenger_id)
            
            if not passenger:
                raise HTTPException(status_code=404, detail="Passenger topilmadi")
            
            if not passenger.user.is_blocked:
                raise HTTPException(status_code=400, detail="Passenger bloklangan emas")
            
            # Blokdan ochish
            await unblock_user(session, passenger.user_id)
            await session.commit()
            
            logger.info(
                f"Passenger {passenger_id} unblocked by admin {current_user['username']}"
            )
            
            # Yo'lovchiga xabar
            from app.tasks.notifications import send_telegram_message
            send_telegram_message.delay( # type: ignore
                passenger.user_id,
                "✅ <b>Sizning hisobingiz ochildi!</b>\n\n"
                "Endi tizimdan foydalanishingiz mumkin."
            )
            
            return {
                'success': True,
                'message': 'Passenger blokdan ochildi'
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to unblock passenger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/overview")
async def get_passengers_statistics(
    current_user: dict = Depends(get_current_user)
):
    """
    Yo'lovchilar statistikasi
    """
    try:
        async with get_session() as session:
            # Total passengers
            total_query = select(func.count(Passenger.passenger_id))
            total_result = await session.execute(total_query)
            total = total_result.scalar()
            
            # Blocked
            blocked_query = select(func.count(Passenger.passenger_id)).join(User).where(
                User.is_blocked == True
            )
            blocked_result = await session.execute(blocked_query)
            blocked = blocked_result.scalar()
            
            # Active (had trip in last 7 days)
            from datetime import timedelta
            week_ago = datetime.now() - timedelta(days=7)
            
            from app.models.order import Order, OrderStatus
            
            active_query = select(func.count(func.distinct(Order.passenger_id))).where(
                Order.completed_at >= week_ago
            ).where(
                Order.status == OrderStatus.COMPLETED
            )
            active_result = await session.execute(active_query)
            active = active_result.scalar()
            
            # Registrations today
            today_start = datetime.now().replace(hour=0, minute=0, second=0)
            today_query = select(func.count(Passenger.passenger_id)).where(
                Passenger.created_at >= today_start
            )
            today_result = await session.execute(today_query)
            today_registrations = today_result.scalar()
            
            return {
                'success': True,
                'statistics': {
                    'total': total or 0,
                    'active_last_week': active or 0,
                    'blocked': blocked or 0,
                    'today_registrations': today_registrations or 0
                }
            }

    except Exception as e:
        logger.error(f"Failed to get passengers statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    


all = ['router']

