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

from app.core.database import get_session, transaction
from app.models.driver import get_driver_by_user_id, Driver
from app.models.order import Order, get_order_by_id, OrderStatus
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from app.models.passenger import Passenger
from app.models.transaction import create_transaction, TransactionType
from app.services.order_service import (
    accept_order_by_driver,
    start_trip,
    complete_trip
)
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import (
    get_trip_confirmation_keyboard,
    get_trip_active_keyboard,
    get_passenger_contact_keyboard,
    get_order_cancellation_keyboard,
    get_driver_main_menu
)
from app.bot.messages import Messages
from app.bot.utils import get_driver_or_error, get_order_or_error
from app.tasks.matching import find_driver_for_order_task

router = Router()


# ============================================
# BUYURTMA QABUL QILISH
# ============================================

@router.callback_query(F.data.startswith("accept_order:"))
async def accept_order_handler(callback: CallbackQuery, state: FSMContext):
    
    if callback.data is None:
        await callback.answer(Messages.Error.CALLBACK_DATA_MISSING)
        return
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    # 1. Loading holati
    if isinstance(callback.message, Message):
        await callback.message.edit_text(Messages.Driver.ACCEPTING_ORDER)
    else:
        await callback.answer(Messages.Error.MESSAGE_OUTDATED, show_alert=True)
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, callback)
        if not driver:
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
            commission_amount = result['order']['commission'] # Extract commission amount


            # Order ma'lumotlarini olish (mijoz ma'lumotlari bilan)
            order_result = await session.execute(
                select(Order)
                .options(selectinload(Order.passenger).selectinload(Passenger.user))
                .where(Order.order_id == order_id)
            )
            order = order_result.scalar_one_or_none()
            
            # 3. ESKI XABARNI TAHRIRLASH (Tugmalarni yo'qotish uchun)
            if isinstance(callback.message, Message):
                await callback.message.edit_text( # type: ignore
                    Messages.Driver.ORDER_ACCEPTED.format(
                        order_id=order_id,
                        commission=commission_amount,
                        new_balance=driver.balance
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
                order_type_text = ""
                if order.passenger_count == 0 and order.has_luggage:
                    order_type_text = "📦 Pochta"
                    if order.luggage_count > 1:
                        order_type_text += f" ({order.luggage_count} dona)"
                    if order.luggage_description:
                        order_type_text += f"\n 📝 {order.luggage_description}"
                elif order.has_luggage and order.passenger_count > 0:
                    order_type_text = f"👥 {order.passenger_count} kishi"
                    if order.luggage_count > 0:
                        order_type_text += f" + 📦 Pochta ({order.luggage_count} dona)"
                        if order.luggage_description:
                            order_type_text += f"\n 📝 {order.luggage_description}"
                else:
                    order_type_text = f"👥 {order.passenger_count} kishi"
                
                # Lokatsiya linklari
                from app.utils.location_helpers import get_google_maps_link, get_telegram_location_link
                
                google_maps_link = get_google_maps_link(float(order.pickup_lat), float(order.pickup_lon), order.pickup_location)
                telegram_location_link = get_telegram_location_link(float(order.pickup_lat), float(order.pickup_lon))
                
                passenger_info = Messages.Driver.PASSENGER_INFO.format(
                    pickup_location=order.pickup_location,
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
                else:
                    # Agar xabar InaccessibleMessage bo'lsa (masalan, juda eski xabar)
                    await callback.bot.send_message(
                        chat_id=callback.from_user.id,
                        text=passenger_info,
                        parse_mode="HTML"
                    )
            
            # 5. YANGI XABAR YUBORISH (Sizning Reply klaviaturangizni chiqarish uchun)
            from app.services.queue_service import driver_queue
            
            # Qolgan bo'sh o'rinlar
            remaining_seats = result['order'].get('available_seats', 0)
            has_more_seats = result['order'].get('has_more_seats', False)
            
            trip_message = Messages.Driver.TRIP_ACCEPTED_PROMPT.format(order_id=order_id)
            
            if has_more_seats:
                trip_message += Messages.Driver.REMAINING_SEATS_INFO.format(remaining_seats=remaining_seats)
            
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
            if order.passenger and order.passenger.user:
                await callback.bot.send_message(
                    chat_id=order.passenger.user.user_id,
                    text=Messages.Passenger.DRIVER_FOUND.format(
                        order_id=order_id,
                        full_name=driver.full_name,
                        car_model=driver.car_model,
                        car_color=driver.car_color,
                        car_number=driver.car_number
                    ),
                    parse_mode="HTML"
                )
            
            logger.success(f"Order {order_id} accepted and UI updated for driver {driver.driver_id}")
        
        else:
            # Xato bo'lsa
            await callback.message.edit_text(f"❌ <b>Xatolik:</b>\n{result['message']}")
            logger.warning(f"Accept failed: {result['message']}")
    
    await callback.answer()


# ============================================
# YO'LGA CHIQDIK (SAFAR BOSHLASH)
# ============================================

@router.message(
    DriverStates.trip_in_progress,
    F.text == "🚗 Yo'lga chiqdik"
)
async def driver_started_trip(message: Message, state: FSMContext):
    """
    Haydovchi "Yo'lga chiqdik" tugmasini bosdi - safar boshlandi
    
    NIMA BO'LADI:
    1. Safar boshlandi (ACCEPTED → IN_PROGRESS)
    2. Driver is_on_trip=True (15 daqiqa davomida yangi buyurtma olmaydi)
    3. Qolgan bo'sh o'rinlar tekshiruvi
    4. Agar o'rinlar to'lganda, navbatdan o'chirish
    5. 15 daqiqadan keyin avtomatik yakunlash
    """
    user_id = message.from_user.id # type: ignore
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    if not order_id:
        await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
        return
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            return
        
        # Order'ni olish
        order = await get_order_by_id(session, order_id)
        
        if not order or order.driver_id != driver.driver_id:
            await message.answer(Messages.Error.ORDER_BUT_DRIVER_MISMATCH)
            return
        
        if order.status != OrderStatus.ACCEPTED:
            await message.answer("⚠️ Bu buyurtma allaqachon boshlandi")
            return
        
        # Safarni boshlash
        result = await start_trip(order_id, driver.driver_id)
        
        if result['success']:
            # Qolgan bo'sh o'rinlar tekshiruvi
            remaining_seats = driver.available_seats - order.passenger_count
            
            # Agar o'rinlar to'lganda, navbatdan o'chirish
            if remaining_seats <= 0:
                from app.services.queue_service import driver_queue
                await driver_queue.remove_driver(driver.driver_id, order.route_id)
                logger.info(
                    f"Driver {driver.driver_id} removed from queue: "
                    f"no more seats available after trip started"
                )
            
            # Avto-yakunlash task (10 daqiqa - aniq)
            from app.tasks.matching import auto_complete_trip_task
            auto_complete_trip_task.apply_async(args=[order_id], countdown=600)  # 10 daqiqa = 600 soniya
            
            # Haydovchiga xabar (Safar menyusi)
            await message.answer(
                f"✅ <b>Safar boshlandi!</b>\n\n"
                f"📦 Buyurtma #{order.order_id}\n\n"
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
                        text=f"✅ <b>Haydovchi yo'lga chiqdi!</b>\n\n"
                             f"📦 Buyurtma #{order_id}\n\n"
                             f"🚗 Xavfsiz yo'l!",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify passenger: {e}")
            
            logger.info(f"Trip started by driver: order={order_id}, driver={driver.driver_id}")
        else:
            await message.answer(f"❌ {result['message']}")


# ============================================
# YETIB KELDIM (GPS CHECK) - ESKILANGA
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
        await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
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
        await callback.answer(Messages.Error.CALLBACK_DATA_MISSING)
        return

    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, callback)
        if not driver:
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
                    f"⏱ <b>10 daqiqadan so'ng</b> safar avtomatik yakunlanadi.",
                    reply_markup=get_trip_active_keyboard(order_id)
                )
            
            logger.info(f"Trip started: order={order_id}, driver={driver.driver_id}")
        
        else:
            if callback.message is not None:
                await callback.message.edit_text(f"❌ {result['message']}") # type: ignore
    
    await callback.answer()


# ============================================
# SAFAR YAKUNLASH (MANUAL - O'CHIRILDI)
# ============================================

# @router.message(
#     DriverStates.trip_in_progress,
#     F.text == "🚗 Safarni yakunlash"
# )
# async def complete_trip_handler(message: Message, state: FSMContext):
#     """
#     Safar yakunlandi (Manual) - O'CHIRILDI (User talabi bilan 10 daqiqa auto)
#     """
#     await message.answer("⚠️ Safar avtomatik yakunlanadi (10 daqiqa).")


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
    Haydovchi yo'lovchi(lar) bilan bog'lanish uchun ma'lumotlarni ko'radi
    Barcha aktiv buyurtmalardagi yo'lovchilar ko'rsatiladi
    """
    user_id = message.from_user.id # type: ignore
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer(Messages.Error.DRIVER_NOT_FOUND)
            return
        
        # Barcha aktiv buyurtmalarni olish (ACCEPTED va IN_PROGRESS) - passenger ma'lumotlari bilan
        active_orders_result = await session.execute(
            select(Order)
            .options(selectinload(Order.passenger).selectinload(Passenger.user))
            .where(Order.driver_id == driver.driver_id)
            .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            .order_by(Order.created_at)
        )
        active_orders = active_orders_result.scalars().all()
        
        if not active_orders:
            await message.answer(Messages.Error.ACTIVE_ORDER_NOT_FOUND)
            return
        
        # Barcha yo'lovchilar ma'lumotlarini yig'ish
        from app.utils.location_helpers import get_google_maps_link
        
        passengers_info = []
        
        for idx, order in enumerate(active_orders, 1):
            if not order.passenger:
                continue
                
            passenger = order.passenger
            passenger_name = passenger.full_name
            passenger_phone = passenger.user.phone_number if passenger.user else "N/A"
            
            # Google Maps link
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
            passenger_text = f"""
<b>{idx}-mijoz</b>
👤 <b>Ism:</b> {passenger_name}
📍 <b>Manzil:</b> <a href="{google_maps_link}">{order.pickup_location}</a>
📱 <b>Telefon:</b> <code>{passenger_phone}</code>
{order_type}
            """.strip()
            
            passengers_info.append(passenger_text)
        
        # Barcha ma'lumotlarni birlashtirish
        contact_text = f"""
📞 <b>Yo'lovchilar ma'lumotlari</b>

{chr(10).join(passengers_info)}
        """.strip()
        
        
        await message.answer(
            contact_text,
            parse_mode="HTML",
            reply_markup=get_passenger_contact_keyboard(active_orders)
        )


@router.message(
    StateFilter(
        DriverStates.trip_in_progress, 
        DriverStates.trip_confirmation
    ),
    F.text == "❌ Buyurtmani bekor qilish"
)
async def cancel_order_handler(message: Message, state: FSMContext):
    """
    Haydovchi buyurtma(lar)ni bekor qiladi
    Barcha aktiv buyurtmalar ko'rsatiladi va tanlash mumkin
    
    DIQQAT: Bu firibgarlik hisoblanadi!
    """
    user_id = message.from_user.id # type: ignore
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer(Messages.Error.DRIVER_NOT_FOUND)
            return
        
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
                f"📦 Buyurtma #{order.order_id}\n\n"
                "Bu jiddiy harakat! Agar bekor qilsangiz:\n"
                "• Komissiya qaytarilmaydi\n"
                "• Warning olasiz\n"
                "• 3 ta warning = 24 soat ban\n\n"
                "Davom ettirish uchun 'Tasdiqlash' yozing"
            )
            await state.set_state(DriverStates.confirming_cancellation)
            return
        
        
        await message.answer(
            "⚠️ <b>Qaysi buyurtmani bekor qilmoqchisiz?</b>\n\n"
            "Tanlang:",
            reply_markup=get_order_cancellation_keyboard(active_orders),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("cancel_order_select:"))
async def cancel_order_select_handler(callback: CallbackQuery, state: FSMContext):
    """Bekor qilish uchun buyurtma tanlandi"""
    if callback.data is None:
        await callback.answer("Xatolik: data mavjud emas")
        return
    
    order_id = int(callback.data.split(":")[1])
    await state.update_data(cancel_order_id=order_id)
    
    if callback.message:
        await callback.message.edit_text(
            "⚠️ <b>Buyurtmani bekor qilmoqchimisiz?</b>\n\n"
            f"📦 Buyurtma #{order_id}\n\n"
            "Bu jiddiy harakat! Agar bekor qilsangiz:\n"
            "• Komissiya qaytarilmaydi\n"
            "• Warning olasiz\n"
            "• 3 ta warning = 24 soat ban\n\n"
            "Davom ettirish uchun 'Tasdiqlash' yozing",
            parse_mode="HTML"
        )
    
    await state.set_state(DriverStates.confirming_cancellation)
    await callback.answer()


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
    order_id = data.get('cancel_order_id') or data.get('current_order_id')
    
    if not order_id:
        await message.answer(Messages.Error.ORDER_NOT_FOUND)
        await state.clear()
        return
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer(Messages.Error.DRIVER_NOT_FOUND)
            await state.clear()
            return
        
        # Bekor qilish logikasi
        from sqlalchemy import update
        from app.core.database import transaction
        
        async with transaction() as trans_session:
            # Order'ni cancel qilish
            order_result = await trans_session.execute(
                select(Order).where(Order.order_id == order_id)
            )
            order = order_result.scalar_one_or_none()
            
            if not order:
                await message.answer(Messages.Error.ORDER_BUT_DRIVER_MISMATCH)
                await state.clear()
                return
            
            if order.driver_id != driver.driver_id:
                await message.answer(Messages.Error.ORDER_BUT_DRIVER_MISMATCH)
                await state.clear()
                return
            
            # Order'ni cancel qilish
            await trans_session.execute(
                update(Order)
                .where(Order.order_id == order_id)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason='driver_cancelled',
                    cancelled_at=func.now(),
                    driver_id=None
                )
            )
            
            # Driver'ni bo'shatish
            await trans_session.execute(
                update(Driver)
                .where(Driver.driver_id == driver.driver_id)
                .values(
                    available_seats=Driver.available_seats + order.passenger_count,
                    is_on_trip=False
                )
            )
            
            # Yo'lovchiga xabar
            if order.passenger:
                from app.bot.main import bot
                try:
                    await bot.send_message(
                        chat_id=order.passenger.user_id,
                        text=f"❌ <b>Buyurtma bekor qilindi</b>\n\n"
                             f"📦 Buyurtma #{order_id}\n\n"
                             f"Haydovchi buyurtmani bekor qildi.\n"
                             f"Yangi haydovchi topilmoqda...",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify passenger: {e}")
            
            # Yangi haydovchi topish
            find_driver_for_order_task.delay(order_id)
        
        await message.answer(
            Messages.Driver.ORDER_CANCELLED.format(order_id=order_id),
            parse_mode="HTML",
            reply_markup=get_driver_main_menu()
        )
        
        await state.clear()




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
        await callback.answer(Messages.Error.CALLBACK_DATA_MISSING)
        return
    
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        driver = await get_driver_or_error(session, user_id, callback)
        if not driver:
            return
        
        # ❗ Bloklangan?
        if driver.is_blocked:
            await callback.answer(
                Messages.Driver.BLOCKED.format(reason="Bloklangansiz"),
                show_alert=True
            )
            return
        
        from datetime import datetime, timedelta
        
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