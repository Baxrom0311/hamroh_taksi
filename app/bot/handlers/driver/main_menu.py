"""
app/bot/handlers/driver/main_menu.py

HAYDOVCHI ASOSIY MENYU

BU HANDLER NIMA QILADI:
- Marshrut tanlash
- Bo'sh joylar kiritish
- Navbatga qo'shilish
"""

from ..base import *
from typing import Any, cast
from app.models.route import get_all_active_routes
from app.models.system_settings import get_pricing_settings
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import (
    get_route_selection_keyboard,
    get_seats_keyboard,
    get_driver_active_keyboard,
    get_location_request_keyboard,
    get_driver_main_menu,
    get_trip_active_keyboard
)
from app.models.order import Order, OrderStatus

router = Router()


# ============================================
# TRIP BLOCKER (SAFAR PAYTIDA MENYUNI BLOKLASH)
# ============================================

_trip_allowed = {
    "📞 Yo'lovchi bilan bog'lanish",
    "✅ Safarni yakunlash"
}


@router.message(DriverStates.trip_in_progress)
async def trip_in_progress_blocker(message: Message, state: FSMContext):
    """
    Agar haydovchi safarda bo'lsa, boshqa menyularga kirishni taqiqlash.
    """
    data = await state.get_data()
    order_id = data.get('current_order_id')
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    from app.core.database import get_session
    from app.models.driver import get_driver_by_user_id
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        if not driver:
            # Driver topilmasa state tozalanadi, shunda passenger oqimi xalaqit qilmaydi
            await state.clear()
            return

        # DB bilan tekshirib, aktiv order qolmagan bo'lsa state ni tozalab yuboramiz
        active_orders_result = await session.execute(
            select(Order)
            .where(Order.driver_id == driver.driver_id)
            .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        active_order = active_orders_result.scalar_one_or_none()
        
        if not active_order:
            # ✅ AUTO-CLEANUP: Centralized helper
            from app.utils.driver_state_utils import cleanup_stuck_driver_state
            
            await state.clear()
            await cleanup_stuck_driver_state(session, driver.driver_id)
            # Driver menyusiga qaytish haqida xabar bermaymiz, passenger konteksti bo'lishi mumkin
            return
        
        # Dinamik ruxsat etilgan tugmalar
        allowed: set[str]
        if active_order.status == OrderStatus.ACCEPTED:
            allowed = {
                "📞 Yo'lovchi bilan bog'lanish",
                "🚗 Yo'lga chiqdik",
                "❌ Buyurtmani bekor qilish",
            }
        elif active_order.status == OrderStatus.IN_PROGRESS:
            allowed = {
                "📞 Yo'lovchi bilan bog'lanish",
                "✅ Safarni yakunlash",
            }
        else:
            allowed = {
                "📞 Yo'lovchi bilan bog'lanish",
            }

        # Agar ruxsat etilgan tugma bo'lsa, boshqa handlerlarga o'tkazamiz
        if message.text and message.text in allowed:
            from aiogram.dispatcher.event.bases import SkipHandler
            raise SkipHandler()

        # State'da order_id yo'q bo'lsa, saqlab qo'yamiz (blok xabari uchun)
        if not order_id:
            order_id = active_order.order_id
            await state.update_data(current_order_id=order_id)
        
        await message.answer(
            "⚠️ <b>Siz hozir safardasiz!</b>\n\n"
            "Safar tugaguncha boshqa menyular ishlamaydi.\n"
            "Iltimos, kuting.",
            reply_markup=get_trip_active_keyboard(order_id), # type: ignore
            parse_mode="HTML"
        )

# ============================================
# BUYURTMA QABUL QILISH
# ============================================

@router.message(F.text == "🚗 Buyurtma qabul qilish")
@with_driver_session  # ✅ Decorator
async def start_accepting_orders(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi buyurtma qabul qilishni boshlaydi
    
    ✅ REFACTORED: Session va driver avtomatik
    
    FLOW:
    1. Marshrut tanlash
    2. Bo'sh joylar kiritish
    3. Navbatga qo'shilish
    """
    # Bloklangan?
    if driver.is_blocked:
        await message.answer(
            Messages.Driver.BLOCKED.format(reason=driver.block_reason or 'Noma\'lum')
        )
        return
    # ❗ Allaqachon aktivmi? (FSM yo‘qolgan bo‘lishi mumkin)
    if driver.is_active:
        await state.set_state(DriverStates.waiting_orders)
        await message.answer(
            Messages.Driver.ALREADY_ACTIVE,
            reply_markup=get_driver_active_keyboard()
        )
        return

    # Balans tekshirish (dynamic)
    pricing = await get_pricing_settings(session)
    commission_amount = pricing['commission_amount']

    if driver.balance < commission_amount:
        await message.answer(
            Messages.Driver.BALANCE_LOW.format(
                required=commission_amount,
                balance=driver.balance
            )
        )
        return
    
    # ✅ CRITICAL FIX: Allaqachon safardaligi tekshiruvi + AUTO-CLEANUP
    if driver.is_on_trip:
        # Database'dan aktiv order borligini tekshirish
        from sqlalchemy import select
        active_check = await session.execute(
            select(Order.order_id)
            .where(Order.driver_id == driver.driver_id)
            .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            .limit(1)
        )
        has_active_order = active_check.scalar_one_or_none()
        
        if has_active_order:
            # ✅ Aktiv safar bor – yakunlashga yo'naltiramiz
            await state.update_data(current_order_id=has_active_order)
            await state.set_state(DriverStates.trip_in_progress)
            await message.answer(
                Messages.Driver.ALREADY_ON_TRIP,
                reply_markup=get_trip_active_keyboard(has_active_order),
                parse_mode="HTML"
            )
            return
        else:
            # ❌ STUCK STATE: is_on_trip=True lekin order yo'q!
            # ✅ AUTO-CLEANUP: Centralized helper
            from app.utils.driver_state_utils import cleanup_stuck_driver_state
            
            await cleanup_stuck_driver_state(session, driver.driver_id)
            
            await message.answer(
                "✅ <b>Holatingiz tuzatildi!</b>\n\n"
                "Siz safarda emasdingiz, lekin tizimda xatolik bo'lgan.\n"
                "Endi buyurtma qabul qilishingiz mumkin.",
                parse_mode="HTML"
            )
            # Davom etish - quyidagi kodlar location so'raydi
    
    # Jonli joylashuv so'rash
    await message.answer(
        Messages.Driver.LOCATION_REQUEST,
        reply_markup=get_location_request_keyboard(),
        parse_mode="HTML"
    )
    
    await state.set_state(DriverStates.send_location)


# ============================================
# MARSHRUT TANLASH (CALLBACK)
# ============================================

@router.callback_query(
    DriverStates.choose_route,
    F.data.startswith("select_route:")
)
async def route_selected(callback: CallbackQuery, state: FSMContext):
    """
    Haydovchi marshrut tanladi
    """
    if callback.data is None:
        await callback.answer("❌ Xatolik: Ma'lumot topilmadi")
        return
    route_id = int(callback.data.split(":")[1])
    
    await state.update_data(route_id=route_id)
    await callback.message.edit_text( # type: ignore
        "👥 <b>Bo'sh joylar sonini tanlang:</b>\n\n"
        "Mashinangizda nechta bo'sh joy bor?",
        reply_markup=get_seats_keyboard()
    )
    
    await state.set_state(DriverStates.enter_seats)
    await callback.answer()


# ============================================
# BO'SH JOYLAR TANLASH
# ============================================

@router.callback_query(
    DriverStates.enter_seats,
    F.data.startswith("select_seats:")
)
@with_driver_session  # ✅ Decorator
async def seats_selected(callback: CallbackQuery, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi bo'sh joylar sonini tanladi
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    if callback.data is None:
        await callback.answer(Messages.Error.CALLBACK_DATA_MISSING)
        return
    seats = int(callback.data.split(":")[1])
    
    data = await state.get_data()
    route_id = data.get('route_id')
    
    if not route_id:
        if callback.message and isinstance(callback.message, Message):
            await callback.message.answer(
                "⚠️ Sessiya tugagan. Iltimos qayta boshlang."
            )
        await state.clear()
        await callback.answer()
        return

    # Driver'ni update qilish
    from sqlalchemy import update
    
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver.driver_id)
        .values(
            current_route_id=route_id,
            available_seats=seats,
            is_active=True
        )
    )
    
    # Route ma'lumotlarini olish
    from app.models.route import get_route_by_id
    route = await get_route_by_id(session, route_id)
    
    # Priority queue'ga qo'shish (Celery task orqali)
    from app.tasks.matching import add_driver_to_queue_task
    cast(Any, add_driver_to_queue_task).delay(driver.driver_id, route_id)
    
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            Messages.Driver.QUEUE_JOINED.format(
                route_name=route.route_name if route else "Noma'lum",
                seats=seats
            ),
            reply_markup=get_driver_active_keyboard()
        )
    
    await state.set_state(DriverStates.waiting_orders)
    await callback.answer("✅ Navbatga qo'shildingiz!")
    
    logger.info(
        f"Driver {driver.driver_id} added to queue: "
        f"route={route_id}, seats={seats}"
    )


# ============================================
# TO'XTATISH
# ============================================

@router.message(
    DriverStates.waiting_orders,
    F.text == " To'xtatish"
)
@router.message(F.text == " To'xtatish") 
@with_driver_session  # ✅ Decorator
async def stop_accepting_orders(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi buyurtma qabul qilishni to'xtatadi.
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    if not driver.is_active:
        await message.answer("Siz allaqachon to'xtatilgansiz.", reply_markup=get_driver_main_menu())
        await state.clear()
        return

    # Driver'ni deactivate qilish
    from sqlalchemy import update
    
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver.driver_id)
        .values(is_active=False, available_seats=0)
    )
    
    # Celery task - Queue'dan o'chirish
    from app.tasks.matching import remove_driver_from_queue_task
    cast(Any, remove_driver_from_queue_task).delay(driver.driver_id)
    
    await state.clear() # FSM holatini tozalaymiz
    await message.answer(
        Messages.Driver.STOPPED,
        reply_markup=get_driver_main_menu()
    )
    logger.info(f"Driver {driver.driver_id} force stopped.")


# ============================================
# STATISTIKA
# ============================================

@router.message(F.text == "📊 Statistika")
@with_driver_session  # ✅ Decorator
async def show_statistics(message: Message, session: AsyncSession, driver: Driver):
    """
    Haydovchi statistikasi
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    # Bugungi safarlar
    from datetime import datetime
    from sqlalchemy import select, func
    from app.models.order import Order, OrderStatus
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0)
    
    result = await session.execute(
        select(func.count(Order.order_id))
        .where(Order.driver_id == driver.driver_id)
        .where(Order.status == OrderStatus.COMPLETED)
        .where(Order.completed_at >= today_start)
    )
    
    today_trips = result.scalar() or 0
    
    await message.answer(
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"👤 Ism: <b>{driver.full_name}</b>\n"
        f"🚗 Mashina: <b>{driver.car_model}</b>\n\n"
        f"💰 Balans: <b>{driver.balance:,} so'm</b>\n"
        f"⭐ Reyting: <b>{driver.rating}/5.0</b>\n\n"
        f"🚕 Jami safarlar: <b>{driver.total_trips}</b>\n"
        f"📅 Bugungi safarlar: <b>{today_trips}</b>\n\n"
        f"📆 Oxirgi safar: {driver.last_trip_at.strftime('%d.%m.%Y %H:%M') if driver.last_trip_at else 'Hali yo\'q'}",
        parse_mode="HTML"
    )





@router.message(F.text == "⚙️ Sozlamalar")
@with_driver_session  # ✅ Decorator
async def driver_settings(message: Message, session: AsyncSession, driver: Driver):
    await message.answer(
        "⚙️ <b>Sozlamalar bo'limi</b>\n\n"
        "Hozircha ishlab chiqilmoqda...",
        parse_mode="HTML"
    )




# Diqqat: .message emas, .callback_query ishlatamiz
@router.callback_query(F.data == "pause_driver")
@with_driver_session  # ✅ Decorator
async def stop_accepting_orders_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi deactive qilish (callback)
    ✅ REFACTORED: Session va driver avtomatik
    """
    # Bazada haydovchini o'chirish
    from sqlalchemy import update
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver.driver_id)
        .values(is_active=False, available_seats=0)
    )
    # Celery task - Queue'dan o'chirish
    from app.tasks.matching import remove_driver_from_queue_task
    cast(Any, remove_driver_from_queue_task).delay(driver.driver_id)
    await state.clear()
    if callback.message and isinstance(callback.message, Message):
        # Inline tugmalarni o'chirib, xabarni yangilaymiz
        await callback.message.edit_text(Messages.Driver.STOPPED)
        
        # Yangi menyuni yuboramiz (ReplyKeyboard)
        await callback.message.answer(
            "Asosiy menyu:", 
            reply_markup=get_driver_main_menu() 
        )
    # Telegramga "Tugma ishladi" degan javob qaytaramiz (loading aylanmasligi uchun)
    await callback.answer(Messages.Driver.OFFLINE)
@router.callback_query(F.data == "driver_stats")
@with_driver_session  # ✅ Decorator
async def show_statistics_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver):
    """
    Haydovchi statistikasi (callback)
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    text = f"📊 <b>Sizning statistikangiz</b>\n\n💰 Balans: {driver.balance} so'm\n⭐ Reyting: {driver.rating}"
    
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(text)
    await callback.answer()
__all__ = ['router']
