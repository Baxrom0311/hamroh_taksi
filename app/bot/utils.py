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
