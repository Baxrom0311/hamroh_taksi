"""
app/bot/handlers/driver/location.py

DRIVER LOCATION HANDLERS

BU HANDLER NIMA QILADI:
- Jonli joylashuv yuborish
- Lokatsiyani yangilash
- Lokatsiyani database'ga saqlash
"""

from ..base import *
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import get_route_selection_keyboard
from app.models.route import get_all_active_routes
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
@with_driver_session  # ✅ Decorator
async def location_received(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi lokatsiyasini yubordi (Oddiy yoki Live Location)
    
    ✅ REFACTORED: Session va driver avtomatik
    
    NIMA BO'LADI:
    1. Lokatsiyani database'ga saqlash
    2. PostGIS geometry yaratish
    3. Live location bo'lsa - real-time yangilanishni yoqish
    4. Marshrut tanlashga o'tish
    """
    try:
        if message.location is None:
            await message.answer("Xatolik: lokatsiya topilmadi")
            logger.error("Location handler: message.location is None")
            return
        
        location = message.location
        lat = location.latitude
        lon = location.longitude
        
        logger.info(f"📍 Location received from driver {driver.driver_id}: lat={lat}, lon={lon}")
        
        # Live location tekshirish
        is_live = hasattr(location, 'live_period') and location.live_period is not None
        
        # Lokatsiyani saqlash
        point_wkt = f"POINT({lon} {lat})"
        try:
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver.driver_id)
                .values(
                    last_location_lat=lat,
                    last_location_lon=lon,
                    location=geo_func.ST_GeomFromText(point_wkt, 4326)
                )
            )
            logger.debug("Location saved with PostGIS")
        except Exception as e:
            # Agar PostGIS bo'lmasa, faqat lat/lon saqlaymiz
            logger.warning(f"PostGIS location save failed, fallback to lat/lon: {e}")
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver.driver_id)
                .values(
                    last_location_lat=lat,
                    last_location_lon=lon
                )
            )
        
        await session.commit()
        logger.success(f"✅ Driver {driver.driver_id} location saved: lat={lat}, lon={lon}")
        
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
        
        # State o'zgartirish
        await state.set_state(DriverStates.choose_route)
        
    except Exception as e:
        logger.error(f"❌ Error in location_received: {e}", exc_info=True)
        await message.answer(Messages.Error.GENERIC)
        await state.clear()



# ============================================
# LOKATSIYANI YANGILASH (Aktiv haydovchi)
# ============================================

@router.message(
    DriverStates.waiting_orders,
    F.location
)
@with_driver_session  # ✅ Decorator
async def update_location_while_waiting(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Haydovchi aktiv bo'lganda lokatsiyasini yangilaydi (Real-time)
    
    ✅ REFACTORED: Session va driver avtomatik
    
    NIMA BO'LADI:
    1. Lokatsiyani yangilash
    2. Database'ga saqlash
    3. Silent update (xabar yuborilmaydi)
    """
    location = message.location
    lat = location.latitude if location else None
    lon = location.longitude if location else None
    
    point_wkt = f"POINT({lon} {lat})"
    try:
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == driver.driver_id)
            .values(
                last_location_lat=lat,
                last_location_lon=lon,
                location=geo_func.ST_GeomFromText(point_wkt, 4326)
            )
        )
    except Exception as e:
        logger.warning(f"PostGIS location update failed (waiting), fallback: {e}")
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == driver.driver_id)
            .values(
                last_location_lat=lat,
                last_location_lon=lon
            )
        )
    await session.commit()
    logger.debug(f"Driver {driver.driver_id} location updated: lat={lat}, lon={lon}")



# ============================================
# EDITED MESSAGE (Live Location Updates)
# ============================================

@router.edited_message(
    DriverStates.waiting_orders,
    F.location
)
@with_driver_session
async def handle_live_location_update(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Jonli joylashuv yangilanishlari (Live Location)
    """
    if message.location is None:
        return
    
    location = message.location
    
    # Live location uchun live_period tekshirish
    if hasattr(location, 'live_period') and location.live_period:
        lat = location.latitude
        lon = location.longitude
        
        point_wkt = f"POINT({lon} {lat})"
        try:
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver.driver_id)
                .values(
                    last_location_lat=lat,
                    last_location_lon=lon,
                    location=geo_func.ST_GeomFromText(point_wkt, 4326)
                )
            )
        except Exception as e:
            logger.warning(f"PostGIS live update failed, fallback: {e}")
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver.driver_id)
                .values(
                    last_location_lat=lat,
                    last_location_lon=lon
                )
            )
        await session.commit()
        logger.debug(f"Driver {driver.driver_id} live location updated: lat={lat}, lon={lon}")



__all__ = ['router']
