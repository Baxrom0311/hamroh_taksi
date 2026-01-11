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
from app.models.driver import get_driver_by_user_id
from app.models.route import get_all_active_routes
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import (
    get_route_selection_keyboard,
    get_seats_keyboard,
    get_driver_active_keyboard
)

router = Router()


# ============================================
# BUYURTMA QABUL QILISH
# ============================================

@router.message(F.text == "🚗 Buyurtma qabul qilish")
async def start_accepting_orders(message: Message, state: FSMContext):
    """
    Haydovchi buyurtma qabul qilishni boshlaydi
    
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
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer("❌ Haydovchi ma'lumotlari topilmadi")
            return
        
        # Bloklangan?
        if driver.is_blocked:
            await message.answer(
                f"🚫 <b>Siz bloklangansiz!</b>\n\n"
                f"Sabab: {driver.block_reason or 'Noma\'lum'}\n\n"
                f"Murojaat: @support"
            )
            return
        # ❗ Allaqachon aktivmi? (FSM yo‘qolgan bo‘lishi mumkin)
        if driver.is_active:
            await state.set_state(DriverStates.waiting_orders)
            await message.answer(
                "⏳ Siz allaqachon buyurtma kutyapsiz",
                reply_markup=get_driver_active_keyboard()
            )
            return

        # Balans tekshirish
        from config.settings import settings
        if driver.balance < settings.COMMISSION_AMOUNT:
            await message.answer(
                f"⚠️ <b>Balans yetarli emas!</b>\n\n"
                f"Kerak: <b>{settings.COMMISSION_AMOUNT:,} so'm</b>\n"
                f"Mavjud: <b>{driver.balance:,} so'm</b>\n\n"
                f"💰 Balansni to'ldirish uchun:\n"
                f"Menyu → Balans"
            )
            return
        
        # Allaqachon safardaligi?
        if driver.is_on_trip:
            await message.answer(
                "⚠️ Siz hozir safardasiz!\n\n"
                "Avval safarni yakunlang."
            )
            return
        
        # Marshrut tanlash
        routes = await get_all_active_routes(session)
        
        if not routes:
            await message.answer("❌ Hozirda aktiv marshrutlar yo'q")
            return
        
        # Jonli joylashuv so'rash
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        
        location_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
                [KeyboardButton(text="❌ Bekor qilish")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False
        )
        
        await message.answer(
            "📍 <b>Jonli joylashuv</b>\n\n"
            "Buyurtma qabul qilish uchun lokatsiyangizni yuboring.\n\n"
            "💡 <b>Maslahat:</b> Telegram'da lokatsiya yuborishda \"Jonli joylashuv\" tanlasangiz, "
            "lokatsiyangiz avtomatik yangilanadi va biz har safar aniq joylashuvni bilamiz.\n\n"
            "📍 Lokatsiyani yuborish tugmasini bosing:",
            reply_markup=location_keyboard,
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
        await callback.answer("❌ Xatolik: Ma'lumot topilmadi")
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
        driver = await get_driver_by_user_id(session, user_id)
        if not driver:
            if callback.message:
                await callback.message.answer("❌ Haydovchi topilmadi") # type: ignore
            await state.clear()
            await callback.answer()
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
        f"✅ <b>Buyurtmalar qabul qilinmoqda!</b>\n\n"
        f"📍 Marshrut: <b>{route.route_name}</b>\n" # type: ignore
        f"👥 Bo'sh joylar: <b>{seats}</b>\n\n"
        f"⏳ Buyurtma kelishini kutmoqdasiz...\n\n"
        f"💡 Buyurtma kelganda sizga xabar beramiz!",
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
        "✅ Buyurtma qabul qilish to'xtatildi",
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
        
        if not driver:
            await message.answer("❌ Ma'lumotlar topilmadi")
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


def get_driver_main_menu():
    """Driver asosiy menyusi"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Buyurtma qabul qilish")],
            [KeyboardButton(text="💰 Balans"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="📞 Support")]
        ],
        resize_keyboard=True
    )


@router.message(F.text == "⚙️ Sozlamalar")
async def driver_settings(message: Message):
    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>\n\nHozircha ishlab chiqilmoqda...")

@router.message(F.text == "📞 Support")
async def driver_support(message: Message):
    await message.answer("👨‍💻 <b>Texnik yordam</b>\n\nMuammo bo'yicha adminga yozing: @Bakhromdev")


# Diqqat: .message emas, .callback_query ishlatamiz
@router.callback_query(F.data == "pause_driver")
async def stop_accepting_orders_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await callback.answer("Haydovchi topilmadi")
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
    await callback.message.edit_text("✅ Buyurtma qabul qilish to'xtatildi") # type: ignore
    
    # Yangi menyuni yuboramiz (ReplyKeyboard)
    await callback.message.answer(
        "Asosiy menyu:", 
        reply_markup=get_driver_main_menu() 
    )
    
    # Telegramga "Tugma ishladi" degan javob qaytaramiz (loading aylanmasligi uchun)
    await callback.answer("Siz oflayn holatga o'tdingiz")



@router.callback_query(F.data == "driver_stats")
async def show_statistics_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        if not driver:
            await callback.answer("Ma'lumot topilmadi")
            return
            
        # ... (statistika hisoblash kodingiz) ...
        
        text = f"📊 <b>Sizning statistikangiz</b>\n\n💰 Balans: {driver.balance} so'm\n⭐ Reyting: {driver.rating}"
        
        await callback.message.answer(text)
        await callback.answer()
__all__ = ['router']
