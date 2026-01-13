"""
app/bot/handlers/driver/orders.py

HAYDOVCHI BUYURTMALAR HANDLER

BU HANDLER NIMA QILADI:
- Buyurtma qabul qilish (LOCK bilan)
- Safar boshlash
- Safar yakunlash
"""
from aiogram.filters import StateFilter

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.core.database import get_session
from app.models.driver import get_driver_by_user_id
from app.models.order import Order, get_order_by_id
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.passenger import Passenger
from app.services.order_service import (
    accept_order_by_driver,
    start_trip,
    complete_trip
)
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import (
    get_trip_confirmation_keyboard,
    get_trip_active_keyboard
)
from app.tasks.matching import find_driver_for_order_task

router = Router()


# ============================================
# BUYURTMA QABUL QILISH
# ============================================

@router.callback_query(F.data.startswith("accept_order:"))
async def accept_order_handler(callback: CallbackQuery, state: FSMContext):
    if callback.data is None:
        await callback.answer("Xatolik: malumot mavjud emas")
        return
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    # 1. Loading holati
    if callback.message:
        await callback.message.edit_text("⏳ <b>Qabul qilinmoqda...</b>")
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)

        if not driver:
            await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
            return
        
        # 2. Buyurtmani qabul qilish logikasi
        result = await accept_order_by_driver(driver_id=driver.driver_id, order_id=order_id)
        
        if result['success']:
            # Order ma'lumotlarini olish (mijoz ma'lumotlari bilan)
            from app.models.order import get_order_by_id
            from sqlalchemy.orm import selectinload
            from app.models.passenger import Passenger
            
            order_result = await session.execute(
                select(Order)
                .options(selectinload(Order.passenger).selectinload(Passenger.user))
                .where(Order.order_id == order_id)
            )
            order = order_result.scalar_one_or_none()
            
            # 3. ESKI XABARNI TAHRIRLASH (Tugmalarni yo'qotish uchun)
            await callback.message.edit_text(
                f"✅ <b>Buyurtma #{order_id} qabul qilindi!</b>\n\n"
                f"💰 Komissiya: <b>{result['order']['commission']:,} so'm</b>\n"
                f"📊 Yangi balans: <b>{result['order']['new_balance']:,} so'm</b>"
            )
            
            # 4. Mijoz ma'lumotlarini yuborish (qabul qilganda)
            if order and order.passenger:
                passenger = order.passenger
                passenger_name = passenger.full_name
                passenger_phone = passenger.user.phone_number if passenger.user else "N/A"
                
                # Buyurtma turi va pochtani aniqlash
                if order.passenger_count == 0 and order.has_luggage:
                    order_type = "📦 Pochta"
                    if order.luggage_count > 1:
                        order_type += f" ({order.luggage_count} dona)"
                    if order.luggage_description:
                        order_type += f"\n📝 {order.luggage_description}"
                elif order.has_luggage and order.passenger_count > 0:
                    order_type = f"👥 {order.passenger_count} kishi"
                    if order.luggage_count > 0:
                        order_type += f" + 📦 Pochta ({order.luggage_count} dona)"
                        if order.luggage_description:
                            order_type += f"\n📝 {order.luggage_description}"
                else:
                    order_type = f"👥 {order.passenger_count} kishi"
                
                # Lokatsiya linklari
                from app.utils.location_helpers import get_google_maps_link, get_telegram_location_link
                
                google_maps_link = get_google_maps_link(order.pickup_lat, order.pickup_lon, order.pickup_location)
                telegram_location_link = get_telegram_location_link(order.pickup_lat, order.pickup_lon)
                
                passenger_info = f"""
✅ <b>Buyurtma qabul qilindi!</b>

📍 <b>Olish joyi:</b> {order.pickup_location}
<a href="{google_maps_link}">🗺️ Google Maps</a> | <a href="{telegram_location_link}">📍 Telegram xarita</a>
{order_type}
📱 <b>Telefon:</b> <code>{passenger_phone}</code>
                """
                
                await callback.message.answer(
                    passenger_info,
                    parse_mode="HTML"
                )
            
            # 5. YANGI XABAR YUBORISH (Sizning Reply klaviaturangizni chiqarish uchun)
            from app.bot.keyboards.driver import get_trip_confirmation_keyboard
            from app.services.queue_service import driver_queue
            
            # Qolgan bo'sh o'rinlar
            remaining_seats = result['order'].get('available_seats', 0)
            has_more_seats = result['order'].get('has_more_seats', False)
            
            trip_message = "🚕 <b>Buyurtma qabul qilindi!</b>\n\n"
            trip_message += "📍 Yo'lovchi joyiga boring.\n"
            trip_message += "📞 Kerak bo'lsa, yo'lovchi bilan bog'laning."
            
            if has_more_seats:
                trip_message += f"\n\n💺 <b>Qolgan bo'sh o'rinlar:</b> {remaining_seats}"
                trip_message += "\n✅ Keyingi buyurtmalar ham sizga beriladi!"
            
            await callback.message.answer(
                trip_message,
                reply_markup=get_trip_confirmation_keyboard(order_id),
                parse_mode="HTML"
            )
            
            # MUHIM: Agar o'rinlar to'lganda, navbatdan o'chirish
            if not has_more_seats:
                # O'rinlar to'ldi - navbatdan o'chirish
                await driver_queue.remove_driver(driver.driver_id, order.route_id)
                logger.info(
                    f"Driver {driver.driver_id} removed from queue: "
                    f"no more seats available"
                )
            
            # 5. State va Tasklar
            await state.update_data(current_order_id=order_id)
            await state.set_state(DriverStates.trip_in_progress)
            
            # Yo'lovchiga xabar yuborish
            from app.tasks.notifications import notify_passenger_driver_found
            notify_passenger_driver_found.delay(result['passenger_id'], driver.driver_id, order_id)
            
            logger.success(f"Order {order_id} accepted and UI updated for driver {driver.driver_id}")
        
        else:
            # Xato bo'lsa
            await callback.message.edit_text(f"❌ <b>Xatolik:</b>\n{result['message']}")
            logger.warning(f"Accept failed: {result['message']}")
    
    await callback.answer()


