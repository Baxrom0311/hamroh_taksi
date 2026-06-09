"""
app/tasks/matching.py

DRIVER MATCHING CELERY TASKS

BU TASK'LAR NIMA QILADI:
1. Buyurtma uchun haydovchi topish
2. Haydovchiga xabar yuborish
3. Auto-confirm (2 daqiqadan keyin)
4. Queue management
"""

import asyncio
from typing import Optional, Any, cast
from loguru import logger
from sqlalchemy import select, update
from app.core.celery_app import async_to_sync # <--- import

from app.core.celery_app import celery_app
from app.core.database import get_session
from app.services.queue_service import driver_queue
from app.models.order import Order, get_order_by_id, OrderStatus
from app.models.driver import get_driver_by_id
from sqlalchemy.sql import func

# ============================================
# 1. HAYDOVCHI TOPISH
# ============================================

@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
@async_to_sync # <--- Dekoratorni shu tartibda qo'ying
async def find_driver_for_order_task(self, order_id: int):

    """
    Buyurtma uchun haydovchi topish
    
    RETRY LOGIC:
    - 30 soniya oralig'i bilan 5 marta retry
    - Har bir retry'da yangi haydovchilar qidiriladi
    - Max retry'dan keyin passenger'ga xabar yuboriladi va order cancel qilinadi
    """
    # Circular task prevention: find_driver → notify fail → find_driver loop ni cheklash
    from app.core.redis_client import redis_client
    cycle_key = f"find_driver_cycle:{order_id}"
    cycle_count = await redis_client.incr(cycle_key)
    if cycle_count == 1:
        await redis_client.expire(cycle_key, 600)  # 10 daqiqa TTL

    MAX_CYCLES = 10  # find_driver qayta chaqirilishi limiti
    if cycle_count > MAX_CYCLES:
        logger.error(
            f"Order {order_id}: find_driver cycle limit reached ({cycle_count}). "
            f"Cancelling order to prevent infinite loop."
        )
        cast(Any, notify_passenger_no_driver_task).delay(order_id)
        return {'success': False, 'reason': 'cycle_limit_reached'}

    async with get_session() as session:
        # Order'ni olish
        order = await get_order_by_id(session, order_id)

        if not order:
            logger.error(f"Order {order_id} not found")
            return {'success': False, 'error': 'Order not found'}

        # Agar allaqachon qabul qilingan bo'lsa
        if order.status != OrderStatus.PENDING:
            logger.info(f"Order {order_id} already accepted (status: {order.status})")
            return {'success': True, 'reason': 'already_accepted'}
        
        # Lokatsiya aniq berilganmi? (Inline location "Lat:" bilan boshlanadi)
        pickup_location_text = (order.pickup_location or "").strip().lower()
        enforce_distance = pickup_location_text.startswith("lat:")

        # Eng yaxshi haydovchini topish (Loop bilan - lock uchun)
        passenger_location = None
        if order.pickup_lat and order.pickup_lon:
            passenger_location = {
                'lat': float(order.pickup_lat),
                'lon': float(order.pickup_lon)
            }
            
        driver_id = None
        
        # Try finding a driver (Retry count = 3 times internally to handle race condition)
        for _ in range(3):
            candidate_id = await driver_queue.get_next_driver(
                route_id=order.route_id,
                passenger_location=passenger_location,
                passenger_count=order.passenger_count,
                max_distance_km=50,
                order_id=order_id,
                enforce_distance=enforce_distance and passenger_location is not None
            )
            
            if not candidate_id:
                break
                
            # ✅ TOPILDI - Try to atomic lock
            locked = await driver_queue.lock_driver_for_offer(candidate_id, order_id)

            if locked:
                try:
                    # ✅ FIX: Atomic status guard — faqat PENDING order'ga driver tayinlash
                    result = await session.execute(
                        update(Order)
                        .where(Order.order_id == order_id)
                        .where(Order.status == OrderStatus.PENDING)
                        .values(driver_id=candidate_id)
                    )
                    if result.rowcount == 0:
                        # Order allaqachon qabul qilingan (race condition)
                        await driver_queue.unlock_driver_offer(candidate_id)
                        logger.warning(f"Order {order_id} no longer PENDING, releasing driver {candidate_id}")
                        return {'success': False, 'reason': 'order_status_changed'}
                    # ✅ FIX: session.commit() — o'zgarishni saqlash!
                    await session.commit()
                    driver_id = candidate_id
                    break
                except Exception as e:
                    await session.rollback()
                    await driver_queue.unlock_driver_offer(candidate_id)
                    logger.error(f"DB update failed after locking driver {candidate_id}: {e}")
                    raise
            else:
                logger.warning(f"Driver {candidate_id} was grabbed by another process. Retrying match...")
                # Continue loop to find next driver
                continue

        if driver_id:
            # ✅ Haydovchi topildi!
            logger.success(f"✅ Driver {driver_id} found for order {order_id}")
            
            # Haydovchiga xabar yuborish
            notify_driver_new_order_task.delay(driver_id, order_id) # type: ignore
            
            return {
                'success': True,
                'driver_id': driver_id,
                'order_id': order_id
            }
        
        else:
            # ❌ Haydovchi topilmadi
            current_attempt = self.request.retries + 1
            
            # Max retry'dan keyin graceful handling
            if current_attempt >= self.max_retries:
                logger.info(
                    f"No driver found for order {order_id} after {current_attempt} attempts. "
                    f"Notifying passenger and cancelling order."
                )
                
                # Passenger'ga xabar yuborish va order'ni cancel qilish
                cast(Any, notify_passenger_no_driver_task).delay(order_id)
                
                return {
                    'success': False,
                    'reason': 'no_driver_available',
                    'attempts': current_attempt
                }
            
            # Retry
            logger.info(
                f"No driver found for order {order_id} "
                f"(attempt {current_attempt}/{self.max_retries}). Retrying in 30s..."
            )
            
            # Retry after delay
            from app.models.system_settings import get_setting_int
            from config.settings import settings
            
            retry_delay = await get_setting_int(
                session, 
                "driver_matching_retry_delay_seconds", 
                default=settings.DRIVER_MATCHING_RETRY_DELAY_SECONDS
            )
            raise self.retry(countdown=retry_delay)


