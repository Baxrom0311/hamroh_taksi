"""
app/bot/handlers/passenger/booking.py
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.sql import func as sql_func
from app.models.route import get_route_by_id
from app.models.order import Order, OrderStatus  # ✅ Order va OrderStatus qo'shildi
from app.core.database import get_session, transaction
from app.models.passenger import get_passenger_by_user_id
from app.models.route import get_all_active_routes
from app.services.order_service import create_new_order
from app.bot.states.passenger import PassengerStates
from app.bot.keyboards.passenger import (
    get_route_selection_keyboard,
    get_passenger_location_keyboard,
    get_passenger_count_keyboard,
    get_passenger_main_menu
)
from app.bot.messages import Messages
from app.bot.utils import get_passenger_or_error, get_order_or_error
from app.tasks.matching import find_driver_for_order_task  # ✅ Task import qo'shildi

router = Router()


@router.message(F.text == "🚖 Taksi chaqirish")
async def start_booking(message: Message, state: FSMContext):
    """Taksi chaqirishni boshlash"""
    user_id = message.from_user.id # type: ignore
    
    async with get_session() as session:
        passenger = await get_passenger_or_error(session, user_id, message)
        
        if not passenger:
            return
        
        # Aktiv marshrutlarni tekshirish
        active_routes = await get_all_active_routes(session)
        if not active_routes:
            await message.answer(Messages.Passenger.NO_ROUTES)
            return
        
        await message.answer(
            Messages.Passenger.WHERE_TO,
            reply_markup=get_route_selection_keyboard(active_routes)
        )
        
        await state.set_state(PassengerStates.choose_route)


@router.callback_query(
    PassengerStates.choose_route,
    F.data.startswith("select_route:")
)
async def route_selected(callback: CallbackQuery, state: FSMContext):
    """Marshrut tanlandi"""
    route_id = int(callback.data.split(":")[1]) # type: ignore
    
    async with get_session() as session:
        route = await get_route_by_id(session, route_id)
        if not route:
            await callback.answer("❌ Marshrut topilmadi", show_alert=True)
            return
        route_name = route.route_name
    
    await state.update_data(route_id=route_id, route_name=route_name)
    
    await callback.message.answer( # type: ignore
        Messages.Passenger.WHERE_FROM
    )
    
    await callback.message.answer( # type: ignore
        Messages.Passenger.SEND_LOCATION,
        reply_markup=get_passenger_location_keyboard()
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
        Messages.Passenger.LOCATION_RECEIVED,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    ) # <--- MATN YOZILGANDA HAM TUGMALARNI OLIB TASHLAYMIZ
    
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
        Messages.Passenger.LOCATION_DESC_RECEIVED,
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
            pickup_location = f"{pickup_location}\n 📝 {data['location_description']}"
        
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
            await message.edit_text( # type: ignore
                Messages.Passenger.ORDER_CREATED.format(order_id=result['order_id']),
                reply_markup=get_passenger_main_menu(),
                parse_mode="HTML"
            )    
            logger.success(f"Order created: {result['order_id']}")
        else:
            # HTML escape qilish - xatolik xabarlarida HTML taglar bo'lmasligi uchun
            error_message = str(result['message']).replace('<', '&lt;').replace('>', '&gt;')
            await message.answer(
                f"❌ {error_message}",
                parse_mode="HTML"
            )
    
    await state.clear()


@router.callback_query(F.data.startswith("passenger_started:"))
async def passenger_started(callback: CallbackQuery):
    """
    Yo'lovchi "Ketdik" tugmasini bosdi - safar boshlandi
    
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
        passenger = await get_passenger_or_error(session, user_id, callback)
        if not passenger:
            return
        
        # Order'ni olish
        from app.models.order import get_order_by_id, OrderStatus
        order = await get_order_or_error(session, order_id, callback)
        if not order:
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
                    "Safar yakunlangach haydovchi sizga xabar beradi.\n\n"
                    "⏱ Safar 10 daqiqadan keyin avtomatik yakunlanadi."
                )
            
            # Haydovchiga xabar
            from app.models.driver import get_driver_by_id
            driver = await get_driver_by_id(session, order.driver_id)
            if driver:
                from app.bot.main import bot
                try:
                    await bot.send_message(
                        chat_id=driver.user_id,
                        text=f"✅ <b>Yo'lovchi ketdi!</b>\n\n"
                             f"📦 Buyurtma #{order_id}\n\n"
                             f"🚗 Xavfsiz yo'l!\n\n"
                             f"⏱ Safar 10 daqiqadan keyin avtomatik yakunlanadi.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify driver: {e}")
            
            # 10 daqiqadan keyin avtomatik safar yakunlanish task
            from app.tasks.matching import auto_complete_trip_task
            auto_complete_trip_task.apply_async(args=[order_id], countdown=600)  # 10 daqiqa = 600 soniya
            
            logger.info(f"Trip started by passenger: order={order_id}, auto-complete scheduled in 10 minutes")
        else:
            if callback.message:
                await callback.message.edit_text(f"❌ {result['message']}")
    
    await callback.answer("✅ Safar boshlandi!")


@router.callback_query(F.data.startswith("passenger_cancel:"))
async def passenger_cancel_order(callback: CallbackQuery):
    """
    Yo'lovchi buyurtmani bekor qildi
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        passenger = await get_passenger_or_error(session, user_id, callback)
        if not passenger:
            return
        
        # Order'ni olish
        from app.models.order import get_order_by_id, OrderStatus
        order = await get_order_or_error(session, order_id, callback)
        if not order:
            return
        
        if order.status not in [OrderStatus.ACCEPTED]:
            await callback.answer("⚠️ Bu buyurtmani bekor qilib bo'lmaydi", show_alert=True)
            return
        
        # Order'ni bekor qilish
        async with transaction() as session:
            from sqlalchemy import update
            from app.models.driver import Driver
            
            await session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='passenger_cancelled',
                    cancelled_at=sql_func.now()
                )
            )
            
            # Driver'ni bo'shatish
            if order.driver_id:
                await session.execute(
                    update(Driver)
                    .where(Driver.driver_id == order.driver_id)
                    .values(
                        available_seats=Driver.available_seats + order.passenger_count,
                        is_on_trip=False
                    )
                )
        
        # Haydovchiga xabar
        if order.driver_id:
            from app.models.driver import get_driver_by_id
            driver = await get_driver_by_id(session, order.driver_id)
            if driver:
                from app.bot.main import bot
                try:
                    await bot.send_message(
                        chat_id=driver.user_id,
                        text=f"❌ <b>Buyurtma bekor qilindi</b>\n\n"
                             f"📦 Buyurtma #{order_id}\n\n"
                             f"Yo'lovchi buyurtmani bekor qildi.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify driver: {e}")
        
        if callback.message:
            await callback.message.edit_text(
                "❌ <b>Buyurtma bekor qilindi</b>\n\n"
                "Yangi buyurtma berish uchun menyudan 'Taksi chaqirish'ni tanlang."
            )
        
        logger.info(f"Order cancelled by passenger: order={order_id}")
    
    await callback.answer("Buyurtma bekor qilindi")


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
        passenger = await get_passenger_or_error(session, user_id, callback)
        if not passenger:
            return
        
        order = await get_order_or_error(session, order_id, callback)
        if not order:
            return
            
        if not order.driver_id:
            await callback.answer(Messages.Error.DRIVER_NOT_FOUND, show_alert=True)
            return
        
        # Safarni bekor qilish va warning
        async with transaction() as session:
            from sqlalchemy import update
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