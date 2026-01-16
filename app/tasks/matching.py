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
from typing import Optional
from loguru import logger
from sqlalchemy import select
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
        
        # Eng yaxshi haydovchini topish
        driver_id = await driver_queue.get_next_driver(
            route_id=order.route_id,
            passenger_location={
                'lat': float(order.pickup_lat),
                'lon': float(order.pickup_lon)
            },
            passenger_count=order.passenger_count,
            max_distance_km=50
        )
        
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
                notify_passenger_no_driver_task.delay(order_id)
                
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
            
            raise self.retry(countdown=30)


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
            "passenger_gender": passenger_gender
        }


    # 2. Telegramga xabar yuborish (Sessiyadan TASHQARIDA)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_order:{order_id}")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_order:{order_id}")]
    ])
    
    # Buyurtma turi
    order_type_text = order_data['type_text']

    
    # Lokatsiya linklari
    from app.utils.location_helpers import get_google_maps_link, get_telegram_location_link
    
    pickup_lat = order.pickup_lat
    pickup_lon = order.pickup_lon
    
    google_maps_link = get_google_maps_link(pickup_lat, pickup_lon, order_data['pickup'])
    telegram_location_link = get_telegram_location_link(pickup_lat, pickup_lon)
    
    message_text = f"""
🔔 <b>Yangi buyurtma!</b>

📦 Buyurtma #{order_id}
📍 <b>Olish joyi:</b> {order_data['pickup']}
<a href="{google_maps_link}">🗺️ Google Maps</a> | <a href="{telegram_location_link}">📍 Telegram xarita</a>
{order_type_text}
📱 <b>Telefon:</b> <code>{order_data['passenger_phone']}</code>

💰 <b>Komissiya:</b> {settings.COMMISSION_AMOUNT:,} so'm

⏰ <b>2 daqiqa</b> ichida javob bering!
    """
    
    try:
        await bot.send_message(
            chat_id=driver_tg_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"✅ Notification sent to driver telegram_id={driver_tg_id}")
        
        # 3. Taymerni rejalashtirish
        from app.tasks.matching import auto_reject_order_task
        auto_reject_order_task.apply_async(args=[driver_id, order_id], countdown=120)
        
        return {'success': True}
        
    except Exception as e:
        # 4. Retry mantiqi (Sessiyadan TASHQARIDA - to'g'ri yo'li shu)
        error_msg = str(e).lower()
        if 'blocked' in error_msg or 'chat not found' in error_msg:
            logger.error(f"Cannot notify driver {driver_id}: Bot blocked or user not found")
            return {'success': False, 'reason': 'forbidden'}
            
        logger.warning(f"Retry sending notification to {driver_id}: {e}")
        raise self.retry(exc=e, countdown=5)


# ============================================
# 3. AVTOMATIK RAD ETISH (2 daqiqa javob yo'q)
# ============================================

@celery_app.task(name="app.tasks.matching.auto_reject_order_task")
@async_to_sync
async def auto_reject_order_task(driver_id: int, order_id: int):
    async with get_session() as session:
        order = await get_order_by_id(session, order_id)
        
        if order and order.status == OrderStatus.PENDING:
            logger.warning(f"Driver {driver_id} didn't respond to order {order_id} - removing from queue")
            
            # 1. Haydovchini navbatdan chiqaramiz (javob bermagani uchun)
            await driver_queue.remove_driver(driver_id, order.route_id)
            
            # 2. Keyingi haydovchini qidirishni boshlaymiz
            find_driver_for_order_task.delay(order_id)
    

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
                                 f"📦 Buyurtma #{order_id}\n\n"
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
                             f"📦 Buyurtma #{order_id}\n\n"
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

