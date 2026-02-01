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
# ============================================
# MASHINANI ALMASHTIRISH (Yo'lovchi haydovchini o'zgartirmoqchi)
# ============================================
@router.callback_query(F.data.startswith("change_car:"))
@with_passenger_session  # ✅ Decorator
async def change_car_handler(callback: CallbackQuery, session: AsyncSession, passenger: Passenger):
    """
    Yo'lovchi mashinani almashtirishni xohlasa
    ✅ REFACTORED: Session va passenger avtomatik
    QACHON:
    - Order ACCEPTED holatida (haydovchi topilgan, lekin hali yetib kelmagan)
    - Komissiya haydovchiga qaytariladi
    - Order CANCELLED bo'ladi
    - Yangi haydovchi topish boshlaydi
    """
    if not callback.data:
        await callback.answer("Xatolik")
        return
    order_id = parse_callback_data(callback.data, "change_car")
    if order_id is None:
        await callback.answer("Xatolik: noto'g'ri format")
        return
    # Order'ni tekshirish
    order = await get_order_by_id(session, order_id)
    if not order or order.passenger_id != passenger.passenger_id:
        await callback.answer("Buyurtma topilmadi yoki sizga tegishli emas")
        return
    if order.status not in [OrderStatus.ACCEPTED, OrderStatus.PENDING]:
        await callback.answer(
            "Bu buyurtmani bekor qilib bo'lmaydi (allaqachon boshlangan yoki yakunlangan)",
            show_alert=True
        )
        return
    # ✅ Komissiya qaytarish (trip_service orqali)
    result = await refund_commission_for_order(
        order_id,
        reason="passenger_changed_car"
    )
    if not result['success']:
        await callback.answer(result['message'], show_alert=True)
        return
    # Order yangilash (cancel)
    await session.commit()
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"✅ <b>Buyurtma bekor qilindi</b>\n\n"
            f"💰 Haydovchiga {result.get('refunded_amount', 0):,.0f} so'm qaytarildi\n\n"
            f"🔄 Yangi haydovchi topilmoqda...",
            parse_mode="HTML"
        )
    # Yangi haydovchi topish task
    from typing import Any, cast
    cast(Any, find_driver_for_order_task).delay(order_id)
    logger.info(
        f"Passenger {passenger.passenger_id} changed car for order {order_id}, "
        f"refunded {result.get('refunded_amount', 0)}"
    )
    await callback.answer("Buyurtma bekor qilindi, yangi haydovchi topilmoqda")
def _build_cancel_keyboard(order_ids: list[int]) -> InlineKeyboardMarkup:
    """Cancellable buyurtmalar uchun inline keyboard."""
    buttons = [
        [InlineKeyboardButton(text=f"❌ #{oid} ni bekor qilish", callback_data=f"passenger_cancel:{oid}")]
        for oid in order_ids
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
__all__ = ['router']