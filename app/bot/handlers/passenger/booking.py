"""
app/bot/handlers/passenger/booking.py
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.sql import func as sql_func

from app.core.database import get_session, transaction
from app.models.passenger import get_passenger_by_user_id
from app.models.route import get_all_active_routes
from app.models.order import Order, OrderStatus, get_order_by_id
from app.services.order_service import create_new_order
from app.bot.states.passenger import PassengerStates
from app.bot.keyboards.passenger import get_route_selection_keyboard
from app.tasks.matching import find_driver_for_order_task

router = Router()


@router.message(F.text == "🚖 Taksi chaqirish")
async def start_booking(message: Message, state: FSMContext):
    """Taksi chaqirishni boshlash"""
    user_id = message.from_user.id # type: ignore
    
    async with get_session() as session:
        passenger = await get_passenger_by_user_id(session, user_id)
        
        if not passenger:
            await message.answer("❌ Ma'lumotlar topilmadi")
            return
        
        # Marshrut tanlash
        routes = await get_all_active_routes(session)
        
        if not routes:
            await message.answer("❌ Hozirda aktiv marshrutlar yo'q")
            return
        
        await message.answer(
            "📍 <b>Qayerga borasiz?</b>\n\n"
            "Marshrutni tanlang:",
            reply_markup=get_route_selection_keyboard(routes)
        )
        
        await state.set_state(PassengerStates.choose_route)


@router.callback_query(
    PassengerStates.choose_route,
    F.data.startswith("select_route:")
)
async def route_selected(callback: CallbackQuery, state: FSMContext):
    """Marshrut tanlandi"""
    route_id = int(callback.data.split(":")[1]) # type: ignore
    
    await state.update_data(route_id=route_id)
    
    await callback.message.edit_text( # type: ignore
        "📍 <b>Qayerdan olishni xohlaysiz?</b>\n\n"
        "Lokatsiyangizni yuboring yoki manzilni yozing:"
    )
    
    # Lokatsiya yuborish tugmasi
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )
    
    await callback.message.answer( # type: ignore
        "📍 Lokatsiyangizni yuboring:",
        reply_markup=keyboard
    )
    
    await state.set_state(PassengerStates.send_location)
    await callback.answer()


@router.message(PassengerStates.send_location, F.location)
async def location_received(message: Message, state: FSMContext):
    """Lokatsiya olindi"""
    location = message.location
    
    await state.update_data(
        pickup_lat=location.latitude, # type: ignore
        pickup_lon=location.longitude, # type: ignore
        pickup_location=f"Lat: {location.latitude:.4f}, Lon: {location.longitude:.4f}" # type: ignore
    )
    
    await message.answer(
        "✅ Lokatsiya qabul qilindi\n\n"
        "📍 Lokatsiya haqida qo'shimcha ma'lumot yozing:\n"
        "(Masalan: \"Uy oldida\", \"Kafe yonida\", \"Ko'cha 5\")"
    )
    
    await state.set_state(PassengerStates.location_description)


@router.message(PassengerStates.send_location, F.text)
async def location_text_received(message: Message, state: FSMContext):
    """Lokatsiya matn ko'rinishida yuborildi"""
    location_text = message.text or ""
    
    # Geocoding qilish kerak (keyinroq implementatsiya qilamiz)
    # Hozircha default koordinatalar
    await state.update_data(
        pickup_location=location_text,
        pickup_lat=41.3111,  # Toshkent default
        pickup_lon=69.2797
    )
    
    await message.answer(
        "✅ Manzil qabul qilindi\n\n"
        "📍 Lokatsiya haqida qo'shimcha ma'lumot yozing:\n"
        "(Masalan: \"Uy oldida\", \"Kafe yonida\", \"Ko'cha 5\")"
    )
    
    await state.set_state(PassengerStates.location_description)


@router.message(PassengerStates.location_description, F.text)
async def location_description_received(message: Message, state: FSMContext):
    """Lokatsiya izohi olindi"""
    description = message.text or ""
    
    await state.update_data(location_description=description)
    
    await message.answer(
        "✅ Izoh qabul qilindi\n\n"
        "👥 Necha kishi borasiz yoki pochtami?\n\n"
        "Tanlang:",
        reply_markup=get_passenger_count_keyboard()
    )
    
    await state.set_state(PassengerStates.add_details)


@router.callback_query(
    PassengerStates.add_details,
    F.data.startswith("passenger_count:")
)
async def passenger_count_selected(callback: CallbackQuery, state: FSMContext):
    """Yo'lovchilar soni yoki pochtani tanlandi"""
    count = int(callback.data.split(":")[1]) # type: ignore
    
    if count == 0:
        # Pochta tanlandi
        await state.update_data(
            passenger_count=0,
            has_luggage=True,
            luggage_count=1
        )
    else:
        # Yo'lovchi soni tanlandi
        await state.update_data(
            passenger_count=count,
            has_luggage=False,
            luggage_count=0
        )
    
    # Buyurtmani yaratish
    await finalize_order(callback.message, state)
    await callback.answer()




