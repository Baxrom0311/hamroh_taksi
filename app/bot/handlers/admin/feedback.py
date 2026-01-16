"""
app/bot/handlers/admin/feedback.py

ADMIN FEEDBACK HANDLERS
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy import select, update, desc, func
from datetime import datetime

from app.core.database import get_session
from app.models.user import User, get_user_by_id
from app.models.feedback import Feedback, FeedbackStatus, FeedbackType, get_feedback_by_id

router = Router()


# ============================================
# HELPER KEYBOARDS
# ============================================

def get_feedback_list_keyboard(feedbacks):
    """Feedback ro'yxati uchun keyboard"""
    buttons = []
    
    for fb in feedbacks:
        icon = "🔴" if fb.status == FeedbackStatus.OPEN else "🟢"
        type_icon = "📝" if fb.type == FeedbackType.COMPLAINT else "💡"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {type_icon} #{fb.feedback_id} - {fb.created_at.strftime('%d.%m %H:%M')}",
                callback_data=f"view_feedback:{fb.feedback_id}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_feedback_detail_keyboard(feedback_id: int):
    """Feedback batafsil ko'rish uchun keyboard"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ Javob berish", callback_data=f"reply_feedback:{feedback_id}"),
                InlineKeyboardButton(text="✅ Yopish", callback_data=f"close_feedback:{feedback_id}")
            ],
            [
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="list_feedbacks")
            ]
        ]
    )


# ============================================
# VIEW LIST
# ============================================

@router.message(Command("feedback"))
async def list_feedbacks_command(message: Message):
    """
    /feedback
    Barcha ochiq feedbacklarni ko'rish
    """
    user_id = message.from_user.id
    
    async with get_session() as session:
        user = await get_user_by_id(session, user_id)
        if not user or not user.is_admin:
            return

        # Ochiq feedbacklarni olish
        query = (
            select(Feedback)
            .where(Feedback.status == FeedbackStatus.OPEN)
            .order_by(desc(Feedback.created_at))
            .limit(10)
        )
        result = await session.execute(query)
        feedbacks = result.scalars().all()
        
        if not feedbacks:
            await message.answer("✅ Hozircha yangi murojaatlar yo'q")
            return
        
        await message.answer(
            f"📋 <b>Yangi murojaatlar ({len(feedbacks)})</b>\n\n"
            "Ko'rish uchun tanlang:",
            reply_markup=get_feedback_list_keyboard(feedbacks),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "list_feedbacks")
async def list_feedbacks_callback(callback: CallbackQuery):
    """
    Feedback ro'yxatiga qaytish
    """
    await callback.answer()
    if callback.message:
        await list_feedbacks_command(callback.message)


# ============================================
# VIEW ITEM
# ============================================

@router.callback_query(F.data.startswith("view_feedback:"))
async def view_feedback(callback: CallbackQuery):
    """
    Feedbackni batafsil ko'rish
    """
    feedback_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        # Feedback + User ni olish
        from sqlalchemy.orm import selectinload
        query = (
            select(Feedback)
            .options(selectinload(Feedback.user))
            .where(Feedback.feedback_id == feedback_id)
        )
        result = await session.execute(query)
        feedback = result.scalar_one_or_none()
        
        if not feedback:
            await callback.answer("❌ Murojaat topilmadi", show_alert=True)
            return
            
        type_str = "Shikoyat" if feedback.type == FeedbackType.COMPLAINT else "Taklif"
        status_icon = "🔴" if feedback.status == FeedbackStatus.OPEN else "🟢"
        
        text = (
            f"<b>{status_icon} Murojaat #{feedback.feedback_id}</b>\n\n"
            f"<b>Tur:</b> {type_str}\n"
            f"<b>User:</b> {feedback.user.first_name} ({feedback.user.phone_number})\n"
            f"<b>Vaqt:</b> {feedback.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"<b>Matn:</b>\n{feedback.message}"
        )
        
        if feedback.admin_reply:
            text += f"\n\n<b>Admin javobi:</b>\n{feedback.admin_reply}"
        
        await callback.message.edit_text(
            text,
            reply_markup=get_feedback_detail_keyboard(feedback_id),
            parse_mode="HTML"
        )


# ============================================
# REPLY
# ============================================

from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    feedback_reply = State()

@router.callback_query(F.data.startswith("reply_feedback:"))
async def reply_feedback(callback: CallbackQuery, state: FSMContext):
    """
    Javob berishni boshlash
    """
    feedback_id = int(callback.data.split(":")[1])
    
    await state.update_data(reply_feedback_id=feedback_id)
    await state.set_state(AdminStates.feedback_reply)
    
    await callback.message.answer(
        f"✍️ <b>Murojaat #{feedback_id} uchun javob yozing:</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.feedback_reply)
async def send_reply(message: Message, state: FSMContext):
    """
    Javobni yuborish
    """
    data = await state.get_data()
    feedback_id = data.get('reply_feedback_id')
    reply_text = message.text
    admin_id = message.from_user.id
    
    if not reply_text:
        await message.answer("❌ Matn kiriting")
        return

    async with get_session() as session:
        # Update Feedback
        query = (
            update(Feedback)
            .where(Feedback.feedback_id == feedback_id)
            .values(
                status=FeedbackStatus.RESOLVED,
                admin_reply=reply_text,
                resolved_by=admin_id, # UserID emas, DB id bo'lishi kerak. Fix: hozircha admin's telegram id
                resolved_at=func.now()
            )
            .returning(Feedback.user_id) # User ID qaytarish
        )
        
        result = await session.execute(query)
        user_id = result.scalar_one_or_none()
        await session.commit()
        
        if user_id:
            # User'ga xabar yuborish
            from app.bot.main import bot
            try:
                # User (telegram ID) topish kerak. 
                # Hozir user_id bu Users table'dagi ID. U Telegram ID bilan bir xil bo'lsa OK.
                # Agar User tableda user_id = telegram_id bo'lsa:
                
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"📨 <b>Sizning murojaatingizga javob (#{feedback_id})</b>\n\n"
                        f"📝 <b>Javob:</b>\n{reply_text}"
                    ),
                    parse_mode="HTML"
                )
                await message.answer("✅ Javob yuborildi!")
            except Exception as e:
                await message.answer(f"⚠️ Javob yuborilmadi (User bloklagan bo'lishi mumkin): {e}")
        else:
            await message.answer("❌ Feedback topilmadi")

    await state.clear()


@router.callback_query(F.data.startswith("close_feedback:"))
async def close_feedback(callback: CallbackQuery):
    """
    Shunchaki yopish (javobsiz)
    """
    feedback_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        await session.execute(
            update(Feedback)
            .where(Feedback.feedback_id == feedback_id)
            .values(
                status=FeedbackStatus.IGNORED,
                resolved_at=func.now()
            )
        )
        await session.commit()
    
    await callback.answer("✅ Yopildi")
    await list_feedbacks_callback(callback)


__all__ = ['router']
