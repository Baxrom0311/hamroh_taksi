"""
app/bot/handlers/driver/location.py

DRIVER LOCATION HANDLERS

BU HANDLER NIMA QILADI:
- Jonli joylashuv yuborish
- Lokatsiyani yangilash
- Lokatsiyani database'ga saqlash
"""

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.core.database import get_session, transaction
from app.models.driver import get_driver_by_user_id, Driver
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import get_route_selection_keyboard
from app.models.route import get_all_active_routes
from sqlalchemy import update
from geoalchemy2 import functions as geo_func
from geoalchemy2 import Geometry

router = Router()


# ============================================
# JONLI JOYLASHUV YUBORISH
# ============================================

@router.message(
    DriverStates.send_location,
    F.location
)
async def location_received(message: Message, state: FSMContext):
    """
    Haydovchi lokatsiyasini yubordi (Oddiy yoki Live Location)
    
    NIMA BO'LADI:
    1. Lokatsiyani database'ga saqlash
    2. PostGIS geometry yaratish
    3. Live location bo'lsa - real-time yangilanishni yoqish
    4. Marshrut tanlashga o'tish
    """
    if message.from_user is None or message.location is None:
        await message.answer("Xatolik: ma'lumotlar topilmadi")
        return
    
    user_id = message.from_user.id
    location = message.location
    
    lat = location.latitude
    lon = location.longitude
    
    # Live location tekshirish
    is_live = hasattr(location, 'live_period') and location.live_period is not None
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            await message.answer("❌ Haydovchi topilmadi")
            await state.clear()
            return
        
        # Lokatsiyani database'ga saqlash
        async with transaction() as session:
            # PostGIS geometry yaratish
            point_wkt = f"POINT({lon} {lat})"
            
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver.driver_id)
                .values(
                    last_location_lat=lat,
                    last_location_lon=lon,
                    location=geo_func.ST_GeomFromText(point_wkt, 4326)
                )
            )
            
            logger.info(
                f"Driver {driver.driver_id} location updated: "
                f"lat={lat}, lon={lon}, live={is_live}"
            )
        
        # Marshrut tanlashga o'tish
        routes = await get_all_active_routes(session)
        
        if not routes:
            await message.answer("❌ Hozirda aktiv marshrutlar yo'q")
            await state.clear()
            return
        
        location_text = "✅ <b>Jonli joylashuv yoqildi!</b>\n\n" if is_live else "✅ <b>Lokatsiya qabul qilindi!</b>\n\n"
        
        await message.answer(
            f"{location_text}"
            "📍 <b>Marshrut tanlang:</b>\n\n"
            "Qayerdan → Qayerga borasiz?",
            reply_markup=get_route_selection_keyboard(routes),
            parse_mode="HTML"
        )
        
        await state.set_state(DriverStates.choose_route)


# ============================================
# LOKATSIYANI YANGILASH (Aktiv haydovchi)
# ============================================

@router.message(
    DriverStates.waiting_orders,
    F.location
)
async def update_location_while_waiting(message: Message, state: FSMContext):
    """
    Haydovchi aktiv bo'lganda lokatsiyasini yangilaydi (Real-time)
    
    NIMA BO'LADI:
    1. Lokatsiyani yangilash
    2. Database'ga saqlash
    3. Silent update (xabar yuborilmaydi)
    """
    if message.from_user is None or message.location is None:
        return
    
    user_id = message.from_user.id
    location = message.location
    
    lat = location.latitude
    lon = location.longitude
    
    async with get_session() as session:
        driver = await get_driver_by_user_id(session, user_id)
        
        if not driver:
            return
        
        # Lokatsiyani yangilash
        async with transaction() as session:
            point_wkt = f"POINT({lon} {lat})"
            
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver.driver_id)
                .values(
                    last_location_lat=lat,
                    last_location_lon=lon,
                    location=geo_func.ST_GeomFromText(point_wkt, 4326)
                )
            )
            
            logger.debug(
                f"Driver {driver.driver_id} location updated (real-time): "
                f"lat={lat}, lon={lon}"
            )


# ============================================
# EDITED MESSAGE (Live Location Updates)
# ============================================

@router.edited_message(
    DriverStates.waiting_orders,
    F.location
)
async def handle_live_location_update(message: Message, state: FSMContext):
    """
    Jonli joylashuv yangilanishlari (Live Location)
    
    Telegram'da live location yuborilganda, har bir yangilanish
    edited_message sifatida keladi.
    """
    if message.from_user is None or message.location is None:
        return
    
    user_id = message.from_user.id
    location = message.location
    
    # Live location uchun live_period tekshirish
    if hasattr(location, 'live_period') and location.live_period:
        lat = location.latitude
        lon = location.longitude
        
        async with get_session() as session:
            driver = await get_driver_by_user_id(session, user_id)
            
            if not driver:
                return
            
            # Lokatsiyani yangilash
            async with transaction() as session:
                point_wkt = f"POINT({lon} {lat})"
                
                await session.execute(
                    update(Driver)
                    .where(Driver.driver_id == driver.driver_id)
                    .values(
                        last_location_lat=lat,
                        last_location_lon=lon,
                        location=geo_func.ST_GeomFromText(point_wkt, 4326)
                    )
                )
                
                logger.debug(
                    f"Driver {driver.driver_id} live location updated: "
                    f"lat={lat}, lon={lon}"
                )


__all__ = ['router']
