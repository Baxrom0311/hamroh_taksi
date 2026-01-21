"""
tests/conftest.py - Enhanced

GLOBAL TEST FIXTURES VA KONFIGURATSIYALAR
"""

import os
import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
from faker import Faker
from sqlalchemy import text

# Force the standard asyncio loop policy to avoid uvloop cross-loop issues in tests
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# Ensure pytest-asyncio uses the standard loop policy (no uvloop)
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()

# ============================================
# DATABASE TEST FIXTURES
# ============================================

@pytest_asyncio.fixture
async def test_engine():
    """Per-test database engine"""
    db_host = os.getenv("DB_HOST", "postgres")
    db_port = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "hamroh_user")
    db_pass = os.getenv("DB_PASSWORD", "your_strong_password_here")
    db_name = os.getenv("DB_NAME", "hamroh_bot")

    TEST_DATABASE_URL = os.getenv(
        "TEST_DATABASE_URL",
        f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    )
    
    from app.core.database import Base
    from app.core.database import db_manager
    
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        pool_pre_ping=False,
    )
    
    # Wire up global db_manager so services that call get_session() use test engine
    db_manager._engine = engine  # type: ignore[attr-defined]
    db_manager._session_factory = async_sessionmaker(  # type: ignore[attr-defined]
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    # Reset schema for every test to avoid cross-test bleed and loop reuse issues
    async with engine.begin() as conn:
        # Terminate stray connections (bot process) to avoid deadlocks during DROP SCHEMA
        await conn.execute(text("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid();
        """))
        # Keep lock waits short so tests don't hang
        await conn.execute(text("SET lock_timeout TO '5s'"))
        # Fast schema reset with cascade to avoid FK dependency issues
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
        # Ensure PostGIS is available for geometry columns
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;"))
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Database session for tests"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()
        await session.close()

@pytest.fixture
def test_db(db_session):
    """Alias for db_session for compatibility"""
    return db_session


@pytest.fixture
def faker():
    """Faker instance for generating test data"""
    # Use default locale to avoid missing locale errors in CI containers
    return Faker()


# ============================================
# INFRA PATCHES
# ============================================

@pytest.fixture(autouse=True)
def disable_order_lock(monkeypatch):
    """
    Tests run without Redis; stub distributed lock to always succeed.
    """
    lock_state = set()

    @asynccontextmanager
    async def _fake_lock(order_id=None, *args, **kwargs):
        key = order_id or kwargs.get("order_id") or "default"
        if key in lock_state:
            yield False
        else:
            lock_state.add(key)
            try:
                yield True
            finally:
                lock_state.discard(key)

    monkeypatch.setattr("app.services.order_service.acquire_order_lock", _fake_lock)


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

# ============================================
# MODEL FIXTURES
# ============================================

@pytest_asyncio.fixture
async def test_user(db_session, faker):
    """Test user fixture"""
    from app.models.user import create_user, UserRole
    user = await create_user(
        db_session,
        user_id=faker.random_int(min=10000, max=99999),
        phone_number=faker.phone_number(),
        first_name=faker.first_name(),
        role=UserRole.PASSENGER
    )
    await db_session.commit()
    return user

@pytest_asyncio.fixture
async def passenger(db_session, test_user, faker):
    """Passenger profile fixture"""
    from app.models.passenger import create_passenger, Gender
    passenger = await create_passenger(
        db_session,
        user_id=test_user.user_id,
        full_name=test_user.full_name,
        gender=Gender.MALE,
        age=25,
        phone_number=test_user.phone_number
    )
    await db_session.commit()
    return passenger

@pytest_asyncio.fixture
async def driver(db_session, faker):
    """Driver profile fixture"""
    from app.models.user import create_user, UserRole
    from app.models.driver import create_driver
    user_id = faker.random_int(min=10000, max=99999)
    await create_user(
        db_session,
        user_id=user_id,
        phone_number=faker.phone_number(),
        first_name=faker.first_name(),
        role=UserRole.DRIVER
    )
    driver = await create_driver(
        db_session,
        user_id=user_id,
        full_name=faker.name(),
        phone_number=faker.phone_number(),
        car_model="Chevrolet Cobalt",
        car_color="Oq",
        car_number=faker.license_plate()
    )
    await db_session.commit()
    return driver
