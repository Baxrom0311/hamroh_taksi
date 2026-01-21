"""
tests/test_models/test_user.py

USER MODEL TESTS (LEGACY)

This file duplicates tests in tests/unit/test_models/test_user.py and
causes pytest import-name collisions. Skip to avoid collection errors.
"""

import pytest
from app.models.user import User, UserRole, create_user

# Skip this legacy module to prevent import collisions with unit/ version
pytestmark = pytest.mark.skip(reason="Duplicate of tests/unit/test_models/test_user.py")


@pytest.mark.asyncio
async def test_create_user(test_db, faker):
    """Test user creation"""
    
    phone = f"+998{faker.random_number(digits=9, fix_len=True)}"
    user = await create_user(
        test_db,
        user_id=987654321,
        phone_number=phone,
        first_name="John",
        last_name="Doe",
        role=UserRole.DRIVER
    )
    
    await test_db.commit()
    
    assert user.user_id == 987654321
    assert user.phone_number == phone
    assert user.full_name == "John Doe"
    assert user.role == UserRole.DRIVER
    assert user.is_blocked == False


@pytest.mark.asyncio
async def test_user_properties(test_user):
    """Test user properties"""
    
    assert test_user.is_passenger == True
    assert test_user.is_driver == False
    assert test_user.is_admin == False