# ============================================
# YETIB KELDIM (GPS CHECK)
# ============================================

@router.message(
    DriverStates.trip_in_progress,
    F.text == "📍 Yetib keldim"
)
async def driver_arrived(message: Message, state: FSMContext):
    """
    Haydovchi yo'lovchi joyiga yetib keldi
    
    NIMA BO'LADI:
    1. GPS proximity check (100m)
    2. Yo'lovchiga tasdiqlash so'rash
    3. 2 daqiqa kutish
    4. Auto-confirm yoki yo'lovchi tasdiqlaydi
    """
    user_id = message.from_user.id # type: ignore
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    if not order_id:
        await message.answer("❌ Aktiv buyurtma topilmadi")
        return
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        # GPS proximity check (TODO: implement)
        # from app.services.geo_service import check_driver_proximity
        # proximity_result = await check_driver_proximity(driver.driver_id, order_id)
        
        # if not proximity_result['is_near']:
        #     await message.answer(
        #         f"⚠️ Siz pickup joyidan uzoqdasiz\n\n"
        #         f"Masofa: {proximity_result['distance']:.0f}m\n"
        #         f"Kerak: 100m ichida"
        #     )
        #     return
        
        # Yo'lovchiga tasdiqlash so'rash
        await message.answer(
            "✅ <b>Yo'lovchiga xabar yuborildi</b>\n\n"
            "Yo'lovchi mashinaga tushganini tasdiqlashi kutilmoqda...\n\n"
            "⏱ Maksimal 2 daqiqa"
        )
        
        # Celery task (yo'lovchiga tasdiqlash so'rash + auto-confirm)
        from app.tasks.notifications import request_passenger_confirmation
        request_passenger_confirmation.delay(order_id, driver.driver_id)
        
        await state.set_state(DriverStates.trip_confirmation)


# ============================================
# SAFAR BOSHLASH (YO'LOVCHI TASDIQLADI)
# ============================================

