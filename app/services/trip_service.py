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
# ========================================
# COMMISSION REFUND (ORDER RESET)
# ========================================
async def refund_commission_for_order(
    order_id: int,
    reason: str = "cancelled_by_passenger",
    session=None,
) -> Dict:
    """
    Safar bekor qilinsa komissiyani haydovchiga qaytaradi.
    ✅ FIX: session parametri qo'shildi (nested transaction oldini olish)
    ✅ FIX: Idempotency — faqat ACCEPTED/IN_PROGRESS orderlarni refund qiladi
    """
    try:
        _own_session = session is None
        if _own_session:
            ctx = transaction()
            session = await ctx.__aenter__()
        
        try:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.driver))
                .where(Order.order_id == order_id)
                .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))  # ✅ Idempotency
                .with_for_update()
            )
            order_obj = result.scalar_one_or_none()

            if not order_obj or not order_obj.driver_id:
                return {'success': False, 'message': 'Order topilmadi yoki allaqachon refund qilingan'}

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
            
            # Reset order
            order_obj.status = OrderStatus.PENDING
            order_obj.driver_id = None
            order_obj.accepted_at = None
            order_obj.completed_at = None
            order_obj.started_at = None
            order_obj.driver_arrived = False
            order_obj.auto_confirmed = False
            order_obj.commission_amount = None

            if _own_session:
                await ctx.__aexit__(None, None, None)
            
            return {'success': True, 'refunded_amount': float(commission)}
        except Exception:
            if _own_session:
                import sys
                await ctx.__aexit__(*sys.exc_info())
            raise
            
    except Exception as e:
        logger.error(f"Refund commission error for order {order_id}: {e}")
        return {'success': False, 'message': str(e)}
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
                o for o in trip.orders if o.status in (OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS)
            ]
            for order_obj in refundable_orders:
                # ✅ FIX: Pass session to avoid nested transaction
                commission = order_obj.commission_amount or Decimal(0)
                if commission > 0:
                    refund_result = await payment_service.refund_commission(
                        session,
                        driver_id=order_obj.driver_id,
                        order_id=order_obj.order_id,
                        amount=commission,
                        reason="trip_cancelled_by_driver"
                    )
                    if not refund_result.get('success'):
                        logger.warning(f"Refund failed for order {order_obj.order_id}: {refund_result}")
                
                # Bekor qilish
                order_obj.status = OrderStatus.CANCELLED
                order_obj.cancelled_at = datetime.now()
                order_obj.commission_amount = None
            message = f"{len(refundable_orders)} ta buyurtma bekor qilindi"
            return {'success': True, 'message': message, 'cancelled_count': len(refundable_orders)}
    except Exception as e:
        logger.error(f"cancel_pending_orders_in_trip error: {e}")
        return {'success': False, 'message': str(e)}
__all__ = [
    'refund_commission_for_order',  # ✅ Still used
    'can_cancel_trip',              # ✅ Still used
    'cancel_pending_orders_in_trip' # ✅ Still used
]