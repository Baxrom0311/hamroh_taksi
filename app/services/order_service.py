"""
app/services/order_service.py

ORDER SERVICE - ENG MUHIM BUSINESS LOGIC

BU FAYL NIMA QILADI:
1. Buyurtma yaratish
2. Haydovchi topish (matching algorithm)
3. Buyurtmani qabul qilish (lock bilan)
4. Safar boshlash/yakunlash

ISHLATISH:
    from app.services.order_service import (
        create_order,
        find_driver_for_order,
        accept_order
    )
"""
from sqlalchemy import update
from app.models.transaction import log_balance_change, TransactionType
from sqlalchemy.sql import func
from app.models.transaction import log_balance_change, TransactionType
from sqlalchemy.sql import func
from typing import Optional
from decimal import Decimal
from loguru import logger
from sqlalchemy.orm import selectinload # <--- Shuni qo'shing

from app.core.database import get_session, transaction
from app.core.locks import acquire_order_lock
from app.core.exceptions import (
    OrderNotFoundException,
    OrderAlreadyAcceptedException,
    InsufficientBalanceError,
    NoDriversAvailableException,
    LocationTooFarException
)
from app.models.order import (
    Order,
    OrderStatus,
    create_order as db_create_order,
    accept_order as db_accept_order,
    start_order,
    complete_order,
    get_order_by_id,
    get_pending_orders_for_route
)
from app.models.driver import Driver
from app.models.passenger import Passenger
from config.settings import settings

# Geo service import (keyinroq yozamiz)
# from app.services.geo_service import find_nearby_drivers


# ============================================
# 1. BUYURTMA YARATISH
# ============================================

async def create_new_order(
    passenger_id: int,
    route_id: int,
    pickup_location: str,
    pickup_lat: float,
    pickup_lon: float,
    passenger_count: int = 1,
    has_luggage: bool = False,
    luggage_count: int = 0,
    luggage_description: Optional[str] = None
) -> dict:
    """
    Yangi buyurtma yaratish
    
    Args:
        passenger_id: Yo'lovchi ID
        route_id: Marshrut ID
        pickup_location: Olish joyi (matn)
        pickup_lat: Latitude
        pickup_lon: Longitude
        passenger_count: Yo'lovchilar soni
        has_luggage: Pochta bor/yo'q
        luggage_count: Pochta soni
        luggage_description: Pochta tavsifi
    
    Returns:
        {
            'success': True,
            'order_id': int,
            'message': str
        }
    
    ISHLATISH:
        result = await create_new_order(
            passenger_id=1,
            route_id=1,
            pickup_location="Gurlan bozori yonida, 5-uy",
            pickup_lat=41.311512,
            pickup_lon=69.249512,
            passenger_count=2
        )
    """
    
    try:
        async with get_session() as session:
            # Buyurtma yaratish
            order = await db_create_order(
                session,
                passenger_id=passenger_id,
                route_id=route_id,
                pickup_location=pickup_location,
                pickup_lat=pickup_lat,
                pickup_lon=pickup_lon,
                passenger_count=passenger_count,
                has_luggage=has_luggage,
                luggage_count=luggage_count,
                luggage_description=luggage_description
            )
            from app.tasks.matching import find_driver_for_order_task

            await session.commit()
            
            logger.info(f"✅ Order created: order_id={order.order_id}, passenger_id={passenger_id}")

            # Haydovchi topishni boshlash (async)
            find_driver_for_order_task.delay(order.order_id)
            
            return {
                'success': True,
                'order_id': order.order_id,
                'message': 'Buyurtma yaratildi. Haydovchi topilmoqda...',
                'order': order.to_dict()
            }
    
    except Exception as e:
        logger.error(f"❌ Failed to create order: {e}")
        return {
            'success': False,
            'message': f'Buyurtma yaratishda xatolik: {str(e)}'
        }


# ============================================
# 2. HAYDOVCHI TOPISH (MATCHING ALGORITHM)
# ============================================

