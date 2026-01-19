"""
app/bot/handlers/common.py

COMMON ENDPOINTS & FALLBACKS

BU HANDLER NIMA QILADI:
1. /cancel command - Har qanday holatdan chiqish
2. Fallback handler - Kutilmagan inputlar uchun (Hanging fix)
3. Echo handler - Tushunarsiz xabarlar uchun

MUHIM:
Bu routerni dispatcherga ENG OXIRIDA qo'shish kerak!
"""
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from loguru import logger

from app.bot.states.registration import RegistrationStates
from app.bot.states.driver import DriverStates
from app.bot.states.passenger import PassengerStates

router = Router()

# ============================================
# 1. GLOBAL CANCEL COMMAND
# ============================================

@router.message(Command(commands=["cancel"]), StateFilter("*"))
@router.message(F.text == "❌ Bekor qilish", StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext):
    """
    Har qanday holatdan chiqish va state'ni tozalash
    """
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer(
            "Hozir hech qanday jarayon ketmayapti.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    logger.info(f"Cancelling state {current_state} for user {message.from_user.id}")
    
    # State'ni tozalash
    await state.clear()
    
    await message.answer(
        "🚫 Jarayon bekor qilindi.\n"
        "Boshlash uchun: /start",
        reply_markup=ReplyKeyboardRemove()
    )


# ============================================
# 2. GENERIC FALLBACK (HANGING FIX)
# ============================================

@router.message(StateFilter("*"))
async def generic_fallback(message: Message, state: FSMContext):
    """
    CATCH-ALL HANDLER
    
    Agar user active state'da bo'lsa va noto'g'ri narsa yuborsa 
    (masalan, Rasm o'rniga Text, yoki Text o'rniga Sticker),
    bu handler ishlaydi va userga to'g'ri yo'l ko'rsatadi.
    
    OSILIB QOLISHNI OLDINI OLADI!
    """
    current_state = await state.get_state()
    
    if current_state:
        # User biror jarayonda, lekin noto'g'ri narsa yubordi
        logger.warning(
            f"Invalid input from user {message.from_user.id} "
            f"in state {current_state}. Content type: {message.content_type}"
        )
        
        # State turiga qarab xabar (Generic)
        await message.answer(
            "⚠️ <b>Noto'g'ri ma'lumot turi!</b>\n\n"
            "Iltimos, so'ralgan ma'lumotni to'g'ri formatda yuboring.\n"
            "Yoki bekor qilish uchun: /cancel",
            parse_mode="HTML"
        )
    else:
        # User hech qanday jarayonda emas (Main Menu bo'lishi kerak edi)
        await message.answer(
            "Tushunmadim. Menyudan fodalaning yoki /start bosing."
        )
