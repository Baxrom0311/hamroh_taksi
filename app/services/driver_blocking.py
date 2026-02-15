"""
app/services/driver_blocking.py

DRIVER BLOCKING SERVICE

Handles automatic cleanup when driver is blocked
"""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.driver import Driver
from app.models.order import Order, OrderStatus
from app.core.database import transaction


async def block_driver_and_cleanup(driver_id: int, reason: str) -> dict:
    """
    Block driver and cleanup active orders
    
    Args:
        driver_id: Driver to block
        reason: Blocking reason
    
    Returns:
        {'success': bool, 'cancelled_orders': int}
    """
    try:
        async with transaction() as session:
            # 1. Get driver
            driver_result = await session.execute(
                select(Driver).where(Driver.driver_id == driver_id)
            )
            driver = driver_result.scalar_one_or_none()
            
            if not driver:
                return {'success': False, 'message': 'Driver topilmadi'}
            
            # 2. Find active orders
            active_orders_result = await session.execute(
                select(Order)
                .where(Order.driver_id == driver_id)
                .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            )
            active_orders = active_orders_result.scalars().all()
            
            # 3. Cancel all active orders
            cancelled_count = 0
            for order in active_orders:
                # Reset order to pending for rematching
                order.status = OrderStatus.PENDING
                order.driver_id = None
                order.accepted_at = None
                order.cancellation_reason = f"driver_blocked:{reason}"
                cancelled_count += 1
                
                # Refund commission if paid
                if order.commission_amount and order.commission_amount > 0:
                    from app.services.payment_service import payment_service
                    await payment_service.refund_commission(
                        session,
                        driver_id=driver_id,
                        order_id=order.order_id,
                        amount=order.commission_amount,
                        reason=f"driver_blocked:{reason}"
                    )
            
            # 4. Block driver
            driver.is_blocked = True
            driver.block_reason = reason
            driver.is_on_trip = False
            driver.is_active = False
            driver.available_seats = 0
            
            logger.warning(
                f"Driver {driver_id} blocked: {reason}. "
                f"Cancelled {cancelled_count} active orders."
            )
            
            return {
                'success': True,
                'cancelled_orders': cancelled_count,
                'driver_name': driver.full_name
            }
    
    except Exception as e:
        logger.error(f"Failed to block driver {driver_id}: {e}")
        return {'success': False, 'message': str(e)}

__all__ = ['block_driver_and_cleanup']