async def find_driver_for_order(order_id: int) -> Optional[int]:
    """
    Buyurtma uchun haydovchi topish
    
    ALGORITM:
    1. Route bo'yicha haydovchilarni topish
    2. Balans tekshirish
    3. Geo-lokatsiya filtrlash (50 km)
    4. Priority queue'dan eng yaxshisini olish
    5. Haydovchiga xabar yuborish
    
    Args:
        order_id: Buyurtma ID
    
    Returns:
        driver_id yoki None
    
    ISHLATISH:
        driver_id = await find_driver_for_order(123)
        if driver_id:
            print(f"Haydovchi topildi: {driver_id}")
    """
    
    try:
        async with get_session() as session:
            # Order'ni olish
            order = await get_order_by_id(session, order_id)
            
            if not order or order.status != OrderStatus.PENDING:
                logger.warning(f"Order {order_id} not found or not pending")
                return None
            
            # 1. Route bo'yicha haydovchilarni topish
            from sqlalchemy import select
            
            result = await session.execute(
                select(Driver)
                .where(Driver.current_route_id == order.route_id)
                .where(Driver.is_active == True)
                .where(Driver.is_on_trip == False)
                .where(Driver.is_blocked == False)
                .where(Driver.available_seats >= order.passenger_count)
            )
            
            drivers = result.scalars().all()
            
            if not drivers:
                logger.warning(f"No drivers available for order {order_id}")
                return None
            
            # 2. Balans tekshirish
            commission = settings.COMMISSION_AMOUNT
            drivers = [d for d in drivers if d.balance >= commission]
            
            if not drivers:
                logger.warning(f"No drivers with sufficient balance for order {order_id}")
                return None
            
            # 3. Geo-lokatsiya filtrlash
            # SIMPLE VERSION: Har bir haydovchi uchun masofa hisoblash
            from app.utils.geo import calculate_distance
            
            nearby_drivers = []
            
            for driver in drivers:
                if driver.last_location_lat and driver.last_location_lon:
                    distance = calculate_distance(
                        float(driver.last_location_lat),
                        float(driver.last_location_lon),
                        float(order.pickup_lat),
                        float(order.pickup_lon)
                    )
                    
                    if distance <= settings.MAX_PICKUP_DISTANCE_KM:
                        nearby_drivers.append({
                            'driver': driver,
                            'distance': distance
                        })
            
            if not nearby_drivers:
                logger.warning(f"No nearby drivers for order {order_id}")
                return None
            
            # 4. Priority bo'yicha saralash (rating + distance)
            nearby_drivers.sort(
                key=lambda x: (
                    -float(x['driver'].rating),  # Yuqori rating birinchi
                    x['distance']                # Yaqin masofa birinchi
                )
            )
            
            # Eng yaxshi haydovchi
            best_driver = nearby_drivers[0]['driver']
            
            logger.info(
                f"✅ Driver found for order {order_id}: "
                f"driver_id={best_driver.driver_id}, "
                f"distance={nearby_drivers[0]['distance']:.1f} km"
            )
            
            return best_driver.driver_id
    
    except Exception as e:
        logger.error(f"❌ Failed to find driver for order {order_id}: {e}")
        return None


# ============================================
# 3. BUYURTMANI QABUL QILISH (100% XAVFSIZ)
# ============================================

