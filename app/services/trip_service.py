"""
app/services/trip_service.py

TRIP SERVICE - Safar boshqaruvi

BU SERVICE NIMA QILADI:
1. GPS proximity check (haydovchi yaqinmi?)
2. Trip confirmation (yo'lovchi tasdiqlashi)
3. Trip start/complete
4. Auto-confirm (2 daqiqadan keyin)
"""

from typing import Dict, Optional, List
from datetime import datetime
from decimal import Decimal
from loguru import logger
from sqlalchemy.orm import selectinload
from app.core.database import get_session, transaction
from app.core.exceptions import (
    OrderNotFoundException,
    InvalidOrderStatusException,
    LocationTooFarException
)
from app.models.order import (
    Order,
    OrderStatus,
    get_order_by_id
)
from app.models.trip import Trip, TripStatus
from app.models.driver import get_driver_by_id
from app.models.passenger import get_passenger_by_id
from app.schemas import order
from app.utils.geo import calculate_distance
from app.services.payment_service import payment_service
from sqlalchemy import select, update


class TripService:
    """
    Trip Management Service
    """
    
    # Constants
    PICKUP_RADIUS_METERS = 100  # 100 metr
    AUTO_CONFIRM_DELAY = 120     # 2 daqiqa
    
    # ========================================
    # GPS PROXIMITY CHECK
    # ========================================
    
    async def check_driver_at_pickup(
        self,
        driver_id: int,
        order_id: int
    ) -> Dict:
        """
        Haydovchi pickup joyiga yetib keldimi?
        
        Returns:
            {
                'is_near': bool,
                'distance': float (meters),
                'allowed': bool
            }
        """
        try:
            async with get_session() as session:
                driver = await get_driver_by_id(session, driver_id)
                order = await get_order_by_id(session, order_id)
                
                if not driver or not order:
                    return {
                        'is_near': False,
                        'distance': 9999,
                        'allowed': False,
                        'error': 'Driver yoki Order topilmadi'
                    }
                
                # Lokatsiya mavjudmi?
                if not driver.last_location_lat or not driver.last_location_lon:
                    return {
                        'is_near': False,
                        'distance': 9999,
                        'allowed': False,
                        'error': 'Driver lokatsiyasi mavjud emas'
                    }
                
                # Masofa hisoblash
                distance_km = calculate_distance(
                    float(driver.last_location_lat),
                    float(driver.last_location_lon),
                    float(order.pickup_lat),
                    float(order.pickup_lon)
                )
                
                distance_meters = distance_km * 1000
                
                is_near = distance_meters <= self.PICKUP_RADIUS_METERS
                
                logger.info(
                    f"GPS check: driver={driver_id}, order={order_id}, "
                    f"distance={distance_meters:.0f}m, near={is_near}"
                )
                
                return {
                    'is_near': is_near,
                    'distance': distance_meters,
                    'allowed': is_near,
                    'pickup_location': {
                        'lat': float(order.pickup_lat),
                        'lon': float(order.pickup_lon)
                    }
                }
        
        except Exception as e:
            logger.error(f"GPS check error: {e}")
            return {
                'is_near': False,
                'distance': 9999,
                'allowed': False,
                'error': str(e)
            }
    
    # ========================================
    # HAYDOVCHI YETIB KELDI
    # ========================================
    
    async def driver_arrived(
        self,
        driver_id: int,
        order_id: int
    ) -> Dict:
        """
        Haydovchi "Yetib keldim" bosdi
        
        FLOW:
        1. GPS proximity check
        2. Order statusini yangilash
        3. Yo'lovchiga tasdiqlash so'rash
        4. Auto-confirm task ishga tushirish
        
        Returns:
            {
                'success': bool,
                'message': str
            }
        """
        try:
            # 1. GPS check
            gps_result = await self.check_driver_at_pickup(driver_id, order_id)
            
            if not gps_result['allowed']:
                raise LocationTooFarException(
                    distance=gps_result['distance'],
                    max_distance=self.PICKUP_RADIUS_METERS,
                    driver_id=driver_id
                )
            
            # 2. Order statusini yangilash
            async with transaction() as session:
                await session.execute(
                    update(Order)
                    .where(Order.order_id == order_id)
                    .where(Order.status == OrderStatus.ACCEPTED)
                    .values(driver_arrived=True)
                )
                
                # AUTO COMMIT
            
            # 3. Yo'lovchiga tasdiqlash so'rash
            from app.tasks.notifications import request_passenger_confirmation
            request_passenger_confirmation.delay(order_id, driver_id) # type: ignore
            from app.tasks.matching import auto_confirm_trip_task as auto_confirm_trip
            auto_confirm_trip.apply_async(args=[order_id], countdown=self.AUTO_CONFIRM_DELAY) # type: ignore
            logger.success(
                f"✅ Driver arrived: driver={driver_id}, order={order_id}"
            )
            
            return {
                'success': True,
                'message': 'Yo\'lovchiga xabar yuborildi',
                'distance': gps_result['distance']
            }
        
        except LocationTooFarException as e:
            logger.warning(f"Driver too far: {e.message}")
            return {
                'success': False,
                'message': e.message,
                'distance': e.details['distance_km'] * 1000
            }
        
        except Exception as e:
            logger.error(f"Driver arrived error: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    # ========================================
    # YO'LOVCHI TASDIQLADI
    # ========================================
    
    async def passenger_confirmed(
        self,
        passenger_id: int,
        order_id: int,
        is_auto: bool = False # QO'SHILDI
    ) -> Dict:
        try:
            async with transaction() as session: # Yagona tranzaksiya
                # 1. Orderni yuklash (Driver va Passenger bilan)
                result = await session.execute(
                    select(Order)
                    .options(selectinload(Order.driver), selectinload(Order.passenger))
                    .where(Order.order_id == order_id)
                    .with_for_update()
                )
                order = result.scalar_one_or_none()

                if not order or order.status != OrderStatus.ACCEPTED:
                    return {'success': False, 'message': 'Holat noto\'g\'ri'}

                # 2. Statuslarni yangilash (komissiya allaqachon qabul qilishda yechilgan)
                order.status = OrderStatus.IN_PROGRESS
                order.started_at = datetime.now()
                if is_auto:
                    order.auto_confirmed = True
                
                # Haydovchini band qilish
                from app.models.driver import Driver
                await session.execute(
                    update(Driver).where(Driver.driver_id == order.driver_id).values(is_on_trip=True)
                )

                assert order.driver is not None
                assert order.passenger is not None
                # Kerakli ma'lumotlarni saqlab olamiz
                d_tg_id = order.driver.user_id
                p_tg_id = order.passenger.user_id

            # Xabarlarni yuborish (Sessiyadan tashqarida)
            from app.tasks.notifications import send_telegram_message
            from typing import Any, cast
            from app.bot.keyboards.driver import get_trip_active_keyboard

            cast(Any, send_telegram_message).delay(p_tg_id, "✅ Safar boshlandi!")
            cast(Any, send_telegram_message).delay(
                d_tg_id, 
                "✅ Safar boshlandi!",
                reply_markup=get_trip_active_keyboard() # Aiogram 3 uslubi
            )
            return {'success': True}
        except Exception as e:
            logger.error(f"Passenger confirmation error: {e}")
            return {
                'success': False,
                'message': str(e)
            }
        

    
    # ========================================
    # YO'LOVCHI RAD ETDI (Firibgarlik!)
    # ========================================
    
    async def passenger_rejected(
        self,
        passenger_id: int,
        order_id: int
    ) -> Dict:
        """
        Yo'lovchi: "Yo'q, hali olishgani yo'q" ❌
        
        Bu haydovchi firibgarlik qilganini anglatadi!
        
        ACTIONS:
        1. Order'ni cancel qilish
        2. Haydovchiga warning berish
        3. 3+ warning = 24 soat ban
        4. Yangi haydovchi topish
        """
        try:
            async with transaction() as session:
                order = await get_order_by_id(session, order_id)
                
                if not order:
                    raise OrderNotFoundException(order_id=order_id)
                
                # Order cancel
                await session.execute(
                    update(Order)
                    .where(Order.order_id == order_id)
                    .values(
                        status=OrderStatus.CANCELLED,
                        cancelled_at=datetime.now(),
                        cancellation_reason='driver_no_show'
                    )
                )
                
                # Driver warning count
                from app.models.driver import Driver
                
                result = await session.execute(
                    update(Driver)
                    .where(Driver.driver_id == order.driver_id)
                    .values(
                        total_ban_count=Driver.total_ban_count + 1,
                        ban_count_today=Driver.ban_count_today + 1
                    )
                    .returning(Driver.total_ban_count, Driver.ban_count_today)
                )
                
                driver_data = result.first()
                
                # Agar 3+ warning bugun
                if driver_data and driver_data.ban_count_today >= 3:
                    # 24 soat ban
                    from datetime import timedelta
                    
                    await session.execute(
                        update(Driver)
                        .where(Driver.driver_id == order.driver_id)
                        .values(
                            is_blocked=True,
                            blocked_until=datetime.now() + timedelta(hours=24),
                            block_reason='Yo\'lovchilarni olmaganlik (3+ warning)'
                        )
                    )
                    
                    # Haydovchiga xabar
                    from app.tasks.notifications import send_telegram_message
                    send_telegram_message.delay( # type: ignore
                        order.driver_id,
                        "🚫 <b>SIZ 24 SOATGA BLOKLANGANSIZ!</b>\n\n"
                        "Sabab: 3 marta yo'lovchini olmaganlik\n\n"
                        "Bu jiddiy buzilish!"
                    )
                    
                    logger.warning(f"Driver {order.driver_id} banned for 24h")
                else:
                    # Oddiy warning
                    from app.tasks.notifications import send_telegram_message
                    warning_count = driver_data.ban_count_today if driver_data else 0
                    
                    send_telegram_message.delay( # type: ignore
                        order.driver_id,
                        f"⚠️ <b>OGOHLANTIRISH #{warning_count}/3</b>\n\n"
                        f"Yo'lovchi sizni olmaganingizni aytdi.\n\n"
                        f"3 ta warning = 24 soat ban"
                    )
                
                # AUTO COMMIT
            
            # Yo'lovchiga xabar
            from app.tasks.notifications import send_telegram_message
            send_telegram_message.delay( # type: ignore
                passenger_id,
                "✅ Safar bekor qilindi\n\n"
                "Yangi haydovchi topilmoqda..."
            )
            
            # Yangi haydovchi topish
            from app.tasks.matching import find_driver_for_order_task
            find_driver_for_order_task.delay(order_id) # type: ignore
            
            logger.warning(f"⚠️ Passenger rejected trip: order={order_id}")
            
            return {
                'success': True,
                'message': 'Safar bekor qilindi, yangi haydovchi topilmoqda'
            }
        
        except Exception as e:
            logger.error(f"Passenger rejection error: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    # ========================================
    # AUTO-CONFIRM (2 daqiqa javob yo'q)
    # ========================================
    
    async def auto_confirm_trip(self, order_id: int) -> Dict:
        """
        2 daqiqada javob bermasa - avtomatik tasdiqlash
        """
        try:
            async with get_session() as session:
                order = await get_order_by_id(session, order_id)
                
                if not order:
                    return {'success': False, 'error': 'Order not found'}
                
                # Faqat ACCEPTED bo'lsa
                if order.status != OrderStatus.ACCEPTED:
                    return {'success': False, 'reason': 'Already processed'}
                
                # Safar boshlash
                result = await self.passenger_confirmed(
                    passenger_id=order.passenger_id,
                    order_id=order_id
                )
                
                if result['success']:
                    # Auto-confirmed flag
                    async with transaction() as sess:
                        await sess.execute(
                            update(Order)
                            .where(Order.order_id == order_id)
                            .values(auto_confirmed=True)
                        )
                    
                    logger.info(f"✅ Trip auto-confirmed: order={order_id}")
                
                return result
        
        except Exception as e:
            logger.error(f"Auto-confirm error: {e}")
            return {'success': False, 'error': str(e)}


# ========================================
# COMMISSION REFUND (ORDER RESET)
# ========================================

async def refund_commission_for_order(
    order_id: int,
    reason: str = "cancelled_by_passenger"
) -> Dict:
    """
    Safar bekor qilinsa komissiyani haydovchiga qaytarib,
    buyurtmani yana pending holatga qaytaradi (yangi haydovchi topish uchun).
    """
    try:
        async with transaction() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.driver))
                .where(Order.order_id == order_id)
                .with_for_update()
            )
            order_obj = result.scalar_one_or_none()

            if not order_obj or not order_obj.driver_id:
                return {'success': False, 'message': 'Order yoki haydovchi topilmadi'}

            commission = order_obj.commission_amount or Decimal(0)

            if commission > 0:
                refund_result = await payment_service.refund_commission(
                    session,
                    driver_id=order_obj.driver_id,
                    order_id=order_obj.order_id,
                    amount=commission,
                    reason=reason
                )
                if not refund_result.get('success'):
                    raise Exception(refund_result.get('error', 'Refund failed'))

            # Reset order to allow rematching
            order_obj.status = OrderStatus.PENDING
            order_obj.driver_id = None
            order_obj.accepted_at = None
            order_obj.completed_at = None
            order_obj.started_at = None
            order_obj.driver_arrived = False
            order_obj.auto_confirmed = False
            order_obj.commission_amount = None

            # Free the driver flag if needed
            if order_obj.driver:
                order_obj.driver.is_on_trip = False

            return {
                'success': True,
                'refunded_amount': float(commission)
            }

    except Exception as e:
        logger.error(f"Refund commission error for order {order_id}: {e}")
        return {
            'success': False,
            'message': str(e)
        }


