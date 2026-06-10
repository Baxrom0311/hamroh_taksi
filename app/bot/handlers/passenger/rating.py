"""
app/bot/handlers/passenger/rating.py
"""

from ..base import *
from aiogram.exceptions import TelegramBadRequest
from app.models.order import Order


router = Router()

@router.callback_query(F.data.startswith("rate_driver:"))
@with_session  # ✅ Decorator
async def rate_driver_handler(callback: CallbackQuery, session: AsyncSession):
    """
    Haydovchiga baho berish
    Format: rate_driver:{order_id}:{stars}
    
    ✅ REFACTORED: Session avtomatik
    """
    from app.bot.utils import parse_callback_multi
    
    result = parse_callback_multi(callback.data, "rate_driver", 2)
    if result is None:
        await callback.answer("Xatolik: noto'g'ri format")
        return
    
    order_id, stars = result

    # Order va Driverni topish
    stmt = select(Order).where(Order.order_id == order_id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        await callback.answer("Buyurtma topilmadi", show_alert=True)
        return

    driver_id = order.driver_id
    if not driver_id:
        await callback.answer("Haydovchi topilmadi", show_alert=True)
        return

    # Haydovchini olish
    driver_stmt = select(Driver).where(Driver.driver_id == driver_id)
    driver_result = await session.execute(driver_stmt)
    driver = driver_result.scalar_one_or_none()

    if not driver:
        await callback.answer("Haydovchi topilmadi", show_alert=True)
        return

    # Reytingni yangilash (Exponential Moving Average)
    # EMA bu yerda aniq — total_rated ga bog'liq emas
    # alpha = 0.3 — yangi baho 30% ta'sir qiladi
    current_rating = float(driver.rating)
    alpha = 0.3
    if current_rating == 0 or driver.total_trips == 0:
        # Birinchi baho
        new_rating = float(stars)
    else:
        new_rating = (alpha * stars) + ((1 - alpha) * current_rating)
    new_rating = max(1.0, min(5.0, new_rating))

    # DB update
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver_id)
        .values(rating=new_rating)
    )
    await session.commit()

    thank_text = (
        f"✅ <b>Rahmat!</b>\n\n"
        f"Sizning bahoingiz: {'⭐️' * stars}"
    )

    # Passengerga javob: xabarni o'chirib, alohida rahmat xabarini yuboramiz
    from app.bot.main import bot
    sent_thanks = False
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.delete()
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=thank_text,
                parse_mode="HTML"
            )
            sent_thanks = True
        except TelegramBadRequest:
            # Agar o'chirib bo'lmasa, mavjud xabarni yangilaymiz
            await callback.message.edit_text(
                thank_text,
                reply_markup=None,
                parse_mode="HTML"
            )
            sent_thanks = True

    if not sent_thanks:
        # Fallback: to'g'ridan-to'g'ri yuborish
        await bot.send_message(
            chat_id=callback.from_user.id,
            text=thank_text,
            parse_mode="HTML"
        )

    # Haydovchiga xabar
    try:
        await bot.send_message(
            chat_id=driver.user_id,
            text=f"⭐️ <b>Sizga yangi baho!</b>\n\n"
                 f"Buyurtma #{order_id}\n"
                 f"Baho: {'⭐️' * stars}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Failed to notify driver about rating: {e}")

    # Callbackga javob – kech qolgan holatlarda (query is too old) xatoni yutamiz
    try:
        await callback.answer("Baho qabul qilindi!")
    except TelegramBadRequest:
        pass
