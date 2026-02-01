import asyncio
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fakeredis import FakeRedis, FakeAsyncRedis
from app.services.queue_service import DriverQueueManager

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

async def main():
    print(f"{GREEN}🚀 STARTING MOCK VERIFICATION (FakeRedis)...{RESET}")

    # 1. Setup Fake Redis
    fake_redis = FakeAsyncRedis()
    fake_redis.client = fake_redis  # ✅ Recursive reference: self.redis.client refers back to self.redis (fake)
    
    # Initialize service
    queue_service = DriverQueueManager()
    
    # Overwrite the redis wrapper with our fake client directly
    queue_service.redis = fake_redis
    queue_service.redis._client = fake_redis # ✅ Force _use_memory() to return False

    # ==========================================
    # TEST 1: FIFO LOGIC
    # ==========================================
    print(f"\n{YELLOW}--- TEST 1: FIFO Logic (TimeStamp Score) ---{RESET}")
    route_id = 999
    
    drivers = [
        (101, "Driver A"),
        (102, "Driver B"),
        (103, "Driver C")
    ]
    
    for did, name in drivers:
        await queue_service.add_driver(did, route_id)
        print(f"Added {name} (ID: {did}) to queue")
        await asyncio.sleep(0.01)
        
    stats = await queue_service.get_queue_stats(route_id)
    top_drivers = stats['top_drivers']
    print(f"Queue Order: {top_drivers}")
    
    # Extract IDs for comparison
    top_driver_ids = [d['driver_id'] for d in top_drivers]
    
    if top_driver_ids == [101, 102, 103]:
        print(f"{GREEN}✅ FIFO Logic Passed.{RESET}")
    else:
         print(f"{RED}❌ FIFO Logic Failed! Got {top_driver_ids}{RESET}")

    # ==========================================
    # TEST 2: OFFER LOCKING
    # ==========================================
    print(f"\n{YELLOW}--- TEST 2: Offer Locking (Double Booking) ---{RESET}")
    driver_id = 101
    order_1 = 5001
    order_2 = 5002
    
    # Lock for Order 1
    success = await queue_service.lock_driver_for_offer(driver_id, order_1)
    if success:
         print(f"{GREEN}✅ Locked for Order 1{RESET}")
    else:
         print(f"{RED}❌ Failed to lock for Order 1{RESET}")

    # Try Lock for Order 2
    success_2 = await queue_service.lock_driver_for_offer(driver_id, order_2)
    if not success_2:
         print(f"{GREEN}✅ Blocked double-booking correctly.{RESET}")
    else:
         print(f"{RED}❌ Logic Failed! Driver double-booked.{RESET}")

    # Unlock
    await queue_service.unlock_driver_offer(driver_id)
    
    # Try Lock again
    success_3 = await queue_service.lock_driver_for_offer(driver_id, order_2)
    if success_3:
         print(f"{GREEN}✅ Re-lock successful after unlock.{RESET}")
    else:
         print(f"{RED}❌ Failed to re-lock after unlock.{RESET}")

    print(f"\n{GREEN}✨ MOCK VERIFICATION COMPLETE ✨{RESET}")

if __name__ == "__main__":
    asyncio.run(main())
