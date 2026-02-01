"""
app/tasks/notifications.py

TELEGRAM NOTIFICATION TASKS

BU TASK'LAR NIMA QILADI:
1. Telegram xabar yuborish (rate limited)
2. Yo'lovchiga haydovchi topilganini bildirish
3. Safar tasdiqlash so'rovi
4. Safar yakunlangani haqida
5. Bulk xabarlar
"""
from typing import Optional, Dict, List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

import asyncio
from loguru import logger

from app.core.celery_app import celery_app
from app.core.redis_client import redis_client
from app.core.database import get_session
from app.models.driver import Driver, get_driver_by_id
from app.models.passenger import get_passenger_by_id
from app.models.order import Order, OrderStatus, get_order_by_id
from app.core.celery_app import async_to_sync


# ============================================
# 1. TELEGRAM XABAR YUBORISH (BASE)
# ============================================

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    rate_limit='30/s'  # Global limit
)
@async_to_sync
async def send_telegram_message(
    self,
    chat_id: int,
    text: str,
    parse_mode: str = 'HTML',
    reply_markup: Optional[Dict] = None,
    **kwargs
):
    """
    Telegram xabar yuborish (rate limited + retry)
    
    Args:
        chat_id: Chat/User ID
        text: Xabar matni
        parse_mode: HTML yoki Markdown
        reply_markup: Klaviatura (dict format)
        **kwargs: Qo'shimcha parametrlar
    
    FEATURES:
    - Per-chat rate limiting (1 msg/sec)
    - Auto retry (Flood wait, connection error)
    - Error handling (blocked, deleted)
    """

    from app.bot.main import bot
    from aiogram.exceptions import (
        TelegramBadRequest,
        TelegramForbiddenError,
        TelegramRetryAfter
    )
    
    # Per-chat rate limit
    rate_key = f"tg_rate:{chat_id}"
    current_count = await redis_client.incr(rate_key)
    
    if current_count == 1:
        await redis_client.expire(rate_key, 1)  # 1 soniya
    
    if current_count > 1:
        # Chat uchun limit oshdi - 1 soniya kutish
        await asyncio.sleep(1)
    
    try:
        # Reply markup parse
        keyboard = None
        if reply_markup:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=btn['text'],
                            callback_data=btn.get('callback_data'),
                            url=btn.get('url')
                        )
                        for btn in row
                    ]
                    for row in reply_markup.get('inline_keyboard', [])
                ]
            )
        
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=keyboard,
            **kwargs
        )
        
        logger.debug(f"✅ Message sent to {chat_id}")
        
        return {'success': True, 'chat_id': chat_id}
    
    except TelegramRetryAfter as e:
        # Flood wait
        logger.warning(f"Flood wait: {e.retry_after} seconds")
        raise self.retry(exc=e, countdown=e.retry_after)
    
    except TelegramForbiddenError:
        # Bot blocked by user
        logger.info(f"Bot blocked by user {chat_id}")
        return {'success': False, 'reason': 'blocked'}
    
    except TelegramBadRequest as e:
        # Bad request (chat not found, etc)
        logger.error(f"Bad request: {e}")
        return {'success': False, 'reason': 'bad_request'}
    
    except Exception as e:
        # Boshqa xatolar
        logger.error(f"Error sending message: {e}")
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)
        else:
            return {'success': False, 'reason': 'error'}
    



# ============================================
# 2. YO'LOVCHIGA HAYDOVCHI TOPILDI
# ============================================

