import asyncio
from sqlalchemy import text
from app.core.database import db_manager
from config.settings import settings

async def fix_sequences():
    print(f"DB URL: {settings.database_url}")
    print(f"Manager ID: {id(db_manager)}")
    
    print("Initializing engine...")
    db_manager.init_engine()
    
    if db_manager._session_factory is None:
        print("ERROR: Session factory is None after init!")
        return

    print("Session factory created.")
    
    async with db_manager.session_factory() as session:
        print("Fixing routes sequence...")
        # Reset sequence to max id + 1
        stmt = text("SELECT setval('routes_route_id_seq', (SELECT MAX(route_id) FROM routes) + 1);")
        await session.execute(stmt)
        await session.commit()
        print("Sequence fixed!")

if __name__ == "__main__":
    asyncio.run(fix_sequences())