async def accept_order_by_driver(
    driver_id: int,
    order_id: int
) -> dict:
    """
    Haydovchi buyurtmani qabul qiladi (LOCK bilan)
    
    NIMA BO'LADI:
    1. Redis lock olish
    2. Order va Driver tekshirish
    3. Balans tekshirish
    4. Order qabul qilish (DB)
    5. Driver available_seats kamaytirish
    6. Transaction log yozish
    
    Args:
        driver_id: Haydovchi ID
        order_id: Buyurtma ID
    
    Returns:
        {
            'success': bool,
            'message': str,
            'order': dict  # Order ma'lumotlari
        }
    
    ISHLATISH:
        result = await accept_order_by_driver(
            driver_id=1,
            order_id=123
        )
        
        if result['success']:
            print("Buyurtma qabul qilindi!")
    """
    
    # 1. REDIS LOCK OLISH (Race condition oldini olish)
    async with acquire_order_lock(order_id, timeout=10) as locked:
        
        if not locked:
            # Boshqa haydovchi qabul qilmoqda
            logger.warning(f"Order {order_id} is locked by another driver")
            return {
                'success': False,
                'message': '⚠️ Bu buyurtma boshqa haydovchi tomonidan qabul qilinmoqda'
            }
        
        # 2. DATABASE TRANSACTION (ATOMIC)
        try:
            async with transaction() as session:
                
                # 2.1. Order'ni olish (FOR UPDATE - row lock)
                from sqlalchemy import select
                
                result = await session.execute(
                    select(Order)
                    .options(selectinload(Order.passenger))
                    .where(Order.order_id == order_id)
                    .with_for_update()  # Row-level lock
                )
                
                order = result.scalar_one_or_none()
                
                if not order:
                    raise OrderNotFoundException(order_id=order_id)
                
                if order.status != OrderStatus.PENDING:
                    raise OrderAlreadyAcceptedException(
                        order_id=order_id,
                        current_driver=order.driver_id
                    )
                
                # 2.2. Driver'ni olish (FOR UPDATE)
                result = await session.execute(
                    select(Driver)
                    .where(Driver.driver_id == driver_id)
                    .with_for_update()
                )
                
                driver = result.scalar_one_or_none()
                
                if not driver:
                    return {
                        'success': False,
                        'message': '❌ Haydovchi topilmadi'
                    }
                
                # 2.3. Balans tekshirish
                commission = Decimal(settings.COMMISSION_AMOUNT)
                
                if driver.balance < commission:
                    raise InsufficientBalanceError(
                        required=int(commission),
                        available=int(driver.balance),
                        driver_id=driver_id
                    )
                
                # 2.4. Bo'sh o'rinlar tekshiruvi
                if driver.available_seats < order.passenger_count:
                    return {
                        'success': False,
                        'message': f'⚠️ Yetarli bo\'sh o\'rin yo\'q\n\n'
                                  f'Kerak: {order.passenger_count}\n'
                                  f'Mavjud: {driver.available_seats}'
                    }
                
                # 2.5. Balansdan komissiya yechish va o'rinlarni kamaytirish (ATOMIC)
                from sqlalchemy import update
                
                new_available_seats = driver.available_seats - order.passenger_count
                
                await session.execute(
                    update(Driver)
                    .where(Driver.driver_id == driver_id)
                    .values(
                        balance=Driver.balance - commission,
                        available_seats=new_available_seats
                    )
                )
                
                # 2.5. Order'ni qabul qilish


                await session.execute(
                    update(Order)
                    .where(Order.order_id == order_id)
                    .values(
                        driver_id=driver_id,
                        status=OrderStatus.ACCEPTED,
                        commission_amount=commission,
                        accepted_at=func.now()
                    )
                )
                
                # 2.6. Transaction log (BALANCE YANGILANISHIDAN OLDIN!)
                old_balance = driver.balance  # Eski balansni saqlash
                new_balance = old_balance - commission  # Yangi balans
                
                await log_balance_change(
                    session,
                    driver_id=driver_id,
                    amount=-commission,
                    type=TransactionType.COMMISSION,
                    old_balance=old_balance,
                    new_balance=new_balance,
                    order_id=order_id,
                    description=f"Buyurtma #{order_id} uchun komissiya"
                )
                passenger_user_id = order.passenger.user_id 
                # COMMIT (async with transaction() avtomatik)
                
                logger.success(
                    f"✅ Order accepted: order_id={order_id}, "
                    f"driver_id={driver_id}, commission={commission}"
                )
                
                # 3. Yo'lovchiga xabar yuborish (Celery task)
                # from app.tasks.notifications import notify_passenger_driver_found
                # notify_passenger_driver_found.delay(order.passenger_id, driver_id)
                
                # Yangilangan balansni olish (UPDATE'dan keyin)
                result = await session.execute(
                    select(Driver.balance)
                    .where(Driver.driver_id == driver_id)
                )
                updated_balance = result.scalar_one()
                
                # Yangilangan o'rinlarni olish
                result = await session.execute(
                    select(Driver.available_seats)
                    .where(Driver.driver_id == driver_id)
                )
                updated_available_seats = result.scalar_one()
                
                return {
                    'success': True,
                    'passenger_id': passenger_user_id, # MUHIM: Yo'lovchining Telegram ID si
                    'message': '✅ Buyurtma qabul qilindi!',
                    'order': {
                        'order_id': order_id,
                        'commission': float(commission),
                        'old_balance': float(old_balance),
                        'new_balance': float(updated_balance),
                        'available_seats': updated_available_seats,
                        'has_more_seats': updated_available_seats > 0  # Keyingi buyurtmalar uchun
                    }
                }
        
        except InsufficientBalanceError as e:
            logger.warning(f"Insufficient balance: driver_id={driver_id}, required={e.details['required']}")
            return {
                'success': False,
                'message': f"⚠️ {e.message}\n\n"
                          f"Kerak: {e.details['required']:,} so'm\n"
                          f"Mavjud: {e.details['available']:,} so'm\n"
                          f"Kamomad: {e.details['shortage']:,} so'm"
            }
        
        except OrderAlreadyAcceptedException as e:
            logger.warning(f"Order already accepted: order_id={order_id}")
            return {
                'success': False,
                'message': '⚠️ Bu buyurtma allaqachon qabul qilingan'
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to accept order: {e}")
            return {
                'success': False,
                'message': f'❌ Xatolik: {str(e)}'
            }


# ============================================
# 4. SAFAR BOSHLASH
# ============================================

async def start_trip(order_id: int, driver_id: int) -> dict:
    """
    Safar boshlash
    
    STATUS: accepted → in_progress
    
    ISHLATISH:
        result = await start_trip(order_id=123, driver_id=1)
    """
    
    try:
        async with get_session() as session:
            # Order tekshirish
            order = await get_order_by_id(session, order_id)
            
            if not order:
                raise OrderNotFoundException(order_id=order_id)
            
            if order.driver_id != driver_id:
                return {
                    'success': False,
                    'message': '⚠️ Bu buyurtma sizga tegishli emas'
                }
            
            if order.status != OrderStatus.ACCEPTED:
                return {
                    'success': False,
                    'message': f'⚠️ Buyurtma holati noto\'g\'ri: {order.status.value}'
                }
            
            # Status o'zgartirish
            await start_order(session, order_id)
            
            # Driver'ni on_trip qilish
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .values(is_on_trip=True)
            )
            
            await session.commit()
            
            logger.info(f"✅ Trip started: order_id={order_id}, driver_id={driver_id}")
            
            return {
                'success': True,
                'message': '✅ Safar boshlandi! Xavfsiz yo\'l!'
            }
    
    except Exception as e:
        logger.error(f"❌ Failed to start trip: {e}")
        return {
            'success': False,
            'message': f'❌ Xatolik: {str(e)}'
        }


