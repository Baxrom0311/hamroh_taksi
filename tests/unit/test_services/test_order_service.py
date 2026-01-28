"""
tests/unit/test_services/test_order_service.py

Unit tests for order_service critical functions
"""
import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from app.models.order import OrderStatus
from app.models.passenger import Gender
from app.services.order_service import accept_order_by_driver, create_new_order


@pytest.mark.asyncio
class TestOrderServiceEdgeCases:
    """Unit tests for order_service edge cases"""
    
    async def test_accept_order_insufficient_balance(self, db_session, sample_driver, sample_order):
        """
        Test that driver with insufficient balance cannot accept order
        """
        # Setup: Driver with low balance
        sample_driver.balance = Decimal("100")  # Less than commission
        await db_session.commit()
        
        # Execute
        result = await accept_order_by_driver(
            driver_id=sample_driver.driver_id,
            order_id=sample_order.order_id
        )
        
        # Verify
        assert result['success'] is False
        assert 'balanс' in result['message'].lower() or 'balance' in result['message'].lower()
        
        # Order should still be PENDING
        await db_session.refresh(sample_order)
        assert sample_order.status == OrderStatus.PENDING
    
    
    async def test_accept_order_already_accepted(self, db_session, sample_driver, sample_order, second_driver):
        """
        Test that already accepted order returns error
        """
        # Setup: First driver accepts
        sample_order.status = OrderStatus.ACCEPTED
        sample_order.driver_id = sample_driver.driver_id
        await db_session.commit()
        
        # Execute: Second driver tries to accept
        result = await accept_order_by_driver(
            driver_id=second_driver.driver_id,
            order_id=sample_order.order_id
        )
        
        # Verify
        assert result['success'] is False
        assert 'allaqachon' in result['message'].lower()
    
    
    async def test_accept_order_driver_on_trip(self, db_session, sample_driver, sample_order):
        """
        Test that driver already on trip cannot accept new order
        """
        # Setup: Driver on trip
        sample_driver.is_on_trip = True
        await db_session.commit()
        
        # Execute
        result = await accept_order_by_driver(
            driver_id=sample_driver.driver_id,
            order_id=sample_order.order_id
        )
        
        # Verify
        assert result['success'] is False
        assert 'safardasiz' in result['message'].lower()
    
    
    async def test_create_order_with_optional_coordinates(self, sample_passenger, test_route_with_id):
        """
        Location is required; missing coords should fail.
        """
        # Setup route (proper fixture usage)
        await test_route_with_id(route_id=1)
        
        result = await create_new_order(
            passenger_id=sample_passenger.passenger_id,
            route_id=1,
            pickup_location="Gurlan bozori, text only",
            pickup_lat=None,
            pickup_lon=None,
            passenger_count=1
        )
        
        assert result['success'] is False
        assert 'lokatsiya' in result['message'].lower()


@pytest.mark.asyncio
class TestQueueService:
    """Unit tests for queue_service driver matching algorithm"""
    
    async def test_get_next_driver_returns_closest(self):
        """
        Test that queue returns closest driver first
        """
        from app.services.queue_service import driver_queue
        
        # Mock drivers with different locations
        drivers = [
            {'driver_id': 1, 'distance': 10.5, 'rating': 4.5},
            {'driver_id': 2, 'distance': 5.2, 'rating': 4.0},  # Closest
            {'driver_id': 3, 'distance': 15.0, 'rating': 5.0},
        ]
        
        # Add to queue
        route_id = 999
        for driver in drivers:
            await driver_queue.add_driver(
                driver_id=driver['driver_id'],
                route_id=route_id,
                priority_score=driver['rating'] - (driver['distance'] * 0.1)
            )
        
        # Get next driver
        next_driver = await driver_queue.get_next_driver(route_id)
        
        # Should be driver 2 (closest with decent rating)
        assert next_driver == 2


# Fixtures reused from integration tests
@pytest_asyncio.fixture
async def sample_passenger(db_session):
    """Create sample passenger"""
    from app.models.passenger import create_passenger
    from app.models.user import create_user, UserRole
    
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
    """Create sample driver"""
    from app.models.driver import create_driver
    from app.models.user import create_user, UserRole
    
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


@pytest_asyncio.fixture
async def second_driver(db_session):
    """Create second driver"""
    from app.models.driver import create_driver
    from app.models.user import create_user, UserRole
    
    user = await create_user(
        db_session,
        user_id=33333,
        phone_number="+998907654321",
        first_name="Second Driver",
        role=UserRole.DRIVER
    )
    
    driver = await create_driver(
        db_session,
        user_id=33333,
        full_name="Second Driver",
        phone_number="+998907654321",
        car_model="Cobalt",
        car_color="Black",
        car_number="01B456DE",
        balance=Decimal("15000"),
        available_seats=4
    )
    
    await db_session.commit()
    return driver


@pytest_asyncio.fixture
async def sample_order(db_session, sample_passenger):
    """Create sample order"""
    from app.models.order import create_order
    from app.models.route import Route

    route = Route(
        from_location="Test A",
        to_location="Test B",
        distance_km=12.3,
        is_active=True
    )
    db_session.add(route)
    await db_session.commit()
    await db_session.refresh(route)
    
    order = await create_order(
        db_session,
        passenger_id=sample_passenger.passenger_id,
        route_id=route.route_id,
        pickup_location="Test Location",
        pickup_lat=41.311,
        pickup_lon=69.249,
        passenger_count=2
    )
    
    await db_session.commit()
    return order
