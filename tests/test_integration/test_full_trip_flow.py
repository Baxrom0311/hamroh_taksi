"""
tests/test_integration/test_full_trip_flow.py

TO'LIQ SAFAR JARAYONI INTEGRATION TESTI

Bu test ro'yxatdan o'tishdan boshlab safarni yakunlashgacha bo'm barcha jarayonni test qiladi.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User, Chat, Update
from aiogram.fsm.context import FSMContext

from app.models.user import User as DBUser, UserRole
from app.models.passenger import Passenger, Gender
from app.models.driver import Driver
from app.models.order import Order, OrderStatus
from app.models.route import Route
from app.core.database import get_session

# Use a single event loop for all tests in this module to avoid cross-loop asyncpg issues
pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestFullTripFlow:
    """
    To'liq safar jarayoni testi
    
    FLOW:
    1. Yo'lovchi ro'yxatdan o'tadi
    2. Haydovchi ro'yxatdan o'tadi
    3. Yo'lovchi taksi chaqiradi
    4. Haydovchi buyurtmani qabul qiladi
    5. Safar bosh lanadi va yakunlanadi
    """
    
    @pytest.mark.asyncio
    async def test_passenger_registration(self, db_session, faker):
        """1. Yo'lovchi ro'yxatdan o'tish"""
        from app.bot.handlers.registration import complete_registration
        
        # Mock message
        message = self._create_mock_message(
            user_id=faker.random_int(min=100000, max=999999),
            text="Alisher Karimov"
        )
        
        # Mock state
        state = self._create_mock_state({
            'role': UserRole.PASSENGER,
            'phone_number': f"+998{faker.random_number(digits=9, fix_len=True)}",
            'age': 25,
            'gender': Gender.MALE
        })
        
        # Execute
        with patch('app.bot.handlers.registration.get_session', return_value=db_session):
            await complete_registration(message, state)
        
        # Verify
        assert message.answer.called
        assert "yakunlandi" in message.answer.call_args[0][0].lower()
        
        # Check database
        from app.models.user import get_user_by_id
        user = await get_user_by_id(db_session, message.from_user.id)
        assert user is not None
        assert user.role == UserRole.PASSENGER
    
    @pytest.mark.asyncio
    async def test_driver_registration(self, db_session, faker):
        """2. Haydovchi ro'yxatdan o'tish"""
        from app.bot.handlers.registration import complete_registration
        
        message = self._create_mock_message(
            user_id=faker.random_int(min=100000, max=999999),
            text="Bobur Alimardonov"
        )
        
        state = self._create_mock_state({
            'role': UserRole.DRIVER,
            'phone_number': f"+998{faker.random_number(digits=9, fix_len=True)}",
            'car_model': 'Chevrolet Cobalt',
            'car_color': 'Oq',
            'car_number': f"{faker.random_int(min=10, max=99)} A {faker.random_int(min=100, max=999)} {faker.random_int(min=10, max=99)}"
        })
        
        with patch('app.bot.handlers.registration.get_session', return_value=db_session):
            await complete_registration(message, state)
        
        # Verify
        from app.models.user import get_user_by_id
        user = await get_user_by_id(db_session, message.from_user.id)
        assert user is not None
        assert user.role == UserRole.DRIVER
        
        # Check driver profile
        from app.models.driver import get_driver_by_user_id
        driver = await get_driver_by_user_id(db_session, message.from_user.id)
        assert driver is not None
        assert driver.car_model == 'Chevrolet Cobalt'
    
    @pytest.mark.asyncio
    async def test_passenger_creates_order(self, db_session, passenger, active_route):
        """3. Yo'lovchi taksi chaqiradi"""
        from app.services.order_service import create_new_order
        
        # Create order
        result = await create_new_order(
            passenger_id=passenger.passenger_id,
            route_id=active_route.route_id,
            pickup_location="Bozor yonida",
            pickup_lat=41.3111,
            pickup_lon=69.2797,
            passenger_count=2
        )
        
        assert result['success'] is True
        assert 'order_id' in result
        
        # Check order in database
        from app.models.order import get_order_by_id
        order = await get_order_by_id(db_session, result['order_id'])
        assert order is not None
        assert order.status == OrderStatus.PENDING
        assert order.passenger_id == passenger.passenger_id
    
    @pytest.mark.asyncio
    async def test_driver_accepts_order(self, db_session, driver, pending_order):
        """4. Haydovchi buyurtmani qabul qiladi"""
        from app.services.order_service import accept_order_by_driver
        
        # Driver should have sufficient balance
        driver.balance = 50000
        await db_session.commit()
        
        # Accept order
        result = await accept_order_by_driver(
            driver_id=driver.driver_id,
            order_id=pending_order.order_id
        )
        
        assert result['success'] is True
        
        # Check order status
        await db_session.refresh(pending_order)
        assert pending_order.status == OrderStatus.ACCEPTED
        assert pending_order.driver_id == driver.driver_id
        
        # Check driver balance (commission deducted if configured)
        from app.models.system_settings import get_pricing_settings
        await db_session.refresh(driver)
        pricing = await get_pricing_settings(db_session)
        commission = pricing.get('commission_amount', 0) or 0
        assert driver.balance == 50000 - commission
    
    @pytest.mark.asyncio
    async def test_trip_start_and_complete(self, db_session, accepted_order):
        """5. Safar boshlash va yakunlash"""
        from app.services.order_service import start_trip, complete_trip
        
        # Start trip
        start_result = await start_trip(
            order_id=accepted_order.order_id,
            driver_id=accepted_order.driver_id
        )
        
        assert start_result['success'] is True
        
        # Check status
        await db_session.refresh(accepted_order)
        assert accepted_order.status == OrderStatus.IN_PROGRESS
        
        # Complete trip
        complete_result = await complete_trip(
            order_id=accepted_order.order_id,
            driver_id=accepted_order.driver_id
        )
        
        assert complete_result['success'] is True
        
        # Check final status
        await db_session.refresh(accepted_order)
        assert accepted_order.status == OrderStatus.COMPLETED
        assert accepted_order.completed_at is not None
    
    # Helper methods
    def _create_mock_message(self, user_id: int, text: str = "", **kwargs):
        """Mock Message yaratish"""
        message = AsyncMock(spec=Message)
        message.from_user = User(id=user_id, is_bot=False, first_name="Test")
        message.chat = Chat(id=user_id, type="private")
        message.text = text
        message.answer = AsyncMock()
        return message
    
    def _create_mock_state(self, data: dict):
        """Mock FSMContext yaratish"""
        state = AsyncMock(spec=FSMContext)
        state.get_data = AsyncMock(return_value=data)
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()
        state.clear = AsyncMock()
        return state


