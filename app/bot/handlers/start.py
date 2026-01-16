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

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from loguru import logger
from app.admin.routes import settings
from app.core.database import get_session
from app.models.user import get_user_by_id
from app.models.driver import get_driver_by_user_id
from app.models.passenger import get_passenger_by_user_id
from app.bot.keyboards.driver import get_driver_main_menu
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.bot.keyboards.common import get_registration_choice_keyboard, get_support_keyboard

# Router yaratish
router = Router()


# ============================================
# /start COMMAND
# ============================================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    /start command handler
    
    FLOW:
    1. User'ni database'dan qidirish
    2. Agar ro'yxatdan o'tmagan → Registration boshlash
    3. Agar ro'yxatdan o'tgan → Role bo'yicha yo'naltirish
    """
    
    user_id = message.from_user.id # type: ignore
    
    # Database'dan user'ni qidirish
    async with get_session() as session:
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
                f"🔐 Davom etish uchun <b>ro'yxatdan o'ting</b>",
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
        
        # Role bo'yicha yo'naltirish
        if user.is_driver:
            # HAYDOVCHI
            driver = await get_driver_by_user_id(session, user_id)
            
            if not driver:
                await message.answer(
                    "❌ Haydovchi ma'lumotlari topilmadi.\n"
                    "Support bilan bog'laning: @support"
                )
                return
            
            # Driver menyusiga yo'naltirish
            await message.answer(
                f"👋 Xush kelibsiz, <b>{driver.full_name}</b>!\n\n"
                f"🚗 {driver.car_model} ({driver.car_number})\n"
                f"💰 Balans: <b>{driver.balance:,} so'm</b>\n"
                f"⭐ Reyting: <b>{driver.rating}/5.0</b>\n"
                f"🚕 Jami safarlar: <b>{driver.total_trips}</b>",
                reply_markup=get_driver_main_menu()
            )
        
        elif user.is_passenger:
            # YO'LOVCHI
            passenger = await get_passenger_by_user_id(session, user_id)
            
            if not passenger:
                await message.answer(
                    "❌ Yo'lovchi ma'lumotlari topilmadi.\n"
                    "Support bilan bog'laning: @support"
                )
                return
            
            # Passenger menyusiga yo'naltirish
            await message.answer(
                f"👋 Xush kelibsiz, <b>{passenger.full_name}</b>!\n\n"
                f"🚕 Jami safarlar: <b>{passenger.total_trips}</b>\n\n"
                f"📍 Qayerga borishni xohlaysiz?",
                reply_markup=get_passenger_main_menu()
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