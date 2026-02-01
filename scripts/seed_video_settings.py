import asyncio
import sys
import os

# Add parent dir to path to import app modules
sys.path.append(os.getcwd())

from app.core.database import get_session, init_database
from app.models.system_settings import set_setting

async def main():
    print("Database init...")
    await init_database()
    
    print("Seeding video settings...")
    async with get_session() as session:
        await set_setting(session, 'onboarding_video_1_id', '', 'Start bosilganda yuboriladigan 1-video ID')
        await set_setting(session, 'onboarding_video_2_id', '', 'Start bosilganda yuboriladigan 2-video ID')
        await session.commit()
    print("✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())