# ========================================
# TRIP CANCEL HELPERS (for driver side)
# ========================================

async def can_cancel_trip(trip_id: int, driver_id: int) -> Dict:
    """
    Trip'ni bekor qilishga ruxsat bormi?
    """
    try:
        async with get_session() as session:
            result = await session.execute(
                select(Trip)
                .options(selectinload(Trip.orders))
                .where(Trip.trip_id == trip_id)
            )
            trip = result.scalar_one_or_none()

            if not trip:
                return {'can_cancel': False, 'reason': 'Trip topilmadi'}

            if trip.driver_id != driver_id:
                return {'can_cancel': False, 'reason': 'Bu trip sizga tegishli emas'}

            if trip.status != TripStatus.ACTIVE:
                return {'can_cancel': False, 'reason': 'Trip allaqachon yakunlangan yoki bekor qilingan'}

            return {'can_cancel': True}
    except Exception as e:
        logger.error(f"can_cancel_trip error: {e}")
        return {'can_cancel': False, 'reason': str(e)}


async def cancel_pending_orders_in_trip(trip_id: int, driver_id: int) -> Dict:
    """
    Trip ichidagi ACCEPTED (boshlanmagan) orderlarni bekor qiladi va komissiyani qaytaradi.
    """
    try:
        async with transaction() as session:
            trip_result = await session.execute(
                select(Trip)
                .options(selectinload(Trip.orders).selectinload(Order.passenger))
                .where(Trip.trip_id == trip_id)
                .with_for_update()
            )
            trip = trip_result.scalar_one_or_none()

            if not trip:
                return {'success': False, 'message': 'Trip topilmadi'}

            if trip.driver_id != driver_id:
                return {'success': False, 'message': 'Bu trip sizga tegishli emas'}

            refundable_orders: List[Order] = [
                o for o in trip.orders if o.status == OrderStatus.ACCEPTED
            ]

            for order_obj in refundable_orders:
                refund_result = await refund_commission_for_order(
                    order_obj.order_id,
                    reason="trip_cancelled_by_driver"
                )
                if not refund_result.get('success'):
                    raise Exception(refund_result.get('message', 'Refund failed'))

                # Bekor qilish (status CANCELLED, driver_id qolsin tarix uchun)
                order_obj.status = OrderStatus.CANCELLED
                order_obj.completed_at = None
                order_obj.started_at = None
                order_obj.driver_arrived = False

            message = f"{len(refundable_orders)} ta buyurtma bekor qilindi"
            return {'success': True, 'message': message}
    except Exception as e:
        logger.error(f"cancel_pending_orders_in_trip error: {e}")
        return {'success': False, 'message': str(e)}


# ============================================
# GLOBAL INSTANCE
# ============================================

trip_service = TripService()


__all__ = [
    'trip_service',
    'TripService',
    'refund_commission_for_order',
    'can_cancel_trip',
    'cancel_pending_orders_in_trip'
]
