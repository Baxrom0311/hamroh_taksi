"""
tests/fixtures/database.py

DATABASE TEST FIXTURES

BU FAYL NIMA QILADI:
- Test uchun database setup/teardown
- Isolated test database
- Transaction rollback after each test
- Async support

ISHLATISH:
    import pytest
    
    async def test_create_user(db_session):
        user = User(...)
        db_session.add(user)
        await db_session.commit()
        # Test logic
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool

from app.core.database import Base
from config.settings import settings


# Test database URL
TEST_DATABASE_URL = f"postgresql+asyncpg://test_user:test_password@localhost:5432/test_hamroh_bot"

# Override with actual test database if configured
if hasattr(settings, 'TEST_DATABASE_URL'):
    TEST_DATABASE_URL = settings.TEST_DATABASE_URL


@pytest.fixture(scope="session")
def event_loop():
    """
    Event loop fixture for async tests
    
    SCOPE: session - Butun test session uchun bitta loop
    """
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """
    Test database engine
    
    SCOPE: session - Bir marta yaratiladi, barcha testlarda ishlatiladi
    
    FEATURES:
    - Isolated test database
    - NullPool - har test uchun yangi connection
    - Echo SQL queries (debug uchun)
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,  # True qilsangiz barcha SQL query'lar ko'rinadi
        poolclass=NullPool,  # Test uchun connection pool yo'q
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine):
    """
    Database session fixture
    
    SCOPE: function - Har test uchun yangi session
    
    FEATURES:
    - Auto rollback after each test (isolation)
    - No need to manually clean up data
    
    ISHLATISH:
        async def test_something(db_session):
            user = User(...)
            db_session.add(user)
            await db_session.commit()
            # Test automatically rolled back after this
    """
    # Create session factory
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        async with session.begin():
            yield session
            # Rollback after test
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def db_session_no_rollback(test_engine):
    """
    Database session without auto-rollback
    
    QACHON KERAK:
    - Commit'dan keyin ma'lumotlarni tekshirish kerak
    - Integration testlar
    
    DIQQAT: Manual cleanup kerak!
    """
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.close()


# ============================================
# HELPER FUNCTIONS
# ============================================

async def clean_database(session: AsyncSession) -> None:
    """
    Database'ni tozalash (barcha ma'lumotlarni o'chirish)
    
    DIQQAT: Faqat test database'da ishlatish!
    
    ISHLATISH:
        async def test_something(db_session):
            await clean_database(db_session)
            # Clean slate for testing
    """
    from sqlalchemy import text
    
    # Disable foreign key checks
    await session.execute(text("SET session_replication_role = 'replica';"))
    
    # Get all table names
    tables_result = await session.execute(
        text("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
        """)
    )
    
    tables = [row[0] for row in tables_result.fetchall()]
    
    # Truncate all tables
    for table in tables:
        await session.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
    
    # Re-enable foreign key checks
    await session.execute(text("SET session_replication_role = 'origin';"))
    
    await session.commit()


@pytest.fixture
def sample_user_data() -> dict:
    """
    Sample user data fixture
    
    ISHLATISH:
        def test_user_creation(sample_user_data):
            user = User(**sample_user_data)
            assert user.first_name == "Test"
    """
    return {
        "user_id": 123456789,
        "username": "test_user",
        "first_name": "Test",
        "last_name": "User",
        "phone_number": "+998901234567",
        "role": "passenger"
    }


@pytest.fixture
def sample_driver_data() -> dict:
    """
    Sample driver data fixture
    """
    return {
        "driver_id": 1,
        "user_id": 123456789,
        "car_model": "Cobalt",
        "car_number": "01 A 123 BC",
        "car_color": "Oq",
        "total_seats": 4,
        "available_seats": 4,
        "is_active": True,
        "balance": 0
    }


# ============================================
# CONFIGURATION
# ============================================

@pytest.fixture(autouse=True)
def reset_settings():
    """
    Reset settings after each test
    
    autouse=True - Har testda avtomatik ishlatiladi
    """
    # Save original settings
    original_env = settings.ENVIRONMENT
    
    yield
    
    # Restore original settings
    settings.ENVIRONMENT = original_env


# ============================================
# EXPORT
# ============================================

__all__ = [
    'test_engine',
    'db_session',
    'db_session_no_rollback',
    'clean_database',
    'sample_user_data',
    'sample_driver_data',
    'reset_settings',
]