@router.callback_query(F.data.startswith("trip_confirmed:"))
async def trip_confirmed(callback: CallbackQuery, state: FSMContext):
    """
    Yo'lovchi tasdiqladi - safar boshlandi
    
    Bu callback Celery task'dan keladi
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return

    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        if not driver:
            if callback.message:
                await callback.message.answer("❌ Haydovchi topilmadi") # type: ignore
            await state.clear()
            await callback.answer()
            return
        # Safarni boshlash
        result = await start_trip(order_id, driver.driver_id)
        
        if result['success']:
            # Avto-yakunlash task (10 daqiqa)
            from app.tasks.matching import auto_complete_trip_task
            auto_complete_trip_task.apply_async(args=[order_id], countdown=600)
            
            # State yangilash - safar boshlandi
            await state.update_data(current_order_id=order_id)
            await state.set_state(DriverStates.trip_in_progress)
            
            if callback.message is not None:
                await callback.message.edit_text( # type: ignore
                    f"✅ <b>Safar boshlandi!</b>\n\n"
                    f"📦 Buyurtma #{order_id}\n\n"
                    f"🚗 Xavfsiz yo'l!\n\n"
                    f"⏭ Safar yakunlangach 'To'lgach ketish' tugmasini bosing",
                    reply_markup=get_trip_active_keyboard()
                )
            
            logger.info(f"Trip started: order={order_id}, driver={driver.driver_id}")
        
        else:
            if callback.message is not None:
                await callback.message.edit_text(f"❌ {result['message']}") # type: ignore
    
    await callback.answer()


# ============================================
# SAFAR YAKUNLASH
# ============================================

@router.message(
    DriverStates.trip_in_progress,
    F.text == "To'lgach ketish"
)
async def complete_trip_handler(message: Message, state: FSMContext):
    """
    Safar yakunlandi
    """
    
    user_id = message.from_user.id # type: ignore
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    if not order_id:
        await message.answer("❌ Aktiv buyurtma topilmadi")
        return
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        if driver is None:
            await message.answer("❌ Haydovchi topilmadi")
            await state.clear()
            return
        # Safarni yakunlash
        result = await complete_trip(order_id, driver.driver_id)
        
        if result['success']:
            await message.answer(
                f"🎉 <b>Safar yakunlandi!</b>\n\n"
                f"📦 Buyurtma #{order_id}\n"
                f"⏱ Davomiyligi: {result.get('duration_minutes', 0)} daqiqa\n\n"
                f"✨ Rahmat! Keyingi safarga muvaffaqiyat tilaymiz!",
                reply_markup=get_driver_main_menu()
            )
            
            # Yo'lovchiga xabar
            # from app.tasks.notifications import notify_trip_completed
            # notify_trip_completed.delay(order_id)
            
            await state.clear()
            
            logger.success(
                f"Trip completed: order={order_id}, driver={driver.driver_id}"
            )
        
        else:
            await message.answer(f"❌ {result['message']}")


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
async def contact_passenger_handler(message: Message, state: FSMContext):
    """
    Haydovchi yo'lovchi bilan bog'lanish uchun ma'lumotlarni ko'radi
    """
    user_id = message.from_user.id # type: ignore
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    if not order_id:
        await message.answer("❌ Aktiv buyurtma topilmadi")
        return
    
    async with get_session() as session:
        order_result = await session.execute(
            select(Order)
            .options(selectinload(Order.passenger).selectinload(Passenger.user))
            .where(Order.order_id == order_id)
        )
        order = order_result.scalar_one_or_none()
        
        if not order or not order.passenger:
            await message.answer("❌ Yo'lovchi ma'lumotlari topilmadi")
            return
        
        passenger = order.passenger
        passenger_phone = passenger.user.phone_number if passenger.user else "N/A"
        passenger_name = passenger.full_name
        
        # Buyurtma turi va pochtani aniqlash
        order_info = ""
        if order.passenger_count == 0 and order.has_luggage:
            order_info = "📦 Pochta"
            if order.luggage_count > 1:
                order_info += f" ({order.luggage_count} dona)"
            if order.luggage_description:
                order_info += f"\n📝 {order.luggage_description}"
        elif order.has_luggage and order.passenger_count > 0:
            order_info = f"👥 {order.passenger_count} kishi"
            if order.luggage_count > 0:
                order_info += f" + 📦 Pochta ({order.luggage_count} dona)"
                if order.luggage_description:
                    order_info += f"\n📝 {order.luggage_description}"
        else:
            order_info = f"👥 {order.passenger_count} kishi"
        
        # Telefon raqamini tekshirish
        phone_valid = passenger_phone and passenger_phone != "N/A" and passenger_phone != "UNKNOWN" and passenger_phone.strip()
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard_buttons = []
        
        if phone_valid:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="📞 Qo'ng'iroq qilish",
                    url=f"tel:{passenger_phone}"
                )
            ])
        
        if passenger.user:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="💬 Telegram",
                    url=f"tg://user?id={passenger.user.user_id}"
                )
            ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None
        
        contact_text = f"""
