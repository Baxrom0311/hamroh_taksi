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
from app.models.transaction import Transaction, TransactionType, create_transaction
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import get_driver_main_menu

router = Router()


# ============================================
# SUPPORT MENYU
# ============================================

@router.message(F.text == "📞 Support")
async def support_menu(message: Message, state: FSMContext):
    """
    Support bo'limi
    
    NIMA BO'LADI:
    1. Chek yuborish (balans to'ldirish)
    2. Shikoyat yuborish
    3. Support bot linki
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Chek yuborish")],
            [KeyboardButton(text="📝 Shikoyat yuborish")],
            [KeyboardButton(text="🔗 Support bot")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "👨‍💻 <b>Support bo'limi</b>\n\n"
        "Quyidagilardan birini tanlang:",
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
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer("❌ Haydovchi ma'lumotlari topilmadi")
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
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer("❌ Haydovchi ma'lumotlari topilmadi")
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
    
    FLOW:
    1. Shikoyat matnini yozish
    2. Admin'ga yuborish
    """
    user_id = message.from_user.id if message.from_user else None
    
    if not user_id:
        await message.answer("Xatolik: user topilmadi")
        return
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer("❌ Haydovchi ma'lumotlari topilmadi")
            return
    
    await message.answer(
        "📝 <b>Shikoyat yuborish</b>\n\n"
        "Shikoyatingizni yozing:\n\n"
        "Masalan: \"Yo'lovchi kechikdi\", \"Mashina muammosi\", va h.k.",
        parse_mode="HTML"
    )
    
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
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer("❌ Haydovchi ma'lumotlari topilmadi")
            await state.clear()
            return
        
        # Admin'ga xabar
        from app.tasks.notifications import notify_admins
        notify_admins.delay(
            f"""
📝 <b>Yangi shikoyat</b>

👤 Haydovchi: {driver.full_name}
📱 Telefon: {driver.phone_number}
🚗 Mashina: {driver.car_model} ({driver.car_number})
🆔 Driver ID: {driver.driver_id}

📄 Shikoyat:
{complaint_text}

---
Admin javob berishi mumkin.
            """
        )
        
        await message.answer(
            "✅ <b>Shikoyat yuborildi!</b>\n\n"
            "Admin ko'rib chiqadi va sizga javob beradi.\n\n"
            "⏳ Javobni kuting...",
            reply_markup=get_driver_main_menu(),
            parse_mode="HTML"
        )
        
        logger.info(
            f"Complaint submitted: driver={driver.driver_id}, "
            f"text_length={len(complaint_text)}"
        )
    
    await state.clear()


# ============================================
# SUPPORT BOT LINKI
# ============================================

@router.message(F.text == "🔗 Support bot")
async def support_bot_link(message: Message):
    """
    Support bot linkini ko'rsatish
    
    NOTE: Support bot username'ni settings'dan olish kerak
    """
    support_bot_username = getattr(settings, 'SUPPORT_BOT_USERNAME', '@support_bot')
    
    await message.answer(
        f"🔗 <b>Support bot</b>\n\n"
        f"Muammo bo'yicha yozing:\n"
        f"{support_bot_username}\n\n"
        f"Yoki quyidagi tugmani bosing:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔗 Support botga o'tish", url=f"https://t.me/{support_bot_username.replace('@', '')}")],
                [KeyboardButton(text="⬅️ Orqaga")]
            ],
            resize_keyboard=True
        ),
        parse_mode="HTML"
    )


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
