"""
app/bot/handlers/driver/orders.py

HAYDOVCHI BUYURTMALAR HANDLER

BU HANDLER NIMA QILADI:
- Buyurtma qabul qilish (LOCK bilan)
- Safar boshlash
- Safar yakunlash
"""
from ..base import *
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest
from app.core.database import transaction
from app.models.order import Order, get_order_by_id, OrderStatus
from app.models.trip import Trip, TripStatus
from app.services.order_service import (
    accept_order_by_driver,
    start_trip,
    complete_trip
)
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import (
    get_trip_confirmation_keyboard,
    get_trip_active_keyboard,
    get_order_cancellation_keyboard,
    get_driver_main_menu
)
from app.tasks.matching import find_driver_for_order_task
from app.services.redis_cleanup import cleanup_skip_keys_for_order


router = Router()


# ============================================
# BUYURTMA QABUL QILISH
# ============================================

@router.callback_query(F.data.startswith("accept_order:"))
@with_driver_session  # ✅ Decorator
async def accept_order_handler(callback: CallbackQuery, session: AsyncSession, driver: Driver, state: FSMContext):
    
    order_id = parse_callback_data(callback.data, "accept_order")
    if order_id is None:
        await callback.answer(Messages.Error.CALLBACK_DATA_MISSING)
        return
    # ❗ Bloklangan?
    if driver.is_blocked:
        await callback.answer(
            Messages.Driver.BLOCKED.format(reason="Bloklangansiz"),
            show_alert=True
        )
        return

    # 2. Buyurtmani qabul qilish logikasi
    result = await accept_order_by_driver(driver_id=driver.driver_id, order_id=order_id)
    
    if result['success']:
        # ✅ Clear inactivity counter (driver javob berdi)
        from app.services.queue_service import driver_queue
        order_route_id = result.get('order', {}).get('route_id') or driver.current_route_id
        if order_route_id:
            await driver_queue.clear_driver_inactivity(driver.driver_id, order_route_id)
        
        # ✅ Unlock driver offer (accepted)
        await driver_queue.unlock_driver_offer(driver.driver_id)
        
        # ✅ SESSION REFRESH: Fresh data olish (balance, available_seats)
        from app.utils.session_utils import refresh_model
        await refresh_model(session, driver)
        
        commission_amount = result['order']['commission'] # Extract commission amount

        # Order ma'lumotlarini olish (mijoz ma'lumotlari bilan)
        order_result = await session.execute(
            select(Order)
            .options(
                selectinload(Order.passenger).selectinload(Passenger.user),
                selectinload(Order.route)
            )
            .where(Order.order_id == order_id)
        )
        order = order_result.scalar_one_or_none()
        fare_amount_value = None
        if order and order.route and order.route.fare_amount is not None:
            fare_amount_value = float(order.route.fare_amount)
        fare_amount_display = f"{fare_amount_value:,.0f} so'm" if fare_amount_value is not None else "N/A"
        
        # 3. ESKI XABARNI TAHRIRLASH (Tugmalarni yo'qotish uchun)
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                Messages.Driver.ORDER_ACCEPTED.format(
                    order_id=order_id,
                    commission=commission_amount,
                    fare_amount=fare_amount_display,
                    new_balance=driver.balance  # ✅ Fresh balance
                ),
                parse_mode="HTML"
            )
        else:
            await callback.answer(Messages.Error.MESSAGE_OUTDATED, show_alert=True)
                            
        # 4. Mijoz ma'lumotlarini yuborish (qabul qilganda)
        if order and order.passenger:
            passenger = order.passenger
            passenger_name = passenger.full_name
            passenger_phone = passenger.user.phone_number if passenger.user else "N/A"
            
            # Buyurtma turi va pochtani aniqlash
            order_type_text = order.type_text
            
            # Lokatsiya linklari
            # ✅ CRITICAL FIX: Handle None coordinates for text-only addresses
            from app.utils.location_helpers import get_google_maps_link, get_telegram_location_link
            
            # Convert to float only if not None
            pickup_lat = float(order.pickup_lat) if order.pickup_lat is not None else None
            pickup_lon = float(order.pickup_lon) if order.pickup_lon is not None else None
            
            google_maps_link = get_google_maps_link(pickup_lat, pickup_lon, order.pickup_location)
            telegram_location_link = get_telegram_location_link(pickup_lat, pickup_lon)
            
            # If no GPS coordinates, use text-only location
            if google_maps_link is None:
                location_display = f"{order.pickup_location} (⚠️ Matn manzil - GPS yo'q)"
                google_maps_link = "#"  # Placeholder for message template
                telegram_location_link = "#"
            else:
                location_display = order.pickup_location
            
            passenger_info = Messages.Driver.PASSENGER_INFO.format(
                pickup_location=location_display,
                google_maps_link=google_maps_link,
                telegram_location_link=telegram_location_link,
                order_type=order_type_text,
                phone=passenger_phone
            )

            if isinstance(callback.message, Message):
                await callback.message.answer(
                    passenger_info,
                    parse_mode="HTML"
                )
            elif callback.bot:
                # Agar xabar InaccessibleMessage bo'lsa (masalan, juda eski xabar)
                await callback.bot.send_message(
                    chat_id=callback.from_user.id,
                    text=passenger_info,
                    parse_mode="HTML"
                )
                
        # 5. YANGI XABAR YUBORISH (Sizning Reply klaviaturangizni chiqarish uchun)
        from app.services.queue_service import driver_queue
        
        # Qolgan bo'sh o'rinlar
        remaining_seats = result['order']['available_seats']
        has_more_seats = result['order']['has_more_seats']
        
        trip_message = Messages.Driver.TRIP_ACCEPTED_PROMPT.format(order_id=order_id)
        
        if has_more_seats:
            trip_message += Messages.Driver.REMAINING_SEATS_INFO.format(remaining_seats=remaining_seats)
        
        if isinstance(callback.message, Message):
            await callback.message.answer(
                trip_message,
                reply_markup=get_trip_confirmation_keyboard(order_id),
                parse_mode="HTML"
            )
        else:
            from app.bot.main import bot
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=trip_message,
                reply_markup=get_trip_confirmation_keyboard(order_id),
                parse_mode="HTML"
            )
        
        # MUHIM: Agar o'rinlar to'lganda, navbatdan o'chirish
        if not has_more_seats and order:
            # O'rinlar to'ldi - navbatdan o'chirish
            await driver_queue.remove_driver(driver.driver_id, order.route_id)
            logger.info(
                f"Driver {driver.driver_id} removed from queue: "
                f"no more seats available"
            )
            from app.tasks.matching import notify_queue_update_task, clear_queue_message_task
            clear_queue_message_task.delay(driver.driver_id, order.route_id)  # type: ignore
            notify_queue_update_task.delay(order.route_id)  # type: ignore
        
        # 5. State va Tasklar
        await state.update_data(current_order_id=order_id)
        await state.set_state(DriverStates.trip_in_progress)
        
        # Yo'lovchiga xabar yuborish
        from app.tasks.notifications import notify_passenger_driver_found
        if order and order.passenger and order.passenger.user:
            from app.bot.main import bot
            from app.utils.location_helpers import get_google_maps_link

            passenger_text = Messages.Passenger.DRIVER_FOUND.format(
                order_id=order_id,
                full_name=driver.full_name,
                phone_number=driver.phone_number or "N/A",
                car_model=driver.car_model,
                car_color=driver.car_color,
                car_number=driver.car_number,
                fare_amount=fare_amount_display
            )
            if driver.last_location_lat and driver.last_location_lon:
                driver_loc_link = get_google_maps_link(
                    float(driver.last_location_lat),
                    float(driver.last_location_lon),
                    f"Haydovchi {driver.full_name}"
                )
                passenger_text += f"\n📍 <a href=\"{driver_loc_link}\">Haydovchi joriy lokatsiyasi</a>"

            try:
                await bot.send_message(
                    chat_id=order.passenger.user.user_id,
                    text=passenger_text,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Failed to notify passenger (accept_order): {e}")
        
        logger.success(f"Order {order_id} accepted and UI updated for driver {driver.driver_id}")
    
    else:
        # Xato bo'lsa
        if isinstance(callback.message, Message):
            await callback.message.edit_text(f"❌ <b>Xatolik:</b>\n{result['message']}")
        logger.warning(f"Accept failed: {result['message']}")
    
    await callback.answer()


# ============================================
# YO'LGA CHIQDIK (SAFAR BOSHLASH)
# ============================================

@router.message(
    StateFilter("*"),  # Agar state yo'qolsa ham tutib qolamiz
    F.text.in_(["🚗 Yo'lga chiqdik", "Yo'lga chiqdik", "🚗 Yo’lga chiqdik", "🚗 Yoʻlga chiqdik"])
    | F.text.regexp(r"(?i)yo.?lga\\s+chiqdik")
)
@with_driver_session  # ✅ Decorator
async def driver_started_trip(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi "Yo'lga chiqdik" tugmasini bosdi - safar boshlandi
    
    NIMA BO'LADI:
    1. Safar boshlandi (ACCEPTED → IN_PROGRESS)
    2. Driver is_on_trip=True (15 daqiqa davomida yangi buyurtma olmaydi)
    3. Qolgan bo'sh o'rinlar tekshiruvi
    4. Agar o'rinlar to'lganda, navbatdan o'chirish
    5. 15 daqiqadan keyin avtomatik yakunlash
    """
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    if not order_id:
        await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
        return
    
    # Order'ni eager load bilan olish (lazy load -> MissingGreenlet bo'lmasligi uchun)
    order_result = await session.execute(
        select(Order)
        .options(selectinload(Order.passenger).selectinload(Passenger.user))
        .where(Order.order_id == order_id)
    )
    order = order_result.scalar_one_or_none()
    
    if not order or order.driver_id != driver.driver_id:
        await message.answer(Messages.Error.ORDER_BUT_DRIVER_MISMATCH)
        return
    
    if order.status != OrderStatus.ACCEPTED:
        await message.answer("⚠️ Bu buyurtma allaqachon boshlandi")
        return
    
    # Safarni boshlash
    result = await start_trip(order_id, driver.driver_id)
    
    if result['success']:
        # Refresh driver data because accept_order_by_driver updated DB
        await session.refresh(driver)
        
        # Agar o'rinlar to'lganda, navbatdan o'chirish
        if driver.available_seats <= 0:
            from app.services.queue_service import driver_queue
            await driver_queue.remove_driver(driver.driver_id, order.route_id)
            logger.info(
                f"Driver {driver.driver_id} removed from queue: "
                f"no more seats available after trip started"
            )
            from app.tasks.matching import notify_queue_update_task, clear_queue_message_task
            clear_queue_message_task.delay(driver.driver_id, order.route_id)  # type: ignore
            notify_queue_update_task.delay(order.route_id)  # type: ignore
        
        # Avto-yakunlash task (10 daqiqa - aniq)
        # ✅ CONSTANTS: Use settings instead of hardcoded 600
        from config.settings import settings
        from app.core.celery_app import celery_app
        # Use Celery send_task to avoid mypy/pylance confusion around task wrapper
        # If this order is part of a trip, auto-complete the whole trip
        target_id = order.trip_id or order_id
        celery_app.send_task(
            "app.tasks.matching.auto_complete_trip_task",
            args=[target_id],
            countdown=settings.AUTO_COMPLETE_TRIP_SECONDS,
        )
            
        # Haydovchiga xabar (Safar menyusi)
        await message.answer(
            f"✅ <b>Safar boshlandi!</b>\n\n"
            f"⏱ <b>10 daqiqadan so'ng</b> safar avtomatik yakunlanadi.\n"
            f"Unga qadar '📞 Yo'lovchi bilan bog'lanish' tugmasidan foydalanishingiz mumkin.",
            reply_markup=get_trip_active_keyboard(order.order_id),
            parse_mode="HTML"
        )
        
        # State ni SAQLAB QOLAMIZ (trip_in_progress)
        # Chunki haydovchi "Contact Passenger" ni bosishi kerak
        # 10 daqiqadan keyin task baribir DB da statusni o'zgartiradi
        # State esa keyingi safar botga kirganda tekshiriladi
            
        # Yo'lovchiga xabar
        if order.passenger and order.passenger.user:
            from app.bot.main import bot
            try:
                await bot.send_message(
                    chat_id=order.passenger.user.user_id,  # ✅ Tuzatildi
                    text=f"✅ <b>Haydovchi yo'lga chiqdi!</b>\n\n",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to notify passenger: {e}")
        
        logger.info(f"Trip started by driver: order={order_id}, driver={driver.driver_id}")
    else:
        await message.answer(f"❌ {result['message']}")


# ============================================
# SAFAR YAKUNLASH (MANUAL FALLBACK)
# ============================================

@router.message(
    StateFilter("*"),  # ✅ CRITICAL FIX: Har qanday state'da qabul qilish!
    F.text == "✅ Safarni yakunlash"
)
@with_driver_session
async def manual_complete_trip(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi o'zi safarni yakunlasa (timer ishlamagan holatlarga fallback).
    
    ✅ SIMPLIFIED: Uses centralized cleanup utility, clearer flow
    """
    from sqlalchemy import select, update, func
    # 1. State'dan order_id olish
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    # 2. Agar state'da yo'q bo'lsa, database'dan topish
    if not order_id:
        logger.warning(f"Driver {driver.driver_id} has no current_order_id in state, checking database...")
        
        # Driver'ning aktiv buyurtmalarini topish
        active_orders_result = await session.execute(
            select(Order)
            .where(Order.driver_id == driver.driver_id)
            .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        active_order = active_orders_result.scalar_one_or_none()
        
        if not active_order:
            # ✅ SIMPLIFIED: Use centralized cleanup utility
            logger.warning(f"No active orders for driver {driver.driver_id}, cleaning stuck state...")
            from app.utils.driver_state_utils import cleanup_stuck_driver_state
            
            await cleanup_stuck_driver_state(session, driver.driver_id, commit=False)
            await state.clear()
            
            await message.answer(
                "✅ Holatingiz tozalandi!\n\n"
                "Aktiv buyurtma topilmadi, siz endi yangi buyurtma qabul qilishingiz mumkin.",
                reply_markup=get_driver_main_menu()
            )
            return
        
        order_id = active_order.order_id
        logger.info(f"Found active order {order_id} from database for driver {driver.driver_id}")

    # 3. Safarni yakunlash (trip bo'lsa - hammasini yakunlash)
    order_ids_to_complete = []
    trip_id = None
    if order_id:
        order_result = await session.execute(
            select(Order)
            .where(Order.order_id == order_id)
        )
        current_order = order_result.scalar_one_or_none()
        if current_order:
            trip_id = current_order.trip_id
    if trip_id:
        # Tripdagi ACCEPTED orderlarni IN_PROGRESS ga o'tkazamiz
        await session.execute(
            update(Order)
            .where(Order.trip_id == trip_id)
            .where(Order.driver_id == driver.driver_id)
            .where(Order.status == OrderStatus.ACCEPTED)
            .values(
                status=OrderStatus.IN_PROGRESS,
                started_at=func.now()
            )
        )
        await session.commit()
        trip_orders_result = await session.execute(
            select(Order.order_id)
            .where(Order.trip_id == trip_id)
            .where(Order.driver_id == driver.driver_id)
            .where(Order.status == OrderStatus.IN_PROGRESS)
        )
        order_ids_to_complete = [row[0] for row in trip_orders_result.all()]
    else:
        order_ids_to_complete = [order_id]

    if not order_ids_to_complete:
        await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
        return

    results = []
    for oid in order_ids_to_complete:
        result = await complete_trip(oid, driver.driver_id)
        results.append(result)
        if not result.get('success'):
            logger.warning(f"Manual trip complete failed for order {oid}: {result.get('message')}")

    if not any(r.get('success') for r in results):
        await message.answer(results[-1].get('message', Messages.Error.SOMETHING_WENT_WRONG))
        return

    # 4. State'ni tozalash - trip complete bo'lgach
    await state.clear()

    # 5. Haydovchiga tasdiq xabari
    completed_count = sum(1 for r in results if r.get('success'))
    await message.answer(
        f"✅ Safar yakunlandi!\n\n"
        f"📦 Yakunlangan buyurtmalar: {completed_count} ta\n"
        f"⏱ Davomiyligi: {results[-1].get('duration_minutes', 'N/A')} daqiqa",
        reply_markup=get_driver_main_menu(),
        parse_mode="HTML"
    )

    # 6. Yo'lovchidan reyting so'rash
    # ✅ SIMPLIFIED: complete_trip already loads passenger data, use it
    from app.bot.main import bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    for oid, res in zip(order_ids_to_complete, results):
        order_data = res.get('order')
        if not order_data:
            continue
        passenger_user_id = order_data.get('passenger_user_id')
        if not passenger_user_id:
            continue
        rating_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐️ 1", callback_data=f"rate_driver:{oid}:1"),
                InlineKeyboardButton(text="⭐️ 2", callback_data=f"rate_driver:{oid}:2"),
                InlineKeyboardButton(text="⭐️ 3", callback_data=f"rate_driver:{oid}:3"),
            ],
            [
                InlineKeyboardButton(text="⭐️ 4", callback_data=f"rate_driver:{oid}:4"),
                InlineKeyboardButton(text="⭐️ 5", callback_data=f"rate_driver:{oid}:5"),
            ]
        ])
        try:
            await bot.send_message(
                chat_id=passenger_user_id,
                text=(
                    f"✅ <b>Safar yakunlandi</b>\n\n"
                    f"✨ <b>Haydovchiga baho bering:</b>"
                ),
                parse_mode="HTML",
                reply_markup=rating_kb
            )
        except Exception as e:
            logger.error(f"Failed to send rating prompt: {e}")


