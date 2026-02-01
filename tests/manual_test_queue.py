import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from app.services.queue_service import DriverQueueManager

class TestQueueInactivity(unittest.IsolatedAsyncioTestCase):
    async def test_inactivity_logic(self):
        print("Testing inactivity logic...")
        queue_service = DriverQueueManager()
        queue_service.redis = AsyncMock()
        
        driver_id = 123
        route_id = 1
        
        # 1. Track inactivity
        queue_service.redis.incr.return_value = 1
        count = await queue_service.track_driver_inactivity(driver_id, route_id)
        print(f"Track result 1: {count}")
        assert count == 1
        
        queue_service.redis.incr.return_value = 2
        count = await queue_service.track_driver_inactivity(driver_id, route_id)
        print(f"Track result 2: {count}")
        assert count == 2
        
        # 2. Get inactivity
        queue_service.redis.get.return_value = "2"
        count = await queue_service.get_driver_inactivity_count(driver_id, route_id)
        print(f"Get result: {count}")
        assert count == 2
        
        # 3. Clear inactivity
        await queue_service.clear_driver_inactivity(driver_id, route_id)
        print("Clear called")
        queue_service.redis.delete.assert_called()
        
        print("✅ Inactivity logic verified!")

if __name__ == "__main__":
    unittest.main()
