"""
tests/test_integration/test_critical_fixes.py

Integration tests for all critical bug fixes
"""
import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from app.models.user import UserRole
from app.models.order import Order, OrderStatus
from app.models.driver import Driver
from app.models.passenger import Passenger, Gender


@pytest.mark.asyncio
class TestSessionManagementLeak:
    """Test Fix #1: Session shadowing in reject_trip"""
    
    async def test_reject_trip_no_session_leak(self, db_session, sample_order, sample_driver):
        """
        CRITICAL FIX #1: Session Management Leak
        
        Verify that reject_trip doesn't shadow the session parameter
        and properly commits changes.
        """
        from app.bot.handlers.passenger.booking import reject_trip
        from aiogram.types import CallbackQuery
        
        # Setup
        order = sample_order
        order.driver_id = sample_driver.driver_id
        order. status = OrderStatus.ACCEPTED
        db_session.add(order)
        await db_session.commit()
        
        # Mock callback
        callback = Mock(spec=CallbackQuery)
        callback.data = f"reject_trip:{order.order_id}"
        callback.from_user = Mock(id=sample_order.passenger.user_id)
        callback.answer = AsyncMock()
        callback.message = Mock()
        callback.message.edit_text = AsyncMock()
    
        # Execute - should not leak session
        # The fix renames inner session to txn_session
        await reject_trip(callback)
        
        # Verify: Order should be cancelled
        await db_session.refresh(order)
        assert order.status == OrderStatus.CANCELLED
        assert order.cancellation_reason == "passenger_rejected"
        
        # Verify: Driver should have warning incremented
        await db_session.refresh(sample_driver)
        assert sample_driver.ban_count_today >= 1


@pytest.mark.asyncio
class TestGPSCoordinatesHandling:
    """Test Fix #3: GPS Coordinates with None values"""
    
    async def test_text_only_location_creates_order_with_none(self, db_session, sample_passenger):
        """
        CRITICAL FIX #3: GPS Coordinates
        
        Verify that text-only locations can be saved with None coordinates.
        This requires nullable pickup_lat/pickup_lon in database.
        """
        from app.services.order_service import create_new_order
        from app.models.route import Route
        
        # Create order with None coordinates (text-only address)
        route = Route(
            from_location="Test A",
            to_location="Test B",
            distance_km=5.5,
            is_active=True
        )
        db_session.add(route)
        await db_session.commit()
        await db_session.refresh(route)

        result = await create_new_order(
            passenger_id=sample_passenger.passenger_id,
            route_id=route.route_id,
            pickup_location="Gurlan bozori, 5-uy (text only)",
            pickup_lat=None,  # ✅ Text-only - no GPS
            pickup_lon=None,
            passenger_count=2,
            session=db_session
        )
        
        assert result['success'] is True
        order_id = result['order_id']
        
        # Verify order created with NULL coordinates
        from app.models.order import get_order_by_id
        order = await get_order_by_id(db_session, order_id)
        
        assert order is not None
        assert order.pickup_location == "Gurlan bozori, 5-uy (text only)"
        assert order.pickup_lat is None
        assert order.pickup_lon is None
    
    
    async def test_location_helpers_handle_none_coordinates(self):
        """
        Verify location helpers return None for None coordinates
        """
        from app.utils.location_helpers import (
            get_google_maps_link,
            get_telegram_location_link,
            format_location_with_links
        )
        
        # Test Google Maps link
        assert get_google_maps_link(None, None) is None
        assert get_google_maps_link(1.0, None) is None
        assert get_google_maps_link(None, 1.0) is None
        
        # Test Telegram link
        assert get_telegram_location_link(None, None) is None
        
        # Test format with fallback message
        result = format_location_with_links("Gurlan bozor", None, None)
        assert "⚠️ GPS lokatsiya yo'q" in result
        assert "Gurlan bozor" in result


@pytest.mark.asyncio
class TestRaceConditionFix:
    """Test Fix #2: Race condition in driver state cleanup"""
    
    async def test_driver_cleanup_no_manual_commit(self, db_session, sample_order, sample_driver):
        """
        CRITICAL FIX #2: Race Condition
        
        Verify manual_complete_trip doesn't manually commit,
        letting decorator handle it.
        """
        from app.bot.handlers.driver.orders import manual_complete_trip
        from aiogram.types import Message
        from aiogram.fsm.context import FSMContext
        
        # Setup
        order = sample_order
        order.driver_id = sample_driver.driver_id
        order.status = OrderStatus.IN_PROGRESS
        sample_driver.is_on_trip = True
        await db_session.commit()
        
        # Mock message and state
        message = Mock(spec=Message)
        message.from_user = Mock(id=sample_driver.user_id)
        message.answer = AsyncMock()
        
        state = Mock(spec=FSMContext)
        state.get_data = AsyncMock(return_value={'current_order_id': order.order_id})
        state.clear = AsyncMock()
        
        # Execute
        await manual_complete_trip(message, state)
        
        # Verify driver state cleaned up
        await db_session.refresh(sample_driver)
        assert sample_driver.is_on_trip is False
        
        # Verify order completed
        await db_session.refresh(order)
        assert order.status == OrderStatus.COMPLETED


