"""
app/bot/handlers/passenger/driver_info.py

PASSENGER DRIVER INFO HANDLERS

BU HANDLER NIMA QILADI:
- Mashinani o'zgartirish (1 soatda 3 marta)
- Haydovchini ban qilish
- Haydovchi ma'lumotlarini ko'rish
"""

from ..base import *
from datetime import datetime, timedelta
from app.models.order import Order, OrderStatus, get_order_by_id
from app.models.driver import get_driver_by_id
from app.models.driver_ban import create_ban_record, check_driver_should_be_blocked
from app.models.system_settings import get_setting_int
from app.services.order_service import find_driver_for_order
from app.tasks.matching import find_driver_for_order_task
from app.bot.keyboards.passenger import get_driver_selection_keyboard, get_driver_action_keyboard

from sqlalchemy.sql import func as sql_func
from datetime import timedelta

router = Router()


# ============================================
# MASHINANI O'ZGARTIRISH
# ============================================

@router.callback_query(F.data.startswith("change_driver:"))
@with_passenger_session  # ✅ Decorator
async def change_driver_handler(callback: CallbackQuery, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """
    Yo'lovchi mashinani o'zgartirmoqchi
    
    ✅ REFACTORED: Session va passenger avtomatik
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    
    # Order'ni olish
    order = await get_order_by_id(session, order_id)
    
    if not order or order.passenger_id != passenger.passenger_id:
        await callback.answer("❌ Buyurtma topilmadi", show_alert=True)
        return
    
    # Limit tekshiruvi (1 soatda 3 marta)
    one_hour_ago = datetime.now() - timedelta(hours=1)
    
    change_count_result = await session.execute(
        select(func.count(Order.order_id))
        .where(Order.passenger_id == passenger.passenger_id)
        .where(Order.status == OrderStatus.CANCELLED)
        .where(Order.cancellation_reason.like('%change_driver%'))
        .where(Order.cancelled_at >= one_hour_ago)
    )
    change_count = change_count_result.scalar() or 0
    
    max_changes = await get_setting_int(session, 'max_driver_change_per_hour', 3)
    
    if change_count >= max_changes:
        await callback.answer(
            f"⚠️ Limit yetdi! 1 soatda {max_changes} martadan ko'p o'zgartirib bo'lmaydi.",
            show_alert=True
        )
        return
    
    # Mavjud haydovchilarni topish (marshrut bo'yicha, bloklanmagan, bo'sh o'rinli)
    from app.models.driver import Driver, get_available_drivers_for_route
    from sqlalchemy.orm import selectinload
    
    available_drivers = await get_available_drivers_for_route(
        session,
        route_id=order.route_id,
        min_seats=order.passenger_count
    )
    
    # Hozirgi haydovchini ro'yxatdan chiqarish
    available_drivers = [d for d in available_drivers if d.driver_id != order.driver_id]
    
    if not available_drivers:
        await callback.answer(
            "⚠️ Hozirda boshqa haydovchilar mavjud emas.\n"
            "Yangi haydovchi topilmoqda...",
            show_alert=True
        )
        # Avtomatik yangi haydovchi topish
        from typing import Any, cast

        cast(Any, find_driver_for_order_task).delay(order_id)
        return
    
    keyboard = get_driver_selection_keyboard(available_drivers, order_id)
    
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            Messages.Passenger.SELECT_NEW_DRIVER.format(order_id=order_id),
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    logger.info(
        f"Passenger {passenger.passenger_id} selecting new driver for order {order_id}. "
        f"Available drivers: {len(available_drivers)}"
    )
    
    await callback.answer("Haydovchi tanlang")


@router.callback_query(F.data.startswith("select_new_driver:"))
@with_passenger_session  # ✅ Decorator
async def select_new_driver_handler(callback: CallbackQuery, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """
    Yo'lovchi yangi haydovchini tanladi
    
    ✅ REFACTORED: Session va passenger avtomatik
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    parts = callback.data.split(":")
    order_id = int(parts[1])
    new_driver_id = int(parts[2])
    
    # Order'ni olish
    order = await get_order_by_id(session, order_id)
    
    if not order or order.passenger_id != passenger.passenger_id:
        await callback.answer("❌ Buyurtma topilmadi", show_alert=True)
        return
    
    old_driver_id = order.driver_id
    
    # Yangi haydovchini olish
    from app.models.driver import get_driver_by_id
    new_driver = await get_driver_by_id(session, new_driver_id)
    
    if not new_driver:
        await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
        return
    
    # Balans va o'rinlar tekshiruvi
    from app.services.order_service import get_pricing_settings
    pricing = await get_pricing_settings(session)
    commission = pricing['commission_amount']
    
    if new_driver.balance < commission:
        await callback.answer("⚠️ Haydovchida balans yetarli emas", show_alert=True)
        return
    
    if new_driver.available_seats < order.passenger_count:
        await callback.answer("⚠️ Haydovchida yetarli bo'sh o'rin yo'q", show_alert=True)
        return
    
    # Buyurtmani yangi haydovchiga biriktirish
    # Order'ni yangi haydovchiga biriktirish
    await session.execute(
        update(Order)
        .where(Order.order_id == order_id)
        .values(
            driver_id=new_driver_id,
            status=OrderStatus.ACCEPTED,
            accepted_at=func.now()
        )
    )
    
    # Yangi haydovchini yangilash
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == new_driver_id)
        .values(
            balance=Driver.balance - commission,
            available_seats=Driver.available_seats - order.passenger_count,
            is_on_trip=True
        )
    )
    
    # Eski haydovchini bo'shatish (o'rinlarni qaytarish)
    if old_driver_id:
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == old_driver_id)
            .values(
                available_seats=Driver.available_seats + order.passenger_count,
                is_on_trip=False
            )
        )
        
        # Eski haydovchiga xabar
        old_driver = await get_driver_by_id(session, old_driver_id)
        if old_driver:
            from app.bot.main import bot
            try:
                await bot.send_message(
                    chat_id=old_driver.user_id,
                    text=f"🔄 <b>Mashina almashtirildi</b>\n\n"
                         f"📦 Buyurtma #{order_id}\n\n"
                         f"Yo'lovchi boshqa haydovchini tanladi.\n"
                         f"Yangi buyurtmalarni qabul qilishingiz mumkin.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to notify old driver: {e}")
    
    # Yangi haydovchiga xabar
    from app.tasks.notifications import notify_passenger_driver_found
    from typing import Any, cast

    cast(Any, notify_passenger_driver_found).delay(
        passenger.user_id,
        new_driver_id,
        order_id
    )
     
    # Xabarni yangilash
    if callback.message  and isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"✅ <b>Yangi haydovchi tanlandi!</b>\n\n"
            f"📦 Buyurtma #{order_id}\n\n"
            f"👤 Haydovchi: {new_driver.full_name}\n"
            f"🚗 Mashina: {new_driver.car_model} ({new_driver.car_color})\n"
            f"🔢 Raqam: {new_driver.car_number}\n\n"
            f"Haydovchi siz tomonga yo'lga chiqdi!",
            parse_mode="HTML"
        )
    
    logger.info(
        f"Passenger {passenger.passenger_id} selected new driver {new_driver_id} "
        f"for order {order_id}. Swapped old driver {old_driver_id}"
    )
    
    await callback.answer("✅ Yangi haydovchi tanlandi!")