@celery_app.task(name="app.tasks.matching.auto_complete_trip_task")
@async_to_sync
async def auto_complete_trip_task(order_id: int):
    """
    "Ketdik" bosilgandan keyin 10 daqiqadan keyin safar avtomatik yakunlanadi.
    
    STATUS: IN_PROGRESS → COMPLETED
    """
    from sqlalchemy import update, select
    from app.models.order import Order, OrderStatus
    from app.models.driver import Driver
    from app.models.passenger import Passenger
    from sqlalchemy.orm import selectinload
    from app.services.order_service import complete_trip
    
    async with get_session() as session:
        order_result = await session.execute(
            select(Order)
            .options(selectinload(Order.passenger).selectinload(Passenger.user))
            .where(Order.order_id == order_id)
        )
        order = order_result.scalar_one_or_none()
        
        # Agar order hali ham IN_PROGRESS holatda bo'lsa, avtomatik yakunlash
        if order and order.status == OrderStatus.IN_PROGRESS:
            logger.info(f"Auto-completing trip for order {order_id} after 10 minutes")
            
            # Safarni yakunlash
            if order.driver_id:
                result = await complete_trip(order_id, order.driver_id)
                
                if result['success']:
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
                                text=f"✅ <b>Safar avtomatik yakunlandi</b>\n\n"
                                     f"📦 Buyurtma #{order_id}\n"
                                     f"⏱ Davomiyligi: {result.get('duration_minutes', 10)} daqiqa\n\n"
                                     f"✨ Rahmat! Keyingi safarga muvaffaqiyat tilaymiz!",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify driver: {e}")
                    
                    logger.info(f"Order {order_id} auto-completed after 10 minutes")
                    
                    # Yo'lovchiga xabar va REYTING
                    if order.passenger and order.passenger.user:
                        from app.bot.main import bot
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        
                        # Reyting klaviaturasi
                        rating_kb = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="⭐️ 1", callback_data=f"rate_driver:{order_id}:1"),
                                InlineKeyboardButton(text="⭐️ 2", callback_data=f"rate_driver:{order_id}:2"),
                                InlineKeyboardButton(text="⭐️ 3", callback_data=f"rate_driver:{order_id}:3"),
                            ],
                            [
                                InlineKeyboardButton(text="⭐️ 4", callback_data=f"rate_driver:{order_id}:4"),
                                InlineKeyboardButton(text="⭐️ 5", callback_data=f"rate_driver:{order_id}:5"),
                            ]
                        ])
                        
                        try:
                            await bot.send_message(
                                chat_id=order.passenger.user.user_id,
                                text=f"✅ <b>Safar yakunlandi (Avtomatik 10 daqiqa)</b>\n\n"
                                     f"📦 Buyurtma #{order_id}\n"
                                     f"⏱ Davomiyligi: {result.get('duration_minutes', 10)} daqiqa\n\n"
                                     f"✨ <b>Haydovchiga baho bering:</b>",
                                parse_mode="HTML",
                                reply_markup=rating_kb
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify passenger: {e}")
                else:
                    logger.error(f"Failed to auto-complete trip: {result.get('message')}")



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
            
            # Order'ni cancel qilish
            from sqlalchemy import update
            
            await session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='no_driver_available',
                    cancelled_at=func.now()
                )
            )
            
            await session.commit()
            logger.info(f"Order {order_id} cancelled due to no driver available")
        
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
    else:
        # Barcha route'lardan (driver deactivate bo'lganda)
        from app.core.redis_client import redis_client
        
        # Barcha driver_queue:* key'larni topish
        async for key in redis_client.client.scan_iter(match="driver_queue:*"):
            await redis_client.client.zrem(key, str(driver_id))
        
        # Join time'larni tozalash
        async for key in redis_client.client.scan_iter(match=f"driver_join_time:{driver_id}:*"):
            await redis_client.delete(key)
    
    logger.info(f"Driver {driver_id} removed from queue")


__all__ = [
    'auto_complete_trip_task',
    'find_driver_for_order_task',
    'notify_driver_new_order_task',
    'auto_reject_order_task',
    'notify_passenger_no_driver_task',
    'add_driver_to_queue_task',
    'remove_driver_from_queue_task'
]