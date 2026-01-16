"""
app/bot/handlers/driver/main_menu.py

HAYDOVCHI ASOSIY MENYU

BU HANDLER NIMA QILADI:
- Marshrut tanlash
- Bo'sh joylar kiritish
- Navbatga qo'shilish
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.core.database import get_session
from app.models.driver import get_driver_by_user_id, Driver
from app.bot.decorators import with_driver_session  # ✅ NEW
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.route import get_all_active_routes
from app.models.system_settings import get_pricing_settings
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import (
    get_route_selection_keyboard,
    get_seats_keyboard,
    get_route_selection_keyboard,
    get_seats_keyboard,
    get_driver_active_keyboard,
    get_location_request_keyboard,
    get_driver_main_menu
)
from app.bot.messages import Messages
from app.bot.utils import get_driver_or_error

router = Router()


# ============================================
# TRIP BLOCKER (SAFAR PAYTIDA MENYUNI BLOKLASH)
# ============================================

@router.message(
    DriverStates.trip_in_progress,
    ~F.text.contains("bog'lanish")
)
async def trip_in_progress_blocker(message: Message, state: FSMContext):
    """
    Agar haydovchi safarda bo'lsa, boshqa menyularga kirishni taqiqlash.
    """
    # Order ID ni olish
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    # Trip keyboardni qaytarish
    from app.bot.keyboards.driver import get_trip_active_keyboard
    
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
    if message.from_user is None:
        await message.answer("Xatolik: user topilmadi")
        return


    user_id = message.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, message)
        if not driver:
            return
        
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
        
        # Allaqachon safardaligi?
        # Allaqachon safardaligi?
        if driver.is_on_trip:
            await message.answer(Messages.Driver.ALREADY_ON_TRIP)
            return
        
        # Marshrut tanlash
        routes = await get_all_active_routes(session)
        
        
        if not routes:
            await message.answer(Messages.Driver.NO_ACTIVE_ROUTES)
            return
        
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
async def seats_selected(callback: CallbackQuery, state: FSMContext):
    """
    Haydovchi bo'sh joylar sonini tanladi
    """
    if callback.data is None:
        await callback.answer(Messages.Error.CALLBACK_DATA_MISSING)
        return
    seats = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    data = await state.get_data()
    route_id = data['route_id']
    
    if not route_id:
        await callback.message.answer( # type: ignore
            "⚠️ Sessiya tugagan. Iltimos qayta boshlang."
        )
        await state.clear()
        await callback.answer()
        return
    # Database'ga saqlash
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, callback)
        if not driver:
            await state.clear()
            return

        # Driver'ni update qilish
        from sqlalchemy import update
        from app.models.driver import Driver
        
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == driver.driver_id)
            .values(
                current_route_id=route_id,
                available_seats=seats,
                is_active=True
            )
        )
        
        await session.commit()
        
        # Route ma'lumotlarini olish
        from app.models.route import get_route_by_id
        route = await get_route_by_id(session, route_id)
    
    # Priority queue'ga qo'shish (Celery task orqali)
    from app.tasks.matching import add_driver_to_queue_task
    add_driver_to_queue_task.delay(driver.driver_id, route_id)
    
    await callback.message.edit_text( # type: ignore
        Messages.Driver.QUEUE_JOINED.format(
            route_name=route.route_name, # type: ignore
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
async def stop_accepting_orders(message: Message, state: FSMContext):
    """
    Haydovchi buyurtma qabul qilishni to'xtatadi.
    Holatdan qat'i nazar ishlaydi.
    """
    user_id = message.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver or not driver.is_active:
            await message.answer("Siz allaqachon to'xtatilgansiz.", reply_markup=get_driver_main_menu())
            await state.clear()
            return

        # Driver'ni deactivate qilish
        from sqlalchemy import update
        from app.models.driver import Driver
        
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == driver.driver_id)
            .values(is_active=False, available_seats=0)
        )
        await session.commit()
    
    # Celery task - Queue'dan o'chirish
    from app.tasks.matching import remove_driver_from_queue_task
    remove_driver_from_queue_task.delay(driver.driver_id)
    
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
async def show_statistics(message: Message):
    """
    Haydovchi statistikasi
    """
    if message.from_user is None:
        await message.answer("Xatolik: user topilmadi")
        return
    user_id = message.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        driver = await get_driver_or_error(session, user_id, message)
        if not driver:
            return
        
        # Bugungi safarlar
        from datetime import datetime, timedelta
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
            f"📆 Oxirgi safar: {driver.last_trip_at.strftime('%d.%m.%Y %H:%M') if driver.last_trip_at else 'Hali yo\'q'}"
        )





@router.message(F.text == "⚙️ Sozlamalar")
async def driver_settings(message: Message):
    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>\n\nHozircha ishlab chiqilmoqda...")




# Diqqat: .message emas, .callback_query ishlatamiz
@router.callback_query(F.data == "pause_driver")
async def stop_accepting_orders_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, callback) 
        if not driver:
            return

        # Bazada haydovchini o'chirish
        from sqlalchemy import update
        from app.models.driver import Driver
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == driver.driver_id)
            .values(is_active=False, available_seats=0)
        )
        await session.commit()
    
    # Celery task - Queue'dan o'chirish
    from app.tasks.matching import remove_driver_from_queue_task
    remove_driver_from_queue_task.delay(driver.driver_id)
    
    await state.clear()
    
    # Inline tugmalarni o'chirib, xabarni yangilaymiz
    await callback.message.edit_text(Messages.Driver.STOPPED) # type: ignore
    
    # Yangi menyuni yuboramiz (ReplyKeyboard)
    await callback.message.answer(
        "Asosiy menyu:", 
        reply_markup=get_driver_main_menu() 
    )
    
    # Telegramga "Tugma ishladi" degan javob qaytaramiz (loading aylanmasligi uchun)
    await callback.answer(Messages.Driver.OFFLINE)



@router.callback_query(F.data == "driver_stats")
async def show_statistics_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, callback)
        if not driver:
            return
            
        # ... (statistika hisoblash kodingiz) ...
        
        text = f"📊 <b>Sizning statistikangiz</b>\n\n💰 Balans: {driver.balance} so'm\n⭐ Reyting: {driver.rating}"
        
        await callback.message.answer(text)
        await callback.answer()
__all__ = ['router']