# ============================================
# BEKOR QILISH
# ============================================

@router.message(
    StateFilter(
        DriverStates.trip_in_progress, 
        DriverStates.trip_confirmation
        ),
    F.text == "📞 Yo'lovchi bilan bog'lanish"
)
@with_driver_session  # ✅ Decorator
async def contact_passenger_handler(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi yo'lovchi(lar) bilan bog'lanish uchun ma'lumotlarni ko'radi
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    try:
        logger.info(f"📞 Contact passenger request from driver {driver.driver_id}")
        
        # Faqat joriy aktiv tripdagi buyurtmalarni ko'rsatamiz
        trip_result = await session.execute(
            select(Trip)
            .options(
                selectinload(Trip.orders)
                .options(
                    selectinload(Order.passenger).selectinload(Passenger.user)
                )
            )
            .where(Trip.driver_id == driver.driver_id)
            .where(Trip.status == TripStatus.ACTIVE)
            .order_by(Trip.created_at.desc())
            .limit(1)
        )
        active_trip = trip_result.scalar_one_or_none()

        if not active_trip:
            logger.warning(f"No active trip found for driver {driver.driver_id}")
            await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
            return

        active_orders = [
            order for order in active_trip.orders
            if order.status in (OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS)
        ]

        if not active_orders:
            logger.warning(f"No active orders in trip for driver {driver.driver_id}")
            await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
            return
        
        # Barcha yo'lovchilar ma'lumotlarini yig'ish
        from app.utils.location_helpers import get_google_maps_link
        
        passengers_info = []
        
        for idx, order in enumerate(active_orders, 1):
            if not order.passenger:
                logger.warning(f"Order {order.order_id} has no passenger")
                continue
                
            passenger = order.passenger
            passenger_name = passenger.full_name
            passenger_phone = passenger.user.phone_number if passenger.user else "N/A"
            
            logger.debug(f"Processing order {order.order_id}: lat={order.pickup_lat}, lon={order.pickup_lon}")
            
            # Google Maps link (location optional)
            google_maps_link = None
            if order.pickup_lat is not None and order.pickup_lon is not None:
                google_maps_link = get_google_maps_link(
                    float(order.pickup_lat),
                    float(order.pickup_lon),
                    order.pickup_location
                )
            
            # Buyurtma turi
            order_type = ""
            if order.passenger_count == 0 and order.has_luggage:
                order_type = "📦 Pochta"
                if order.luggage_count > 1:
                    order_type += f" ({order.luggage_count} dona)"
                if order.luggage_description:
                    order_type += f"\n  📝 {order.luggage_description}"
            elif order.has_luggage and order.passenger_count > 0:
                order_type = f"👥 {order.passenger_count} kishi"
                if order.luggage_count > 0:
                    order_type += f" + 📦 Pochta ({order.luggage_count} dona)"
                    if order.luggage_description:
                        order_type += f"\n 📝 {order.luggage_description}"
            else:
                order_type = f"👥 {order.passenger_count} kishi"
            
            # Yo'lovchi ma'lumotlari
            if google_maps_link:
                location_display = f'<a href="{google_maps_link}">{order.pickup_location}</a>'
            else:
                location_display = order.pickup_location
            
            passenger_text = f"""
<b>{idx}-mijoz</b>
👤 <b>Ism:</b> {passenger_name}
📍 <b>Manzil:</b> {location_display}
📱 <b>Telefon:</b> {passenger_phone}
{order_type}
            """.strip()
            
            passengers_info.append(passenger_text)
        
        # Barcha ma'lumotlarni birlashtirish
        contact_text = f"📞 <b>Yo'lovchilar ma'lumotlari</b>\n\n" + chr(10).join(passengers_info)
        
        logger.info(f"Sending contact info to driver {driver.driver_id}: {len(passengers_info)} passengers")

        await message.answer(
            contact_text,
            parse_mode="HTML",
        )
        
        logger.success(f"✅ Contact info sent to driver {driver.driver_id}")
        
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR in contact_passenger_handler: {type(e).__name__}: {e}", exc_info=True)
        await message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring yoki /start bosing.",
            parse_mode="HTML"
        )
        raise  # Re-raise to let StateGuard handle it


