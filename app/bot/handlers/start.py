"""
app/bot/handlers/start.py

/start COMMAND HANDLER

BU HANDLER NIMA QILADI:
- /start commandni qabul qiladi
- User ro'yxatdan o'tganligini tekshiradi
- Rol bo'yicha yo'naltiradi (driver/passenger)

ISHLATISH:
    User: /start
    Bot: Assalomu alaykum! ... (ro'yxatdan o'tish)
"""

from .base import *
from app.admin.routes import settings
from app.bot.keyboards.driver import get_driver_main_menu, get_trip_active_keyboard
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.bot.keyboards.common import get_registration_choice_keyboard, get_support_keyboard
from app.bot.states.driver import DriverStates
from app.models.order import Order, OrderStatus


# Router yaratish
router = Router()


# ============================================
# /start COMMAND
# ============================================

@router.message(CommandStart())
@with_session  # ✅ Decorator
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
    """
    /start command handler
    
    ✅ REFACTORED: Session auto
    """
    
    user_id = message.from_user.id # type: ignore
    
    # Database'dan user'ni qidirish
    user = await get_user_by_id(session, user_id)
    
    if not user:
        # ========================================
        # RO'YXATDAN O'TMAGAN
        # ========================================
        
        await message.answer(
            f"👋 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n" # type: ignore
            f"🚗 <b>Hamroh Bot</b>ga xush kelibsiz!\n\n"
            f"Bu bot orqali siz:\n"
            f"• Yo'lovchi sifatida taksi chaqirishingiz\n"
            f"• Haydovchi sifatida buyurtma qabul qilishingiz mumkin\n\n"
            f"🔐 Davom etish uchun <b>ro'yxatdan o'teing</b>",
            reply_markup=get_registration_choice_keyboard()
        )
        
        # FSM state o'rnatish
        from app.bot.states.registration import RegistrationStates
        await state.set_state(RegistrationStates.choose_role)
        
        return
    
    # ========================================
    # RO'YXATDAN O'TGAN
    # ========================================
    
    # User bloklangan?
    if user.is_blocked:
        await message.answer(
            "🚫 <b>Hisobingiz bloklangan!</b>\n\n"
            "Murojaat uchun: @support",
            reply_markup=get_support_keyboard()
        )
        return
    
    # Role bo'yicha yo'naltirish (avval passenger, keyin driver)
    if user.is_passenger:
        # YO'LOVCHI
        passenger = await get_passenger_by_user_id(session, user_id)
        
        if not passenger:
            await message.answer(
                "❌ Yo'lovchi ma'lumotlari topilmadi.\n"
                "Support bilan bog'laning: @support"
            )
            return
        
        # Har qanday eski state'ni tozalab yuboramiz (driver state i yoki boshqalar)
        await state.clear()

        # Passenger menyusiga yo'naltirish
        await message.answer(
            f"👋 Xush kelibsiz, <b>{passenger.full_name}</b>!\n\n"
            f"🚕 Jami safarlar: <b>{passenger.total_trips}</b>\n\n"
            f"📍 Qayerga borishni xohlaysiz?",
            reply_markup=get_passenger_main_menu()
        )

    elif user.is_driver:
        # HAYDOVCHI
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer(
                "❌ Haydovchi ma'lumotlari topilmadi.\n"
                "Support bilan bog'laning: @support"
            )
            return

        # Agar safarda bo'lsa, aktiv buyurtmani qayta yuklab state ni tiklash
        if driver.is_on_trip:
            order_result = await session.execute(
                select(Order)
                .where(Order.driver_id == driver.driver_id)
                .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
                .order_by(Order.created_at.desc())
                .limit(1)
            )
            active_order = order_result.scalar_one_or_none()

            if active_order:
                await state.update_data(current_order_id=active_order.order_id)
                await state.set_state(DriverStates.trip_in_progress)
                await message.answer(
                    Messages.Driver.ALREADY_ON_TRIP,
                    reply_markup=get_trip_active_keyboard(active_order.order_id),
                    parse_mode="HTML"
                )
                return
            else:
                # DB flag safarda, lekin aktiv order topilmadi -> flagni tozalaymiz
                await session.execute(
                    update(Driver)
                    .where(Driver.driver_id == driver.driver_id)
                    .values(is_on_trip=False)
                )
                await session.commit()
                await state.clear()
        
        # Driver menyusiga yo'naltirish
        # Oldingi state'larni tozalaymiz (safarda bo'lmasa)
        await state.clear()
        await state.set_state(DriverStates.waiting_orders)
        await message.answer(
            f"👋 Xush kelibsiz, <b>{driver.full_name}</b>!\n\n"
            f"🚗 {driver.car_model} ({driver.car_number})\n"
            f"💰 Balans: <b>{driver.balance:,} so'm</b>\n"
            f"⭐ Reyting: <b>{driver.rating}/5.0</b>\n"
            f"🚕 Jami safarlar: <b>{driver.total_trips}</b>",
            reply_markup=get_driver_main_menu()
        )

    elif user.is_admin:
        # ADMIN
        await message.answer(
            f"👨‍💼 Admin panel\n\n"
            f"Rol: <b>{user.role.value}</b>\n\n"
            f"Web admin: {getattr(settings, 'ADMIN_PANEL_URL', 'N/A')}",
            reply_markup=get_support_keyboard()
        )
    
    else:
        await message.answer("❌ Noma'lum rol. Support bilan bog'laning.")


# ============================================
# EXPORT
# ============================================

__all__ = ['router']
