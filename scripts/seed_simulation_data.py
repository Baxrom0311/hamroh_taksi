import asyncio
import sys
import os
import random
from typing import List
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Patch GeoAlchemy2 for SQLite (Mock Geometry)
import sys
from sqlalchemy.types import TypeDecorator, TEXT

class MockGeometry(TypeDecorator):
    impl = TEXT
    
    def __init__(self, *args, **kwargs):
        # Ignore arguments like srid, spatial_index, etc.
        super().__init__()
        
    def process_bind_param(self, value, dialect):
        return str(value) if value else None
    def process_result_value(self, value, dialect):
        return value

# Mock module BEFORE imports
import types
mock_geo = types.ModuleType("geoalchemy2")
mock_geo.Geometry = MockGeometry
sys.modules["geoalchemy2"] = mock_geo

# Now import project modules
from app.core.database import Base
from app.models.user import User, UserRole
from app.models.driver import Driver
from app.models.passenger import Passenger, Gender
# Removed invalid imports (location, transport, payment)

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# Simulation DB URL
SIMULATION_DB_URL = "sqlite+aiosqlite:///simulation.db"

# Init DB Engine
engine = create_async_engine(SIMULATION_DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    print(f"{YELLOW}🔄 Creating tables in simulation.db...{RESET}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print(f"{GREEN}✅ Tables created.{RESET}")

async def seed_data():
    async with AsyncSessionLocal() as session:
        print(f"{YELLOW}🌱 Seeding 1000 Users...{RESET}")
        
        # 1. Routes (Places)
        # Simplified: We just need Places to link Routes.
        # In this system route is often just ID in logic, but let's create Places if needed.
        # Actually, booking logic uses 'route_id'. We will assume route_id 1..5 exists in logic.
        
        users: List[User] = []
        drivers: List[Driver] = []
        passengers: List[Passenger] = []
        
        # 2. Drivers (500)
        for i in range(1, 501):
            uid = 1000 + i
            phone = f"+99890{i:07d}"
            
            user = User(
                user_id=uid,
                phone_number=phone,
                first_name=f"Driver_{i}",
                role=UserRole.DRIVER,
                username=f"driver_{i}"
            )
            users.append(user)
            
            # Driver
            driver = Driver(
                driver_id=i,  # Explicit ID
                user_id=uid,
                full_name=f"Driver_{i}",
                phone_number=phone,
                car_model="Chevrolet Cobalt",
                car_color="White",
                car_number=f"01 {i:03d} AAA",
                balance=100000,
                rating=round(random.uniform(4.0, 5.0), 1),
                available_seats=4,
                is_active=True,
                last_location_lat=41.31 + random.uniform(-0.05, 0.05),
                last_location_lon=69.24 + random.uniform(-0.05, 0.05)
            )
            drivers.append(driver)
            
        # 3. Passengers (500)
        for i in range(1, 501):
            uid = 2000 + i
            phone = f"+99891{i:07d}"
            
            user = User(
                user_id=uid,
                phone_number=phone,
                first_name=f"Passenger_{i}",
                role=UserRole.PASSENGER,
                username=f"passenger_{i}"
            )
            users.append(user)
            
            passenger = Passenger(
                passenger_id=i, # Explicit ID
                user_id=uid,
                gender=random.choice(list(Gender)),
                age=random.randint(18, 60),
                full_name=f"Passenger_{i}",
                phone_number=phone
            )
            passengers.append(passenger)
            
        print(f"Adding objects to session...")
        session.add_all(users)
        await session.flush() # To ensure user_ids exist for users
        
        session.add_all(drivers)
        session.add_all(passengers)
        
        await session.commit()
        print(f"{GREEN}✅ Seeded: 500 Drivers, 500 Passengers.{RESET}")

async def main():
    await init_db()
    await seed_data()
    print(f"{GREEN}✨ Simulation Data Ready! ✨{RESET}")

if __name__ == "__main__":
    asyncio.run(main())
