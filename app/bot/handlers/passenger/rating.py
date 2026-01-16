"""
app/bot/handlers/passenger/rating.py
"""

from ..base import *
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
    if callback.data is None:
        await callback.answer("Xatolik: data yo'q")
        return

    try:
        _, order_id_str, stars_str = callback.data.split(":")
        order_id = int(order_id_str)
        stars = int(stars_str)
    except ValueError:
        await callback.answer("Xatolik: noto'g'ri format")
        return

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

        # Reytingni yangilash
        # Formula: (Eski * (N) + Yangi) / (N + 1)
        # Hozircha oddiyroq:
        current_rating = float(driver.rating)
        # Agar bu birinchi safar bo'lsa yoki count yo'q bo'lsa, oddiy o'rtacha olamiz
        # Total trips tahminan ratinglar soni deb olamiz (aniq emas, lekin MVP uchun yetadi)
        total_rated = max(1, driver.total_trips) 
        
        new_rating = ((current_rating * total_rated) + stars) / (total_rated + 1)
        # Cheklov 5.0
        new_rating = min(5.0, new_rating)

        # DB update
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == driver_id)
            .values(rating=new_rating)
        )
        await session.commit()

        # Passengerga javob
        await callback.message.edit_text(
            f"✅ <b>Rahmat!</b>\n\n"
            f"Sizning bahoingiz: {'⭐️' * stars}",
            reply_markup=None,
            parse_mode="HTML"
        )

        # Haydovchiga xabar
        from app.bot.main import bot
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

    await callback.answer("Baho qabul qilindi!")
