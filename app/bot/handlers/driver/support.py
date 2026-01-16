"""
app/bot/handlers/driver/support.py

HAYDOVCHI SUPPORT HANDLERS

BU HANDLER NIMA QILADI:
- Chek yuborish (balans to'ldirish)
- Shikoyat yuborish
- Support bot linki
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger
from config.settings import settings

from app.core.database import get_session, transaction
from app.models.driver import get_driver_by_user_id
from app.models.driver import get_driver_by_user_id
from app.models.transaction import Transaction, TransactionType, create_transaction
from app.models.feedback import create_feedback, FeedbackType
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import get_driver_main_menu
from app.bot.messages import Messages
from app.bot.utils import get_driver_or_error

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
            [KeyboardButton(text="💰 Chek yuborish")],
            [KeyboardButton(text="📝 Shikoyat yuborish"), KeyboardButton(text="💡 Taklif yuborish")],
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
# CHEK YUBORISH (BALANS TO'LDIRISH)
# ============================================

@router.message(F.text == "💰 Chek yuborish")
async def start_receipt_upload(message: Message, state: FSMContext):
    """
    Chek yuborishni boshlash
    
    FLOW:
    1. Summa kiritish
    2. Chek rasm yuborish
    3. Admin'ga yuborish
    """
    user_id = message.from_user.id if message.from_user else None
    
    if not user_id:
        await message.answer("Xatolik: user topilmadi")
        return
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, message)
        if not driver:
            return
    
    await message.answer(
        "💰 <b>Balans to'ldirish</b>\n\n"
        "Summani kiriting (so'm):\n\n"
        "Masalan: <code>50000</code>",
        parse_mode="HTML"
    )
    
    await state.set_state(DriverStates.support_receipt_amount)


@router.message(DriverStates.support_receipt_amount, F.text)
async def receipt_amount_entered(message: Message, state: FSMContext):
    """Summa kiritildi"""
    try:
        amount = int(message.text or "0")
        
        if amount <= 0:
            await message.answer("❌ Summa 0 dan katta bo'lishi kerak")
            return
        
        if amount > 10_000_000:  # 10 million limit
            await message.answer("❌ Summa juda katta (maksimal 10,000,000 so'm)")
            return
        
        await state.update_data(receipt_amount=amount)
        
        await message.answer(
            f"✅ Summa: <b>{amount:,} so'm</b>\n\n"
            f"📸 Endi chek rasmini yuboring:",
            parse_mode="HTML"
        )
        
        await state.set_state(DriverStates.support_receipt_photo)
    
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting")


@router.message(DriverStates.support_receipt_photo, F.photo)
async def receipt_photo_uploaded(message: Message, state: FSMContext):
    """Chek rasmi yuklandi"""
    if message.from_user is None or message.photo is None:
        await message.answer("Xatolik: ma'lumotlar topilmadi")
        return
    
    user_id = message.from_user.id
    photo = message.photo[-1]  # Eng katta rasm
    data = await state.get_data()
    amount = data.get('receipt_amount', 0)
    
    if amount <= 0:
        await message.answer("❌ Summa topilmadi. Qaytadan boshlang.")
        await state.clear()
        return
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, message)
        if not driver:
            await state.clear()
            return
        
        # Transaction yaratish
        async with transaction() as session:
            transaction_obj = await create_transaction(
                session,
                driver_id=driver.driver_id,
                amount=amount,
                type=TransactionType.DEPOSIT,
                receipt_file_id=photo.file_id,
                description=f"Balans to'ldirish: {amount:,} so'm"
            )
            
            # Admin'ga xabar
            from app.tasks.notifications import notify_admins
            notify_admins.delay(
                f"""
💰 <b>Yangi balans to'ldirish so'rovi</b>

👤 Haydovchi: {driver.full_name}
📱 Telefon: {driver.phone_number}
💵 Summa: {amount:,} so'm
🆔 Transaction ID: #{transaction_obj.transaction_id}

Admin panel: /admin/transactions/{transaction_obj.transaction_id}
                """
            )
        
        await message.answer(
            f"✅ <b>So'rov yuborildi!</b>\n\n"
            f"💵 Summa: <b>{amount:,} so'm</b>\n"
            f"🆔 So'rov ID: <code>#{transaction_obj.transaction_id}</code>\n\n"
            f"⏳ Admin ko'rib chiqadi (odatda 1 soat ichida)\n\n"
            f"Holat haqida xabar beramiz!",
            reply_markup=get_driver_main_menu(),
            parse_mode="HTML"
        )
        
        logger.info(
            f"Balance topup request: driver={driver.driver_id}, "
            f"amount={amount}, transaction={transaction_obj.transaction_id}"
        )
    
    await state.clear()


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
        "Masalan: \"Yo'lovchi kechikdi\", \"Mashina muammosi\", va h.k.",
        parse_mode="HTML"
    )
    
    await state.update_data(feedback_type=FeedbackType.COMPLAINT.value)
    await state.set_state(DriverStates.support_complaint)


@router.message(F.text == "💡 Taklif yuborish")
async def start_suggestion(message: Message, state: FSMContext):
    """
    Taklif yuborishni boshlash
    """
    await message.answer(
        "💡 <b>Taklif yuborish</b>\n\n"
        "Taklifingizni yozing:\n\n"
        "Biz xizmat sifatini yaxshilash uchun harakat qilamiz!",
        parse_mode="HTML"
    )
    
    await state.update_data(feedback_type=FeedbackType.SUGGESTION.value)
    await state.set_state(DriverStates.support_complaint)


@router.message(DriverStates.support_complaint, F.text)
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
        driver = await get_driver_or_error(session, user_id, message)
        if not driver:
            await state.clear()
            return

        # Feedback yaratish
        feedback = await create_feedback(
            session,
            user_id=user_id, # User model ID si kerak (driver.user_id)
            message=complaint_text,
            type=FeedbackType(feedback_type)
        )
        
        # Admin'ga xabar
        from app.tasks.notifications import notify_admins
        notify_admins.delay(
            f"📝 <b>Yangi {feedback.type.value}</b> #{feedback.feedback_id}\n\n"
            f"👤 Haydovchi: {driver.full_name}\n"
            f"📱 Telefon: {driver.phone_number}\n\n"
            f"📄 Matn:\n"
            f"{complaint_text}\n\n"
            f"---\n"
            f"Javob berish: /reply {feedback.feedback_id}"
        )
        
        await message.answer(
            f"✅ <b>{feedback.type.value.capitalize()} yuborildi!</b>\n\n"
            "Admin ko'rib chiqadi va sizga javob beradi.\n\n"
            "⏳ Javobni kuting...",
            reply_markup=get_driver_main_menu(),
            parse_mode="HTML"
        )
        
        logger.info(
            f"Feedback submitted: driver={driver.driver_id}, "
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
        reply_markup=get_driver_main_menu()
    )


__all__ = ['router']
