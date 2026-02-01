
import asyncio
import sys
import os
import random
import time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update
from unittest.mock import MagicMock
import types
from sqlalchemy.types import TypeDecorator, TEXT

# 1. SETUP ENVIRONMENT
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Patch GeoAlchemy2 for SQLite (Mock Geometry)
class MockGeometry(TypeDecorator):
    impl = TEXT
    def __init__(self, *args, **kwargs): super().__init__()
    def process_bind_param(self, value, dialect): return str(value) if value else None
    def process_result_value(self, value, dialect): return value

mock_geo = types.ModuleType("geoalchemy2")
mock_geo.Geometry = MockGeometry
sys.modules["geoalchemy2"] = mock_geo

import os
# Must be set before imports
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["REDIS_PASSWORD"] = ""

# Imports
from app.core.database import Base
from app.models.user import User
from app.models.driver import Driver
from app.models.passenger import Passenger
from app.models.order import Order, OrderStatus
from app.services.queue_service import DriverQueueManager
from app.core.redis_client import RedisClient

# 2. CONFIG: DOCKER CONNECTION
DB_URL = "postgresql+asyncpg://hamroh_user:root@localhost:5433/hamroh_bot"

CONCURRENT_USERS = 50

# Init Resources
# Engine for Postgres
engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Real Redis Client
queue_service = DriverQueueManager()
# We trust it picks up env vars

STATS = {
    "created": 0,
    "matched": 0,
    "accepted": 0,
    "failed": 0,
    "no_driver": 0
}

from contextlib import asynccontextmanager
@asynccontextmanager
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Patch Queue Service DB
import app.services.queue_service as qs_module
qs_module.get_session = get_db

async def simulate_driver_queue_population():
    """Populate queue with all active drivers"""
    print(f"📥 Populating Driver Queue (Docker Postgres)...")
    async with AsyncSessionLocal() as session:
        # Check if we have drivers in DB? 
        # Since it's a fresh docker volume, it might be empty!
        # We need to seed it first if empty.
        result = await session.execute(select(Driver))
        drivers = result.scalars().all()
        
        # Seed Routes
        from app.models.route import Route
        # Ensure all 5 routes exist
        for i in range(1, 6):
            r = await session.get(Route, i)
            if not r:
                session.add(Route(
                    route_id=i, 
                    from_location=f"Start {i}", 
                    to_location=f"End {i}", 
                    fare_amount=5000,
                    distance_km=10.0
                ))
        await session.commit()
        print("✅ Verified/Seeded 5 routes.")

        # Check drivers
        result = await session.execute(select(Driver))
        drivers = result.scalars().all()
        
        if not drivers:
            print("⚠️ DB is empty! Seeding drivers...")
            # ... (seeding code)
            for i in range(100):
                u = User(user_id=1000+i, username=f"d{i}", first_name=f"Driver {i}", phone_number=f"998900000{i}")
                session.add(u)
                d = Driver(
                    driver_id=u.user_id, 
                    status="active", 
                    is_active=True, 
                    available_seats=4, 
                    user=u, 
                    balance=50000, 
                    current_route_id=random.randint(1,5),
                    last_location_lat=41.0 + (random.random() - 0.5) * 0.01,
                    last_location_lon=69.0 + (random.random() - 0.5) * 0.01
                )
                session.add(d)
            await session.commit()
            print("✅ Seeded 100 drivers.")
            
        # Refresh and FORCE UPDATE locations
        result = await session.execute(select(Driver))
        drivers = result.scalars().all()
        for d in drivers:
            d.last_location_lat = 41.0 + (random.random() - 0.5) * 0.01
            d.last_location_lon = 69.0 + (random.random() - 0.5) * 0.01
            # Ensure route is valid (1-5)
            if not d.current_route_id or d.current_route_id > 5:
                d.current_route_id = random.randint(1, 5)
                
        await session.commit()
        print(f"🔄 Updated locations for {len(drivers)} drivers.")

        # Connect Redis
        await queue_service.redis.connect()
        await queue_service.redis.client.flushdb()
        print("🧹 Redis flushed.")
        
        for driver in drivers:
            route_id = driver.current_route_id or 1
            await queue_service.add_driver(driver.driver_id, route_id)

        
        print(f"✅ Queue Populated with {len(drivers)} drivers.")

async def create_order(session, passenger_id, route_id):
    order = Order(
        passenger_id=passenger_id,
        route_id=route_id,
        status=OrderStatus.PENDING,
        pickup_location="Toshkent Docker Test",
        pickup_lat=41.0,
        pickup_lon=69.0,
        passenger_count=1,
        has_luggage=False
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order

async def user_flow(passenger_id):
    async with AsyncSessionLocal() as session:
        try:
            # Ensure passenger exists
            p = await session.get(Passenger, passenger_id)
            if not p:
                u = User(user_id=passenger_id, first_name=f"Pass {passenger_id}", phone_number=f"99890123{passenger_id}")
                session.add(u)
                p = Passenger(
                    passenger_id=passenger_id, 
                    user=u,
                    full_name=f"Pass {passenger_id}",
                    gender="male", # Using string as simple enum mock or we need the enum class
                    age=25,
                    phone_number=f"99890123{passenger_id}"
                )
                session.add(p)
                await session.commit()



            route_id = random.randint(1, 5)
            order = await create_order(session, passenger_id, route_id)
            STATS["created"] += 1
            
            # Match
            driver_found = None
            for _ in range(3):
                driver_id = await queue_service.get_next_driver(
                    route_id, 
                    passenger_location={'lat': 41.0, 'lon': 69.0}
                )
                if driver_id:
                    locked = await queue_service.lock_driver_for_offer(driver_id, order.order_id)
                    if locked:
                        driver_found = driver_id
                        break
                await asyncio.sleep(0.1)
            
            if driver_found:
                STATS["matched"] += 1
                if random.random() < 0.9:
                    await queue_service.remove_driver(driver_found, route_id)
                    order.status = OrderStatus.ACCEPTED
                    order.driver_id = driver_found
                    await session.commit()
                    STATS["accepted"] += 1
            else:
                STATS["no_driver"] += 1

        except Exception as e:
            STATS["failed"] += 1
            print(f"Error: {e}")

async def main():
    print(f"🚀 Starting Docker Load Test ({CONCURRENT_USERS} users)...")
    await simulate_driver_queue_population()
    
    tasks = []
    test_passenger_ids = list(range(2000, 2000 + CONCURRENT_USERS))
    
    start_time = time.time()
    for pid in test_passenger_ids:
        tasks.append(user_flow(pid))
    
    await asyncio.gather(*tasks)
    duration = time.time() - start_time
    
    print(f"\n=== DOCKER TEST REPORT ===")
    print(f"Time Taken: {duration:.2f}s")
    print(f"Orders Created: {STATS['created']}")
    print(f"Matched: {STATS['matched']}")
    print(f"Accepted: {STATS['accepted']}")
    print(f"No Driver: {STATS['no_driver']}")
    print(f"Errors: {STATS['failed']}")

if __name__ == "__main__":
    asyncio.run(main())
