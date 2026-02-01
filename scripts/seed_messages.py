import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import get_session
from app.models.system_settings import seed_default_settings

async def main():
    print("🌱 Seeding default settings...")
    async with get_session() as session:
        await seed_default_settings(session)
        await session.commit()
    print("✅ Seeding complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
