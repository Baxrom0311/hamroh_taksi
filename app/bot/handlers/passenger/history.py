"""
app/bot/handlers/passenger/history.py

YO'LOVCHI - SAFAR TARIXI

Yo'lovchi o'zining tugallangan safarlari tarixini ko'ra oladi (pagination bilan).
"""

from ..base import *
from app.models.order import Order, OrderStatus
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.bot.states.passenger import PassengerStates


router = Router()

# Pagination settings
ITEMS_PER_PAGE = 10


@router.message(F.text == "📜 Safar tarixi")
@with_passenger_session
async def view_trip_history(message: Message, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """
    Yo'lovchining tugallangan safarlar tarixini ko'rsatish
    """
    # Tugallangan buyurtmalarni olish (so'ngi 10 ta)
    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.route),
            selectinload(Order.driver), # selectinload(Driver.user) base.py may not export relationship chains
        )
        .where(Order.passenger_id == passenger.passenger_id)
        .where(Order.status == OrderStatus.COMPLETED)
        .order_by(Order.completed_at.desc())
        .limit(ITEMS_PER_PAGE + 1)
    )
    completed_orders = result.scalars().all()
    
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
    
    # State'ga yozish
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
@with_passenger_session
async def navigate_history(callback: CallbackQuery, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """
    Safar tarixi sahifalari orasida navigatsiya
    """
    if not callback.data:
        return
    
    page = int(callback.data.split(":")[1])
    
    # Offset va limit
    offset = page * ITEMS_PER_PAGE
    
    # Buyurtmalarni olish
    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.route),
            selectinload(Order.driver)
        )
        .where(Order.passenger_id == passenger.passenger_id)
        .where(Order.status == OrderStatus.COMPLETED)
        .order_by(Order.completed_at.desc())
        .offset(offset)
        .limit(ITEMS_PER_PAGE + 1)
    )
    completed_orders = result.scalars().all()
    
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
