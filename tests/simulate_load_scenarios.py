import asyncio
import sys
import os
import random
import time
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Patch GeoAlchemy2 for SQLite (Mock Geometry)
# MUST BE DONE BEFORE IMPORTS
import types
from sqlalchemy.types import TypeDecorator, TEXT
class MockGeometry(TypeDecorator):
    impl = TEXT
    def __init__(self, *args, **kwargs): super().__init__()
    def process_bind_param(self, value, dialect): return str(value) if value else None
    def process_result_value(self, value, dialect): return value

mock_geo = types.ModuleType("geoalchemy2")
mock_geo.Geometry = MockGeometry
sys.modules["geoalchemy2"] = mock_geo

# Imports
from app.core.database import Base
from app.models.user import User
from app.models.driver import Driver
from app.models.passenger import Passenger
from app.models.order import Order, OrderStatus
from app.services.queue_service import DriverQueueManager
from app.core.redis_client import RedisClient # Using real class but backed by fake redis

import fakeredis.aioredis

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

# Simulation Config
SIMULATION_DB_URL = "sqlite+aiosqlite:///simulation.db"
CONCURRENT_USERS = 100

# Init Resources
# Increase pool size for load testing
engine = create_async_engine(
    SIMULATION_DB_URL, 
    echo=False,
    pool_size=20,
    max_overflow=40
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Mock Queue Service
# Use real RedisClient wrapper but inject fake redis
from app.services import queue_service as qs_module
qs_module.get_session = get_db # ✅ Patch DB Session

queue_service = DriverQueueManager()
queue_service.redis = RedisClient() # Real wrapper
queue_service.redis._client = fake_redis # Fake backend

STATS = {
    "created": 0,
    "matched": 0,
    "accepted": 0,
    "failed": 0,
    "no_driver": 0
}

# Duplicate get_db removed

async def simulate_driver_queue_population():
    """Populate queue with all active drivers"""
    print(f"{BLUE}📥 Populating Driver Queue...{RESET}")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Driver).where(Driver.is_active == True))
        drivers = result.scalars().all()
        
        for driver in drivers:
            # Add to Queue (Route 1-5 random)
            route_id = random.randint(1, 5)
            # Update DB
            driver.current_route_id = route_id
            await queue_service.add_driver(driver.driver_id, route_id)
        
        await session.commit()
        print(f"{GREEN}✅ Queue Populated with {len(drivers)} drivers.{RESET}")

async def create_order(session, passenger_id, route_id):
    order = Order(
        # user_id argument removed
        passenger_id=passenger_id,
        route_id=route_id,
        status=OrderStatus.PENDING, # ✅ Fixed Status
        # seats_count removed (using passenger_count)
        pickup_location="Toshkent", # ✅ Fixed field name
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
    """
    Simulates one user journey:
    1. Create Order
    2. Wait for Driver Match (Queue Service)
    3. Accept/Reject (Simulated)
    """
    async with AsyncSessionLocal() as session:
        try:
            start_time = time.time()
            route_id = random.randint(1, 5)
            
            # 1. Create Order
            # Need to find actual passenger user_id ? No, just use passenger_id FK is enough for simulation?
            # Model needs user_id or passenger_id? 
            # Order model links to Passenger via passenger_id.
            
            order = await create_order(session, passenger_id, route_id)
            STATS["created"] += 1
            
            # 2. Match Driver (Simulate Task)
            # Try 3 times to find a driver
            driver_found = None
            for attempt in range(3):
                # ✅ Pass location as DICT to fix tuple index error
                driver_id = await queue_service.get_next_driver(
                    route_id, 
                    passenger_location={'lat': 41.0, 'lon': 69.0}
                )
                if driver_id:
                    # driver_id is already an int return
                    
                    # Lock Driver
                    locked = await queue_service.lock_driver_for_offer(driver_id, order.order_id)
                    if locked:
                        driver_found = driver_id
                        break
                await asyncio.sleep(0.1) # Simulate delay
            
            if not driver_found:
                STATS["no_driver"] += 1
                return

            STATS["matched"] += 1
            
            # 3. Driver Accepts (Simulated probability 80%)
            if random.random() < 0.8:
                # Accept
                # Remove from Queue
                await queue_service.remove_driver(driver_found, route_id)
                
                # Update Order
                order.status = OrderStatus.ACCEPTED
                order.driver_id = driver_found
                await session.commit()
                
                STATS["accepted"] += 1
            else:
                # Reject/Timeout
                # In real system, lock expires. Here we just count it as missed matching opportunity
                pass
                
        except Exception as e:
            STATS["failed"] += 1
            print(f"{RED}Error passenger {passenger_id}: {e}{RESET}")

async def main():
    print(f"{YELLOW}🚀 Starting Load Test ({CONCURRENT_USERS} users)...{RESET}")
    
    # 1. Populate Queues
    await simulate_driver_queue_population()
    
    # 2. Run Scenarios
    tasks = []
    # Passenger IDs 1..500 exist
    test_passenger_ids = list(range(1, CONCURRENT_USERS + 1))
    
    start_time = time.time()
    for pid in test_passenger_ids:
        tasks.append(user_flow(pid))
    
    await asyncio.gather(*tasks)
    duration = time.time() - start_time
    
    # 3. Report
    print(f"\n{BLUE}=== SIMULATION REPORT ==={RESET}")
    print(f"Time Taken: {duration:.2f}s")
    print(f"Orders Created: {STATS['created']}")
    print(f"Matched: {STATS['matched']}")
    print(f"Accepted: {STATS['accepted']} (Happy Path)")
    print(f"No Driver Found: {STATS['no_driver']}")
    print(f"Errors: {STATS['failed']}")
    print(f"=========================")

if __name__ == "__main__":
    asyncio.run(main())
