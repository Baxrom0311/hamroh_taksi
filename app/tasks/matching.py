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
from app.core.celery_app import async_to_sync # <--- import

from app.core.celery_app import celery_app
from app.core.database import get_session
from app.services.queue_service import driver_queue
from app.models.order import get_order_by_id, OrderStatus
from app.models.driver import get_driver_by_id

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
    """
        
    async with get_session() as session:
        # Order'ni olish
        order = await get_order_by_id(session, order_id)
        
        if not order:
            logger.error(f"Order {order_id} not found")
            return {'success': False, 'error': 'Order not found'}
        
        # Agar allaqachon qabul qilingan bo'lsa
        if order.status != OrderStatus.PENDING:
            logger.warning(f"Order {order_id} already accepted")
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
            # ❌ Haydovchi topilmadi - retry
            logger.warning(
                f"No driver found for order {order_id} "
                f"(attempt {self.request.retries + 1}/{self.max_retries})"
            )
            
            # Retry
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
    if order_data['passengers'] == 0:
        order_type_text = "📦 Pochta"
    else:
        order_type_text = f"👥 {order_data['passengers']} kishi"
    
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
    Haydovchi pickup nuqtasiga kelgan, lekin yo'lovchi 2 minut 
    ichida tasdiqlamagan bo'lsa, safarni avtomatik boshlash.
    """
    from app.services.trip_service import trip_service
    from app.models.order import OrderStatus
    
    async with get_session() as session:
        order = await get_order_by_id(session, order_id)
        
        # Agar order hali ham ACCEPTED holatda bo'lsa (ya'ni IN_PROGRESS bo'lmagan)
        # va haydovchi yetib kelgan bo'lsa
        if order and order.status == OrderStatus.ACCEPTED and order.driver_arrived:
            logger.info(f"Auto-confirming trip for order {order_id}")
            await trip_service.passenger_confirmed(
                passenger_id=order.passenger_id,
                order_id=order_id,
            )



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
    
    async with get_session() as session:
        order = await get_order_by_id(session, order_id)
        
        if not order:
            return
        
        message = """
😔 <b>Haydovchi topilmadi</b>

Hozirda bu yo'nalish bo'yicha bo'sh haydovchilar yo'q.

Iltimos:
- 10-15 daqiqadan keyin qayta urinib ko'ring
- Yoki boshqa marshrut tanlang

Noqulaylik uchun uzr so'raymiz!
        """
        
        try:
            await bot.send_message(
                chat_id=order.passenger_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            # Order'ni cancel qilish
            from sqlalchemy import update
            from app.models.order import Order
            
            await session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='no_driver_available'
                )
            )
            
            await session.commit()
        
        except Exception as e:
            logger.error(f"Failed to notify passenger: {e}")
    
    

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
    'find_driver_for_order_task',
    'notify_driver_new_order_task',
    'auto_reject_order_task',
    'notify_passenger_no_driver_task',
    'add_driver_to_queue_task',
    'remove_driver_from_queue_task'
]