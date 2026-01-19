"""
app/utils/driver_state_utils.py

DRIVER STATE UTILITIES

Centralized helper functions for driver state management
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from loguru import logger

from app.models.driver import Driver


async def cleanup_stuck_driver_state(
    session: AsyncSession,
    driver_id: int,
    commit: bool = True
) -> None:
    """
    Auto-cleanup stuck driver state
    
    Resets is_on_trip and is_active to False when driver is stuck
    (marked as on_trip but no active orders exist)
    
    Args:
        session: Database session
        driver_id: Driver ID to clean
        commit: Whether to commit (default True)
    
    Usage:
        # When driver stuck in trip_in_progress state
        await cleanup_stuck_driver_state(session, driver.driver_id)
    """
    logger.warning(
        f"Auto-cleaning stuck driver state: driver_id={driver_id}"
    )
    
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver_id)
        .values(
            is_on_trip=False,
            is_active=False
        )
    )
    
    if commit:
        await session.commit()
    
    logger.info(f"✅ Driver {driver_id} state cleaned")


async def validate_driver_trip_state(
    session: AsyncSession,
    driver_id: int
) -> bool:
    """
    Validate if driver actually has active orders
    
    Returns:
        True if driver has active orders, False otherwise
    """
    from sqlalchemy import select
    from app.models.order import Order, OrderStatus
    
    result = await session.execute(
        select(Order.order_id)
        .where(Order.driver_id == driver_id)
        .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
        .limit(1)
    )
    
    return result.scalar_one_or_none() is not None


__all__ = [
    'cleanup_stuck_driver_state',
    'validate_driver_trip_state'
]
