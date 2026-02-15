import asyncio
import time
from app.services.queue_service import driver_queue
from app.models.driver import Driver
from app.core.database import get_session
from sqlalchemy import text

# Mock data
DRIVER_ID = 99999
ROUTE_ID = 1

async def test_priority_queue_logic():
    print("🚀 Starting Priority Queue Verification...")
    
    # Initialize DB
    from app.core.database import db_manager, init_database
    await init_database()

    # Initialize Redis
    from app.core.redis_client import redis_client
    await redis_client.connect()

    # 1. Setup: Clear previous state
    await driver_queue.remove_driver(DRIVER_ID, ROUTE_ID)
    # Models
    from app.models.user import User, UserRole
    from app.models.driver import Driver
    from app.models.route import Route

    async with get_session() as session:
        # Clean up existing test data
        await session.execute(text(f"DELETE FROM drivers WHERE driver_id = {DRIVER_ID}"))
        await session.execute(text(f"DELETE FROM users WHERE user_id = {DRIVER_ID}"))
        await session.execute(text(f"DELETE FROM routes WHERE route_id = {ROUTE_ID}"))
        await session.commit()

        # Insert Route (ORM)
        route = Route(
            route_id=ROUTE_ID,
            from_location="Test From",
            to_location="Test To",
            distance_km=10.0,
            fare_amount=10000,
            is_active=True
        )
        session.add(route)
        await session.flush()

        # Insert User (ORM)
        user = User(
            user_id=DRIVER_ID,
            phone_number='+998901234567',
            first_name='Test Driver',
            role=UserRole.DRIVER
        )
        session.add(user)
        await session.flush() # Ensure user exists before driver

        # Insert Driver (ORM)
        driver = Driver(
            driver_id=DRIVER_ID,
            user_id=DRIVER_ID,
            full_name='Test Driver',
            phone_number='+998901234567',
            car_model='Cobalt',
            car_color='White',
            car_number='01A123Test',
            is_active=True,
            is_priority=False,
            current_route_id=1,
            balance=0
        )
        session.add(driver)
        await session.commit()
    
    # 2. Add to queue (Normal)
    print("Step 1: Adding driver to queue (Normal)...")
    await driver_queue.add_driver(DRIVER_ID, ROUTE_ID)
    
    score_normal = await driver_queue.redis.client.zscore(f"driver_queue:{ROUTE_ID}", str(DRIVER_ID))
    print(f"   -> Score (Normal): {score_normal}")
    assert score_normal > 0, "Score should be positive (timestamp)"
    
    # 3. Toggle Priority ON
    print("Step 2: Toggling Priority ON...")
    success = await driver_queue.toggle_driver_priority(DRIVER_ID, True)
    assert success is True, "Toggle should succeed"
    
    score_priority = await driver_queue.redis.client.zscore(f"driver_queue:{ROUTE_ID}", str(DRIVER_ID))
    print(f"   -> Score (Priority): {score_priority}")
    assert score_priority < 0, "Score should be negative (timestamp - offset)"
    assert score_priority == score_normal - driver_queue.PRIORITY_OFFSET, "Score calculation mismatch"
    
    # 4. Toggle Priority OFF
    print("Step 3: Toggling Priority OFF...")
    success = await driver_queue.toggle_driver_priority(DRIVER_ID, False)
    assert success is True, "Toggle should succeed"
    
    score_back = await driver_queue.redis.client.zscore(f"driver_queue:{ROUTE_ID}", str(DRIVER_ID))
    print(f"   -> Score (Back): {score_back}")
    assert score_back > 0, "Score should be positive again"
    # Note: explicit float comparison might fail due to precision, but they should be very close. 
    # Since we strictly added/subtracted OFFSET, it should ideally be equal.
    assert abs(score_back - score_normal) < 0.001, "Score should return to original value"

    # 5. Add NEW Priority Driver
    print("Step 4: Adding NEW priority driver...")
    # Set priority in DB first
    async with get_session() as session:
        await session.execute(text(f"UPDATE drivers SET is_priority = true WHERE driver_id = {DRIVER_ID}"))
        await session.commit()
        
    await driver_queue.remove_driver(DRIVER_ID, ROUTE_ID)
    await driver_queue.add_driver(DRIVER_ID, ROUTE_ID)
    
    score_new_priority = await driver_queue.redis.client.zscore(f"driver_queue:{ROUTE_ID}", str(DRIVER_ID))
    print(f"   -> Score (New Priority Add): {score_new_priority}")
    assert score_new_priority < 0, "New priority driver should have negative score"

    # Cleanup
    await driver_queue.remove_driver(DRIVER_ID, ROUTE_ID)
    async with get_session() as session:
        await session.execute(text(f"DELETE FROM drivers WHERE driver_id = {DRIVER_ID}"))
        await session.execute(text(f"DELETE FROM users WHERE user_id = {DRIVER_ID}"))
        await session.execute(text(f"DELETE FROM routes WHERE route_id = {ROUTE_ID}"))
        await session.commit()
    
    print("✅ Verification Passed Successfuly!")
    
    await db_manager.close()
    await redis_client.close()

if __name__ == "__main__":
    asyncio.run(test_priority_queue_logic())
