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
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.registration import RegistrationStates
from app.bot.states.driver import DriverStates
from app.bot.states.passenger import PassengerStates
from app.bot.decorators import with_session
from app.models.user import get_user_by_id

router = Router()

# ============================================
# 0. ADMIN TOOLS (Get File ID)
# ============================================

@router.message(F.video, StateFilter("*"))
@with_session
async def get_video_id(message: Message, session: AsyncSession, state: FSMContext):
    """
    Admin video yuborilganda File ID sini qaytaradi
    """
    try:
        user_id = message.from_user.id
        user = await get_user_by_id(session, user_id)
        
        if user and user.is_admin:
            file_id = message.video.file_id
            await message.reply(
                f"📹 <b>Video File ID:</b>\n\n"
                f"<code>{file_id}</code>\n\n"
                f"<i>Bu ID ni Admin panel > Sozlamalar bo'limiga qo'ying.</i>",
                parse_mode="HTML"
            )
            return
        
        # Agar admin bo'lmasa, pastdagi generic_fallback ishlashi kerak edi, 
        # lekin handler ushlab qoldi. 
        # Shuning uchun oddiy fallback logikasini shu yerda bajaramiz:
        
        current_state = await state.get_state()
        if current_state:
            await message.answer("⚠️ <b>Noto'g'ri ma'lumot turi!</b>\nVideo qabul qilinmaydi.", parse_mode="HTML")
        else:
            await message.answer("Tushunmadim. /start bosing.")

    except Exception as e:
        logger.error(f"Error in get_video_id: {e}")


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

    user_id = message.from_user.id if message.from_user else "Unknown"
    logger.info(f"Cancelling state {current_state} for user {user_id}")
     
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
        user_id = message.from_user.id if message.from_user else "Unknown"
        logger.warning(
            f"Invalid input from user {user_id} "
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