# Fixtures

@pytest.fixture
async def passenger(db_session, faker):
    """Test passenger yaratish"""
    from app.models.user import create_user
    from app.models.passenger import create_passenger, get_passenger_by_user_id
    
    user_id = faker.random_int(min=100000, max=999999)
    
    # Create using isolated session to avoid sharing long-lived connections
    async with get_session() as session:
        user = await create_user(
            session,
            user_id=user_id,
            phone_number=f"+998{faker.random_number(digits=9, fix_len=True)}",
            first_name="Test Passenger",
            role=UserRole.PASSENGER
        )
        await create_passenger(
            session,
            user_id=user_id,
            full_name="Test Passenger",
            gender=Gender.MALE,
            age=25,
            phone_number=user.phone_number
        )

    # Reload into the shared test session
    passenger = await get_passenger_by_user_id(db_session, user_id)
    return passenger


@pytest.fixture
async def driver(db_session, faker):
    """Test driver yaratish"""
    from app.models.user import create_user
    from app.models.driver import create_driver, get_driver_by_user_id
    
    user_id = faker.random_int(min=100000, max=999999)
    
    async with get_session() as session:
        await create_user(
            session,
            user_id=user_id,
            phone_number=f"+998{faker.random_number(digits=9, fix_len=True)}",
            first_name="Test Driver",
            role=UserRole.DRIVER
        )
        await create_driver(
            session,
            user_id=user_id,
            full_name="Test Driver",
            phone_number=f"+998{faker.random_number(digits=9, fix_len=True)}",
            car_model='Chevrolet Cobalt',
            car_color='Oq',
            car_number=f"{faker.random_int(min=10, max=99)} A {faker.random_int(min=100, max=999)} {faker.random_int(min=10, max=99)}"
        )

    driver = await get_driver_by_user_id(db_session, user_id)
    driver.available_seats = 4
    await db_session.commit()
    return driver


@pytest.fixture
async def active_route(db_session, faker):
    """Test route yaratish"""
    route = Route(
        from_location=f"Gurlan {faker.random_int(min=1, max=999)}",
        to_location=f"Vazir {faker.random_int(min=1, max=999)}",
        distance_km=45.5,
        is_active=True,
    )
    
    db_session.add(route)
    await db_session.commit()
    await db_session.refresh(route)
    return route


@pytest.fixture
async def pending_order(db_session, passenger, active_route):
    """PENDING buyurtma yaratish"""
    from app.services.order_service import create_new_order
    
    result = await create_new_order(
        passenger_id=passenger.passenger_id,
        route_id=active_route.route_id,
        pickup_location="Test location",
        pickup_lat=41.3111,
        pickup_lon=69.2797,
        passenger_count=2
    )
    
    from app.models.order import get_order_by_id
    order = await get_order_by_id(db_session, result['order_id'])
    return order


@pytest.fixture
async def accepted_order(db_session, pending_order, driver):
    """ACCEPTED buyurtma yaratish"""
    from app.services.order_service import accept_order_by_driver
    
    driver.balance = 50000
    await db_session.commit()
    
    await accept_order_by_driver(
        driver_id=driver.driver_id,
        order_id=pending_order.order_id
    )
    
    await db_session.refresh(pending_order)
    return pending_order