📞 <b>Yo'lovchi ma'lumotlari</b>

👤 <b>Ism:</b> {passenger_name}
📱 <b>Telefon:</b> <code>{passenger_phone}</code>
{order_info}
        """
        
        await message.answer(
            contact_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )


@router.message(
    DriverStates.trip_in_progress,
    F.text == "❌ Buyurtmani bekor qilish"
)
async def cancel_order_handler(message: Message, state: FSMContext):
    """
    Haydovchi buyurtmani bekor qiladi
    
    DIQQAT: Bu firibgarlik hisoblanadi!
    """
    await message.answer(
        "⚠️ <b>Buyurtmani bekor qilmoqchimisiz?</b>\n\n"
        "Bu jiddiy harakat! Agar bekor qilsangiz:\n"
        "• Komissiya qaytarilmaydi\n"
        "• Warning olasiz\n"
        "• 3 ta warning = 24 soat ban\n\n"
        "Davom ettirish uchun 'Tasdiqlash' yozing"
    )
    
    await state.set_state(DriverStates.confirming_cancellation)


@router.message(
    DriverStates.confirming_cancellation,
    F.text.lower() == "tasdiqlash"
)
async def confirm_cancellation(message: Message, state: FSMContext):
    """
    Bekor qilish tasdiqlandi
    """
    user_id = message.from_user.id # type: ignore
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    # Bekor qilish logikasi
    # from app.services.order_service import cancel_order_by_driver
    # result = await cancel_order_by_driver(order_id, driver.driver_id)
    
    await message.answer(
        "❌ <b>Buyurtma bekor qilindi</b>\n\n"
        "⚠️ Warning olindingiz!",
        reply_markup=get_driver_main_menu(),
        parse_mode="HTML"
    )
    
    await state.clear()


def get_driver_main_menu():
    """Driver asosiy menyusi"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Buyurtma qabul qilish")],
            [KeyboardButton(text="💰 Balans"), KeyboardButton(text="📊 Statistika")],
        ],
        resize_keyboard=True
    )

@router.callback_query(F.data.startswith("reject_order:"))
async def reject_order_handler(callback: CallbackQuery):
    """
    Haydovchi buyurtmani rad etdi
    
    NIMA BO'LADI:
    1. Rad etish sonini hisoblash
    2. Kunlik limit tekshiruvi
    3. Yangi haydovchi topish
    4. Haydovchiga xabar
    """
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
            return
        
        # Rad etish sonini oshirish (kunlik)
        from datetime import datetime, timedelta
        from sqlalchemy import select, func
        from app.models.order import Order, OrderStatus
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0)
        
        # Bugungi rad etilgan buyurtmalar soni
        result = await session.execute(
            select(func.count(Order.order_id))
            .where(Order.driver_id == driver.driver_id)
            .where(Order.status == OrderStatus.CANCELLED)
            .where(Order.cancelled_at >= today_start)
        )
        
        today_rejects = result.scalar() or 0
        
        # Kunlik limit tekshiruvi
        from config.settings import settings
        max_rejects = settings.MAX_DRIVER_REJECTS_PER_DAY
        
        if today_rejects >= max_rejects:
            await callback.message.edit_text( # type: ignore
                f"⚠️ <b>Kunlik limit yetdi!</b>\n\n"
                f"Siz bugun {max_rejects} ta buyurtmani rad etdingiz.\n"
                f"Ertaga qayta urinib ko'ring."
            )
            await callback.answer("Kunlik limit yetdi", show_alert=True)
            return
        
        # Xabarni yangilash
        if callback.message is not None:
            await callback.message.edit_text( # type: ignore
                f"❌ <b>Buyurtma rad etildi</b>\n\n"
                f"📊 Bugungi rad etishlar: {today_rejects + 1}/{max_rejects}\n\n"
                f"⏳ Yangi buyurtma kutyapsiz..."
            )
        
        # Keyingi haydovchiga yuborish
        find_driver_for_order_task.delay(order_id)
        
        logger.info(
            f"Driver {driver.driver_id} rejected order {order_id}. "
            f"Today rejects: {today_rejects + 1}/{max_rejects}"
        )
    
    await callback.answer("Buyurtma rad etildi")

__all__ = ['router']