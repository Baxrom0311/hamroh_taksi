"""
app/bot/handlers/passenger/support.py

PASSENGER SUPPORT HANDLERS
"""

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger
from config.settings import settings

from app.core.database import get_session
from app.models.feedback import create_feedback, FeedbackType
from app.bot.messages import Messages
from app.bot.states.passenger import PassengerStates
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.bot.utils import get_passenger_or_error

router = Router()


# ============================================
# SUPPORT MENYU
# ============================================

@router.message(F.text.in_(["📞 Support", "📞 Support xizmati", "SOS"]))
async def support_menu(message: Message, state: FSMContext):
    """
    Support bo'limi
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Shikoyat yuborish"), KeyboardButton(text="� Taklif yuborish")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        Messages.Error.SUPPORT_INFO,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ============================================
# SHIKOYAT YUBORISH
# ============================================

@router.message(F.text == "📝 Shikoyat yuborish")
async def start_complaint(message: Message, state: FSMContext):
    """
    Shikoyat yuborishni boshlash
    """
    await message.answer(
        "📝 <b>Shikoyat yuborish</b>\n\n"
        "Shikoyatingizni yozing:\n\n"
        "Masalan: \"Haydovchi qo'pol muomala qildi\", \"Mashina toza emas\", va h.k.",
        parse_mode="HTML"
    )
    
    await state.update_data(feedback_type=FeedbackType.COMPLAINT.value)
    await state.set_state(PassengerStates.support_complaint)


@router.message(F.text == "💡 Taklif yuborish")
async def start_suggestion(message: Message, state: FSMContext):
    """
    Taklif yuborishni boshlash
    """
    await message.answer(
        "� <b>Taklif yuborish</b>\n\n"
        "Taklifingizni yozing:\n\n"
        "Biz xizmat sifatini yaxshilash uchun harakat qilamiz!",
        parse_mode="HTML"
    )
    
    await state.update_data(feedback_type=FeedbackType.SUGGESTION.value)
    await state.set_state(PassengerStates.support_complaint)


@router.message(PassengerStates.support_complaint, F.text)
async def complaint_text_entered(message: Message, state: FSMContext):
    """Shikoyat matni kiritildi"""
    if message.from_user is None or not message.text:
        await message.answer("Xatolik: matn topilmadi")
        await state.clear()
        return
    
    user_id = message.from_user.id
    complaint_text = message.text
    
    if len(complaint_text) < 10:
        await message.answer("❌ Shikoyat juda qisqa (minimal 10 belgi)")
        return
    
    data = await state.get_data()
    feedback_type = data.get('feedback_type', FeedbackType.COMPLAINT.value)
    
    async with get_session() as session:
        passenger = await get_passenger_or_error(session, user_id, message)
        if not passenger:
            await state.clear()
            return
        
        # Feedback yaratish
        feedback = await create_feedback(
            session,
            user_id=user_id, # User ID (passenger.user_id)
            message=complaint_text,
            type=FeedbackType(feedback_type)
        )
        
        # Admin'ga xabar
        from app.tasks.notifications import notify_admins
        notify_admins.delay(
            f"📝 <b>Yangi {feedback.type.value} (Yo'lovchi)</b> #{feedback.feedback_id}\n\n"
            f"👤 Yo'lovchi: {passenger.full_name}\n"
            f"📱 Telefon: {passenger.phone_number}\n\n"
            f"📄 Matn:\n"
            f"{complaint_text}\n\n"
            f"---\n"
            f"Javob berish: /reply {feedback.feedback_id}"
        )
        
        await message.answer(
            f"✅ <b>{feedback.type.value.capitalize()} yuborildi!</b>\n\n"
            "Admin ko'rib chiqadi va sizga javob beradi.\n\n"
            "⏳ Javobni kuting...",
            reply_markup=get_passenger_main_menu(),
            parse_mode="HTML"
        )
        
        logger.info(
            f"Feedback submitted: passenger={passenger.passenger_id}, "
            f"id={feedback.feedback_id}"
        )
    
    await state.clear()





# ============================================
# ORQAGA
# ============================================

@router.message(F.text == "⬅️ Orqaga")
async def back_to_main_menu(message: Message, state: FSMContext):
    """Asosiy menyuga qaytish"""
    await state.clear()
    await message.answer(
        "⬅️ Asosiy menyu",
        reply_markup=get_passenger_main_menu()
    )


__all__ = ['router']
