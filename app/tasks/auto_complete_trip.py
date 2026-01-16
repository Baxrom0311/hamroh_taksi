"""
app/tasks/matching.py - Auto Complete Trip Task (YANGILANGAN)

Trip-based auto-complete logic
"""

# Eski auto_complete_trip_task'ni almashtiring

@celery_app.task(name="app.tasks.matching.auto_complete_trip_task")
@async_to_sync
async def auto_complete_trip_task(trip_id: int):
    """
    Trip'ni avtomatik yakunlash (10 daqiqadan keyin)
    
    YANGI LOGIKA:
    1. Trip'dagi barcha orderlarni COMPLETED qilish
    2. Trip'ni COMPLETED qilish
    3. Driver'ni yangilash (is_on_trip=False)
    4. Yo'lovchilarga xabar
    5. Statistika yangilash
    
    Args:
        trip_id: Trip ID
    """
    logger.info(f"🕐 Auto-completing trip: trip_id={trip_id}")
    
    async with get_session() as session:
        # Trip'ni olish
        from app.models.trip import get_trip_by_id, complete_trip
        from app.models.driver import Driver
        from app.models.passenger import Passenger
        from sqlalchemy import select, update
        
        trip = await get_trip_by_id(session, trip_id)
        
        if not trip:
            logger.warning(f"Trip {trip_id} not found")
            return
        
        if trip.status != TripStatus.ACTIVE:
            logger.info(f"Trip {trip_id} already completed/cancelled")
            return
        
        # Trip'dagi barcha orderlarni olish
        result = await session.execute(
            select(Order)
            .options(
                selectinload(Order.passenger).selectinload(Passenger.user)
            )
            .where(Order.trip_id == trip_id)
            .where(Order.status == OrderStatus.IN_PROGRESS)
        )
        
        orders = result.scalars().all()
        
        if not orders:
            logger.warning(f"No IN_PROGRESS orders found for trip {trip_id}")
            return
        
        # 1. Barcha orderlarni COMPLETED qilish
        await session.execute(
            update(Order)
            .where(Order.trip_id == trip_id)
            .where(Order.status == OrderStatus.IN_PROGRESS)
            .values(
                status=OrderStatus.COMPLETED,
                completed_at=func.now()
            )
        )
        
        # 2. Trip'ni yakunlash
        await complete_trip(session, trip_id)
        
        # 3. Driver'ni yangilash
        driver_id = trip.driver_id
        
        await session.execute(
            update(Driver)
            .where(Driver.driver_id == driver_id)
            .values(
                is_on_trip=False,
                is_active=False,  # Navbatdan chiqarish
                available_seats=0,
                total_trips=Driver.total_trips + 1,
                last_trip_at=func.now()
            )
        )
        
        # 4. Yo'lovchilar statistikasini yangilash
        for order in orders:
            await session.execute(
                update(Passenger)
                .where(Passenger.passenger_id == order.passenger_id)
                .values(total_trips=Passenger.total_trips + 1)
            )
        
        await session.commit()
        
        # 5. Yo'lovchilarga xabar yuborish
        from app.bot.main import bot
        
        for order in orders:
            if order.passenger and order.passenger.user:
                try:
                    await bot.send_message(
                        chat_id=order.passenger.user.user_id,
                        text=f"✅ <b>Safar yakunlandi!</b>\n\n"
                             f"📦 Buyurtma #{order.order_id}\n"
                             f"🚗 Haydovchi: {trip.driver.full_name if trip.driver else 'N/A'}\n\n"
                             f"Rahmat! Haydovchini baholang ⭐",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify passenger: {e}")
        
        # 6. Haydovchiga xabar
        if trip.driver and trip.driver.user:
            try:
                await bot.send_message(
                    chat_id=trip.driver.user_id,
                    text=f"✅ <b>Trip yakunlandi!</b>\n\n"
                         f"🚗 Trip #{trip_id}\n"
                         f"👥 Jami yo'lovchilar: {len(orders)}\n\n"
                         f"Rahmat!",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to notify driver: {e}")
        
        logger.success(f"✅ Trip {trip_id} auto-completed with {len(orders)} orders")
        
        return {
            'trip_id': trip_id,
            'completed_orders': len(orders),
            'driver_id': driver_id
        }
