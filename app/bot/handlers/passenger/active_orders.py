"""
app/bot/handlers/passenger/active_orders.py

YO'LOVCHI - FAOL BUYURTMALAR

Yo'lovchi o'zining barcha faol buyurtmalarini (PENDING, ACCEPTED, IN_PROGRESS) ko'ra oladi.
"""

from ..base import *
from app.models.order import Order, OrderStatus, get_order_by_id
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.bot.states.driver import DriverStates
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.services.trip_service import refund_commission_for_order
from app.tasks.matching import find_driver_for_order_task
router = Router()
STATUS_EMOJI = {
    OrderStatus.PENDING: "⏳",
    OrderStatus.ACCEPTED: "✅",
    OrderStatus.IN_PROGRESS: "🚗"
}
STATUS_TEXT = {
    OrderStatus.PENDING: "Haydovchi kutilmoqda",
    OrderStatus.ACCEPTED: "Haydovchi topildi",
    OrderStatus.IN_PROGRESS: "Safar davom etmoqda"
}
@router.message(F.text == "📋 Faol buyurtmalar")
@with_passenger_session  # ✅ Decorator
async def view_active_orders(message: Message, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """
    Yo'lovchining barcha faol buyurtmalarini ko'rsatish
    ✅ REFACTORED: Session va passenger avtomatik
    NIMA KO'RSATILADI:
    - PENDING buyurtmalar - Haydovchi kutilmoqda
    - ACCEPTED buyurtmalar - Haydovchi topildi
    - IN_PROGRESS buyurtmalar - Safar davom etmoqda
    """
    # Agar oldindan driver state qolib ketgan bo'lsa, tozalaymiz
    current_state = await state.get_state()
    if current_state and current_state.startswith(DriverStates.__name__):
        await state.clear()
    # Barcha faol buyurtmalarni olish
    active_orders_result = await session.execute(
            select(Order)
            .options(
                selectinload(Order.route),
                selectinload(Order.driver).selectinload(Driver.user)
            )
            .where(Order.passenger_id == passenger.passenger_id)
            .where(Order.status.in_([OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            .order_by(Order.created_at.desc())
        )
    active_orders = active_orders_result.scalars().all()
    if not active_orders:
        await message.answer(
            "📋 <b>Faol buyurtmalar yo'q</b>\n\n"
            "Hozirda sizda aktiv buyurtmalar mavjud emas.\n\n"
            "Taksi chaqirish uchun 'Taksi chaqirish' tugmasini bosing.",
            reply_markup=get_passenger_main_menu(),
            parse_mode="HTML"
        )
        return
    # Buyurtmalarni formatlash
    orders_text = "📋 <b>Sizning faol buyurtmalaringiz:</b>\n\n"
    cancellable_ids: list[int] = []
    for order in active_orders:
        status_emoji = STATUS_EMOJI.get(order.status, "❓")
        status_text = STATUS_TEXT.get(order.status, "Noma'lum")
        # Marshrut nomi
        route_name = order.route.route_name if order.route else "Noma'lum"
        # Vaqt
        from datetime import datetime
        import pytz
        created_time = order.created_at.astimezone(pytz.timezone('Asia/Tashkent'))
        time_str = created_time.strftime("%H:%M, %d.%m.%Y")
        orders_text += f"{status_emoji} <b>Buyurtma #{order.order_id}</b>\n"
        orders_text += f"├ 🛣 Marshrut: {route_name}\n"
        orders_text += f"├ 📍 Joylashuv: {order.pickup_location}\n"
        orders_text += f"├ 📅 Vaqt: {time_str}\n"
        orders_text += f"└ 📊 Holat: {status_text}\n"
        # Haydovchi ma'lumotlari (agar ACCEPTED yoki IN_PROGRESS bo'lsa)
        if order.status in [OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS] and order.driver:
            driver = order.driver
            orders_text += f"\n🚗 <b>Haydovchi:</b>\n"
            orders_text += f"  👤 {driver.full_name}\n"
            orders_text += f"  🚙 {driver.car_model}, {driver.car_color}\n"
            orders_text += f"  📋 {driver.car_number}\n"
            if driver.user:
                orders_text += f"  📱 {driver.user.phone_number}\n"
        if order.status in [OrderStatus.PENDING, OrderStatus.ACCEPTED]:
            cancellable_ids.append(order.order_id)
        orders_text += "\n"
    orders_text += "ℹ️ <i>Buyurtma yakunlangach bu ro'yxatdan o'chadi va 'Safar tarixi'da ko'rinadi.</i>"
    reply_markup = _build_cancel_keyboard(cancellable_ids) if cancellable_ids else get_passenger_main_menu()
    await message.answer(
        orders_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    logger.info(f"Passenger {passenger.passenger_id} viewed {len(active_orders)} active orders")

def _build_cancel_keyboard(order_ids: list[int]) -> InlineKeyboardMarkup:
    """Cancellable buyurtmalar uchun inline keyboard."""
    buttons = [
        [InlineKeyboardButton(text=f"❌ #{oid} ni bekor qilish", callback_data=f"passenger_cancel:{oid}")]
        for oid in order_ids
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
__all__ = ['router']