# ============================================
# 2. HAYDOVCHIGA XABAR YUBORISH
# ============================================
@celery_app.task(bind=True, max_retries=3, name="app.tasks.matching.notify_driver_new_order_task")
@async_to_sync
async def notify_driver_new_order_task(self, driver_id: int, order_id: int):
    """
    Haydovchiga yangi buyurtma xabari (Senior level version)
    """
    from app.bot.main import bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.enums import ParseMode
    from config.settings import settings
    from app.bot.messages import Messages
    
    # 1. Ma'lumotlarni yig'ish (Sessiya faqat shu yerda kerak)
    order_data = None
    driver_tg_id = None
    
    async with get_session() as session:
        from sqlalchemy.orm import selectinload
        from app.models.passenger import Passenger
        
        # Order'ni passenger ma'lumotlari bilan yuklash
        order_result = await session.execute(
            select(Order)
            .options(selectinload(Order.passenger).selectinload(Passenger.user))
            .where(Order.order_id == order_id)
        )
        order = order_result.scalar_one_or_none()
        
        driver = await get_driver_by_id(session, driver_id)
        
        if not order or not driver:
            logger.warning(f"Order {order_id} or Driver {driver_id} not found in DB")
            return {'success': False, 'reason': 'not_found'}
        
        # Kerakli ma'lumotlarni lokal o'zgaruvchilarga olamiz
        driver_tg_id = driver.user_id
        
        # Passenger ma'lumotlari
        passenger = order.passenger
        passenger_name = passenger.full_name if passenger else "Noma'lum"
        passenger_phone = passenger.user.phone_number if passenger and passenger.user else "N/A"
        passenger_gender = "Erkak" if passenger and passenger.gender == "MALE" else "Ayol" if passenger and passenger.gender == "FEMALE" else "Noma'lum"
        
        order_data = {
            "pickup": order.pickup_location,
            "passengers": order.passenger_count,
            "luggage": f"Ha ({order.luggage_count})" if order.has_luggage else "Yo'q",
            "type_text": order.type_text,
            "passenger_name": passenger_name,
            "passenger_phone": passenger_phone,
            "passenger_gender": passenger_gender,
            "pickup_lat": float(order.pickup_lat) if order.pickup_lat else None,
            "pickup_lon": float(order.pickup_lon) if order.pickup_lon else None,
        }
        order_route_id = order.route_id
        
        # Dynamic settings fetch
        from app.models.system_settings import get_setting_int
        auto_reject_seconds = await get_setting_int(
            session,
            "auto_reject_order_seconds",
            default=settings.AUTO_REJECT_ORDER_SECONDS
        )


    # 2. Telegramga xabar yuborish (Sessiyadan TASHQARIDA)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_order:{order_id}", style="success")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_order:{order_id}", style="danger")]
    ])
    
    # Buyurtma turi
    order_type_text = order_data['type_text']

    
    # Lokatsiya linklari - conditional
    location_links_html = ""
    
    if order_data['pickup_lat'] and order_data['pickup_lon']:
        # ✅ GPS bor - linklar ko'rsatish
        from app.utils.location_helpers import get_google_maps_link, get_telegram_location_link
        
        pickup_lat = order_data['pickup_lat']
        pickup_lon = order_data['pickup_lon']
        
        google_maps_link = get_google_maps_link(pickup_lat, pickup_lon, order_data['pickup'])
        telegram_location_link = get_telegram_location_link(pickup_lat, pickup_lon)
        
        if google_maps_link and telegram_location_link:
            location_links_html = f'<a href="{google_maps_link}">🗺️ Google Maps</a> | <a href="{telegram_location_link}">📍 Telegram xarita</a>'
    else:
        # ❌ GPS yo'q - faqat matn
        location_links_html = "⚠️ <i>GPS yo'q - matn manzil</i>"
    
    message_text = f"""
🔔 <b>Yangi buyurtma!</b>

📍 <b>Olish joyi:</b> {order_data['pickup']}
{location_links_html}
{order_type_text}
📱 <b>Telefon:</b> {order_data['passenger_phone']}

💰 <b>Komissiya:</b> {settings.COMMISSION_AMOUNT:,} so'm

⏰ <b>2 daqiqa</b> ichida javob bering!
    """
    
    try:
        # Navbat xabarini tozalash (navbat keldi)
        await _clear_queue_message_for_driver(driver_id, order_route_id)

        # Quvnoq sticker + navbat keldi xabari
        sticker_id = getattr(settings, "QUEUE_TURN_STICKER_ID", "") or ""
        if sticker_id:
            try:
                await bot.send_sticker(
                    chat_id=driver_tg_id,
                    sticker=sticker_id
                )
            except Exception as e:
                logger.debug(f"Failed to send queue sticker to driver {driver_id}: {e}")

        try:
            await bot.send_message(
                chat_id=driver_tg_id,
                text=Messages.Driver.QUEUE_TURN,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.debug(f"Failed to send queue turn message to driver {driver_id}: {e}")

        await bot.send_message(
            chat_id=driver_tg_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"✅ Notification sent to driver telegram_id={driver_tg_id}")
        
        # 3. Taymerni rejalashtirish
        from app.tasks.matching import auto_reject_order_task
        # ✅ CONSTANTS: Auto-reject timer from settings
        from config.settings import settings
        cast(Any, auto_reject_order_task).apply_async(
            args=[driver_id, order_id], 
            countdown=auto_reject_seconds
        )
        
        return {'success': True}
        
    except Exception as e:
        # 4. Retry mantiqi (Sessiyadan TASHQARIDA - to'g'ri yo'li shu)
        error_msg = str(e).lower()
        if 'blocked' in error_msg or 'chat not found' in error_msg:
            logger.error(f"Cannot notify driver {driver_id}: Bot blocked or user not found")
            # Lockni bo'shatib, orderni qayta matching ga yuborish
            await driver_queue.unlock_driver_offer(driver_id)
            async with get_session() as recovery_session:
                await recovery_session.execute(
                    update(Order)
                    .where(Order.order_id == order_id)
                    .where(Order.driver_id == driver_id)
                    .values(driver_id=None)
                )
            cast(Any, find_driver_for_order_task).delay(order_id)
            return {'success': False, 'reason': 'forbidden'}

        logger.warning(f"Retry sending notification to {driver_id}: {e}")
        try:
            raise self.retry(exc=e, countdown=5)
        except self.MaxRetriesExceededError:
            # Max retry tugadi — lockni bo'shatib, qayta matching
            logger.error(f"Max retries exhausted for notifying driver {driver_id} about order {order_id}")
            await driver_queue.unlock_driver_offer(driver_id)
            async with get_session() as recovery_session:
                await recovery_session.execute(
                    update(Order)
                    .where(Order.order_id == order_id)
                    .where(Order.driver_id == driver_id)
                    .values(driver_id=None)
                )
            cast(Any, find_driver_for_order_task).delay(order_id)
            return {'success': False, 'reason': 'max_retries_exhausted'}


# ============================================
# 3. AVTOMATIK RAD ETISH (2 daqiqa javob yo'q)
# ============================================

@celery_app.task(name="app.tasks.matching.auto_reject_order_task", bind=True, max_retries=3)
@async_to_sync
async def auto_reject_order_task(self, driver_id: int, order_id: int):
    """
    Haydovchi 2 daqiqa ichida javob bermasa.
    
    2-STRIKE RULE:
    - 1-marta: counter oshadi, keyingi driver izlanadi
    - 2-marta: navbatdan chiqariladi, xabar yuboriladi
    """
    async with get_session() as session:
        order = await get_order_by_id(session, order_id)

        if not order:
            logger.warning(f"auto_reject_order_task: Order {order_id} not found (may be deleted)")
            return

        if order.status != OrderStatus.PENDING:
            logger.info(
                f"auto_reject_order_task: Order {order_id} already processed "
                f"(status={order.status.value}), skipping auto-reject"
            )
            # Driver lockini tozalash
            await driver_queue.unlock_driver_offer(driver_id)
            return

        if order.status == OrderStatus.PENDING:
            # 1. Inactivity count'ni oshirish
            inactivity_count = await driver_queue.track_driver_inactivity(
                driver_id, order.route_id
            )
            
            # Threshold'ni olish (Start dynamic setting)
            from app.models.system_settings import get_setting_int
            from config.settings import settings
            
            threshold = await get_setting_int(
                session, 
                "driver_inactivity_threshold", 
                default=settings.DRIVER_INACTIVITY_THRESHOLD
            )
            
            logger.warning(
                f"Driver {driver_id} didn't respond to order {order_id} "
                f"(inactivity: {inactivity_count}/{threshold})"
            )
            
            # 2. Agar threshold ga yetgan bo'lsa - navbatdan chiqarish
            if inactivity_count >= threshold:
                await driver_queue.remove_driver(driver_id, order.route_id)
                logger.warning(f"🚨 Driver {driver_id} removed from queue ({threshold} strikes)")
                
                # Driver'ga xabar yuborish
                driver = await get_driver_by_id(session, driver_id)
                if driver:
                    from app.bot.main import bot
                    try:
                        await bot.send_message(
                            chat_id=driver.user_id,
                            text="⚠️ <b>Navbatdan chiqarildingiz</b>\n\n"
                                 f"Sabab: {threshold} marta buyurtmaga javob bermagansiz.\n\n"
                                 "Qayta navbatga qo'shilish uchun '🚗 Buyurtma qabul qilish' bosing.",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify driver {driver_id}: {e}")
            
            # 3. Bu buyurtma uchun skip qilish
            await driver_queue.skip_driver_for_order(driver_id, order_id)
            
            # ✅ FIX: Driver offer lock'ni bo'shatish (boshqa orderlarga match bo'lishi uchun)
            await driver_queue.unlock_driver_offer(driver_id)
            
            # 4. Keyingi haydovchini qidirish
            cast(Any, find_driver_for_order_task).delay(order_id)
    

@celery_app.task(name="app.tasks.matching.auto_confirm_trip_task")
@async_to_sync
async def auto_confirm_trip_task(order_id: int):
    """
    30 daqiqa ichida yo'lovchi "Ketdik" yoki bekor qilmagan bo'lsa,
    sessiya yopiladi va buyurtma bekor qilinadi.
    """
    from sqlalchemy import update, select
    from app.models.order import Order, OrderStatus
    from app.models.driver import Driver
    from app.models.passenger import Passenger
    from sqlalchemy.orm import selectinload
    
    async with get_session() as session:
        order_result = await session.execute(
            select(Order)
            .options(selectinload(Order.passenger).selectinload(Passenger.user))
            .where(Order.order_id == order_id)
        )
        order = order_result.scalar_one_or_none()
        
        # Agar order hali ham ACCEPTED holatda bo'lsa (ya'ni IN_PROGRESS bo'lmagan)
        # va 30 daqiqa o'tgan bo'lsa, sessiya yopiladi
        if order and order.status == OrderStatus.ACCEPTED:
            logger.warning(f"Order {order_id} timeout after 30 minutes - cancelling")
            
            # Order'ni bekor qilish
            await session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='timeout_30_minutes',
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
                driver_result = await session.execute(
                    select(Driver).where(Driver.driver_id == order.driver_id)
                )
                driver = driver_result.scalar_one_or_none()
                if driver:
                    from app.bot.main import bot
                    try:
                        await bot.send_message(
                            chat_id=driver.user_id,
                            text=f"⏱ <b>Vaqt tugadi</b>\n\n"
                                 f"30 daqiqa ichida yo'lovchi javob bermadi.\n"
                                 f"Buyurtma bekor qilindi.",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify driver: {e}")
            
            # Yo'lovchiga xabar
            if order.passenger and order.passenger.user:
                from app.bot.main import bot
                try:
                    await bot.send_message(
                        chat_id=order.passenger.user.user_id,
                        text=f"⏱ <b>Vaqt tugadi</b>\n\n"
                             f"30 daqiqa ichida javob berilmadi.\n"
                             f"Buyurtma bekor qilindi.\n\n"
                             f"Yangi buyurtma berish uchun menyudan 'Taksi chaqirish'ni tanlang.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify passenger: {e}")
            
            await session.commit()
            logger.info(f"Order {order_id} cancelled due to 30 minute timeout")


# ============================================
# 6. AVTOMATIK SAFAR YAKUNLASH (10 daqiqa)
# ============================================

@celery_app.task(
    bind=True,
    name="app.tasks.matching.auto_complete_trip_task",
    max_retries=3,  # ✅ NEW: Max 3 marta retry
    default_retry_delay=600  # ✅ NEW: 1 daqiqa oraliqda
)
@async_to_sync
async def auto_complete_trip_task(self, target_id: int):
    """
    "Ketdik" bosilgandan keyin 10 daqiqa o'tsa safarni avtomatik yakunlash.
    
    target_id:
        - trip_id (Trip bo'lsa) → tripdagi IN_PROGRESS orderlarning barchasini yakunlash
        - order_id (Order bo'lsa) → faqat shu orderni yakunlash
    """
    from sqlalchemy import select
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.models.order import Order, OrderStatus
    from app.models.trip import Trip, TripStatus
    from app.models.driver import Driver
    from app.models.passenger import Passenger
    from sqlalchemy.orm import selectinload
    from app.services.order_service import complete_trip
    from app.bot.main import bot

    async with get_session() as session:
        # Avval trip sifatida qidiramiz
        trip_result = await session.execute(
            select(Trip)
            .options(
                selectinload(Trip.orders)
                .options(selectinload(Order.passenger).selectinload(Passenger.user))
            )
            .where(Trip.trip_id == target_id)
        )
        trip = trip_result.scalar_one_or_none()

        orders_to_complete: list[Order] = []

        if trip and trip.status == TripStatus.ACTIVE:
            orders_to_complete = [
                o for o in trip.orders if o.status == OrderStatus.IN_PROGRESS
            ]
            logger.info(f"Auto-completing trip #{trip.trip_id} with {len(orders_to_complete)} orders")
        else:
            # Trip topilmasa, target_id ni order_id deb qaraymiz
            order_result = await session.execute(
                select(Order)
                .options(selectinload(Order.passenger).selectinload(Passenger.user))
                .where(Order.order_id == target_id)
            )
            order = order_result.scalar_one_or_none()
            if order and order.status == OrderStatus.IN_PROGRESS:
                orders_to_complete = [order]
                logger.info(f"Auto-completing single order #{target_id}")

        if not orders_to_complete:
            logger.info(f"Auto-complete skipped: nothing to complete for id={target_id}")
            return

        # Yakunlash va xabar berish
        driver_id: Optional[int] = None
        for order in orders_to_complete:
            driver_id = order.driver_id
            if not driver_id:
                continue

            result = await complete_trip(order.order_id, driver_id)
            if not result.get('success'):
                msg = result.get('message', '')
                # Agar order allaqachon manual yakunlangan bo'lsa — xato emas, skip
                if 'noto\'g\'ri' in msg.lower() or 'status' in msg.lower() or 'IN_PROGRESS' in msg:
                    logger.info(f"Auto-complete skipped for order {order.order_id}: already completed manually")
                else:
                    logger.error(f"Failed to auto-complete order {order.order_id}: {msg}")
                continue

            # Haydovchiga xabar
            driver_result = await session.execute(
                select(Driver).where(Driver.driver_id == driver_id)
            )
            driver = driver_result.scalar_one_or_none()
            if driver:
                try:
                    await bot.send_message(
                        chat_id=driver.user_id,
                        text=(
                            f"✅ <b>Safar avtomatik yakunlandi</b>\n\n"
                            f"⏱ Davomiyligi: {result.get('duration_minutes', 10)} daqiqa\n\n"
                            f"✨ Rahmat!"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify driver: {e}")

            # Yo'lovchiga baho so'rash
            if order.passenger and order.passenger.user:
                rating_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="⭐️ 1", callback_data=f"rate_driver:{order.order_id}:1"),
                        InlineKeyboardButton(text="⭐️ 2", callback_data=f"rate_driver:{order.order_id}:2"),
                        InlineKeyboardButton(text="⭐️ 3", callback_data=f"rate_driver:{order.order_id}:3"),
                    ],
                    [
                        InlineKeyboardButton(text="⭐️ 4", callback_data=f"rate_driver:{order.order_id}:4"),
                        InlineKeyboardButton(text="⭐️ 5", callback_data=f"rate_driver:{order.order_id}:5"),
                    ]
                ])
                try:
                    await bot.send_message(
                        chat_id=order.passenger.user.user_id,
                        text=(
                            f"✅ <b>Safar yakunlandi (avtomatik)</b>\n\n"
                            f"⏱ Davomiyligi: {result.get('duration_minutes', 10)} daqiqa\n\n"
                            f"✨ <b>Haydovchiga baho bering:</b>"
                        ),
                        parse_mode="HTML",
                        reply_markup=rating_kb
                    )
                except Exception as e:
                    logger.error(f"Failed to notify passenger: {e}")

        # Agar trip ishlovdan o'tgan bo'lsa, statusni COMPLETED ga o'zgartiramiz
        if trip and trip.status == TripStatus.ACTIVE:
            try:
                await session.execute(
                    update(Trip)
                    .where(Trip.trip_id == trip.trip_id)
                    .values(
                        status=TripStatus.COMPLETED,
                        completed_at=func.now()
                    )
                )
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to update trip status: {e}")
                # ✅ NEW: Retry on database errors
                if hasattr(self, 'retry'):
                    # Retry with delay
                    from app.models.system_settings import get_setting_int
                    from config.settings import settings
                    
                    retry_delay = await get_setting_int(
                        session, 
                        "task_retry_delay_seconds", 
                        default=settings.TASK_RETRY_DELAY_SECONDS
                    )
                    raise self.retry(exc=e, countdown=retry_delay)

        if driver_id:
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .values(is_on_trip=False, is_active=False)
            )
            await session.commit()



