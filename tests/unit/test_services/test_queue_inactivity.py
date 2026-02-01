import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.queue_service import DriverQueueManager

@pytest.mark.asyncio
async def test_driver_inactivity_tracking():
    # Setup
    queue_service = DriverQueueManager()
    # Mock redis to avoid actual redis connection
    queue_service.redis = AsyncMock()
    # Force use of memory queue is NOT needed if we mock redis correctly, 
    # but let's see how the class handles it. 
    # Actually, the class checks self._use_memory() which checks self.redis._client.
    # If we want to test redis logic, we should mock the redis calls.
    
    # Let's mock the redis methods used
    driver_id = 123
    route_id = 1
    
    # 1. Test track_driver_inactivity
    # Mock incr to return 1
    queue_service.redis.incr.return_value = 1
    count = await queue_service.track_driver_inactivity(driver_id, route_id)
    assert count == 1
    queue_service.redis.incr.assert_called_with(f"driver_inactivity:{driver_id}:{route_id}")
    queue_service.redis.expire.assert_called_with(f"driver_inactivity:{driver_id}:{route_id}", 3600)
    
    # Mock incr to return 2
    queue_service.redis.incr.return_value = 2
    count = await queue_service.track_driver_inactivity(driver_id, route_id)
    assert count == 2
    
    # 2. Test get_driver_inactivity_count
    queue_service.redis.get.return_value = "2"
    count = await queue_service.get_driver_inactivity_count(driver_id, route_id)
    assert count == 2
    queue_service.redis.get.assert_called_with(f"driver_inactivity:{driver_id}:{route_id}")
    
    # 3. Test clear_driver_inactivity
    await queue_service.clear_driver_inactivity(driver_id, route_id)
    queue_service.redis.delete.assert_called_with(f"driver_inactivity:{driver_id}:{route_id}")

@pytest.mark.asyncio
async def test_nightly_queue_cleanup():
    queue_service = DriverQueueManager()
    queue_service.redis = AsyncMock()
    queue_service.redis.client = MagicMock()
    
    # Mock scan_iter to return some keys
    async def mock_scan_iter(match):
        if match == "driver_queue:*":
            yield "driver_queue:1"
            yield "driver_queue:2"
        elif match == "driver_join_time:*":
            yield "driver_join_time:123:1"
        elif match == "driver_inactivity:*":
            yield "driver_inactivity:123:1"

    queue_service.redis.client.scan_iter = mock_scan_iter
    
    count = await queue_service.remove_all_drivers_from_queues()
    
    # Should delete 2 queues + 1 join time + 1 inactivity = 4 delete calls
    # but the function returns count of "queues" cleared (which is 2)
    assert count == 2
    assert queue_service.redis.delete.call_count == 4
