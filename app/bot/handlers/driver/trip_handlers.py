"""
app/bot/handlers/driver/trip_handlers.py

HAYDOVCHI TRIP HANDLERS

Yangi trip-based flow:
1. Buyurtmalar qabul qilish → Trip avtomatik yaratiladi
2. "Ketish" → Trip va barcha orderlar IN_PROGRESS
3. 10 daqiqadan keyin → Avtomatik COMPLETED
4. "Bekor qilish" → Tripdagi hamma orderlar CANCELLED
"""

from ..base import *
from app.models.order import Order, OrderStatus
from app.models.trip import Trip, TripStatus, get_active_trip_by_driver, start_trip, complete_trip
from app.bot.keyboards.driver import get_driver_main_menu
from typing import Any, cast
from sqlalchemy.sql import func as sql_func

router = Router()


# ============================================
# YO'LOVCHI BILAN BOG'LANISH (YANGILANGAN)
# ============================================

@router.message(F.text == "📞 Yo'lovchi bilan bog'lanish")
@with_driver_session  # ✅ Decorator
async def contact_passenger_handler(message: Message, session: AsyncSession, driver: Driver):
    """
    Yo'lovchi bilan bog'lanish - Faqat aktiv trip'dagi yo'lovchilar
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    # Aktiv trip'ni olish
    active_trip = await get_active_trip_by_driver(session, driver.driver_id)
    
    if not active_trip:
        await message.answer(
            "📋 <b>Hozirda aktiv trip yo'q</b>\n\n"
            "Buyurtma qabul qiling va trip boshlang.",
            reply_markup=get_driver_main_menu(),
            parse_mode="HTML"
        )
        return
    
    # Trip'dagi orderlarni olish
    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.passenger).selectinload(Passenger.user)
        )
        .where(Order.trip_id == active_trip.trip_id)
        .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
        .order_by(Order.created_at)
    )
    
    trip_orders = result.scalars().all()
    
    if not trip_orders:
        await message.answer("Bu trip'da hali order yo'q", parse_mode="HTML")
        return
    
    # Yo'lovchilar ro'yxati
    text = f"🚗 <b>Trip #{active_trip.trip_id}</b>\n\n"
    text += f"👥 Yo'lovchilar: {active_trip.passenger_count}/{active_trip.total_seats}\n\n"
    
    for idx, order in enumerate(trip_orders, 1):
        passenger = order.passenger
        if passenger and passenger.user:
            text += f"{idx}. <b>{passenger.full_name}</b>\n"
            text += f"   📞 {passenger.phone_number}\n"
            text += f"   👤 {order.passenger_count} kishi\n"
            text += f"   📍 {order.pickup_location[:50]}...\n\n"
    
    # Keyboard
    await message.answer(text, parse_mode="HTML")
    
    logger.info(f"Driver {driver.driver_id} viewed trip #{active_trip.trip_id} passengers")


# ============================================
# TRIP BOSHLASH ("KETISH" TUGMASI)
# ============================================

@router.message(F.text == "🚗 Ketish")
@with_driver_session  # ✅ Decorator
async def start_trip_handler(message: Message, session: AsyncSession, driver: Driver):
    """
    Trip boshlash - Barcha qabul qilingan orderlar IN_PROGRESS bo'ladi
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    # Aktiv trip olish
    active_trip = await get_active_trip_by_driver(session, driver.driver_id)
    
    if not active_trip:
        await message.answer(
            "❌ Aktiv trip topilmadi\n\nAvval buyurtma qabul qiling.",
            reply_markup=get_driver_main_menu()
        )
        return
    
    # Trip boshlash
    await start_trip(session, active_trip.trip_id)
    
    # Trip'dagi barcha ACCEPTED orderlarni IN_PROGRESS qilish
    result = await session.execute(
        update(Order)
        .where(Order.trip_id == active_trip.trip_id)
        .where(Order.status == OrderStatus.ACCEPTED)
        .values(
            status=OrderStatus.IN_PROGRESS,
            started_at=sql_func.now()
        )
        .returning(Order.order_id)
    )
    
    updated_orders = result.scalars().all()
    
    # Driver is_on_trip = True
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver.driver_id)
        .values(is_on_trip=True)
    )
    
    await session.commit()
    
    # Avtomatik yakunlash task (10 daqiqa)
    from app.tasks.matching import auto_complete_trip_task
    cast(Any, auto_complete_trip_task).apply_async(
        args=[active_trip.trip_id],
        countdown=600  # 10 daqiqa
    )
    
    await message.answer(
        f"✅ <b>Trip boshlandi!</b>\n\n"
        f"🚗 Trip #{active_trip.trip_id}\n"
        f"👥 Yo'lovchilar: {len(updated_orders)} ta buyurtma\n\n"
        f"⏱ <b>10 daqiqadan keyin avtomatik yakunlanadi</b>\n\n"
        f"Xavfsiz yo'l!",
        parse_mode="HTML"
    )
    
    logger.success(f"Trip #{active_trip.trip_id} started with {len(updated_orders)} orders")


# ============================================
# TRIP BEKOR QILISH
# ============================================

@router.callback_query(F.data.startswith("cancel_trip:"))
@with_driver_session  # ✅ Decorator
async def cancel_trip_handler(callback: CallbackQuery, session: AsyncSession, driver: Driver):
    """
    Trip'ni bekor qilish - Tripdagi barcha orderlar CANCELLED
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    if not callback.data:
        await callback.answer("Xatolik")
        return
    
    trip_id = int(callback.data.split(":")[1])
    
    # ✅ Permission check
    from app.services.trip_service import can_cancel_trip, cancel_pending_orders_in_trip
    
    check_result = await can_cancel_trip(trip_id, driver.driver_id)
    
    if not check_result['can_cancel']:
        await callback.answer(check_result['reason'], show_alert=True)
        return
    
    # ✅ Faqat PENDING orderlarni bekor qilish va komissiya qaytarish
    result = await cancel_pending_orders_in_trip(trip_id, driver.driver_id)
    
    if not result['success']:
        await callback.answer(result['message'], show_alert=True)
        return
    
    # Trip bekor qilish
    from app.models.trip import get_trip_by_id, cancel_trip
    await cancel_trip(session, trip_id)
    
    # Driver'ni yangilash
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver.driver_id)
        .values(
            is_on_trip=False,
            is_active=False,
            available_seats=0
        )
    )
    
    await session.commit()
    
    if callback.message:
        await callback.message.edit_text(
            f"✅ {result['message']}\n\n"
            f"🚗 Trip #{trip_id} bekor qilindi.",
            parse_mode="HTML"
        )
    
    logger.warning(f"Trip #{trip_id} cancelled by driver {driver.driver_id}: {result}")
    
    await callback.answer("Trip bekor qilindi")


__all__ = ['router']
