"""
app/core/database.py

BU FAYL NIMA QILADI:
- PostgreSQL database'ga ulanadi
- Connection pool yaratadi (ko'p user uchun tez ishlash)
- Async query'lar uchun session beradi
- Transaction management (COMMIT, ROLLBACK)

ISHLATISH:
    from app.core.database import get_session
    
    async with get_session() as session:
        result = await session.execute(query)
"""

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import AsyncAdaptedQueuePool
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from loguru import logger
from sqlalchemy import text
from config.settings import settings
from typing import cast, Optional


# ============================================
# BASE CLASS (Barcha model'lar bundan meros oladi)
# ============================================

Base = declarative_base()
# BU NIMA: Barcha database model'lar (User, Driver, Order) Base dan kelib chiqadi
# MISOL:
#   class User(Base):
#       __tablename__ = 'users'
#       ...


# ============================================
# DATABASE ENGINE (Asosiy ulanish)
# ============================================

class DatabaseManager:
    """
    Database bilan ishlash uchun manager class
    
    BU CLASS NIMA QILADI:
    1. Engine yaratadi (database connection)
    2. Session factory yaratadi (har bir so'rov uchun)
    3. Connection pool boshqaradi
    """
    
    def __init__(self):
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker | None = None
    
    def init_engine(self):
        """
        Database engine'ni yaratish
        
        ENGINE NIMA:
        - Database'ga asosiy ulanish
        - Connection pool (10-50 ta ulanish)
        - Async ishlaydi (blocking yo'q)
        """
        
        # Development va Production uchun turli sozlamalar
        if settings.is_production:
            # PRODUCTION: Pool bilan (ko'p foydalanuvchi)
            pool_config = {
                "poolclass": AsyncAdaptedQueuePool,
                "pool_size": 20,        # Min connection'lar
                "max_overflow": 30,      # Qo'shimcha connection'lar
                "pool_timeout": 30,      # Kutish vaqti (soniya)
                "pool_recycle": 3600,    # 1 soatda connection'ni yangilash
                "pool_pre_ping": True,   # Connection tekshiruvi
            }
            logger.info("🚀 Production database pool configured")
        else:
            # DEVELOPMENT: Oddiy pool (test uchun)
            pool_config = {
                "poolclass": AsyncAdaptedQueuePool,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,
            }
            logger.info("🔧 Development database pool configured")
        
        # Engine yaratish
        self._engine = create_async_engine(
            settings.database_url,
            echo=settings.is_development,  # SQL query'larni chiqarish (development)
            future=True,                   # SQLAlchemy 2.0 style
            **pool_config
        )
        
        # Session factory yaratish
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Object'lar commit'dan keyin ham ishlaydi
            autoflush=False,         # Manual flush
            autocommit=False,        # Manual commit
        )
        
        logger.success(f"✅ Database engine initialized: {settings.DB_NAME}")
    
    @property
    def engine(self) -> AsyncEngine:
        """Engine'ni olish"""
        if self._engine is None:
            raise RuntimeError("Database engine initialized emas! init_engine() ni chaqiring.")
        return self._engine
    
    @property
    def session_factory(self) -> async_sessionmaker:
        """Session factory'ni olish"""
        if self._session_factory is None:
            raise RuntimeError("Session factory initialized emas!")
        return self._session_factory
    
    async def close(self):
        """
        Database connection'larni yopish
        
        QACHON: Bot o'chganda yoki restart'da
        """
        if self._engine:
            await self._engine.dispose()
            logger.info("🔌 Database connections closed")


# ============================================
# GLOBAL DATABASE MANAGER
# ============================================

# BU OBJECT BUTUN LOYIHADA ISHLATILADI
db_manager = DatabaseManager()


