"""
tests/conftest.py

PYTEST CONFIGURATION

BU FAYL NIMA QILADI:
- Test uchun fixtures
- Test database setup
- Mock objects
"""

import pytest
import asyncio
from typing import AsyncGenerator




# ============================================
# DATABASE FIXTURES
# ============================================

@pytest.fixture(scope="function")
async def test_db():
    """
    Test database session
    """
    from app.core.database import init_database, close_database, get_session
    
    # Init
    await init_database()
    
    # Session
    async with get_session() as session:
        yield session
    
    # Cleanup
    await close_database()


# ============================================
# REDIS FIXTURES
# ============================================

@pytest.fixture(scope="function")
async def test_redis():
    """
    Test Redis client
    """
    from app.core.redis_client import init_redis, close_redis, redis_client
    
    # Init
    await init_redis()
    
    yield redis_client
    
    # Cleanup
    await close_redis()


# ============================================
# MODEL FIXTURES
# ============================================

@pytest.fixture
async def test_user(test_db):
    """
    Test user
    """
    from app.models.user import User, UserRole
    
    user = User(
        user_id=123456789,
        phone_number="+998901234567",
        first_name="Test",
        last_name="User",
        role=UserRole.PASSENGER
    )
    
    test_db.add(user)
    await test_db.commit()
    
    return user


@pytest.fixture
async def test_driver(test_db, test_user):
    """
    Test driver
    """
    from app.models.driver import Driver
    from decimal import Decimal
    
    driver = Driver(
        user_id=test_user.user_id,
        full_name="Test Driver",
        car_model="Nexia",
        car_color="White",
        car_number="01 A 123 BC",
        balance=Decimal("50000.00"),
        rating=Decimal("5.00")
    )
    
    test_db.add(driver)
    await test_db.commit()
    
    return driver


# ============================================
# MOCK FIXTURES
# ============================================

@pytest.fixture
def mock_bot():
    """
    Mock Telegram bot
    """
    from unittest.mock import AsyncMock
    
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)
    
    return bot


# ============================================
# HELPERS
# ============================================

@pytest.fixture
def anyio_backend():
    """Anyio backend"""
    return 'asyncio'