# ============================================
# HAYDOVCHINI BAN QILISH
# ============================================

@router.callback_query(F.data.startswith("ban_driver:"))
@with_passenger_session  # ✅ Decorator
async def ban_driver_handler(callback: CallbackQuery, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """
    Yo'lovchi haydovchini ban qiladi
    
    ✅ REFACTORED: Session va passenger avtomatik
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    
    # Order'ni olish
    order = await get_order_by_id(session, order_id)
    
    if not order or order.passenger_id != passenger.passenger_id:
        await callback.answer("❌ Buyurtma topilmadi", show_alert=True)
        return
    
    if not order.driver_id:
        await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
        return
    
    # Ban record yaratish
    ban = await create_ban_record(
        session,
        driver_id=order.driver_id,
        passenger_id=passenger.passenger_id,
        order_id=order_id,
        reason="Yo'lovchi ban tashladi"
    )
    
    # Bloklanish tekshiruvi
    block_check = await check_driver_should_be_blocked(session, order.driver_id)
    
    if block_check['should_block']:
        # Haydovchini bloklash
        from app.models.driver import Driver
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == order.driver_id)
            .values(
                is_blocked=True,
                block_reason=block_check['reason']
            )
        )
        
        # Admin'ga bildirishnoma
        from app.tasks.notifications import notify_admins
        from typing import Any, cast
        cast(Any, notify_admins).delay(
            f"🚫 <b>Haydovchi bloklandi!</b>\n\n"
            f"Driver ID: {order.driver_id}\n"
            f"Sabab: {block_check['reason']}\n"
            f"Ban foizi: {block_check['ban_percentage']:.1f}%\n"
            f"Kunlik ban: {block_check['today_ban_count']}"
        )
    
    # Xabarni yangilash
    # Xabar yuborish
    await callback.message.edit_text( # type: ignore
        Messages.Passenger.DRIVER_BANNED,
        parse_mode="HTML"
    )
    # Yangi haydovchi topish
    from typing import Any, cast

    cast(Any, find_driver_for_order_task).delay(order_id)

    logger.info(
        f"Passenger {passenger.passenger_id} banned driver {order.driver_id} "
        f"for order {order_id}"
    )
    
    await callback.answer("Ban qilindi. Admin ko'rib chiqadi")


# ============================================
# HAYDOVCHI MA'LUMOTLARINI KO'RISH
# ============================================

@router.callback_query(F.data.startswith("view_driver:"))
@with_session  # ✅ Decorator (only session needed here as it views driver info, not necessarily restricted to passenger context in this way)
async def view_driver_info(callback: CallbackQuery, session: AsyncSession):
    """
    Haydovchi ma'lumotlarini ko'rish - ✅ REFACTORED
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    
    order = await get_order_by_id(session, order_id)
    
    if not order or not order.driver_id:
        await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
        return
    
    driver = await get_driver_by_id(session, order.driver_id, eager_load_user=True)
    
    if not driver:
        await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
        return
    
    text = f"""
👤 <b>Haydovchi ma'lumotlari</b>

<b>Ism:</b> {driver.full_name}
🚗 <b>Mashina:</b> {driver.car_model}
🎨 <b>Rang:</b> {driver.car_color}
🔢 <b>Raqam:</b> <code>{driver.car_number}</code>
📱 <b>Telefon:</b> {driver.phone_number}
⭐ <b>Reyting:</b> {driver.rating:.1f}/5.0
🚕 <b>Jami safarlar:</b> {driver.total_trips}
    """

    # Lokatsiya linki (agar mavjud bo'lsa)
    if driver.last_location_lat and driver.last_location_lon:
        from app.utils.location_helpers import get_google_maps_link
        driver_loc_link = get_google_maps_link(
            float(driver.last_location_lat),
            float(driver.last_location_lon),
            f"Haydovchi {driver.full_name}"
        )
        text += f"\n📍 <a href=\"{driver_loc_link}\">Haydovchi joriy lokatsiyasi</a>\n"
    
    keyboard = get_driver_action_keyboard(driver.user_id, order_id)
    
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    
    await callback.answer()


__all__ = ['router']
