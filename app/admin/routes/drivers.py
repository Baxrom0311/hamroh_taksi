"""
app/admin/routes/drivers.py

DRIVERS MANAGEMENT

ENDPOINTS:
- GET /drivers - Barcha haydovchilar
- GET /drivers/{id} - Bitta haydovchi
- PUT /drivers/{id}/block - Bloklash
- PUT /drivers/{id}/unblock - Blokdan ochish
- GET /drivers/statistics - Statistika
- PUT /drivers/{id}/balance - Balans o'zgartirish (manual)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timedelta
from loguru import logger

from app.admin.auth import get_current_user
from app.core.database import get_session, transaction
from app.models.driver import Driver, get_driver_by_id
from app.models.user import User
from sqlalchemy import select, func, update, or_
from sqlalchemy.orm import selectinload
from app.models.order import Order


router = APIRouter(prefix="/drivers", tags=["drivers"])


# ============================================
# SCHEMAS
# ============================================

class DriverResponse(BaseModel):
    """Driver response model"""
    driver_id: int
    user_id: int
    full_name: str
    phone_number: str
    car_model: str
    car_color: str
    car_number: str
    balance: float
    rating: float
    total_trips: int
    is_active: bool
    is_on_trip: bool
    is_blocked: bool
    blocked_until: Optional[str]
    block_reason: Optional[str]
    available_seats: int
    created_at: str
    last_trip_at: Optional[str]


class BlockRequest(BaseModel):
    """Bloklash so'rovi"""
    reason: str
    duration_hours: int = 24  # Default: 24 soat


class UnblockRequest(BaseModel):
    """Blokdan ochish so'rovi"""
    pass


class BalanceUpdateRequest(BaseModel):
    """Balans o'zgartirish"""
    amount: float
    reason: str
    operation: str = "add"  # "add" yoki "subtract"


# ============================================
# ENDPOINTS
# ============================================

