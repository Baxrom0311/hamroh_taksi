"""
app/bot/handlers/passenger/main_menu.py
"""

from ..base import *
from aiogram.filters import StateFilter
from app.bot.states.passenger import PassengerStates
from app.bot.keyboards.passenger import get_passenger_main_menu


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
async def passenger_settings(message: Message, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """Yo'lovchi sozlamalari - ✅ REFACTORED"""
    settings_text = f"""
⚙️ <b>Sozlamalar</b>

👤 <b>Ism:</b> {passenger.full_name}
📱 <b>Telefon:</b> {passenger.user.phone_number if passenger.user else 'N/A'}
🚕 <b>Jami safarlar:</b> {passenger.total_trips}
📅 <b>Ro'yxatdan o'tgan:</b> {passenger.created_at.strftime('%d.%m.%Y')}

<b>Funksiyalar:</b>
• Profil ma'lumotlarini o'zgartirish
    """
     
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Ismni o'zgartirish")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(settings_text, parse_mode="HTML", reply_markup=keyboard)
    # Back tugmasi ushbu kontekstda ishlashi uchun state belgilaymiz
    await state.set_state(PassengerStates.main_menu)


@router.message(F.text == "✏️ Ismni o'zgartirish")
@with_passenger_session
async def start_edit_name(message: Message, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """Ismni o'zgartirishni boshlash"""
    await message.answer(
        "✏️ Yangi ismingizni kiriting:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
            resize_keyboard=True
        )
    )
    await state.set_state(PassengerStates.edit_name)


@router.message(StateFilter(PassengerStates.edit_name), F.text)
@with_passenger_session
async def finish_edit_name(message: Message, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """Ismni yangilash"""
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("⬅️ Asosiy menyu", reply_markup=get_passenger_main_menu())
        return
    
    if not message.text:
        await message.answer("⚠️ Iltimos, ism kiriting.")
        return

    new_name = message.text.strip()
    if len(new_name) < 2:
        await message.answer("❌ Ism juda qisqa. Iltimos, to'liq ismingizni kiriting.")
        return
    
    passenger.full_name = new_name
    if passenger.user:
        passenger.user.first_name = new_name
    await session.flush()
    
    await state.clear()
    await message.answer(
        f"✅ Ismingiz yangilandi: <b>{new_name}</b>",
        parse_mode="HTML",
        reply_markup=get_passenger_main_menu()
    )


@router.message(StateFilter(PassengerStates.main_menu), F.text == "⬅️ Orqaga")
@with_passenger_session
async def back_from_settings(message: Message, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """Sozlamalardan asosiy menyuga qaytish"""
    await state.clear()
    await message.answer("⬅️ Asosiy menyu", reply_markup=get_passenger_main_menu())



__all__ = ['router']