@pytest.mark.asyncio
class TestMiddlewareExceptionHandling:
    """Test Fix #5: Middleware exception handling"""
    
    async def test_state_guard_handles_critical_exceptions(self):
        """
        CRITICAL FIX #5: Middleware Exception Handling
        
        Verify StateGuardMiddleware doesn't swallow exceptions
        and properly notifies user.
        """
        from app.bot.middlewares.state_guard import StateGuardMiddleware
        from aiogram.types import Message
        from aiogram.fsm.context import FSMContext
        
        middleware = StateGuardMiddleware()
        
        # Mock handler that raises exception
        async def failing_handler(*args, **kwargs):
            raise ValueError("Simulated critical error")
        
        # Mock event and state
        event = Mock(spec=Message)
        event.from_user = Mock(id=12345)
        event.answer = AsyncMock()
        
        state = Mock(spec=FSMContext)
        state.clear = AsyncMock()
        state.get_state = AsyncMock(return_value="SomeState:active")
        
        data = {'handler': failing_handler, 'event': event, 'state': state}
        
        # Execute - should catch exception and notify user
        with patch('app.bot.middlewares.state_guard.logger') as mock_logger:
            result = await middleware.__call__(
                failing_handler,
                event,
                data
            )
            
            # Verify exception was logged
            assert mock_logger.error.called
            
            # Verify state was cleared
            state.clear.assert_called_once()
            
            # Verify user was notified
            event.answer.assert_called()
            call_args = event.answer.call_args[0][0]
            assert "/start" in call_args


@pytest.mark.asyncio
class TestConcurrentOrderAcceptance:
    """Test Redis lock prevents double booking"""
    
    async def test_two_drivers_one_order_lock_prevents_double_acceptance(
        self,
        db_session,
        sample_order,
        sample_driver,
        second_driver
    ):
        """
        Integration test: Concurrent order acceptance
        
        Verify Redis lock prevents two drivers from accepting same order.
        """
        from app.services.order_service import accept_order_by_driver
        import asyncio
        
        # Setup order
        order = sample_order
        order.status = OrderStatus.PENDING
        db_session.add(order)
        await db_session.commit()
        
        # Simulate concurrent acceptance
        results = await asyncio.gather(
            accept_order_by_driver(sample_driver.driver_id, order.order_id),
            accept_order_by_driver(second_driver.driver_id, order.order_id),
            return_exceptions=True
        )
        
        # Verify: Exactly one success
        successes = [r for r in results if isinstance(r, dict) and r.get('success')]
        failures = [r for r in results if isinstance(r, dict) and not r.get('success')]
        
        assert len(successes) == 1, "Only one driver should succeed"
        assert len(failures) == 1, "One driver should fail due to lock"
        
        # Verify order accepted by exactly one driver
        await db_session.refresh(order)
        assert order.status == OrderStatus.ACCEPTED
        assert order.driver_id in [sample_driver.driver_id, second_driver.driver_id]


# Fixtures
@pytest_asyncio.fixture
async def sample_passenger(db_session):
    """Create sample passenger"""
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
async def sample_driver(db_session, faker):
    """Create sample driver"""
    from app.models.driver import create_driver
    from app.models.user import create_user

    user_id = faker.random_int(min=20000, max=99999)

    user = await create_user(
        db_session,
        user_id=user_id,
        phone_number="+998909876543",
        first_name="Test Driver",
        role=UserRole.DRIVER
    )
    
    driver = await create_driver(
        db_session,
        user_id=user_id,
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
async def second_driver(db_session, faker):
    """Create second driver for concurrent tests"""
    from app.models.driver import create_driver
    from app.models.user import create_user
    
    user_id = faker.random_int(min=30000, max=199999)

    user = await create_user(
        db_session,
        user_id=user_id,
        phone_number="+998907654321",
        first_name="Second Driver",
        role=UserRole.DRIVER
    )
    
    driver = await create_driver(
        db_session,
        user_id=user_id,
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
        distance_km=10.5,
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
