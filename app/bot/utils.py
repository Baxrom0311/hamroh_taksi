"""
app/bot/utils.py
Helper functions for the bot.
"""

from typing import Optional, Union, Tuple
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.driver import get_driver_by_user_id, Driver
from app.models.passenger import get_passenger_by_user_id, Passenger
from app.models.order import get_order_by_id, Order
from app.bot.messages import Messages


# ============================================
# CALLBACK DATA PARSING (Safe Pattern)
# ============================================

def parse_callback_data(data: Optional[str], prefix: str) -> Optional[int]:
    """
    Safely parse callback data with prefix.
    
    Args:
        data: Callback data string (e.g. "select_route:123")
        prefix: Expected prefix (e.g. "select_route")
    
    Returns:
        Parsed integer ID or None if invalid
    
    Example:
        order_id = parse_callback_data(callback.data, "passenger_cancel")
        if order_id is None:
            await callback.answer("Invalid data", show_alert=True)
            return
    """
    if not data:
        return None
    
    if not data.startswith(f"{prefix}:"):
        return None
    
    try:
        return int(data.removeprefix(f"{prefix}:"))
    except (ValueError, AttributeError):
        return None


def parse_callback_str(data: Optional[str], prefix: str) -> Optional[str]:
    """
    Safely parse callback data and return string value.
    
    For non-integer callback values like "action:confirm" or "type:pochta"
    """
    if not data:
        return None
    
    if not data.startswith(f"{prefix}:"):
        return None
    
    return data.removeprefix(f"{prefix}:")


def parse_callback_multi(data: Optional[str], prefix: str, count: int = 2) -> Optional[tuple[int, ...]]:
    """
    Safely parse callback data with multiple colon-separated integer values.
    
    Args:
        data: Callback data string (e.g. "select_new_driver:123:456")
        prefix: Expected prefix (e.g. "select_new_driver")
        count: Number of values expected after prefix (default 2)
    
    Returns:
        Tuple of parsed integers or None if invalid
    
    Example:
        result = parse_callback_multi(callback.data, "select_new_driver", 2)
        if result is None:
            await callback.answer("Invalid data", show_alert=True)
            return
        order_id, new_driver_id = result
    """
    if not data:
        return None
    
    if not data.startswith(f"{prefix}:"):
        return None
    
    try:
        parts = data.split(":")
        if len(parts) != count + 1:  # prefix + count values
            return None
        
        values = tuple(int(parts[i]) for i in range(1, count + 1))
        return values
    except (ValueError, IndexError, AttributeError):
        return None


async def get_driver_or_error(
    session: AsyncSession, 
    user_id: int, 
    event: Union[Message, CallbackQuery]
) -> Optional[Driver]:
    """
    Get driver by user_id or send error message.
    """
    driver = await get_driver_by_user_id(session, user_id)
    if not driver:
        if isinstance(event, Message):
            await event.answer(Messages.Error.DRIVER_NOT_FOUND)
        elif isinstance(event, CallbackQuery):
            await event.answer(Messages.Error.DRIVER_NOT_FOUND, show_alert=True)
        return None
    return driver


async def get_passenger_or_error(
    session: AsyncSession, 
    user_id: int, 
    event: Union[Message, CallbackQuery]
) -> Optional[Passenger]:
    """
    Get passenger by user_id or send error message.
    """
    passenger = await get_passenger_by_user_id(session, user_id)
    if not passenger:
        if isinstance(event, Message):
            await event.answer(Messages.Error.PASSENGER_NOT_FOUND)
        elif isinstance(event, CallbackQuery):
            await event.answer(Messages.Error.PASSENGER_NOT_FOUND, show_alert=True)
        return None
    return passenger


async def get_order_or_error(
    session: AsyncSession,
    order_id: int,
    event: Union[Message, CallbackQuery]
) -> Optional[Order]:
    """
    Get order by id or send error message.
    """
    order = await get_order_by_id(session, order_id)
    if not order:
        if isinstance(event, Message):
            await event.answer(Messages.Error.ORDER_NOT_FOUND)
        elif isinstance(event, CallbackQuery):
            await event.answer(Messages.Error.ORDER_NOT_FOUND, show_alert=True)
        return None
    return order