@router.message(
    StateFilter("*"),  # Har qanday state'da tutib, keyin o'zimiz tekshiramiz
    F.text.in_(["❌ Buyurtmani bekor qilish", "Buyurtmani bekor qilish"])
)
@with_driver_session  # ✅ Decorator
async def cancel_order_handler(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi buyurtma(lar)ni bekor qiladi
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    # Barcha aktiv buyurtmalarni olish
    active_orders_result = await session.execute(
        select(Order)
        .options(selectinload(Order.passenger))
        .where(Order.driver_id == driver.driver_id)
        .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
        .order_by(Order.created_at)
    )
    active_orders = active_orders_result.scalars().all()
    
    if not active_orders:
        await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
        return
    
    # Agar bitta buyurtma bo'lsa, to'g'ridan-to'g'ri tasdiqlash so'rash
    if len(active_orders) == 1:
        order = active_orders[0]
        await state.update_data(cancel_order_id=order.order_id)
        await message.answer(
            "⚠️ <b>Buyurtmani bekor qilmoqchimisiz?</b>\n\n"
            "Bu jiddiy harakat! Agar bekor qilsangiz:\n"
            "• Komissiya qaytarilmaydi\n"
            "• Warning olasiz\n"
            "• 3 ta warning = 24 soat ban\n\n"
            "Davom ettirish uchun 'Tasdiqlash' yozing",
            parse_mode="HTML"
        )
        await state.set_state(DriverStates.confirming_cancellation)
    
    # Agar bir nechta bo'lsa, tanlashni ko'rsatish
    else:
        from app.bot.keyboards.driver import get_order_cancellation_keyboard
        await message.answer(
            "⚠️ <b>Qaysi buyurtmani bekor qilmoqchisiz?</b>\n\n"
            "Tanlang:",
            reply_markup=get_order_cancellation_keyboard(active_orders),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("cancel_order_select:"))
async def cancel_order_select_handler(callback: CallbackQuery, state: FSMContext):
    """Bekor qilish uchun buyurtma tanlandi"""
    order_id = parse_callback_data(callback.data, "cancel_order_select")
    if order_id is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    await state.update_data(cancel_order_id=order_id)
    
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "⚠️ <b>Buyurtmani bekor qilmoqchimisiz?</b>\n\n"
            "Bu jiddiy harakat! Agar bekor qilsangiz:\n"
            "• Komissiya qaytarilmaydi\n"
            "• Warning olasiz\n"
            "• 3 ta warning = 24 soat ban\n\n"
            "Davom ettirish uchun 'Tasdiqlash' yozing",
            parse_mode="HTML"
        )
    
    await state.set_state(DriverStates.confirming_cancellation)
    await callback.answer()