async def finalize_order(message, state: FSMContext):
    """Buyurtmani yaratish"""
    data = await state.get_data()
    user_id = message.chat.id
    
    async with get_session() as session:
        passenger = await get_passenger_by_user_id(session, user_id)
        
        # Location description bilan birlashtirish
        pickup_location = data['pickup_location']
        if data.get('location_description'):
            pickup_location = f"{pickup_location}\n📝 {data['location_description']}"
        
        # Buyurtma yaratish
        result = await create_new_order(
            passenger_id=passenger.passenger_id, # type: ignore
            route_id=data['route_id'],
            pickup_location=pickup_location,
            pickup_lat=data['pickup_lat'],
            pickup_lon=data['pickup_lon'],
            passenger_count=data['passenger_count'],
            has_luggage=data.get('has_luggage', False),
            luggage_count=data.get('luggage_count', 0)
        )
        
        if result['success']:
            await message.answer(
                f"✅ <b>Buyurtma qabul qilindi!</b>\n\n"
                f"📦 Buyurtma #{result['order_id']}\n\n"
                f"⏳ Haydovchi topilmoqda...\n\n"
                f"📱 Haydovchi topilgach xabar beramiz!",
                reply_markup=get_passenger_main_menu()
            )
            
            logger.success(f"Order created: {result['order_id']}")
        else:
            await message.answer(f"❌ {result['message']}")
    
    await state.clear()


def get_passenger_count_keyboard():
    """Yo'lovchilar soni (1-4) va Pochta"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1️⃣", callback_data="passenger_count:1"),
            InlineKeyboardButton(text="2️⃣", callback_data="passenger_count:2"),
        ],
        [
            InlineKeyboardButton(text="3️⃣", callback_data="passenger_count:3"),
            InlineKeyboardButton(text="4️⃣", callback_data="passenger_count:4"),
        ],
        [
            InlineKeyboardButton(text="📦 Pochta", callback_data="passenger_count:0")
        ]
    ])




def get_luggage_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="has_luggage:yes"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="has_luggage:no"),
        ]
    ])


def get_passenger_main_menu():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Taksi chaqirish")],
            [KeyboardButton(text="📍 Mening buyurtmalarim"), KeyboardButton(text="⭐ Tarix")],
        ],
        resize_keyboard=True
    )
@router.callback_query(F.data.startswith("confirm_trip:"))
async def confirm_trip(callback: CallbackQuery):
    """
    Yo'lovchi safar boshlashni tasdiqladi
    
    NIMA BO'LADI:
    1. Order statusini yangilash (ACCEPTED → IN_PROGRESS)
    2. Driver'ni on_trip qilish
    3. Haydovchiga xabar
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
        
        if order.status != OrderStatus.ACCEPTED:
            await callback.answer("⚠️ Bu buyurtma allaqachon boshlandi", show_alert=True)
            return
        
        # Safarni boshlash
        from app.services.order_service import start_trip
        result = await start_trip(order_id, order.driver_id)
        
        if result['success']:
            if callback.message:
                await callback.message.edit_text(
                    "✅ <b>Safar boshlandi!</b>\n\n"
                    "🚗 Xavfsiz yo'l!\n\n"
                    "Safar yakunlangach haydovchi sizga xabar beradi."
                )
            
            logger.info(f"Trip confirmed by passenger: order={order_id}")
        else:
            if callback.message:
                await callback.message.edit_text(f"❌ {result['message']}")
    
    await callback.answer("✅ Safar boshlandi!")


@router.callback_query(F.data.startswith("reject_trip:"))
async def reject_trip(callback: CallbackQuery):
    """
    Yo'lovchi: "Yo'q, hali olishgani yo'q"
    
    Bu haydovchi firibgarlik qilganini anglatadi!
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
        
        # Safarni bekor qilish va warning
        async with transaction() as session:
            from app.models.driver import Driver
            
            # Order'ni cancel qilish
            await session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='driver_no_show',
                    cancelled_at=sql_func.now()
                )
            )
            
            # Driver'ga warning (driver_warnings jadvali kerak, lekin hozircha Driver model'da ban_count oshirish)
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == order.driver_id)
                .values(
                    ban_count_today=Driver.ban_count_today + 1,
                    total_ban_count=Driver.total_ban_count + 1
                )
            )
            
            # Warning count tekshirish
            driver_result = await session.execute(
                select(Driver).where(Driver.driver_id == order.driver_id)
            )
            driver = driver_result.scalar_one()
            
            # Agar 3+ warning bo'lsa → 24 soat ban
            if driver.ban_count_today >= 3:
                await session.execute(
                    update(Driver)
                    .where(Driver.driver_id == order.driver_id)
                    .values(
                        is_blocked=True,
                        block_reason='multiple_fake_trips',
                        blocked_until=func.now() + func.make_interval(hours=24)
                    )
                )
        
        # Haydovchiga xabar
        from app.tasks.notifications import send_telegram_message
        send_telegram_message.delay(
            order.driver_id,
            f"""
⚠️ OGOHLANTIRISH

Yo'lovchi sizni olmaganingizni aytdi.

Safar bekor qilindi. Iltimos, faqat olmoqchi bo'lgan buyurtmalarni qabul qiling.

3 ta warning = 24 soat ban
            """
        )
        
        # Yangi haydovchi topish
        find_driver_for_order_task.delay(order_id)
        
        if callback.message:
            await callback.message.edit_text(
                "✅ <b>Safar bekor qilindi</b>\n\n"
                "Admin ko'rib chiqadi.\n"
                "Yangi haydovchi topilmoqda..."
            )
        
        logger.warning(
            f"Trip rejected by passenger: order={order_id}, driver={order.driver_id}"
        )
    
    await callback.answer("Safar bekor qilindi. Yangi haydovchi topilmoqda...")

__all__ = ['router']