# ============================================
# 4. YO'LOVCHIGA "HAYDOVCHI TOPILMADI" XABARI
# ============================================

@celery_app.task
@async_to_sync
async def notify_passenger_no_driver_task(order_id: int):
    """
    Yo'lovchiga haydovchi topilmaganini bildirish
    """

    from app.bot.main import bot
    from aiogram.enums import ParseMode
    from sqlalchemy.orm import selectinload
    from app.models.passenger import Passenger
    
    async with get_session() as session:
        # Order'ni passenger va user ma'lumotlari bilan yuklash
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.passenger).selectinload(Passenger.user))
            .where(Order.order_id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            logger.warning(f"Order {order_id} not found for no driver notification")
            return
        
        # Agar allaqachon qabul qilingan bo'lsa, xabar yubormaymiz
        if order.status != OrderStatus.PENDING:
            logger.info(f"Order {order_id} already processed (status: {order.status}), skipping notification")
            return
        
        message = """
😔 <b>Taksi topilmadi</b>

Hozirda bu yo'nalish bo'yicha bo'sh haydovchilar yo'q.

Iltimos:
- 10-15 daqiqadan keyin qayta urinib ko'ring
- Yoki boshqa marshrut tanlang

Noqulaylik uchun uzr so'raymiz!
        """
        
        try:
            # Passenger'ning user_id'sini olish
            if order.passenger and order.passenger.user:
                passenger_user_id = order.passenger.user.user_id
                
                await bot.send_message(
                    chat_id=passenger_user_id,
                    text=message,
                    parse_mode=ParseMode.HTML
                )
                
                logger.info(f"Notified passenger {passenger_user_id} about no driver for order {order_id}")
            else:
                logger.warning(f"Passenger or user not found for order {order_id}")
            
            # Order'ni cancel qilish — ✅ FIX: status guard (TOCTOU prevention)
            from sqlalchemy import update
            
            result = await session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .where(Order.status == OrderStatus.PENDING)  # ✅ Atomic status check
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='no_driver_available',
                    cancelled_at=func.now()
                )
            )
            
            if result.rowcount > 0:
                await session.commit()
                logger.info(f"Order {order_id} cancelled due to no driver available")
            else:
                logger.info(f"Order {order_id} was already accepted/processed, skipping cancel")
        
        except Exception as e:
            logger.error(f"Failed to notify passenger or cancel order: {e}")
    
    

