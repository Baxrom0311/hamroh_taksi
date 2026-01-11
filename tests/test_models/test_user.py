"""
tests/test_models/test_user.py

USER MODEL TESTS
"""

import pytest
from app.models.user import User, UserRole, create_user


@pytest.mark.asyncio
async def test_create_user(test_db):
    """Test user creation"""
    
    user = await create_user(
        test_db,
        user_id=987654321,
        phone_number="+998901111111",
        first_name="John",
        last_name="Doe",
        role=UserRole.DRIVER
    )
    
    await test_db.commit()
    
    assert user.user_id == 987654321
    assert user.phone_number == "+998901111111"
    assert user.full_name == "John Doe"
    assert user.role == UserRole.DRIVER
    assert user.is_blocked == False


@pytest.mark.asyncio
async def test_user_properties(test_user):
    """Test user properties"""
    
    assert test_user.is_passenger == True
    assert test_user.is_driver == False
    assert test_user.is_admin == False