@router.callback_query(F.data == "cancel_all_orders")
@with_driver_session
async def cancel_all_orders_handler(callback: CallbackQuery, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Barcha aktiv buyurtmalarni bekor qilish

    NIMA BO'LADI:
    1. Barcha ACCEPTED/IN_PROGRESS buyurtmalar PENDING ga qaytadi
    2. Driver bo'shatiladi (is_on_trip=False, available_seats qaytadi)
    3. Har bir order uchun yangi haydovchi topish task ishga tushadi
    4. Yo'lovchilarga xabar yuboriladi
    """
    # Barcha aktiv buyurtmalarni olish
    active_orders_result = await session.execute(
        select(Order)
        .options(selectinload(Order.passenger).selectinload(Passenger.user))
        .where(Order.driver_id == driver.driver_id)
        .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
        .order_by(Order.created_at)
    )
    active_orders = active_orders_result.scalars().all()

    if not active_orders:
        await callback.answer("Aktiv buyurtmalar topilmadi", show_alert=True)
        return

    cancelled_count = 0
    total_passengers_returned = 0

    for order in active_orders:
        # Order'ni PENDING qilish (qayta match qilish uchun)
        await session.execute(
            update(Order)
            .where(Order.order_id == order.order_id)
            .values(
                status=OrderStatus.PENDING,
                cancellation_reason=None,
                cancelled_at=None,
                driver_id=None,
                accepted_at=None
            )
        )
        total_passengers_returned += order.passenger_count
        cancelled_count += 1
        
        # Remove redis skip keys
        await cleanup_skip_keys_for_order(order.order_id)

        # Yo'lovchiga xabar
        if order.passenger and order.passenger.user:
            from app.bot.main import bot
            try:
                await bot.send_message(
                    chat_id=order.passenger.user.user_id,
                    text=f"❌ <b>Buyurtma bekor qilindi</b>\n\n"
                         f"Haydovchi buyurtmani bekor qildi.\n"
                         f"Yangi haydovchi topilmoqda...",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to notify passenger for order {order.order_id}: {e}")

        # Yangi haydovchi topish
        find_driver_for_order_task.delay(order.order_id)  # type: ignore

    # Driver'ni bo'shatish
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

    # Xabarni yangilash
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"✅ <b>Barcha buyurtmalar bekor qilindi</b>\n\n"
            f"📦 Bekor qilingan: {cancelled_count} ta buyurtma\n"
            f"🔄 Har bir buyurtma uchun yangi haydovchi topilmoqda...",
            parse_mode="HTML"
        )

    await state.clear()

    # Asosiy menyuni yuborish
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "Asosiy menyu:",
            reply_markup=get_driver_main_menu()
        )

    logger.warning(
        f"Driver {driver.driver_id} cancelled ALL orders: "
        f"{cancelled_count} orders cancelled"
    )

    await callback.answer(f"{cancelled_count} ta buyurtma bekor qilindi")


@router.message(
    DriverStates.confirming_cancellation, 
    F.text.lower() == "tasdiqlash"
)
@with_driver_session  # ✅ Decorator
async def confirm_cancellation(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Bekor qilish tasdiqlandi
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    data = await state.get_data()
    order_id = data.get('cancel_order_id') or data.get('current_order_id')
    
    if not order_id:
        await message.answer(Messages.Error.ORDER_NOT_FOUND)
        await state.clear()
        return
    
    # Bekor qilish logikasi
    from sqlalchemy import update
    
    # Order'ni cancel qilish
    order_result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.passenger).selectinload(Passenger.user)
        )
        .where(Order.order_id == order_id)
    )
    order = order_result.scalar_one_or_none()
    
    if not order:
        await message.answer(Messages.Error.ORDER_BUT_DRIVER_MISMATCH)
        await state.clear()
        return
    
    if order.driver_id != driver.driver_id or order.status not in [OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]:
        await message.answer("⚠️ Bu buyurtmani bekor qilib bo'lmaydi (yakunlangan yoki noto'g'ri status)")
        await state.clear()
        return
    
    # Order'ni PENDING qilish (qayta match qilish uchun)
    await session.execute(
        update(Order)
        .where(Order.order_id == order_id)
        .values(
            status=OrderStatus.PENDING,
            cancellation_reason=None,
            cancelled_at=None,
            driver_id=None,
            accepted_at=None
        )
    )
    
    # Remove redis skip keys
    await cleanup_skip_keys_for_order(order_id)
    
    # Driver'ni bo'shatish
    await session.execute(
        update(Driver)
        .where(Driver.driver_id == driver.driver_id)
        .values(
            available_seats=Driver.available_seats + order.passenger_count,
            is_on_trip=False
        )
    )
    
    # Yo'lovchiga xabar
    if order.passenger and order.passenger.user:
        from app.bot.main import bot
        try:
            await bot.send_message(
                chat_id=order.passenger.user.user_id,
                text=f"❌ <b>Buyurtma bekor qilindi</b>\n\n"
                     f"Haydovchi buyurtmani bekor qildi.\n"
                     f"Yangi haydovchi topilmoqda...",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify passenger: {e}")
    
    # Yangi haydovchi topish
    find_driver_for_order_task.delay(order_id) # type: ignore
    
    await message.answer(
        Messages.Driver.ORDER_CANCELLED.format(order_id=order_id),
        parse_mode="HTML",
        reply_markup=get_driver_main_menu()
    )
    
    await state.clear()




@router.callback_query(F.data.startswith("reject_order:"))
@with_driver_session  # ✅ Decorator
async def reject_order_handler(callback: CallbackQuery, session: AsyncSession, driver: Driver):
    """
    Haydovchi buyurtmani rad etdi
    
    ✅ REFACTORED: Session va driver avtomatik
    """
    order_id = parse_callback_data(callback.data, "reject_order")
    if order_id is None:
        await callback.answer(Messages.Error.CALLBACK_DATA_MISSING)
        return
    
    # ❗ Bloklangan?
    if driver.is_blocked:
        await callback.answer(
            Messages.Driver.BLOCKED.format(reason="Bloklangansiz"),
            show_alert=True
        )
        return
    
    # Bugungi rad etishlar sonini Redis'dan olish
    from app.services.queue_service import driver_queue
    today_rejects = await driver_queue.get_driver_reject_count(driver.driver_id)
    
    # Kunlik limit tekshiruvi (config/settings dan)
    from config.settings import settings
    max_rejects = settings.MAX_DRIVER_REJECTS_PER_DAY
    
    if today_rejects >= max_rejects:
        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"⚠️ <b>Kunlik limit yetdi!</b>\n\n"
                f"Siz bugun {max_rejects} ta buyurtmani rad etdingiz.\n"
                f"Ertaga qayta urinib ko'ring.",
                parse_mode="HTML"
            )
        await callback.answer("Kunlik limit yetdi", show_alert=True)
        return
    
    # ✅ Unlock driver offer (rejected)
    await driver_queue.unlock_driver_offer(driver.driver_id)
    
    # 1. Rad etishni sanash va skip qilish
    await driver_queue.track_driver_reject(driver.driver_id)
    await driver_queue.skip_driver_for_order(driver.driver_id, order_id)
    
    # ✅ Clear inactivity counter (driver javob berdi)
    if driver.current_route_id:
        await driver_queue.clear_driver_inactivity(driver.driver_id, driver.current_route_id)
    
    # 2. Xabarni yangilash
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"❌ <b>Buyurtma rad etildi</b>\n\n"
            f"📊 Bugungi rad etishlar: {today_rejects + 1}/{max_rejects}\n\n"
            f"⏳ Yangi buyurtma kutyapsiz...",
            parse_mode="HTML"
        )
    
    # Keyingi haydovchini topish uchun orderni PENDING qilib re-queue qilish
    # MUHIM: Faqat PENDING holatdagi buyurtmani yangilaymiz (race condition'ni oldini olish uchun)
    result = await session.execute(
        update(Order)
        .where(Order.order_id == order_id)
        .where(Order.status == OrderStatus.PENDING)
        .values(
            driver_id=None,
            accepted_at=None
        )
    )
    
    if result.rowcount > 0:
        # Keyingi haydovchiga yuborish
        find_driver_for_order_task.delay(order_id) # type: ignore
        logger.info(f"Order {order_id} re-queued for matching after reject.")
    else:
        logger.warning(f"Order {order_id} was already accepted by another driver, skipping re-queue.")
    
    logger.info(
        f"Driver {driver.driver_id} rejected order {order_id}. "
        f"Today rejects: {today_rejects + 1}/{max_rejects}"
    )
    
    await callback.answer("Buyurtma rad etildi")


# ============================================
# SAFAR (TRIP) BEKOR QILISH
# ============================================

@router.message(
    StateFilter("*"),
    F.text.in_(["❌ Safarni bekor qilish", "Safarni bekor qilish"])
)
@with_driver_session
async def cancel_trip_handler(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Safar (trip) bekor qilish - tripdagi BARCHA buyurtmalarni bekor qiladi
    
    CRITICAL: Bu juda katta harakat!
    - Tripdagi barcha ACCEPTED buyurtmalar cancelled
    - Komissiyalar qaytariladi
    - Warning beriladi
    """
    # Aktiv trip olish
    from app.models.trip import get_active_trip_by_driver
    active_trip = await get_active_trip_by_driver(session, driver.driver_id)
    
    if not active_trip:
        await message.answer(
            "⚠️ Aktiv trip topilmadi.\n\n"
            "Avval buyurtma qabul qiling.",
            reply_markup=get_driver_main_menu()
        )
        return
    
    # Permission check
    from app.services.trip_service import can_cancel_trip
    check_result = await can_cancel_trip(active_trip.trip_id, driver.driver_id)
    
    if not check_result['can_cancel']:
        await message.answer(
            f"❌ {check_result['reason']}",
            reply_markup=get_trip_active_keyboard(active_trip.trip_id) if active_trip else get_driver_main_menu(),
            parse_mode="HTML"
        )
        return
    
    # Tasdiqlash so'rash
    await state.update_data(cancel_trip_id=active_trip.trip_id)
    await state.set_state(DriverStates.confirming_trip_cancellation)
    
    await message.answer(
        "⚠️ <b>SAFAR BEKOR QILISH</b>\n\n"
        f"🚗 Trip #{active_trip.trip_id}\n"
        f"👥 Buyurtmalar: {active_trip.passenger_count} ta\n\n"
        "<b>Bu jiddiy harakat!</b> Agar bekor qilsangiz:\n"
        "• BARCHA buyurtmalar cancelled\n"
        "• Komissiyalar qaytariladi\n"
        "• Warning olasiz\n"
        "• 3 ta warning = 24 soat ban\n\n"
        "Davom ettirish uchun 'Tasdiqlash' yozing",
        parse_mode="HTML"
    )


@router.message(
    DriverStates.confirming_trip_cancellation,
    F.text.lower() == "tasdiqlash"
)
@with_driver_session
async def confirm_trip_cancellation(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Trip bekor qilish tasdiqlandi
    """
    data = await state.get_data()
    trip_id = data.get('cancel_trip_id')
    
    if not trip_id:
        await message.answer("❌ Trip topilmadi")
        await state.clear()
        return
    
    # Trip'ni bekor qilish
    from app.services.trip_service import cancel_pending_orders_in_trip
    result = await cancel_pending_orders_in_trip(trip_id, driver.driver_id)
    
    if not result['success']:
        await message.answer(
            f"❌ {result['message']}",
            reply_markup=get_driver_main_menu(),
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    # Trip statusini o'zgartirish
    from app.models.trip import Trip, TripStatus
    
    await session.execute(
        update(Trip)
        .where(Trip.trip_id == trip_id)
        .values(
            status=TripStatus.CANCELLED,
            completed_at=func.now()
        )
    )
    
    # Driver'ni reset qilish
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
    
    await message.answer(
        f"✅ <b>Safar bekor qilindi</b>\n\n"
        f"🚗 Trip #{trip_id}\n"
        f"📊 {result.get('cancelled_count', 0)} ta buyurtma bekor qilindi\n"
        f"💰 Komissiyalar qaytarildi",
        reply_markup=get_driver_main_menu(),
        parse_mode="HTML"
    )
    
    await state.clear()
    
    logger.warning(f"Trip #{trip_id} cancelled by driver {driver.driver_id}")


__all__ = ['router']
