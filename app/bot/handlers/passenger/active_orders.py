"""
app/bot/handlers/passenger/active_orders.py

YO'LOVCHI - FAOL BUYURTMALAR

Yo'lovchi o'zining barcha faol buyurtmalarini (PENDING, ACCEPTED, IN_PROGRESS) ko'ra oladi.
"""

from aiogram import Router, F
from aiogram.types import Message
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
async def view_active_orders(message: Message, state: FSMContext):
    """
    Yo'lovchining barcha faol buyurtmalarini ko'rsatish
    
    NIMA KO'RSATILADI:
    - PENDING buyurtmalar - Haydovchi kutilmoqda
    - ACCEPTED buyurtmalar - Haydovchi topildi
    - IN_PROGRESS buyurtmalar - Safar davom etmoqda
    """
    user_id = message.from_user.id  # type: ignore
    
    async with get_session() as session:
        passenger = await get_passenger_or_error(session, user_id, message)
        if not passenger:
            return
        
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
                    orders_text += f"  📱 <code>{driver.user.phone_number}</code>\n"
            
            orders_text += "\n"
        
        orders_text += "ℹ️ <i>Buyurtma yakunlangach bu ro'yxatdan o'chadi va 'Safar tarixi'da ko'rinadi.</i>"
        
        await message.answer(
            orders_text,
            reply_markup=get_passenger_main_menu(),
            parse_mode="HTML"
        )
        
        logger.info(f"Passenger {passenger.passenger_id} viewed {len(active_orders)} active orders")


__all__ = ['router']
