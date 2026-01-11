#!/usr/bin/env python3
"""
scripts/seed_routes.py

MARSHRUTLARNI DATABASE'GA QO'SHISH

BU SCRIPT NIMA QILADI:
- Default marshrutlarni database'ga qo'shadi
- Gurlan, Vazir, Qoratol, etc.

ISHLATISH:
    python scripts/seed_routes.py
"""

import asyncio
import sys
from pathlib import Path

# Root path qo'shish
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))

from loguru import logger
from app.core.database import init_database, get_session
from app.models.route import Route, create_route, find_route


# ============================================
# DEFAULT ROUTES
# ============================================

DEFAULT_ROUTES = [
    {
        'from_location': 'Gurlan',
        'to_location': 'Vazir',
        'from_location_lat': 41.8453,
        'from_location_lon': 60.4015,
        'to_location_lat': 41.3775,
        'to_location_lon': 60.3614,
        'distance_km': 51.5
    },
    {
        'from_location': 'Vazir',
        'to_location': 'Gurlan',
        'from_location_lat': 41.3775,
        'from_location_lon': 60.3614,
        'to_location_lat': 41.8453,
        'to_location_lon': 60.4015,
        'distance_km': 51.5
    },
    {
        'from_location': 'Gurlan',
        'to_location': 'Qoratol',
        'from_location_lat': 41.8453,
        'from_location_lon': 60.4015,
        'to_location_lat': 41.6667,
        'to_location_lon': 60.3167,
        'distance_km': 35.0
    },
    {
        'from_location': 'Qoratol',
        'to_location': 'Gurlan',
        'from_location_lat': 41.6667,
        'from_location_lon': 60.3167,
        'to_location_lat': 41.8453,
        'to_location_lon': 60.4015,
        'distance_km': 35.0
    },
    {
        'from_location': 'Vazir',
        'to_location': 'Urganch',
        'from_location_lat': 41.3775,
        'from_location_lon': 60.3614,
        'to_location_lat': 41.5500,
        'to_location_lon': 60.6333,
        'distance_km': 28.0
    },
    {
        'from_location': 'Urganch',
        'to_location': 'Vazir',
        'from_location_lat': 41.5500,
        'from_location_lon': 60.6333,
        'to_location_lat': 41.3775,
        'to_location_lon': 60.3614,
        'distance_km': 28.0
    },
]


# ============================================
# SEED FUNCTION
# ============================================

async def seed_routes():
    """
    Marshrutlarni database'ga qo'shish
    """
    
    logger.info("🌱 Starting route seeding...")
    
    # Database init
    await init_database()
    
    async with get_session() as session:
        created_count = 0
        skipped_count = 0
        
        for route_data in DEFAULT_ROUTES:
            # Mavjudligini tekshirish
            existing = await find_route(
                session,
                route_data['from_location'],
                route_data['to_location']
            )
            
            if existing:
                logger.info(
                    f"⏭️  Skipped: {route_data['from_location']} → {route_data['to_location']} "
                    f"(already exists)"
                )
                skipped_count += 1
                continue
            
            # Yangi marshrut yaratish
            route = await create_route(session, **route_data)
            
            logger.success(
                f"✅ Created: {route.from_location} → {route.to_location} "
                f"({route.distance_km} km)"
            )
            
            created_count += 1
        
        # Commit
        await session.commit()
    
    # Summary
    logger.info("━" * 60)
    logger.success(f"✅ Route seeding completed!")
    logger.info(f"   Created: {created_count}")
    logger.info(f"   Skipped: {skipped_count}")
    logger.info(f"   Total: {len(DEFAULT_ROUTES)}")
    logger.info("━" * 60)


# ============================================
# MAIN
# ============================================

async def main():
    """Main function"""
    try:
        await seed_routes()
    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🌱 HAMROH BOT - ROUTE SEEDING")
    print("=" * 60 + "\n")
    
    asyncio.run(main())
    
    print("\n✅ Done!\n")