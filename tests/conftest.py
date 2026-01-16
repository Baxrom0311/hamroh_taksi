"""
tests/conftest.py - Enhanced

GLOBAL TEST FIXTURES VA KONFIGURATSIYALAR
"""

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from faker import Faker

# ============================================
# DATABASE TEST FIXTURES
# ============================================

@pytest.fixture(scope="session")
def event_loop():
    """Event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Test database engine"""
    # Use in-memory SQLite for fast tests
    # Or PostgreSQL test database
    TEST_DATABASE_URL = "postgresql+asyncpg://hamroh_user:test@localhost:5432/hamroh_test"
    
    from app.core.database import Base
    
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Database session for tests"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()  # Rollback after each test


@pytest.fixture
def faker():
    """Faker instance for generating test data"""
    return Faker('uz_UZ')


# ============================================
# BOT TEST FIXTURES
# ============================================

@pytest.fixture
def mock_bot():
    """Mock Telegram Bot"""
    from unittest.mock import AsyncMock
    
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.answer = AsyncMock()
    
    return bot


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    from unittest.mock import AsyncMock, MagicMock
    
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.lock = MagicMock()
    
    return redis


# ============================================
# CELERY TEST FIXTURES
# ============================================

@pytest.fixture
def mock_celery():
    """Mock Celery tasks"""
    from unittest.mock import MagicMock
    
    celery = MagicMock()
    celery.delay = MagicMock()
    celery.apply_async = MagicMock()
    
    return celery