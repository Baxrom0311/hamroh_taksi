from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart

from loguru import logger
from sqlalchemy import select, update, delete, func, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.bot.decorators import with_driver_session, with_passenger_session, with_admin_session, with_session
from app.bot.messages import Messages

from app.models.user import User, UserRole, get_user_by_id
from app.models.driver import Driver, get_driver_by_user_id
from app.models.passenger import Passenger, get_passenger_by_user_id
from app.bot.utils import (
    get_driver_or_error, get_passenger_or_error, get_order_or_error,
    parse_callback_data, parse_callback_str, parse_callback_multi  # ✅ Safe callback parsing
)

__all__ = [
    'Router', 'F', 'Message', 'CallbackQuery', 'ReplyKeyboardMarkup', 
    'KeyboardButton', 'ReplyKeyboardRemove', 'FSMContext', 'Command', 
    'CommandStart', 'logger', 'select', 'update', 'delete', 'func', 
    'desc', 'AsyncSession', 'get_session', 'with_driver_session', 
    'with_passenger_session', 'with_admin_session', 'with_session', 
    'Messages', 'User', 'UserRole', 'get_user_by_id', 'Driver', 
    'get_driver_by_user_id', 'Passenger', 'get_passenger_by_user_id',
    'get_driver_or_error', 'get_passenger_or_error', 'get_order_or_error',
    'selectinload', 'parse_callback_data', 'parse_callback_str', 'parse_callback_multi'
]

