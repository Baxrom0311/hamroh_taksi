"""
tests/test_integration/test_edge_cases.py

Additional edge case tests for 5-star coverage
"""
import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from app.models.order import OrderStatus
from app.models.passenger import Gender


@pytest.mark.asyncio
@pytest.mark.critical
class TestOrderEdgeCases:
    """Edge cases for order service"""
    
    async def test_order_with_max_passengers(self, db_session, sample_passenger):
        """Test order with maximum passenger count (4)"""
        from app.services.order_service import create_new_order
        from app.models.route import Route

        route = Route(
            from_location="Test A",
            to_location="Test B",
            distance_km=10,
            is_active=True
        )
        db_session.add(route)
        await db_session.commit()
        await db_session.refresh(route)

        result = await create_new_order(
            passenger_id=sample_passenger.passenger_id,
            route_id=route.route_id,
            pickup_location="Test",
            pickup_lat=41.0,
            pickup_lon=69.0,
            passenger_count=4,  # Maximum allowed
            session=db_session
        )
        
        assert result['success'] is True
    
    
    async def test_order_with_zero_passengers_but_luggage(self, db_session, sample_passenger):
        """Test luggage-only order (0 passengers)"""
        from app.services.order_service import create_new_order
        from app.models.route import Route

        route = Route(
            from_location="Test A",
            to_location="Test B",
            distance_km=10,
            is_active=True
        )
        db_session.add(route)
        await db_session.commit()
        await db_session.refresh(route)

        result = await create_new_order(
            passenger_id=sample_passenger.passenger_id,
            route_id=route.route_id,
            pickup_location="Test",
            pickup_lat=41.0,
            pickup_lon=69.0,
            passenger_count=0,  # Luggage only
            has_luggage=True,
            luggage_count=2,
            session=db_session
        )
        
        assert result['success'] is True
    
    
    async def test_driver_accepts_order_then_gets_blocked(
        self,
        db_session,
        sample_driver,
        sample_order
    ):
        """Test driver accepts order then gets blocked immediately"""
        from app.services.order_service import accept_order_by_driver
        from app.services.driver_blocking import block_driver_and_cleanup
        
        # Accept order
        sample_driver.balance = Decimal("10000")
        await db_session.commit()
        
        result = await accept_order_by_driver(
            driver_id=sample_driver.driver_id,
            order_id=sample_order.order_id
        )
        assert result['success'] is True
        
        # Block driver
        block_result = await block_driver_and_cleanup(
            driver_id=sample_driver.driver_id,
            reason="Test block"
        )
        
        # Order should be cancelled
        assert block_result['success'] is True
        assert block_result['cancelled_orders'] == 1
        
        # Verify order status
        await db_session.refresh(sample_order)
        assert sample_order.status == OrderStatus.PENDING
        assert sample_order.driver_id is None


@pytest.mark.asyncio
class TestPerformance:
    """Performance and load tests"""
    
    async def test_concurrent_driver_registration(self, db_session):
        """Test multiple drivers registering concurrently"""
        import asyncio
        from app.models.driver import create_driver
        from app.models.user import create_user, UserRole
        
        async def register_driver(i):
            user = await create_user(
                db_session,
                user_id=100000 + i,
                phone_number=f"+99890000{i:04d}",
                first_name=f"Driver {i}",
                role=UserRole.DRIVER
            )
            
            driver = await create_driver(
                db_session,
                user_id=user.user_id,
                full_name=f"Driver {i}",
                phone_number=user.phone_number,
                car_model="Cobalt",
                car_color="White",
                car_number=f"01A{i:03d}BC"
            )
            return driver
        
        # Register 10 drivers concurrently
        drivers = await asyncio.gather(*[
            register_driver(i) for i in range(10)
        ])
        
        await db_session.commit()
        assert len(drivers) == 10


@pytest.mark.asyncio
class TestValidation:
    """Input validation tests"""
    
    async def test_invalid_phone_number(self):
        """Test phone number validation"""
        from app.core.validation import validate_phone_number
        
        # Invalid formats
        assert validate_phone_number("123")[0] is False
        assert validate_phone_number("abc")[0] is False
        assert validate_phone_number("+1234")[0] is False
        
        # Valid format
        assert validate_phone_number("+998901234567")[0] is True
    
    
    async def test_invalid_car_number(self):
        """Test car number validation"""
        from app.core.validation import validate_car_number
        
        # Invalid
        assert validate_car_number("ABC")[0] is False
        assert validate_car_number("12 34")[0] is False
        
        # Valid
        assert validate_car_number("01 A 123 BC")[0] is True
        assert validate_car_number("99Z999ZZ")[0] is True


# Fixtures
@pytest_asyncio.fixture
async def sample_passenger(db_session):
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
async def sample_order(db_session, sample_passenger):
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
