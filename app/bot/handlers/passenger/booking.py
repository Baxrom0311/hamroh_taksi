"""
app/bot/handlers/passenger/booking.py
"""
from ..base import *
from app.core.database import transaction
from app.models.route import get_route_by_id, get_all_active_routes
from app.models.order import Order, OrderStatus
from app.services.order_service import create_new_order
from app.bot.states.passenger import PassengerStates
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
    """
    Taksi chaqirishni boshlash
    ✅ REFACTORED + RATE LIMITED
    """
    # ✅ RATE LIMIT CHECK (3 orders per minute)
    from app.utils.rate_limiter import order_rate_limiter
    if not await order_rate_limiter.check_limit(
        user_id=message.from_user.id,  # type: ignore
        action="order_creation"
    ):
        await message.answer(
            "⏳ **Juda ko'p so'rov!**\n\n"
            "Siz 1 daqiqada 3 ta buyurtma bera olasiz.\n"
            "Iltimos, biroz kutib turing.",
            parse_mode="Markdown"
        )
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
@with_session
async def route_selected(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    route_id = parse_callback_data(callback.data, "select_route")
    if route_id is None:
        await callback.answer("❌ Marshrut ma'lumoti topilmadi", show_alert=True)
        return
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
    )
    await state.set_state(PassengerStates.location_description)
@router.message(PassengerStates.send_location)
async def location_required(message: Message, state: FSMContext):
    """Only accept shared location; text is rejected."""
    await message.answer(
        "📍 Iltimos, lokatsiyani yuboring (Share Location tugmasi). Matn qabul qilinmaydi.",
        reply_markup=get_passenger_location_keyboard()
    )
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
    count = parse_callback_data(callback.data, "passenger_count")
    if count is None:
        await callback.answer("❌ Ma'lumot topilmadi", show_alert=True)
        return
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
    """
    Buyurtmani yaratish
    ✅ IDEMPOTENCY: Takroriy button bosilishini oldini oladi
    """
    data = await state.get_data()
    user_id = message.chat.id
    # ✅ IDEMPOTENCY CHECK: Allaqachon order yaratilganmi?
    if data.get('order_created'):
        logger.warning(f"Duplicate order creation attempt by user {user_id}")
        await message.answer("✅ Buyurtma allaqachon yaratilgan!")
        return
    passenger = await get_passenger_by_user_id(session, user_id)
    # Location description bilan birlashtirish
    pickup_location = data['pickup_location']
    if data.get('location_description'):
        pickup_location = f"{pickup_location}\n 📝 {data['location_description']}"
    # ✅ Idempotency key yaratish (session uchun unique)
    import uuid
    idempotency_key = data.get('idempotency_key')
    if not idempotency_key:
        idempotency_key = str(uuid.uuid4())
        await state.update_data(idempotency_key=idempotency_key)
    # Buyurtma yaratish
    result = await create_new_order(
        passenger_id=passenger.passenger_id, # type: ignore
        route_id=data['route_id'],
        pickup_location=pickup_location,
        pickup_lat=data['pickup_lat'],
        pickup_lon=data['pickup_lon'],
        passenger_count=data['passenger_count'],
        has_luggage=data.get('has_luggage', False),
        luggage_count=data.get('luggage_count', 0),
        idempotency_key=idempotency_key  # ✅ Pass idempotency key
    )
    if result['success']:
        # ✅ ORDER CREATED flag set qilish
        await state.update_data(order_created=True)
        # Inline callback message cannot carry ReplyKeyboardMarkup, so split into edit + new message
        await message.edit_text(  # type: ignore
            Messages.Passenger.ORDER_CREATED.format(order_id=result['order_id']),
            parse_mode="HTML"
        )
        await message.answer(
            "🔝 Asosiy menyu:",
            reply_markup=get_passenger_main_menu()
        )
        # ✅ EXPLICIT COMMIT & TASK TRIGGER
        # Transaction commit qilinishi shart, shunda worker orderni ko'radi
        await session.commit()
        
        # Matching task'ni ishga tushirish
        find_driver_for_order_task.delay(result['order_id']) # type: ignore
        
        logger.success(f"Order created & matching started: {result['order_id']} with idempotency_key={idempotency_key}")
    else:
        # ✅ SECURITY FIX: Error sanitization
        from app.utils.error_sanitizer import sanitize_error_for_user
        
        safe_error = sanitize_error_for_user(
            str(result['message']),
            context='order_creation'
        )
        await message.answer(
            f"❌ {safe_error}",
            parse_mode="HTML"
        )
    await state.clear()