# ============================================
# 5. HAYDOVCHINI NAVBATGA QO'SHISH
# ============================================

@celery_app.task
@async_to_sync
async def add_driver_to_queue_task(driver_id: int, route_id: int):
    """
    Haydovchini navbatga qo'shish (background)
    """
    
    result = await driver_queue.add_driver(driver_id, route_id)
    if result['success']:
        logger.info(
            f"Driver {driver_id} added to queue: "
            f"route={route_id}, position={result['position']}"
        )
        await _notify_queue_positions(route_id)
    
    return result


# ============================================
# 6. HAYDOVCHINI NAVBATDAN O'CHIRISH
# ============================================

@celery_app.task
@async_to_sync
async def remove_driver_from_queue_task(driver_id: int, route_id: Optional[int] = None):
    """
    Haydovchini navbatdan o'chirish
    
    Args:
        driver_id: Driver ID
        route_id: Route ID (None bo'lsa barcha route'lardan)
    """

    if route_id:
        # Faqat bitta route'dan
        await driver_queue.remove_driver(driver_id, route_id)
        await _clear_queue_message_for_driver(driver_id, route_id)
        await _notify_queue_positions(route_id)
    else:
        # Barcha route'lardan (driver deactivate bo'lganda)
        from app.core.redis_client import redis_client
        
        # Barcha driver_queue:* key'larni topish
        route_ids: list[int] = []
        async for key in redis_client.client.scan_iter(match="driver_queue:*"):
            await redis_client.client.zrem(key, str(driver_id))
            try:
                route_ids.append(int(str(key).split(":")[1]))
            except Exception:
                continue
        
        # Join time'larni tozalash
        async for key in redis_client.client.scan_iter(match=f"driver_join_time:{driver_id}:*"):
            await redis_client.delete(key)

        for rid in set(route_ids):
            await _clear_queue_message_for_driver(driver_id, rid)
            await _notify_queue_positions(rid)
    
    logger.info(f"Driver {driver_id} removed from queue")