@router.get("/")
async def get_drivers_list(
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_blocked: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """
    Barcha haydovchilar (filtrlash va qidiruv bilan)
    
    Query params:
    - search: Ism, telefon, mashina raqami bo'yicha qidirish
    - is_active: Aktiv haydovchilar
    - is_blocked: Bloklangan haydovchilar
    - limit: Maksimal natijalar soni
    - offset: Pagination offset
    """
    try:
        async with get_session() as session:
            # Base query - User relationship'ni oldindan yuklaymiz (async lazy load xatosidan qochish uchun)
            query = select(Driver).options(selectinload(Driver.user)).join(User)
            
            # Filters
            if search:
                search_pattern = f"%{search}%"
                query = query.where(
                    or_(
                        Driver.full_name.ilike(search_pattern),
                        Driver.car_number.ilike(search_pattern),
                        User.phone_number.ilike(search_pattern)
                    )
                )
            
            if is_active is not None:
                query = query.where(Driver.is_active == is_active)
            
            if is_blocked is not None:
                query = query.where(Driver.is_blocked == is_blocked)
            
            # Pagination
            query = query.order_by(Driver.created_at.desc())
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            drivers = result.scalars().all()
            
            # Total count
            count_query = select(func.count(Driver.driver_id)).join(User)
            
            if search:
                search_pattern = f"%{search}%"
                count_query = count_query.where(
                    or_(
                        Driver.full_name.ilike(search_pattern),
                        Driver.car_number.ilike(search_pattern),
                        User.phone_number.ilike(search_pattern)
                    )
                )
            
            if is_active is not None:
                count_query = count_query.where(Driver.is_active == is_active)
            
            if is_blocked is not None:
                count_query = count_query.where(Driver.is_blocked == is_blocked)
            
            total_result = await session.execute(count_query)
            total = total_result.scalar()
            
            # Response
            drivers_list = []
            for driver in drivers:
                drivers_list.append({
                    'driver_id': driver.driver_id,
                    'user_id': driver.user_id,
                    'full_name': driver.full_name,
                    'phone_number': driver.phone_number,
                    'car_model': driver.car_model,
                    'car_color': driver.car_color,
                    'car_number': driver.car_number,
                    'balance': float(driver.balance),
                    'rating': float(driver.rating),
                    'total_trips': driver.total_trips,
                    'is_active': driver.is_active,
                    'is_on_trip': driver.is_on_trip,
                    'is_blocked': driver.is_blocked,
                    'blocked_until': driver.blocked_until.isoformat() if driver.blocked_until else None,
                    'block_reason': driver.block_reason,
                    'available_seats': driver.available_seats,
                    'created_at': driver.created_at.isoformat(),
                    'last_trip_at': driver.last_trip_at.isoformat() if driver.last_trip_at else None
                })
            
            return {
                'success': True,
                'drivers': drivers_list,
                'total': total,
                'limit': limit,
                'offset': offset
            }
    
    except Exception as e:
        logger.error(f"Failed to get drivers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{driver_id}")
async def get_driver_details(
    driver_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Bitta haydovchi ma'lumotlari (to'liq)
    """
    try:
        async with get_session() as session:
            # User ma'lumotlarini ham birga yuklaymiz (async lazy load xatosidan qochish uchun)
            driver = await get_driver_by_id(session, driver_id, eager_load_user=True)
            
            if not driver:
                raise HTTPException(status_code=404, detail="Driver topilmadi")
            
            # Recent trips
            from app.models.order import Order, OrderStatus
            
            recent_trips_query = select(Order).where(
                Order.driver_id == driver_id
            ).where(
                Order.status == OrderStatus.COMPLETED
            ).order_by(
                Order.completed_at.desc()
            ).limit(10)
            
            trips_result = await session.execute(recent_trips_query)
            recent_trips = trips_result.scalars().all()
            
            # Transaction history
            from app.models.transaction import TransactionLog
            
            trans_query = select(TransactionLog).where(
                TransactionLog.driver_id == driver_id
            ).order_by(
                TransactionLog.created_at.desc()
            ).limit(20)
            
            trans_result = await session.execute(trans_query)
            transactions = trans_result.scalars().all()
            
            # Response
            return {
                'success': True,
                'driver': {
                    'driver_id': driver.driver_id,
                    'user_id': driver.user_id,
                    'full_name': driver.full_name,
                    'phone_number': driver.phone_number,
                    'car_model': driver.car_model,
                    'car_color': driver.car_color,
                    'car_number': driver.car_number,
                    'license_number': driver.license_number,
                    'balance': float(driver.balance),
                    'rating': float(driver.rating),
                    'total_trips': driver.total_trips,
                    'total_ban_count': driver.total_ban_count,
                    'ban_count_today': driver.ban_count_today,
                    'is_active': driver.is_active,
                    'is_on_trip': driver.is_on_trip,
                    'is_blocked': driver.is_blocked,
                    'blocked_until': driver.blocked_until.isoformat() if driver.blocked_until else None,
                    'block_reason': driver.block_reason,
                    'current_route_id': driver.current_route_id,
                    'available_seats': driver.available_seats,
                    'location': {
                        'lat': float(driver.last_location_lat) if driver.last_location_lat else None,
                        'lon': float(driver.last_location_lon) if driver.last_location_lon else None
                    },
                    'created_at': driver.created_at.isoformat(),
                    'last_trip_at': driver.last_trip_at.isoformat() if driver.last_trip_at else None
                },
                'recent_trips': [
                    {
                        'order_id': trip.order_id,
                        'passenger_count': trip.passenger_count,
                        'commission_amount': float(trip.commission_amount) if trip.commission_amount else 0,
                        'completed_at': trip.completed_at.isoformat() if trip.completed_at else None
                    }
                    for trip in recent_trips
                ],
                'transactions': [
                    {
                        'log_id': t.log_id,
                        'amount': float(t.amount),
                        'type': t.type.value,
                        'old_balance': float(t.old_balance),
                        'new_balance': float(t.new_balance),
                        'description': t.description,
                        'created_at': t.created_at.isoformat()
                    }
                    for t in transactions
                ]
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to get driver details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{driver_id}/block")
async def block_driver(
    driver_id: int,
    request: BlockRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Haydovchini bloklash
    """
    try:
        async with get_session() as session:
            driver = await get_driver_by_id(session, driver_id)
            
            if not driver:
                raise HTTPException(status_code=404, detail="Driver topilmadi")
            
            if driver.is_blocked:
                raise HTTPException(status_code=400, detail="Driver allaqachon bloklangan")
            
            # Bloklash
            blocked_until = datetime.now() + timedelta(hours=request.duration_hours)
            
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .values(
                    is_blocked=True,
                    blocked_until=blocked_until,
                    block_reason=request.reason,
                    is_active=False  # Deactivate ham
                )
            )
            
            await session.commit()
            
            logger.warning(
                f"Driver {driver_id} blocked by admin {current_user['username']} "
                f"for {request.duration_hours}h: {request.reason}"
            )
            
            # Haydovchiga xabar
            from app.tasks.notifications import send_telegram_message
            send_telegram_message.delay( # type: ignore
                driver.user_id,
                f"🚫 <b>Sizning hisobingiz bloklandi!</b>\n\n"
                f"Muddat: {request.duration_hours} soat\n"
                f"Sabab: {request.reason}\n\n"
                f"Agar bu xato deb hisoblasangiz, admin bilan bog'laning."
            )
            
            return {
                'success': True,
                'message': 'Driver bloklandi',
                'blocked_until': blocked_until.isoformat()
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to block driver: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{driver_id}/unblock")
async def unblock_driver(
    driver_id: int,
    request: UnblockRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Haydovchini blokdan ochish
    """
    try:
        async with get_session() as session:
            driver = await get_driver_by_id(session, driver_id)
            
            if not driver:
                raise HTTPException(status_code=404, detail="Driver topilmadi")
            
            if not driver.is_blocked:
                raise HTTPException(status_code=400, detail="Driver bloklangan emas")
            
            # Blokdan ochish
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .values(
                    is_blocked=False,
                    blocked_until=None,
                    block_reason=None
                )
            )
            
            await session.commit()
            
            logger.info(f"Driver {driver_id} unblocked by admin {current_user['username']}")
            
            # Haydovchiga xabar
            from app.tasks.notifications import send_telegram_message
            send_telegram_message.delay( # type: ignore
                driver.user_id,
                "✅ <b>Sizning hisobingiz ochildi!</b>\n\n"
                "Endi tizimdan foydalanishingiz mumkin."
            )
            
            return {
                'success': True,
                'message': 'Driver blokdan ochildi'
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to unblock driver: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{driver_id}")
async def update_driver(
    driver_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Haydovchi ma'lumotlarini tahrirlash
    """
    try:
        async with get_session() as session:
            driver = await get_driver_by_id(session, driver_id)
            
            if not driver:
                raise HTTPException(status_code=404, detail="Driver topilmadi")
            
            # Ma'lumotlarni yangilash
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .values(
                    full_name=request.get('full_name', driver.full_name),
                    car_model=request.get('car_model', driver.car_model),
                    car_color=request.get('car_color', driver.car_color),
                    car_number=request.get('car_number', driver.car_number),
                    license_number=request.get('license_number', driver.license_number)
                )
            )
            
            # Telefon raqamini yangilash (User jadvalida)
            if 'phone_number' in request:
                from app.models.user import User
                await session.execute(
                    update(User)
                    .where(User.user_id == driver.user_id)
                    .values(phone_number=request['phone_number'])
                )
            
            await session.commit()
            
            logger.info(f"Driver {driver_id} updated by admin {current_user['username']}")
            
            return {
                'success': True,
                'message': 'Driver ma\'lumotlari yangilandi'
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to update driver: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{driver_id}/balance")
async def update_driver_balance(
    driver_id: int,
    request: BalanceUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Driver balansini manual o'zgartirish (admin)
    """
    try:
        from app.services.payment_service import payment_service
        from decimal import Decimal
        
        amount = Decimal(str(abs(request.amount)))
        
        # Barcha balans o'zgarishlari bitta transaction ichida bo'lishi kerak
        async with transaction() as session:
            if request.operation == "add":
                # Qo'shish
                result = await payment_service.add_balance(
                    session,
                    driver_id=driver_id,
                    amount=amount,
                    description=f"Admin tomonidan qo'shildi: {request.reason}"
                )
            else:
                # Yechish (manual). Bu yerda order_id yo'q, shuning uchun None beramiz.
                result = await payment_service.deduct_commission(
                    session,
                    driver_id=driver_id,
                    order_id=None,  # Manual operatsiya, real order yo‘q
                    amount=amount
                )
        
        if result['success']:
            logger.info(
                f"Balance {request.operation}: driver={driver_id}, "
                f"amount={amount}, admin={current_user['username']}"
            )
            
            # Haydovchiga xabar
            from app.tasks.notifications import send_telegram_message
            operation_text = "qo'shildi" if request.operation == "add" else "yechildi"
            
            send_telegram_message.delay( # type: ignore
                driver_id,
                f"💰 <b>Balans {operation_text}</b>\n\n"
                f"Miqdor: {amount:,} so'm\n"
                f"Sabab: {request.reason}\n\n"
                f"📊 Yangi balans: {result['new_balance']:,} so'm"
            )
            
            return {
                'success': True,
                'message': f'Balans {operation_text}',
                'new_balance': float(result['new_balance'])
            }
        else:
            raise HTTPException(status_code=400, detail=result.get('error'))
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to update balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/overview")
async def get_drivers_statistics(
    current_user: dict = Depends(get_current_user)
):
    """
    Haydovchilar statistikasi
    """
    try:
        async with get_session() as session:
            # Total drivers
            total_query = select(func.count(Driver.driver_id))
            total_result = await session.execute(total_query)
            total = total_result.scalar()
            
            # Active drivers
            active_query = select(func.count(Driver.driver_id)).where(
                Driver.is_active == True
            )
            active_result = await session.execute(active_query)
            active = active_result.scalar()
            
            # On trip
            on_trip_query = select(func.count(Driver.driver_id)).where(
                Driver.is_on_trip == True
            )
            on_trip_result = await session.execute(on_trip_query)
            on_trip = on_trip_result.scalar()
            
            # Blocked
            blocked_query = select(func.count(Driver.driver_id)).where(
                Driver.is_blocked == True
            )
            blocked_result = await session.execute(blocked_query)
            blocked = blocked_result.scalar()
            
            # Average rating
            rating_query = select(func.avg(Driver.rating))
            rating_result = await session.execute(rating_query)
            avg_rating = rating_result.scalar()
            
            # Total balance (all drivers)
            balance_query = select(func.sum(Driver.balance))
            balance_result = await session.execute(balance_query)
            total_balance = balance_result.scalar()
            
            # Registrations today
            today_start = datetime.now().replace(hour=0, minute=0, second=0)
            today_query = select(func.count(Driver.driver_id)).where(
                Driver.created_at >= today_start
            )
            today_result = await session.execute(today_query)
            today_registrations = today_result.scalar()
            
            return {
                'success': True,
                'statistics': {
                    'total': total or 0,
                    'active': active or 0,
                    'on_trip': on_trip or 0,
                    'blocked': blocked or 0,
                    'avg_rating': float(avg_rating) if avg_rating else 0,
                    'total_balance': float(total_balance) if total_balance else 0,
                    'today_registrations': today_registrations or 0
                }
            }
    
    except Exception as e:
        logger.error(f"Failed to get drivers statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ['router']