@router.callback_query(F.data.startswith("passenger_cancel:"))
@with_passenger_session
async def passenger_cancel_order(callback: CallbackQuery, session: AsyncSession, passenger: Passenger):
    """
    Yo'lovchi buyurtmani bekor qildi
    
    ✅ SECURITY FIX: Ownership validation qo'shildi
    """
    order_id = parse_callback_data(callback.data, "passenger_cancel")
    if order_id is None:
        return
    
    # Order'ni olish
    order = await get_order_or_error(session, order_id, callback)
    if not order:
        return
    
    # ✅ CRITICAL SECURITY FIX: Ownership validation
    # Faqat o'z buyurtmasini bekor qilishi mumkin!
    if order.passenger_id != passenger.passenger_id:
        await callback.answer(
            "❌ Bu sizning buyurtmangiz emas! Faqat o'z buyurtmalaringizni bekor qilishingiz mumkin.",
            show_alert=True
        )
        logger.warning(
            f"🚨 SECURITY: Passenger {passenger.passenger_id} (user {callback.from_user.id}) "
            f"tried to cancel order {order_id} belonging to passenger {order.passenger_id}"
        )
        return
    
    # Status tekshirish
    if order.status not in [OrderStatus.ACCEPTED, OrderStatus.PENDING]:
        await callback.answer("⚠️ Bu buyurtmani bekor qilib bo'lmaydi", show_alert=True)
        return
    
    # Order'ni bekor qilish - TRANSACTION
    try:
        async with transaction() as cancel_session:
            from app.models.driver import Driver
            from app.services.payment_service import payment_service
            
            # Komissiya haydovchiga qaytariladi (agar bor bo'lsa)
            if order.driver_id and order.commission_amount:
                await payment_service.refund_commission(
                    cancel_session,
                    driver_id=order.driver_id,
                    order_id=order.order_id,
                    amount=order.commission_amount,
                    reason="cancelled_by_passenger"
                )

            # ✅ ATOMIC UPDATE: Faqat PENDING yoki ACCEPTED bo'lsa bekor qilish
            result = await cancel_session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .where(Order.status.in_([OrderStatus.PENDING, OrderStatus.ACCEPTED]))
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='passenger_cancelled',
                    cancelled_at=func.now()
                )
            )
            
            if result.rowcount == 0:
                await callback.answer("⚠️ Buyurtma holati o'zgargan, bekor qilib bo'lmaydi.", show_alert=True)
                return
            
            # Driver'ni bo'shatish (max 6 seats)
            if order.driver_id:
                await cancel_session.execute(
                    update(Driver)
                    .where(Driver.driver_id == order.driver_id)
                    .values(
                        available_seats=func.least(
                            Driver.available_seats + order.passenger_count,
                            6  # Maximum seats
                        ),
                        is_on_trip=False
                    )
                )
        
        logger.info(f"✅ Order cancelled by passenger: order={order_id}, passenger={passenger.passenger_id}")
    
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")
        error_msg = str(e)[:100]  # Truncate to prevent MESSAGE_TOO_LONG
        await callback.answer(f"❌ Xatolik: {error_msg}", show_alert=True)
        return
    
    # Haydovchiga xabar
    if order.driver_id:
        from app.models.driver import get_driver_by_id
        driver = await get_driver_by_id(session, order.driver_id)
        if driver:
            from app.bot.main import bot
            from aiogram.exceptions import (
                TelegramForbiddenError,
                TelegramBadRequest
            )
            
            try:
                await bot.send_message(
                    chat_id=driver.user_id,
                    text=f"❌ <b>Buyurtma bekor qilindi</b>\n\n"
                         f"Yo'lovchi buyurtmani bekor qildi.",
                    parse_mode="HTML"
                )
            except (TelegramForbiddenError, TelegramBadRequest) as e:
                logger.warning(f"Cannot notify driver {driver.user_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to notify driver: {e}")
    
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "❌ <b>Buyurtma bekor qilindi</b>\n\n"
            "Yangi buyurtma berish uchun menyudan 'Taksi chaqirish'ni tanlang.",
            parse_mode="HTML"
        )
    
    await callback.answer("Buyurtma bekor qilindi")


__all__ = ['router']