# ============================================
# QUEUE POSITION NOTIFICATIONS
# ============================================

QUEUE_MESSAGE_TTL_SECONDS = 86400  # 24 soat


def _queue_message_key(driver_id: int, route_id: int) -> str:
    return f"driver_queue_msg:{driver_id}:{route_id}"


async def _clear_queue_message_for_driver(driver_id: int, route_id: int) -> None:
    """
    Haydovchining navbat xabarini o'chirish
    """
    try:

        from app.core.redis_client import redis_client
        from app.core.database import get_session
        from app.models.driver import Driver
        from app.bot.main import bot

        key = _queue_message_key(driver_id, route_id)
        prev = await redis_client.get(key)
        if not prev or not isinstance(prev, dict) or "message_id" not in prev:
            return

        async with get_session() as session:
            result = await session.execute(
                select(Driver.user_id).where(Driver.driver_id == driver_id)
            )
            user_id = result.scalar_one_or_none()

        if not user_id:
            return

        try:
            await bot.delete_message(
                chat_id=user_id,
                message_id=prev["message_id"]
            )
        except Exception:
            pass

        await redis_client.delete(key)
    except Exception as e:
        logger.debug(f"Queue message cleanup failed: {e}")


async def _notify_queue_positions(route_id: int) -> None:
    """
    Navbatdagi haydovchilarga pozitsiyalarini yuborish (xabarni yangilab turish)
    """
    try:

        from app.core.redis_client import redis_client
        from app.core.database import get_session
        from app.models.driver import Driver
        from app.models.route import get_route_by_id
        from app.bot.main import bot
        from app.bot.messages import Messages

        driver_ids = await driver_queue.get_queue_driver_ids(route_id)
        if not driver_ids:
            return

        async with get_session() as session:
            route = await get_route_by_id(session, route_id)
            route_name = route.route_name if route else "Noma'lum"

            result = await session.execute(
                select(Driver.driver_id, Driver.user_id)
                .where(Driver.driver_id.in_(driver_ids))
            )
            rows = result.all()

        user_map = {int(did): uid for did, uid in rows if uid}
        total = len(driver_ids)

        for idx, driver_id in enumerate(driver_ids, start=1):
            user_id = user_map.get(driver_id)
            if not user_id:
                continue

            key = _queue_message_key(driver_id, route_id)
            prev = await redis_client.get(key)
            if isinstance(prev, dict) and "message_id" in prev:
                try:
                    await bot.delete_message(
                        chat_id=user_id,
                        message_id=prev["message_id"]
                    )
                except Exception:
                    pass

            if idx == 1:
                # 1-o'rin uchun maxsus xabar
                text = (
                    f"{Messages.Driver.QUEUE_TURN}\n\n"
                    f"📍 Marshrut: <b>{route_name}</b>\n"
                    f"🔢 Sizning navbatingiz: <b>1</b>\n\n"
                    f"✅ Teyyor turing, keyingi buyurtma sizniki!"
                )
            else:
                text = Messages.Driver.QUEUE_POSITION.format(
                    position=idx,
                    total=total,
                    route_name=route_name
                )

            try:
                sent = await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML"
                )
                await redis_client.set(
                    key,
                    {"message_id": sent.message_id},
                    ex=QUEUE_MESSAGE_TTL_SECONDS
                )
            except Exception as e:
                logger.warning(f"Failed to notify driver {driver_id} queue position: {e}")

    except Exception as e:
        logger.debug(f"Queue notify failed: {e}")