# ============================================
# 5. SAFAR YAKUNLASH
# ============================================

async def complete_trip(order_id: int, driver_id: int) -> dict:
    """
    Safar yakunlash
    
    STATUS: in_progress → completed
    
    NIMA BO'LADI:
    1. Status o'zgartirish
    2. Driver statistikasini yangilash
    3. Passenger statistikasini yangilash
    4. Driver'ni bo'shatish
    
    ISHLATISH:
        result = await complete_trip(order_id=123, driver_id=1)
    """
    
    try:
        async with transaction() as session:
            # Order tekshirish
            order = await get_order_by_id(session, order_id)
            
            if not order:
                raise OrderNotFoundException(order_id=order_id)
            
            if order.driver_id != driver_id:
                return {
                    'success': False,
                    'message': '⚠️ Bu buyurtma sizga tegishli emas'
                }
            
            if order.status != OrderStatus.IN_PROGRESS:
                return {
                    'success': False,
                    'message': f'⚠️ Buyurtma holati noto\'g\'ri: {order.status.value}'
                }
            
            # 1. Status o'zgartirish
            await complete_order(session, order_id)
            
            # 2. Driver statistikasi
            from sqlalchemy import update
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .values(
                    total_trips=Driver.total_trips + 1,
                    is_on_trip=False,
                    available_seats=0,  # Reset
                    last_trip_at=func.now()
                )
            )
            
            # 3. Passenger statistikasi
            await session.execute(
                update(Passenger)
                .where(Passenger.passenger_id == order.passenger_id)
                .values(total_trips=Passenger.total_trips + 1)
            )
            
            # COMMIT (async with transaction() avtomatik)
            
            logger.success(f"✅ Trip completed: order_id={order_id}, driver_id={driver_id}")
            
            return {
                'success': True,
                'message': '✅ Safar yakunlandi!',
                'duration_minutes': order.duration_minutes
            }
    
    except Exception as e:
        logger.error(f"❌ Failed to complete trip: {e}")
        return {
            'success': False,
            'message': f'❌ Xatolik: {str(e)}'
        }


# ============================================
# EXPORT
# ============================================

__all__ = [
    'create_new_order',
    'find_driver_for_order',
    'accept_order_by_driver',
    'start_trip',
    'complete_trip'
]