# ============================================
# SESSION OLISH (Context Manager)
# ============================================

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session olish (async with bilan)
    
    ISHLATISH:
        async with get_session() as session:
            user = await session.execute(
                select(User).where(User.user_id == 123)
            )
    
    NIMA BO'LADI:
    1. Session ochiladi
    2. Siz query bajarasiz
    3. Auto COMMIT (xato bo'lmasa)
    4. Auto ROLLBACK (xato bo'lsa)
    5. Session yopiladi
    """
    
    session = db_manager.session_factory()
    
    try:
        yield session  # Session'ni berish
        await session.commit()  # Auto commit
    except Exception as e:
        # Aiogram SkipHandler kabi control-flow istisnolari uchun log yozmaymiz
        if e.__class__.__name__ == "SkipHandler":
            await session.rollback()
            raise
        await session.rollback()  # Xato bo'lsa rollback
        logger.error(f"❌ Database error: {e}")
        raise  # Xatoni qaytarish
    finally:
        await session.close()  # Session'ni yopish


# ============================================
# TRANSACTION CONTEXT MANAGER
# ============================================

@asynccontextmanager
async def transaction():
    """
    Explicit transaction (COMMIT/ROLLBACK qo'lda)
    
    ✅ FIX: get_session() auto-commit va session.begin() double commit muammosi tuzatildi.
    session.begin() o'zi commit/rollback boshqaradi, shuning uchun get_session() 
    auto-commit'ni bypass qilamiz.
    
    ISHLATISH:
        async with transaction() as session:
            await session.execute(...)
            # Auto COMMIT yoki ROLLBACK
    """
    session = db_manager.session_factory()
    try:
        async with session.begin():
            yield session
            # session.begin() exits → auto COMMIT
    except Exception as e:
        # session.begin() exits with exception → auto ROLLBACK
        if e.__class__.__name__ != "SkipHandler":
            logger.error(f"❌ Transaction error: {e}")
        raise
    finally:
        await session.close()


# ============================================
# DATABASE INITIALIZATION
# ============================================

async def init_database():
    """
    Database'ni ishga tushirish
    
    QACHON: Bot start bo'lganda
    
    NIMA QILADI:
    1. Engine yaratadi
    2. Connection test qiladi
    3. Jadvallar borligini tekshiradi
    """
    
    logger.info("🔄 Initializing database...")
    
    # Engine yaratish
    db_manager.init_engine()
    
    # Connection test
    try:
        async with get_session() as session:
            result = await session.execute(text("SELECT 1"))
            logger.success("✅ Database connection successful!")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        raise
    
    # Jadvallarni yaratish (Development'da)
    if settings.is_development:
        async with db_manager.engine.begin() as conn:
            # await conn.run_sync(Base.metadata.create_all)
            # DIQQAT: Production'da Alembic ishlatamiz!
            logger.info("📋 Using Alembic for migrations")


async def close_database():
    """
    Database'ni yopish
    
    QACHON: Bot o'chganda
    """
    logger.info("🔄 Closing database connections...")
    await db_manager.close()


# ============================================
# HELPER FUNCTIONS
# ============================================

async def check_database_health() -> dict:
    """
    Database sog'ligini tekshirish
    
    QAYTARADI:
        {
            'status': 'healthy' | 'unhealthy',
            'message': str,
            'pool_size': int,
            'pool_available': int
        }
    
    QACHON: /health endpoint'da
    """
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        
        # Pool statistikasi
        pool = cast(AsyncAdaptedQueuePool, db_manager.engine.pool)

        return {
            'status': 'healthy',
            'message': 'Database connection OK',
            'pool_size': pool.size(),
            'pool_available': pool.size() - pool.checkedout()
        }
    
    except Exception as e:
        return {
            'status': 'unhealthy',
            'message': f'Database error: {str(e)}',
            'pool_size': 0,
            'pool_available': 0
        }


# ============================================
# QUERY HELPER (Opsional - Qulaylik uchun)
# ============================================

async def fetch_one(query: str, params: Optional[dict] = None):
    """
    Bitta qatorni olish
    
    ISHLATISH:
        user = await fetch_one(
            "SELECT * FROM users WHERE user_id = :id",
            {'id': 123}
        )
    """
    async with get_session() as session:
        result = await session.execute(text(query), params or {})
        return result.fetchone()


async def fetch_all(query: str, params: Optional[dict] = None):
    """
    Barcha qatorlarni olish
    
    ISHLATISH:
        drivers = await fetch_all(
            "SELECT * FROM drivers WHERE is_active = :active",
            {'active': True}
        )
    """
    async with get_session() as session:
        result = await session.execute(text(query), params or {})
        return result.fetchall()


async def execute_query(query: str, params: Optional[dict] = None):
    """
    Query bajarish (INSERT, UPDATE, DELETE)
    
    ISHLATISH:
        await execute_query(
            "UPDATE drivers SET balance = balance - :amount WHERE driver_id = :id",
            {'amount': 5000, 'id': 123}
        )
    """
    async with get_session() as session:
        await session.execute(text(query), params or {})
        await session.commit()


# ============================================
# FAYLNI TEST QILISH
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.core.database
    """
    import asyncio
    
    async def test_database():
        print("\n🧪 Testing database connection...\n")
        
        # Initialize
        await init_database()
        
        # Health check
        health = await check_database_health()
        print(f"Health: {health}")
        
        # Close
        await close_database()
        
        print("\n✅ Database test completed!\n")
    
    asyncio.run(test_database())
