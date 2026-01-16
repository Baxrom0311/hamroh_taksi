"""
app/bot/handlers/passenger/main_menu.py
"""

from ..base import *


router = Router()


@router.message(F.text == "📍 Mening buyurtmalarim")
@with_passenger_session  # ✅ Decorator
async def my_orders(message: Message, session: AsyncSession, passenger: Passenger):
    """Yo'lovchining aktiv buyurtmalari - ✅ REFACTORED"""
    # Aktiv buyurtmalarni olish
    from sqlalchemy import select
    from app.models.order import Order, OrderStatus
    
    result = await session.execute(
        select(Order)
        .where(Order.passenger_id == passenger.passenger_id)
        .where(Order.status.in_([
            OrderStatus.PENDING,
            OrderStatus.ACCEPTED,
            OrderStatus.IN_PROGRESS
        ]))
        .order_by(Order.created_at.desc())
    )
    
    orders = result.scalars().all()
    
    if not orders:
        await message.answer(
            "📭 <b>Aktiv buyurtmalar yo'q</b>\n\n"
            "Yangi buyurtma berish uchun:\n"
            "Menyu → Taksi chaqirish"
        )
        return
    
    text = "📦 <b>Sizning buyurtmalaringiz:</b>\n\n"
    
    for order in orders:
        status_emoji = {
            OrderStatus.PENDING: "⏳",
            OrderStatus.ACCEPTED: "✅",
            OrderStatus.IN_PROGRESS: "🚗"
        }
        
        text += (
            f"{status_emoji.get(order.status, '📦')} <b>Buyurtma #{order.order_id}</b>\n"
            f"Holat: {order.status.value}\n"
            f"📍 Olish joyi: {order.pickup_location}\n"
            f"👥 Yo'lovchilar: {order.passenger_count}\n"
            f"───────────────\n\n"
        )
    
    await message.answer(text)


@router.message(F.text == "⭐ Tarix")
@with_passenger_session  # ✅ Decorator
async def order_history(message: Message, session: AsyncSession, passenger: Passenger):
    """Buyurtmalar tarixi - ✅ REFACTORED"""
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👤 Ism: <b>{passenger.full_name}</b>\n"
        f"🚕 Jami safarlar: <b>{passenger.total_trips}</b>\n\n"
        f"📅 Ro'yxatdan o'tgan: {passenger.created_at.strftime('%d.%m.%Y')}"
    )


@router.message(F.text == "⚙️ Sozlamalar")
@with_passenger_session  # ✅ Decorator
async def passenger_settings(message: Message, session: AsyncSession, passenger: Passenger):
    """Yo'lovchi sozlamalari - ✅ REFACTORED"""
    settings_text = f"""
⚙️ <b>Sozlamalar</b>

👤 <b>Ism:</b> {passenger.full_name}
📱 <b>Telefon:</b> <code>{passenger.user.phone_number if passenger.user else 'N/A'}</code>
🚕 <b>Jami safarlar:</b> {passenger.total_trips}
📅 <b>Ro'yxatdan o'tgan:</b> {passenger.created_at.strftime('%d.%m.%Y')}

<b>Funksiyalar:</b>
• Profil ma'lumotlarini o'zgartirish (tez orada)
• Xabarnomalarni boshqarish (tez orada)
• Tilni o'zgartirish (tez orada)
    """
    
    await message.answer(settings_text, parse_mode="HTML")



__all__ = ['router']