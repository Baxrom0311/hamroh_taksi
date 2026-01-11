"""
scripts/seed_system_settings.py

Default system settings'larni yuklash

ISHLATISH:
    python scripts/seed_system_settings.py
"""

import asyncio
import sys
from pathlib import Path

# Root path
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))

from app.core.database import get_session
from app.models.system_settings import seed_default_settings


async def main():
    """Default sozlamalarni yuklash"""
    print("\n🔄 Default system settings yuklanmoqda...\n")
    
    try:
        # Database'ni ishga tushirish
        from app.core.database import init_database
        await init_database()
        
        async with get_session() as session:
            await seed_default_settings(session)
            await session.commit()
        
        print("\n✅ Default sozlamalar muvaffaqiyatli yuklandi!\n")
        
        # Sozlamalarni ko'rsatish
        async with get_session() as session:
            from app.models.system_settings import get_setting
            
            print("📋 YUKLANGAN SOZLAMALAR:\n")
            print(f"  • commission_amount: {await get_setting(session, 'commission_amount', '5000')}")
            print(f"  • bot_is_free: {await get_setting(session, 'bot_is_free', 'true')}")
            print(f"  • ban_percentage_threshold: {await get_setting(session, 'ban_percentage_threshold', '50')}")
            print(f"  • ban_count_threshold: {await get_setting(session, 'ban_count_threshold', '5')}")
            print(f"  • max_driver_change_per_hour: {await get_setting(session, 'max_driver_change_per_hour', '3')}")
            print()
        
        # Database'ni yopish
        from app.core.database import close_database
        await close_database()
    
    except Exception as e:
        print(f"\n❌ Xatolik: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