@celery_app.task(name="app.tasks.notifications.notify_passenger_driver_found")
@async_to_sync
async def notify_passenger_driver_found(passenger_user_id: int, driver_id: int, order_id: int):
    """
    Yo'lovchiga haydovchi topilganini bildirish
    
    NIMA BO'LADI:
    1. Haydovchi ma'lumotlarini olish
    2. Mashina ma'lumotlari (model, rang, raqam)
    3. Telefon raqam
    4. "Mashinani o'zgartirish" tugmasi (1 soatda 3 marta limit)
    """
    from app.bot.main import bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from sqlalchemy.orm import selectinload
    from app.models.driver import Driver
    from app.models.order import Order
    from datetime import datetime, timedelta

    async with get_session() as session:
        # Driver ma'lumotlarini olish (user bilan)
        result = await session.execute(
            select(Driver)
            .options(selectinload(Driver.user))
            .where(Driver.driver_id == driver_id)
        )
        driver = result.scalar_one_or_none()
        
        # Order ma'lumotlarini olish
        order_result = await session.execute(
            select(Order)
            .options(selectinload(Order.route))
            .where(Order.order_id == order_id)
        )
        order = order_result.scalar_one_or_none()
        
        if not driver or not order:
            logger.error(f"Driver {driver_id} or Order {order_id} not found")
            return
        
        # Mashina o'zgartirish sonini tekshirish (1 soatda 3 marta)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        
        change_count_result = await session.execute(
            select(func.count(Order.order_id))
            .where(Order.passenger_id == order.passenger_id)
            .where(Order.status == OrderStatus.CANCELLED)
            .where(Order.cancellation_reason.like('%change_driver%'))
            .where(Order.cancelled_at >= one_hour_ago)
        )
        change_count = change_count_result.scalar() or 0
        
        max_changes = 3  # System settings'dan olish mumkin
        can_change = change_count < max_changes
        
        # Telefon raqamini tekshirish
        phone_number = driver.phone_number or "N/A"
        phone_valid = phone_number and phone_number != "N/A" and phone_number != "UNKNOWN" and phone_number.strip()
        
        fare_amount_value = None
        if order.route and order.route.fare_amount is not None:
            fare_amount_value = float(order.route.fare_amount)
        fare_amount_display = f"{fare_amount_value:,.0f} so'm" if fare_amount_value is not None else "N/A"

        # Xabar matni (Telegram linki olib tashlandi)
        text = f"""
✅ <b>Haydovchi topildi!</b>

👤 <b>Haydovchi:</b> {driver.full_name}
🚗 <b>Mashina:</b> {driver.car_model}
🎨 <b>Rang:</b> {driver.car_color}
🔢 <b>Raqam:</b> <code>{driver.car_number}</code>
📱 <b>Telefon:</b> {phone_number}
🛣 <b>Yo'l haqi:</b> {fare_amount_display}

Haydovchi siz tomonga yo'lga chiqdi!
        """
        
        # Klaviatura
        keyboard_buttons = []
        
        # Telefon raqami faqat matn sifatida ko'rsatiladi (tel: URL Telegram tomonidan qo'llab-quvvatlanmaydi)
        
        # Mashinani o'zgartirish tugmasi (limit bo'lsa)
        if can_change:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="🔄 Mashinani o'zgartirish",
                    callback_data=f"change_driver:{order_id}"
                )
            ])
        else:
            # Limit yetdi
            text += f"\n\n⚠️ Mashinani o'zgartirish limiti yetdi ({change_count}/{max_changes})"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # ✅ PRODUCTION FIX: Specific exception handling
        from aiogram.exceptions import (
            TelegramForbiddenError,
            TelegramBadRequest,
            TelegramRetryAfter
        )
        
        try:
            await bot.send_message(
                chat_id=passenger_user_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            logger.info(f"✅ Driver found notification sent to passenger {passenger_user_id}")
        
        except TelegramForbiddenError:
            # Don't retry - user blocked bot
            logger.warning(f"Passenger {passenger_user_id} has blocked the bot")
        
        except TelegramBadRequest as e:
            # Chat not found or other bad request
            logger.warning(f"Bad request for passenger {passenger_user_id}: {e}")
        
        except TelegramRetryAfter as e:
            # Flood wait - just log, don't crash
            logger.warning(f"Flood wait for passenger {passenger_user_id}: {e.retry_after}s")
        
        except Exception as e:
            # Other unexpected errors
            logger.error(f"Failed to notify passenger {passenger_user_id}: {e}")



# ============================================
# 3. SAFAR TASDIQLASH SO'ROVI
# ============================================

@celery_app.task(name="app.tasks.notifications.request_passenger_confirmation")
@async_to_sync
async def request_passenger_confirmation(order_id: int, driver_id: int):
    from app.bot.main import bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    async with get_session() as session:
        # Orderni Yo'lovchi (Passenger) ma'lumotlari bilan yuklaymiz
        # Shunda order.passenger.user_id o'qilganda xato bermaydi
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.passenger)) 
            .where(Order.order_id == order_id)
        )
        order = result.scalar_one_or_none()
        
        res_driver = await session.execute(select(Driver).where(Driver.driver_id == driver_id))
        driver = res_driver.scalar_one_or_none()
        
        if not order or not driver:
            return

        # Driver ma'lumotlarini olish
        driver_result = await session.execute(
            select(Driver)
            .options(selectinload(Driver.user))
            .where(Driver.driver_id == driver_id)
        )
        driver = driver_result.scalar_one_or_none()
        
        if not driver:
            logger.error(f"Driver {driver_id} not found")
            return
        
        # Driver ma'lumotlari
        driver_name = driver.full_name
        driver_phone = driver.phone_number or "N/A"
        driver_car = f"{driver.car_model} ({driver.car_color})"
        driver_number = driver.car_number
        
        # Telefon raqamini tekshirish
        phone_valid = driver_phone and driver_phone != "N/A" and driver_phone != "UNKNOWN" and driver_phone.strip()
        
        # Klaviatura tugmalari
        keyboard_buttons = []
        
        # Telefon raqami faqat matn sifatida ko'rsatiladi (tel: URL Telegram tomonidan qo'llab-quvvatlanmaydi)
        
        # Telefon raqami faqat matn sifatida ko'rsatiladi (tel: URL Telegram tomonidan qo'llab-quvvatlanmaydi)
        
        # "Ketdik" va "Bekor qilish" tugmalari
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="✅ Ketdik",
                callback_data=f"passenger_started:{order_id}"
            )
        ])
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="❌ Buyurtmani bekor qilish",
                callback_data=f"passenger_cancel:{order_id}"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Xabar matni
        message_text = f"""
✅ <b>Haydovchi topildi!</b>

👤 <b>Haydovchi:</b> {driver_name}
🚗 <b>Mashina:</b> {driver_car}
🔢 <b>Raqam:</b> <code>{driver_number}</code>
📱 <b>Telefon:</b> {driver_phone}

📍 Haydovchi siz tomonga yo'lga chiqdi!
        """
        
        # ✅ PRODUCTION FIX: Specific exception handling
        from aiogram.exceptions import (
            TelegramForbiddenError,
            TelegramBadRequest,
            TelegramRetryAfter
        )
        
        try:
            # order.passenger.user_id - endi xavfsiz olinadi!
            await bot.send_message(
                chat_id=order.passenger.user_id, 
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            # ✅ CONSTANTS: Auto-confirm timer from settings
            from config.settings import settings
            from app.core.celery_app import celery_app
            celery_app.send_task(
                "app.tasks.matching.auto_confirm_trip_task",
                args=[order_id],
                countdown=settings.AUTO_CONFIRM_TRIP_SECONDS,
            )
        
        except TelegramForbiddenError:
            logger.warning(f"Passenger {order.passenger.user_id} blocked the bot")
        
        except TelegramBadRequest as e:
            logger.warning(f"Bad request for passenger {order.passenger.user_id}: {e}")
        
        except TelegramRetryAfter as e:
            logger.warning(f"Flood wait: {e.retry_after}s")
            
        except Exception as e:
            logger.error(f"Confirmation request failed: {e}")


# ============================================
# 4. SAFAR YAKUNLANDI
# ============================================

@celery_app.task
@async_to_sync
async def notify_trip_completed(order_id: int):
    """
    Safar yakunlanganini bildirish (haydovchi va yo'lovchiga)
    """
    
    async with get_session() as session:
        order = await get_order_by_id(session, order_id)
        
        if not order:
            return
        if order.driver_id is None:
            return  # yoki xatolik log qil
        driver = await get_driver_by_id(session, order.driver_id)
        passenger = await get_passenger_by_id(session, order.passenger_id)
        
        if not driver or not passenger:
            return
        
        # Haydovchiga
        driver_text = f"""
🎉 <b>Safar yakunlandi!</b>

⏱ Davomiyligi: {order.duration_minutes or 0} daqiqa

✨ Rahmat! Keyingi safarga muvaffaqiyat tilaymiz!
        """
        
        send_telegram_message.delay(driver.user_id, driver_text) # type: ignore
        
        # Yo'lovchiga (reyting so'rash)
        passenger_text = f"""
🎉 <b>Safar yakunlandi!</b>

Xavfsiz yetib borgansizdan xursandmiz!

⭐ Haydovchini baholang:
        """
        
        rating_keyboard = {
            'inline_keyboard': [
                [
                    {'text': '⭐️ 1', 'callback_data': f'rate_driver:{order_id}:1'},
                    {'text': '⭐️ 2', 'callback_data': f'rate_driver:{order_id}:2'},
                    {'text': '⭐️ 3', 'callback_data': f'rate_driver:{order_id}:3'},
                ],
                [
                    {'text': '⭐️ 4', 'callback_data': f'rate_driver:{order_id}:4'},
                    {'text': '⭐️ 5', 'callback_data': f'rate_driver:{order_id}:5'},
                ]
            ]
        }
        
        send_telegram_message.delay( # type: ignore
            passenger.user_id,
            passenger_text,
            reply_markup=rating_keyboard
        )
        
        logger.info(f"✅ Trip completion notifications sent: order={order_id}")
    


# ============================================
# 5. BULK XABARLAR
# ============================================

@celery_app.task
@async_to_sync
async def send_bulk_messages(user_ids: List[int], text: str, **kwargs):
    """
    Ko'p foydalanuvchilarga xabar yuborish
    
    Args:
        user_ids: User ID'lar ro'yxati
        text: Xabar matni
        **kwargs: Qo'shimcha parametrlar
    
    ISHLATISH:
        # Barcha haydovchilarga
        send_bulk_messages.delay([123, 456, 789], "Yangi yangilik!")
    """
    
    for user_id in user_ids:
        send_telegram_message.delay(user_id, text, **kwargs) # type: ignore
    
    logger.info(f"✅ Bulk messages queued: {len(user_ids)} users")
    
    return {
        'queued': len(user_ids),
        'message': f'{len(user_ids)} ta xabar navbatga qo\'shildi'
    }


# ============================================
# 6. ADMIN XABARLARI
# ============================================

@celery_app.task
@async_to_sync

async def notify_admins(text: str, **kwargs):
    """
    Barcha adminlarga xabar yuborish
    """
    from config.settings import settings
    
    admin_ids = settings.admin_ids_list
    
    if not admin_ids:
        logger.warning("No admin IDs configured")
        return
    
    for admin_id in admin_ids:
        send_telegram_message.delay(admin_id, text, **kwargs) # type: ignore
    
    logger.info(f"✅ Admin notifications sent to {len(admin_ids)} admins")


# ============================================
# 7. ERROR NOTIFICATIONS
# ============================================

@celery_app.task
@async_to_sync
async def notify_critical_error(error_type: str, error_message: str, details: Dict = None): # type: ignore
    """
    Kritik xatolar haqida adminlarga xabar
    """
    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # asyncio.run shart emas!
    text = f"""
🚨 <b>KRITIK XATO!</b>

Type: <code>{error_type}</code>
Message: {error_message}

Details:
<pre>{details or {}}</pre>

⏰ Vaqt: {now_str}
    """
    
    notify_admins.delay(text)  # type: ignore



__all__ = [
    'send_telegram_message',
    'notify_passenger_driver_found',
    'request_passenger_confirmation',
    'notify_trip_completed',
    'send_bulk_messages',
    'notify_admins',
    'notify_critical_error'
]
