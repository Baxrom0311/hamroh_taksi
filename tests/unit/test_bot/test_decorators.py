"""
tests/unit/test_bot/test_decorators.py

Unit tests for decorator role-based validation
"""
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from aiogram.types import Message
from aiogram.dispatcher.event.bases import SkipHandler

from app.bot.decorators import with_driver_session, with_passenger_session
from app.models.user import UserRole
from app.models.passenger import Gender


@pytest.mark.asyncio
class TestDecoratorRoleValidation:
    """Test decorator role-based access control"""
    
    async def test_driver_decorator_allows_driver_role(self, db_session, sample_driver):
        """
        Test that @with_driver_session allows DRIVER role
        """
        # Create test handler
        handler_called = False
        
        @with_driver_session
        async def test_handler(event, session, driver, *args, **kwargs):
            nonlocal handler_called
            handler_called = True
            assert driver.driver_id == sample_driver.driver_id
            return "success"
        
        # Mock message
        message = Mock(spec=Message)
        message.from_user = Mock(id=sample_driver.user_id)
        message.answer = AsyncMock()
        
        # Execute
        result = await test_handler(message)
        
        # Verify
        assert handler_called is True
        assert result == "success"
    
    
    async def test_driver_decorator_blocks_passenger_role(self, db_session, sample_passenger):
        """
        Test that @with_driver_session raises SkipHandler for PASSENGER role
        """
        @with_driver_session
        async def test_handler(event, session, driver):
            pytest.fail("Handler should not be called for passenger")
        
        message = Mock(spec=Message)
        message.from_user = Mock(id=sample_passenger.user_id)
        
        # Execute - should raise SkipHandler
        with pytest.raises(SkipHandler):
            await test_handler(message)
    
    
    async def test_passenger_decorator_allows_passenger_role(self, db_session, sample_passenger):
        """
        Test that @with_passenger_session allows PASSENGER role
        """
        handler_called = False
        
        @with_passenger_session
        async def test_handler(event, session, passenger):
            nonlocal handler_called
            handler_called = True
            assert passenger.passenger_id == sample_passenger.passenger_id
            return "success"
        
        message = Mock(spec=Message)
        message.from_user = Mock(id=sample_passenger.user_id)
        message.answer = AsyncMock()
        
        result = await test_handler(message)
        
        assert handler_called is True
        assert result == "success"
    
    
    async def test_passenger_decorator_blocks_driver_role(self, db_session, sample_driver):
        """
        Test that @with_passenger_session raises SkipHandler for DRIVER role
        """
        @with_passenger_session
        async def test_handler(event, session, passenger):
            pytest.fail("Handler should not be called for driver")
        
        message = Mock(spec=Message)
        message.from_user = Mock(id=sample_driver.user_id)
        
        with pytest.raises(SkipHandler):
            await test_handler(message)
    
    
    async def test_decorator_handles_missing_profile_gracefully(self, db_session):
        """
        Test that decorator returns error message if profile is missing
        (data integrity error)
        """
        from app.models.user import create_user
        
        # Create user WITHOUT profile (data integrity issue)
        orphan_user = await create_user(
            db_session,
            user_id=99999,
            phone_number="+998999999999",
            first_name="Orphan",
            role=UserRole.DRIVER  # Role is DRIVER but no driver profile
        )
        await db_session.commit()
        
        @with_driver_session
        async def test_handler(event, session, driver):
            pytest.fail("Should not reach handler")
        
        message = Mock(spec=Message)
        message.from_user = Mock(id=orphan_user.user_id)
        message.answer = AsyncMock()
        
        # Execute - should send error message and return
        result = await test_handler(message)
        
        # Verify error message sent
        assert message.answer.called
        call_args = message.answer.call_args[0][0]
        assert "xatolik" in call_args.lower() or "error" in call_args.lower()
        
        # Should not raise SkipHandler (stops propagation)
        assert result is None


# Fixtures
@pytest_asyncio.fixture
async def sample_passenger(db_session):
    from app.models.passenger import create_passenger
    from app.models.user import create_user
    
    user = await create_user(
        db_session,
        user_id=11111,
        phone_number="+998901234567",
        first_name="Test",
        role=UserRole.PASSENGER
    )
    
    passenger = await create_passenger(
        db_session,
        user_id=11111,
        full_name="Test Passenger",
        gender=Gender.MALE,
        age=25,
        phone_number="+998901234567"
    )
    
    await db_session.commit()
    return passenger


@pytest_asyncio.fixture
async def sample_driver(db_session):
    from app.models.driver import create_driver
    from app.models.user import create_user
    from decimal import Decimal
    
    user = await create_user(
        db_session,
        user_id=22222,
        phone_number="+998909876543",
        first_name="Test Driver",
        role=UserRole.DRIVER
    )
    
    driver = await create_driver(
        db_session,
        user_id=22222,
        full_name="Test Driver",
        phone_number="+998909876543",
        car_model="Nexia",
        car_color="White",
        car_number="01A123BC",
        balance=Decimal("10000"),
        available_seats=4
    )
    
    await db_session.commit()
    return driver
