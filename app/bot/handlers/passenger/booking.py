"""
app/bot/handlers/passenger/booking.py
"""

from ..base import *
from typing import Any, cast
from app.core.database import transaction
from app.models.route import get_route_by_id, get_all_active_routes
from app.models.order import Order, OrderStatus
from app.services.order_service import create_new_order
from app.bot.states.passenger import PassengerStates
from app.bot.states.driver import DriverStates
from app.bot.keyboards.passenger import (
    get_route_selection_keyboard,
    get_passenger_location_keyboard,
    get_passenger_count_keyboard,
    get_passenger_main_menu
)
from app.tasks.matching import find_driver_for_order_task
  # ✅ Task import qo'shildi

router = Router()


@router.message(F.text == "🚖 Taksi chaqirish")
@with_passenger_session  # ✅ Decorator
async def start_booking(message: Message, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """Taksi chaqirishni boshlash - ✅ REFACTORED"""
        
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
@with_session
async def route_selected(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Marshrut tanlandi"""
    route_id = int(callback.data.split(":")[1]) # type: ignore
    
    route = await get_route_by_id(session, route_id)
    if not route:
        await callback.answer("❌ Marshrut topilmadi", show_alert=True)
        return
    
    route_name = route.route_name
    
    await state.update_data(route_id=route_id, route_name=route_name)
    
    # Bitta xabarda ko'rsatamiz (takrorlarsiz)
    await callback.message.answer(  # type: ignore
        Messages.Passenger.WHERE_FROM,
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
@with_session
async def passenger_count_selected(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
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
    await finalize_order(callback.message, session, state)
    await callback.answer()


async def finalize_order(message, session: AsyncSession, state: FSMContext):
    """Buyurtmani yaratish"""
    data = await state.get_data()
    user_id = message.chat.id
    
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
        # Inline callback message cannot carry ReplyKeyboardMarkup, so split into edit + new message
        await message.edit_text(  # type: ignore
            Messages.Passenger.ORDER_CREATED.format(order_id=result['order_id']),
            parse_mode="HTML"
        )
        await message.answer(
            "🔝 Asosiy menyu:",
            reply_markup=get_passenger_main_menu()
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
@with_passenger_session
async def passenger_started(callback: CallbackQuery, session: AsyncSession, passenger: Passenger, state: FSMContext):
    """
    Yo'lovchi "Ketdik" tugmasini bosdi - safar boshlandi
    """
    # Agar tasodifan driver state qolgan bo'lsa, tozalab ketamiz
    current_state = await state.get_state()
    if current_state and current_state.startswith(DriverStates.__name__):
        await state.clear()
    if callback.data is None:
        return
    
    order_id = int(callback.data.split(":")[1])
    
    # Order'ni olish
    order = await get_order_or_error(session, order_id, callback)
    if not order:
        return
    
    if order.status != OrderStatus.ACCEPTED:
        await callback.answer("⚠️ Bu buyurtma allaqachon boshlandi", show_alert=True)
        return
    
    # Safarni boshlash
    from app.services.order_service import start_trip
    if order.driver_id is None:
        await callback.answer(Messages.Error.DRIVER_NOT_FOUND, show_alert=True)
        return
    result = await start_trip(order_id, order.driver_id)
    
    if result['success']:
        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                "✅ <b>Safar boshlandi!</b>\n\n"
                "🚗 Xavfsiz yo'l!\n\n"
                "Safar yakunlangach haydovchi sizga xabar beradi.\n\n"
                "⏱ Safar 10 daqiqadan keyin avtomatik yakunlanadi.",
                parse_mode="HTML"
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
        from typing import Any, cast
        cast(Any, auto_complete_trip_task).apply_async(args=[order_id], countdown=600)
        
        logger.info(f"Trip started by passenger: order={order_id}")
        await callback.answer("✅ Safar boshlandi!")
    else:
        error_msg = result.get('message', 'Noma\'lum')
        await callback.answer(f"❌ Xatolik: {error_msg}", show_alert=True)




@router.callback_query(F.data.startswith("passenger_cancel:"))
@with_passenger_session
async def passenger_cancel_order(callback: CallbackQuery, session: AsyncSession, passenger: Passenger):
    """
    Yo'lovchi buyurtmani bekor qildi
    """
    if callback.data is None:
        return
    
    order_id = int(callback.data.split(":")[1])
    
    # Order'ni olish
    order = await get_order_or_error(session, order_id, callback)
    if not order:
        return
    
    if order.status not in [OrderStatus.ACCEPTED, OrderStatus.PENDING]:
        await callback.answer("⚠️ Bu buyurtmani bekor qilib bo'lmaydi", show_alert=True)
        return
    
    # Order'ni bekor qilish
    async with transaction() as session:
        from app.models.driver import Driver
        from app.services import payment_service
        
        # Komissiya haydovchiga qaytariladi (agar bor bo'lsa)
        if order.driver_id and order.commission_amount:
            await payment_service.refund_commission(
                session,
                driver_id=order.driver_id,
                order_id=order.order_id,
                amount=order.commission_amount,
                reason="cancelled_by_passenger"
            )

        await session.execute(
            update(Order)
            .where(Order.order_id == order_id)
            .values(
                status=OrderStatus.CANCELLED,
                cancellation_reason='passenger_cancelled',
                cancelled_at=func.now()
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
    
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "❌ <b>Buyurtma bekor qilindi</b>\n\n"
            "Yangi buyurtma berish uchun menyudan 'Taksi chaqirish'ni tanlang.",
            parse_mode="HTML"
        )
    
    logger.info(f"Order cancelled by passenger: order={order_id}")
    await callback.answer("Buyurtma bekor qilindi")



@router.callback_query(F.data.startswith("reject_trip:"))
@with_passenger_session
async def reject_trip(callback: CallbackQuery, session: AsyncSession, passenger: Passenger):
    """
    Yo'lovchi: "Yo'q, hali olishgani yo'q"
    
    Bu haydovchi firibgarlik qilganini anglatadi!
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    
    order = await get_order_or_error(session, order_id, callback)
    if not order:
        return
        
    if not order.driver_id:
        await callback.answer(Messages.Error.DRIVER_NOT_FOUND, show_alert=True)
        return
    
    # Safarni bekor qilish va warning
    async with transaction() as session:
        from app.models.driver import Driver
        from sqlalchemy import update, select
        from sqlalchemy.sql import func
        from app.tasks.matching import find_driver_for_order_task
        
        # Order'ni cancel qilish
        await session.execute(
            update(Order)
            .where(Order.order_id == order_id)
            .values(
                status=OrderStatus.CANCELLED,
                cancellation_reason='driver_no_show',
                cancelled_at=func.now()
            )
        )
        
        # Driver'ga warning
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == order.driver_id)
            .values(
                ban_count_today=Driver.ban_count_today + 1,
                total_ban_count=Driver.total_ban_count + 1
            )
        )
        # Warning count tekshirish
        result = await session.execute(
            select(Driver).where(Driver.driver_id == order.driver_id)
        )
        driver = result.scalar_one_or_none()
        
        if driver and driver.ban_count_today >= 3:
            # Bugun uchun bloklash
            driver.is_blocked = True
            driver.block_reason = "Kunlik ogohlantirishlar limiti (3 ta) tugadi."
            logger.warning(f"Driver {driver.driver_id} blocked automatically (3 warnings)")
    
    # Haydovchiga xabar
    from app.tasks.notifications import send_telegram_message
    from typing import Any, cast
    cast(Any, send_telegram_message).delay(
        order.driver_id,
        f"""
⚠️ OGOHLANTIRISH

Yo'lovchi sizni olmaganingizni aytdi.

Safar bekor qilindi. Iltimos, faqat olmoqchi bo'lgan buyurtmalarni qabul qiling.

3 ta warning = 24 soat ban
            """
        )
        
    # Yangi haydovchi topish
    cast(Any, find_driver_for_order_task).delay(order_id)
    
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "✅ <b>Safar bekor qilindi</b>\n\n"
            "Admin ko'rib chiqadi.\n"
            "Yangi haydovchi topilmoqda...",
            parse_mode="HTML"
        )
    
    logger.warning(
        f"Trip rejected by passenger: order={order_id}, driver={order.driver_id}"
    )
    
    await callback.answer("Safar bekor qilindi. Yangi haydovchi topilmoqda...")


__all__ = ['router']
