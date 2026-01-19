"""
tests/unit/test_models/test_user.py

USER MODEL UNIT TESTS

BU FAYL NIMA QILADI:
- User model'ini test qilish
- Model methods test qilish
- Helper functions test qilish

ISHLATISH:
    pytest tests/unit/test_models/test_user.py -v
"""
import pytest
from datetime import datetime

from app.models.user import (
    User,
    UserRole,
    get_user_by_id,
    get_user_by_phone,
    create_user,
    block_user,
    unblock_user
)


class TestUserModel:
    """User model testlari"""
    
    @pytest.mark.asyncio
    async def test_create_user_basic(self, db_session):
        """Oddiy user yaratish"""
        user = User(
            user_id=123456789,
            username="test_user",
            first_name="Test",
            last_name="User",
            phone_number="+998901234567",
            role=UserRole.PASSENGER
        )
        
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        assert user.user_id == 123456789
        assert user.full_name == "Test User"
        assert user.is_passenger is True
        assert user.is_driver is False
        assert user.is_admin is False
    
    @pytest.mark.asyncio
    async def test_user_roles(self, db_session):
        """User rollari"""
        # Passenger
        passenger = User(
            user_id=1,
            first_name="Pass",
            phone_number="+998901111111",
            role=UserRole.PASSENGER
        )
        assert passenger.is_passenger is True
        assert passenger.is_driver is False
        assert passenger.is_admin is False
        
        # Driver
        driver = User(
            user_id=2,
            first_name="Driver",
            phone_number="+998902222222",
            role=UserRole.DRIVER
        )
        assert driver.is_driver is True
        assert driver.is_passenger is False
        assert driver.is_admin is False
        
        # Admin
        admin = User(
            user_id=3,
            first_name="Admin",
            phone_number="+998903333333",
            role=UserRole.ADMIN
        )
        assert admin.is_admin is True
        assert admin.is_glavni_admin is False
        
        # Glavni Admin
        glavni = User(
            user_id=4,
            first_name="Glavni",
            phone_number="+998904444444",
            role=UserRole.GLAVNI_ADMIN
        )
        assert glavni.is_glavni_admin is True
        assert glavni.is_admin is True
    
    @pytest.mark.asyncio
    async def test_full_name_property(self):
        """full_name property"""
        # With last name
        user1 = User(
            user_id=1,
            first_name="John",
            last_name="Doe",
            phone_number="+998901111111"
        )
        assert user1.full_name == "John Doe"
        
        # Without last name
        user2 = User(
            user_id=2,
            first_name="John",
            phone_number="+998902222222"
        )
        assert user2.full_name == "John"
    
    @pytest.mark.asyncio
    async def test_to_dict_method(self, db_session):
        """to_dict() method"""
        user = User(
            user_id=123,
            username="testuser",
            first_name="Test",
            last_name="User",
            phone_number="+998901234567",
            role=UserRole.PASSENGER,
            is_blocked=False
        )
        
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        user_dict = user.to_dict()
        
        assert user_dict['user_id'] == 123
        assert user_dict['username'] == "testuser"
        assert user_dict['full_name'] == "Test User"
        assert user_dict['phone_number'] == "+998901234567"
        assert user_dict['role'] == "passenger"
        assert user_dict['is_blocked'] is False
        assert 'registration_date' in user_dict


class TestUserHelperFunctions:
    """User helper functions testlari"""
    
    @pytest.mark.asyncio
    async def test_get_user_by_id(self, db_session):
        """get_user_by_id() funksiyasi"""
        # Create user
        user = User(
            user_id=999,
            first_name="Test",
            phone_number="+998909999999"
        )
        db_session.add(user)
        await db_session.commit()
        
        # Find user
        found_user = await get_user_by_id(db_session, 999)
        assert found_user is not None
        assert found_user.user_id == 999
        
        # Not found
        not_found = await get_user_by_id(db_session, 888)
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_get_user_by_phone(self, db_session):
        """get_user_by_phone() funksiyasi"""
        # Create user
        user = User(
            user_id=777,
            first_name="Test",
            phone_number="+998907777777"
        )
        db_session.add(user)
        await db_session.commit()
        
        # Find user
        found_user = await get_user_by_phone(db_session, "+998907777777")
        assert found_user is not None
        assert found_user.phone_number == "+998907777777"
        
        # Not found
        not_found = await get_user_by_phone(db_session, "+998906666666")
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_create_user_helper(self, db_session):
        """create_user() helper funksiyasi"""
        new_user = await create_user(
            session=db_session,
            user_id=555,
            phone_number="+998905555555",
            first_name="New",
            last_name="User",
            role=UserRole.DRIVER,
            username="newuser"
        )
        
        await db_session.commit()
        
        assert new_user.user_id == 555
        assert new_user.first_name == "New"
        assert new_user.last_name == "User"
        assert new_user.phone_number == "+998905555555"
        assert new_user.role == UserRole.DRIVER
        assert new_user.username == "newuser"
    
    @pytest.mark.asyncio
    async def test_block_user(self, db_session):
        """block_user() funksiyasi"""
        # Create user
        user = User(
            user_id=444,
            first_name="Test",
            phone_number="+998904444444"
        )
        db_session.add(user)
        await db_session.commit()
        
        assert user.is_blocked is False
        
        # Block user
        result = await block_user(db_session, 444)
        await db_session.commit()
        
        assert result is True
        
        # Refresh to get updated data
        await db_session.refresh(user)
        assert user.is_blocked is True
    
    @pytest.mark.asyncio
    async def test_unblock_user(self, db_session):
        """unblock_user() funksiyasi"""
        # Create blocked user
        user = User(
            user_id=333,
            first_name="Test",
            phone_number="+998903333333",
            is_blocked=True
        )
        db_session.add(user)
        await db_session.commit()
        
        assert user.is_blocked is True
        
        # Unblock user
        result = await unblock_user(db_session, 333)
        await db_session.commit()
        
        assert result is True
        
        # Refresh
        await db_session.refresh(user)
        assert user.is_blocked is False


class TestUserConstraints:
    """User model constraints testlari"""
    
    @pytest.mark.asyncio
    async def test_unique_phone_constraint(self, db_session):
        """Phone number unique constraint"""
        from sqlalchemy.exc import IntegrityError
        
        # First user
        user1 = User(
            user_id=111,
            first_name="User1",
            phone_number="+998901111111"
        )
        db_session.add(user1)
        await db_session.commit()
        
        # Second user with same phone - should fail
        user2 = User(
            user_id=222,
            first_name="User2",
            phone_number="+998901111111"  # Same phone!
        )
        db_session.add(user2)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()
    
    @pytest.mark.asyncio
    async def test_required_fields(self, db_session):
        """Required fields validation"""
        from sqlalchemy.exc import IntegrityError
        
        # Missing phone_number
        user = User(
            user_id=100,
            first_name="Test"
            # phone_number missing!
        )
        db_session.add(user)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()


# ============================================
# RUN TESTS
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
