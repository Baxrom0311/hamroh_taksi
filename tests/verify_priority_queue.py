import asyncio
import sys
import os
import time
from unittest.mock import MagicMock, patch, AsyncMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.queue_service import DriverQueueManager

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

class MockRedisClient:
    def __init__(self):
        self.data = {} # Key -> Score
        
    async def zadd(self, key, mapping):
        # mapping: {member: score}
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)
        return len(mapping)

    async def zscore(self, key, member):
        if key in self.data and member in self.data[key]:
            return self.data[key][member]
        return None

    async def zrange(self, key, start, end, withscores=False, desc=False):
        # Simple implementation for verification
        if key not in self.data:
            return []
            
        items = list(self.data[key].items())
        # Sort by score (asc)
        items.sort(key=lambda x: x[1])
        
        # Slice
        # Note: Redis end is inclusive, Python slice is exclusive
        if end == -1:
            sliced = items[start:]
        else:
            sliced = items[start:end+1]
            
        if withscores:
            return sliced
        return [item[0] for item in sliced]

    async def zcard(self, key):
        if key not in self.data:
            return 0
        return len(self.data[key])

    async def zrank(self, key, member):
        if key not in self.data:
            return None
        items = list(self.data[key].items())
        items.sort(key=lambda x: x[1])
        for idx, (m, score) in enumerate(items):
            if m == member:
                return idx
        return None

async def verify_priority_logic():
    print(f"{GREEN}🚀 STARTING PRIORITY QUEUE VERIFICATION (AsyncMock)...{RESET}")

    # ==========================================
    # SETUP
    # ==========================================
    
    # 1. Mock Redis
    mock_redis_client = MockRedisClient()
    
    # 2. Mock Drivers
    mock_drivers = {
        101: MagicMock(driver_id=101, is_priority=False, current_route_id=1),  # Normal
        102: MagicMock(driver_id=102, is_priority=True, current_route_id=1),   # Priority
        103: MagicMock(driver_id=103, is_priority=False, current_route_id=1),  # Normal
        104: MagicMock(driver_id=104, is_priority=True, current_route_id=1),   # Priority
    }
    
    # 3. Mock DB Session & Get Driver
    # We need to patch where queue_service imports these
    with patch("app.services.queue_service.get_session") as mock_get_session, \
         patch("app.services.queue_service.get_driver_by_id") as mock_get_driver, \
         patch("app.services.queue_service.redis_client") as mock_redis_wrapper:
        
        # Configure Mock Session
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        # Configure Mock Get Driver
        async def side_effect_get_driver(session, driver_id):
            return mock_drivers.get(driver_id)
        
        mock_get_driver.side_effect = side_effect_get_driver
        
        # Configure Redis Wrapper
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_wrapper.expire = AsyncMock(return_value=True)
        mock_redis_wrapper.delete = AsyncMock(return_value=1)
        mock_redis_wrapper.set = AsyncMock(return_value=True)
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        mock_redis_wrapper.incr = AsyncMock(return_value=1)
        mock_redis_wrapper.exists = AsyncMock(return_value=False)

        # Initialize Service
        queue_service = DriverQueueManager()
        # Force service to use our mock client
        queue_service.redis = mock_redis_wrapper
        # Monkey patch _use_memory to return False (so it uses our redis mock)
        queue_service._use_memory = MagicMock(return_value=False)


        # ==========================================
        # TEST 1: MIXED ADDITION (FIFO + PRIORITY)
        # ==========================================
        print(f"\n{YELLOW}--- TEST 1: Mixed Addition (FIFO + Priority) ---{RESET}")
        route_id = 1
        
        # Add in sequence:
        # 1. Normal (101)
        # 2. Priority (102) -> Should jump to front
        # 3. Normal (103) -> Should go behind 101
        # 4. Priority (104) -> Should go behind 102 but before 101/103
        
        print("Adding Driver 101 (Normal)...")
        await queue_service.add_driver(101, route_id)
        await asyncio.sleep(0.01) # Ensure time difference
        
        print("Adding Driver 102 (Priority)...")
        await queue_service.add_driver(102, route_id)
        await asyncio.sleep(0.01)
        
        print("Adding Driver 103 (Normal)...")
        await queue_service.add_driver(103, route_id)
        await asyncio.sleep(0.01)
        
        print("Adding Driver 104 (Priority)...")
        await queue_service.add_driver(104, route_id)
        
        # Check Stats (which uses zrange)
        stats = await queue_service.get_queue_stats(route_id)
        top_drivers = stats['top_drivers']
        top_ids = [d['driver_id'] for d in top_drivers]
        
        print(f"Queue Order: {top_ids}")
        
        # Expected: [102, 104, 101, 103]
        # Explanation:
        # Priority group (102, 104) - FIFO within group
        # Normal group (101, 103) - FIFO within group
        # Note: zrange in stats returns strings usually from redis, but my mock returns what was put in (strings likely)
        # QueueService converts to int? Let's check stats implementation or assume strings
        # The service code does: 'driver_id': int(driver_id) usually.
        
        # Redis ZADD usually stores keys as strings. My mock stores keys as provided in mapping key.
        # queue_service.add_driver calls zadd with str(driver_id). So keys are strings.
        # get_queue_stats does int(d_id)
        
        expected_order = [102, 104, 101, 103]
        
        if top_ids == expected_order:
            print(f"{GREEN}✅ Mix Logic Passed!{RESET}")
        else:
            print(f"{RED}❌ Mix Logic Failed! Expected {expected_order}, got {top_ids}{RESET}")

        # ==========================================
        # TEST 2: TOGGLE PRIORITY (Dynamic Check)
        # ==========================================
        print(f"\n{YELLOW}--- TEST 2: Toggle Priority ---{RESET}")
        
        # Driver 101 (Normal) is currently 3rd.
        # Promote 101 to Priority.
        # He joined FIRST (earliest timestamp).
        # So his score (T0 - offset) will be smallest.
        # He should become #1.
        
        print("Toggling Driver 101 to Priority=True...")
        
        # Mock DB update for toggle
        with patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_execute:
             await queue_service.toggle_driver_priority(101, True)
        
        stats = await queue_service.get_queue_stats(route_id)
        new_ids = [d['driver_id'] for d in stats['top_drivers']]
        print(f"New Queue Order: {new_ids}")
        
        expected_after_toggle = [101, 102, 104, 103]
        
        if new_ids == expected_after_toggle:
             print(f"{GREEN}✅ Toggle Logic Passed! (Oldest driver promoted to #1){RESET}")
        else:
             print(f"{RED}❌ Toggle Logic Failed! Expected {expected_after_toggle}, got {new_ids}{RESET}")

    print(f"\n{GREEN}✨ VERIFICATION COMPLETE ✨{RESET}")

if __name__ == "__main__":
    asyncio.run(verify_priority_logic())
