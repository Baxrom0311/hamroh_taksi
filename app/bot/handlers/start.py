"""
app/bot/handlers/start.py

/start COMMAND HANDLER
"""

import os
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.database import get_session
from app.bot.decorators import with_session
from app.models.user import get_user_by_id
from app.models.passenger import get_passenger_by_user_id
from app.models.driver import get_driver_by_user_id
from app.bot.keyboards.driver import get_driver_main_menu, get_trip_active_keyboard
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.bot.keyboards.common import get_registration_choice_keyboard, get_support_keyboard
from app.bot.states.driver import DriverStates
from app.models.order import Order, OrderStatus
from config.settings import settings as config_settings


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
            f"🔐 Davom etish uchun <b>ro'yxatdan o'ting</b>",
            reply_markup=get_registration_choice_keyboard()
        )

        try:
            # Video yuborish (Local File or File ID)
            from app.models.system_settings import get_setting, set_setting
            
            # Helper function to send or upload video
            async def send_or_upload_video(key_id, filename, caption):
                video_id = await get_setting(session, key_id)
                
                # 1. Agar ID bo'lsa - ID orqali yuboramiz
                if video_id:
                    try:
                        await message.answer_video(video_id, caption=caption)
                        return
                    except Exception:
                        # ID eskirgan bo'lishi mumkin, reset qilamiz
                        logger.warning(f"Invalid video file_id for {key_id}, retrying with file...")
                
                # 2. Agar ID yo'q bo'lsa yoki xato bersa - Fayldan yuklaymiz
                video_path = f"/app/videos/{filename}"
                if os.path.exists(video_path):
                    logger.info(f"Uploading video from {video_path}...")
                    video_file = FSInputFile(video_path)
                    msg = await message.answer_video(video_file, caption=caption)
                    
                    # 3. Yangi ID ni saqlab qo'yamiz (Cache)
                    if msg.video:
                        await set_setting(session, key_id, msg.video.file_id)
                        await session.commit()
                        logger.success(f"Cached new video ID for {key_id}")
                else:
                    logger.debug(f"Video file not found: {video_path}")

            # 1-video
            await send_or_upload_video(
                'onboarding_video_1_id', 
                'telegram-cloud-document-2-5474487790769052786.mp4',
                "📹 <b>Tizimdan foydalanish (1-qism)</b>"
            )
            
            # 2-video
            await send_or_upload_video(
                'onboarding_video_2_id', 
                'telegram-cloud-document-2-5474487790769052826.mp4',
                "📹 <b>Tizimdan foydalanish (2-qism)</b>"
            )

        except Exception as e:
            logger.error(f"Failed to send onboarding video: {e}")
        
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
            # Profil o'chirilgan bo'lsa, qayta ro'yxatdan o'tishni taklif qilamiz
            await message.answer(
                "⚠️ <b>Sizning profilingiz topilmadi</b> (ehtimol o'chirilgan).\n"
                "Iltimos, qayta ro'yxatdan o'ting:",
                reply_markup=get_registration_choice_keyboard()
            )
            from app.bot.states.registration import RegistrationStates
            await state.set_state(RegistrationStates.choose_role)
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
            # Profil o'chirilgan bo'lsa, qayta ro'yxatdan o'tishni taklif qilamiz
            await message.answer(
                "⚠️ <b>Sizning profilingiz topilmadi</b> (ehtimol o'chirilgan).\n"
                "Iltimos, qayta ro'yxatdan o'ting:",
                reply_markup=get_registration_choice_keyboard()
            )
            from app.bot.states.registration import RegistrationStates
            await state.set_state(RegistrationStates.choose_role)
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
                # ✅ AUTO-CLEANUP: Centralized helper
                from app.utils.driver_state_utils import cleanup_stuck_driver_state
                
                await cleanup_stuck_driver_state(session, driver.driver_id)
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
