"""
app/bot/handlers/passenger/history.py

YO'LOVCHI - SAFAR TARIXI

Yo'lovchi o'zining tugallangan safarlari tarixini ko'ra oladi (pagination bilan).
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.models.order import Order, OrderStatus
from app.models.passenger import get_passenger_by_user_id, Passenger
from app.models.driver import Driver
from app.bot.utils import get_passenger_or_error
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.bot.states.passenger import PassengerStates
from app.bot.decorators import with_passenger_session  # ✅ NEW
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()

# Pagination settings
ITEMS_PER_PAGE = 10


@router.message(F.text == "📜 Safar tarixi")
async def view_trip_history(message: Message, state: FSMContext):
    """
    Yo'lovchining tugallangan safarlar tarixini ko'rsatish
    """
    user_id = message.from_user.id  # type: ignore
    
    async with get_session() as session:
        passenger = await get_passenger_or_error(session, user_id, message)
        if not passenger:
            return
        
        # Tugallangan buyurtmalarni olish (so'ngi 10 ta)
        completed_orders_result = await session.execute(
            select(Order)
            .options(
                selectinload(Order.route),
                selectinload(Order.driver).selectinload(Driver.user)
            )
            .where(Order.passenger_id == passenger.passenger_id)
            .where(Order.status == OrderStatus.COMPLETED)
            .order_by(Order.completed_at.desc())
            .limit(ITEMS_PER_PAGE + 1)  # +1 to check if there are more
        )
        completed_orders = completed_orders_result.scalars().all()
        
        if not completed_orders:
            await message.answer(
                "📜 <b>Safar tarixi bo'sh</b>\n\n"
                "Hozircha tugallangan safarlaringiz yo'q.\n\n"
                "Birinchi safaringizni boshlash uchun 'Taksi chaqirish' tugmasini bosing.",
                reply_markup=get_passenger_main_menu(),
                parse_mode="HTML"
            )
            return
        
        # Pagination tekshiruvi
        has_more = len(completed_orders) > ITEMS_PER_PAGE
        orders_to_show = completed_orders[:ITEMS_PER_PAGE]
        
        # State'ga yozish (keyingi sahifalar uchun)
        await state.update_data(history_page=0)
        await state.set_state(PassengerStates.viewing_history)
        
        # Buyurtmalarni formatlash
        history_text = await _format_history_page(orders_to_show, page=0, total_trips=passenger.total_trips)
        
        # Keyboard yaratish
        keyboard = _build_pagination_keyboard(page=0, has_more=has_more)
        
        await message.answer(
            history_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Passenger {passenger.passenger_id} viewed trip history (page 0)")


@router.callback_query(F.data.startswith("history_page:"))
async def navigate_history(callback: CallbackQuery, state: FSMContext):
    """
    Safar tarixi sahifalari orasida navigatsiya
    """
    if not callback.data:
        await callback.answer("Xatolik: data yo'q")
        return
    
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        passenger = await get_passenger_by_user_id(session, user_id)
        if not passenger:
            await callback.answer("Xatolik: Yo'lovchi topilmadi")
            return
        
        # Offset va limit
        offset = page * ITEMS_PER_PAGE
        
        # Buyurtmalarni olish
        completed_orders_result = await session.execute(
            select(Order)
            .options(
                selectinload(Order.route),
                selectinload(Order.driver).selectinload(Driver.user)
            )
            .where(Order.passenger_id == passenger.passenger_id)
            .where(Order.status == OrderStatus.COMPLETED)
            .order_by(Order.completed_at.desc())
            .offset(offset)
            .limit(ITEMS_PER_PAGE + 1)
        )
        completed_orders = completed_orders_result.scalars().all()
        
        if not completed_orders:
            await callback.answer("Bu sahifada ma'lumot yo'q", show_alert=True)
            return
        
        # Pagination
        has_more = len(completed_orders) > ITEMS_PER_PAGE
        orders_to_show = completed_orders[:ITEMS_PER_PAGE]
        
        # Formatlash
        history_text = await _format_history_page(orders_to_show, page=page, total_trips=passenger.total_trips)
        
        # Keyboard
        keyboard = _build_pagination_keyboard(page=page, has_more=has_more)
        
        # Update state
        await state.update_data(history_page=page)
        
        # Edit message
        if callback.message:
            await callback.message.edit_text(
                history_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        await callback.answer()
        logger.info(f"Passenger {passenger.passenger_id} navigated to history page {page}")


@router.callback_query(F.data == "close_history")
async def close_history(callback: CallbackQuery, state: FSMContext):
    """
    Safar tarixini yopish
    """
    await state.clear()
    
    if callback.message:
        await callback.message.delete()
    
    await callback.answer("Safar tarixi yopildi")


# Helper functions

async def _format_history_page(orders: list[Order], page: int, total_trips: int) -> str:
    """Safar tarixi sahifasini formatlash"""
    
    from datetime import datetime
    import pytz
    
    history_text = f"📜 <b>Safar tarixi</b> (Sahifa {page + 1})\n"
    history_text += f"🚗 Jami safarlar: {total_trips}\n\n"
    
    for idx, order in enumerate(orders, start=1):
        # Vaqt
        completed_time = order.completed_at.astimezone(pytz.timezone('Asia/Tashkent')) if order.completed_at else None
        time_str = completed_time.strftime("%H:%M, %d.%m.%Y") if completed_time else "Noma'lum"
        
        # Marshrut
        route_name = order.route.route_name if order.route else "Noma'lum"
        
        # Davomiylik
        duration = order.duration_minutes if hasattr(order, 'duration_minutes') else None
        duration_str = f"{duration} daqiqa" if duration else "Noma'lum"
        
        # Haydovchi
        driver_name = order.driver.full_name if order.driver else "Noma'lum"
        
        history_text += f"{idx}. <b>Buyurtma #{order.order_id}</b>\n"
        history_text += f"   🛣 {route_name}\n"
        history_text += f"   🚗 Haydovchi: {driver_name}\n"
        history_text += f"   📅 {time_str}\n"
        history_text += f"   ⏱ Davomiyligi: {duration_str}\n\n"
    
    return history_text


def _build_pagination_keyboard(page: int, has_more: bool) -> InlineKeyboardMarkup:
    """Pagination klaviaturasini yaratish"""
    
    buttons = []
    
    # Oldingi sahifa
    if page > 0:
        buttons.append(InlineKeyboardButton(
            text="◀️ Oldingi",
            callback_data=f"history_page:{page - 1}"
        ))
    
    # Keyingi sahifa
    if has_more:
        buttons.append(InlineKeyboardButton(
            text="Keyingi ▶️",
            callback_data=f"history_page:{page + 1}"
        ))
    
    keyboard_rows = []
    if buttons:
        keyboard_rows.append(buttons)
    
    # Yopish tugmasi
    keyboard_rows.append([
        InlineKeyboardButton(text="❌ Yopish", callback_data="close_history")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


__all__ = ['router']
