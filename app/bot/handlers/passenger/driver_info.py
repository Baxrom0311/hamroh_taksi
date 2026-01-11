"""
app/bot/handlers/passenger/driver_info.py

PASSENGER DRIVER INFO HANDLERS

BU HANDLER NIMA QILADI:
- Mashinani o'zgartirish (1 soatda 3 marta)
- Haydovchini ban qilish
- Haydovchi ma'lumotlarini ko'rish
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from loguru import logger
from datetime import datetime, timedelta

from app.core.database import get_session, transaction
from app.models.passenger import get_passenger_by_user_id
from app.models.order import Order, OrderStatus, get_order_by_id
from app.models.driver import Driver, get_driver_by_id
from app.models.driver_ban import create_ban_record, check_driver_should_be_blocked
from app.models.system_settings import get_setting_int
from app.services.order_service import find_driver_for_order
from app.tasks.matching import find_driver_for_order_task
from sqlalchemy import select, func, update
from sqlalchemy.sql import func as sql_func
from datetime import timedelta

router = Router()


# ============================================
# MASHINANI O'ZGARTIRISH
# ============================================

@router.callback_query(F.data.startswith("change_driver:"))
async def change_driver_handler(callback: CallbackQuery, state: FSMContext):
    """
    Yo'lovchi mashinani o'zgartirmoqchi
    
    NIMA BO'LADI:
    1. Limit tekshiruvi (1 soatda 3 marta)
    2. Order'ni cancel qilish
    3. Yangi haydovchi topish
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        passenger = await get_passenger_by_user_id(session, user_id)
        
        if not passenger:
            await callback.answer("❌ Yo'lovchi topilmadi", show_alert=True)
            return
        
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
        
        # Order'ni cancel qilish
        async with transaction() as session:
            await session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason=f'change_driver_{change_count + 1}',
                    cancelled_at=sql_func.now(),
                    driver_id=None  # Driver'ni tozalash
                )
            )
            
            # Driver'ni bo'shatish (available_seats qaytarish)
            if order.driver_id:
                await session.execute(
                    update(Driver)
                    .where(Driver.driver_id == order.driver_id)
                    .values(
                        available_seats=Driver.available_seats + order.passenger_count,
                        is_on_trip=False
                    )
                )
        
        # Yangi haydovchi topish
        find_driver_for_order_task.delay(order_id)
        
        # Xabarni yangilash
        if callback.message:
            await callback.message.edit_text(
                f"🔄 <b>Mashina o'zgartirildi</b>\n\n"
                f"Yangi haydovchi topilmoqda...\n\n"
                f"📊 O'zgartirishlar: {change_count + 1}/{max_changes} (1 soatda)"
            )
        
        logger.info(
            f"Passenger {passenger.passenger_id} changed driver for order {order_id}. "
            f"Changes: {change_count + 1}/{max_changes}"
        )
    
    await callback.answer("Yangi haydovchi topilmoqda...")


# ============================================
# HAYDOVCHINI BAN QILISH
# ============================================

@router.callback_query(F.data.startswith("ban_driver:"))
async def ban_driver_handler(callback: CallbackQuery, state: FSMContext):
    """
    Yo'lovchi haydovchini ban qiladi
    
    NIMA BO'LADI:
    1. Ban record yaratish
    2. Bloklanish tekshiruvi (50% yoki 5 ta ban)
    3. Admin'ga bildirishnoma
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        passenger = await get_passenger_by_user_id(session, user_id)
        
        if not passenger:
            await callback.answer("❌ Yo'lovchi topilmadi", show_alert=True)
            return
        
        # Order'ni olish
        order = await get_order_by_id(session, order_id)
        
        if not order or order.passenger_id != passenger.passenger_id:
            await callback.answer("❌ Buyurtma topilmadi", show_alert=True)
            return
        
        if not order.driver_id:
            await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
            return
        
        # Ban record yaratish
        async with transaction() as session:
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
                notify_admins.delay(
                    f"🚫 <b>Haydovchi bloklandi!</b>\n\n"
                    f"Driver ID: {order.driver_id}\n"
                    f"Sabab: {block_check['reason']}\n"
                    f"Ban foizi: {block_check['ban_percentage']:.1f}%\n"
                    f"Kunlik ban: {block_check['today_ban_count']}"
                )
        
        # Xabarni yangilash
        if callback.message:
            await callback.message.edit_text(
                "🚫 <b>Haydovchi ban qilindi</b>\n\n"
                "Admin ko'rib chiqadi.\n"
                "Yangi haydovchi topilmoqda..."
            )
        
        # Yangi haydovchi topish
        find_driver_for_order_task.delay(order_id)
        
        logger.info(
            f"Passenger {passenger.passenger_id} banned driver {order.driver_id} "
            f"for order {order_id}"
        )
    
    await callback.answer("Ban qilindi. Admin ko'rib chiqadi")


# ============================================
# HAYDOVCHI MA'LUMOTLARINI KO'RISH
# ============================================

@router.callback_query(F.data.startswith("view_driver:"))
async def view_driver_info(callback: CallbackQuery):
    """
    Haydovchi ma'lumotlarini ko'rish
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
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
📱 <b>Telefon:</b> <code>{driver.user.phone_number if driver.user else 'N/A'}</code>
⭐ <b>Reyting:</b> {driver.rating:.1f}/5.0
🚕 <b>Jami safarlar:</b> {driver.total_trips}
        """
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📞 Qo'ng'iroq",
                    url=f"tel:{driver.user.phone_number if driver.user else ''}"
                ),
                InlineKeyboardButton(
                    text="💬 Telegram",
                    url=f"tg://user?id={driver.user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Mashinani o'zgartirish",
                    callback_data=f"change_driver:{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Ban tashlash",
                    callback_data=f"ban_driver:{order_id}"
                )
            ]
        ])
        
        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
        await callback.answer()


__all__ = ['router']