@celery_app.task(name="app.tasks.matching.notify_queue_update_task")
@async_to_sync
async def notify_queue_update_task(route_id: int):
    await _notify_queue_positions(route_id)


@celery_app.task(name="app.tasks.matching.clear_queue_message_task")
@async_to_sync
async def clear_queue_message_task(driver_id: int, route_id: int):
    await _clear_queue_message_for_driver(driver_id, route_id)


# ============================================
# AUTO-START TRIP (DELAYED)
# ============================================

@celery_app.task(bind=True)
@async_to_sync
async def auto_start_trip_task(self, trip_id: int, driver_id: int):
    """
    O'rinlar to'lganda tripni avtomatik boshlash (delayed)
    
    Bu task countdown bilan chaqiriladi:
    - Default: 180 soniya (3 daqiqa)
    - Admin paneldan o'zgartiriladi
    """
    from app.services.order_service import _start_trip_sync
    
    logger.info(f"Auto-starting trip {trip_id} for driver {driver_id} (delayed)")
    
    # Unlock driver
    await driver_queue.unlock_driver_offer(driver_id)

    async with get_session() as session:
        try:
            await _start_trip_sync(session, trip_id, driver_id)
            await session.commit()
            logger.success(f"✅ Trip {trip_id} auto-started successfully")
        except Exception as e:
            logger.error(f"❌ Failed to auto-start trip {trip_id}: {e}")
            raise


__all__ = [
    'auto_complete_trip_task',
    'find_driver_for_order_task',
    'notify_driver_new_order_task',
    'auto_reject_order_task',
    'notify_passenger_no_driver_task',
    'add_driver_to_queue_task',
    'remove_driver_from_queue_task',
    'notify_queue_update_task',
    'clear_queue_message_task',
    'auto_start_trip_task'  # NEW
]
