import asyncio
import sys
import os
import time
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import get_session, init_database
from app.core.redis_client import init_redis, redis_client
from app.services.queue_service import driver_queue
from app.models.system_settings import get_setting

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

async def test_fifo_logic():
    print(f"\n{YELLOW}--- TEST 1: FIFO Logic (TimeStamp Score) ---{RESET}")
    route_id = 999
    
    # 1. Clear queue
    await driver_queue.redis.delete(f"driver_queue:{route_id}")
    
    drivers = [
        (101, "Driver A"),
        (102, "Driver B"),
        (103, "Driver C")
    ]
    
    # 2. Add drivers with delay
    for did, name in drivers:
        await driver_queue.add_driver(did, route_id)
        print(f"Added {name} (ID: {did}) to queue")
        await asyncio.sleep(0.1) # Ensure timestamps differ
        
    # 3. Check queue order
    stats = await driver_queue.get_queue_stats(route_id)
    top_driver_ids = stats['top_drivers']
    print(f"Queue Order: {top_driver_ids}")
    
    # Expect: 101, 102, 103 (Low score = Early timestamp = First)
    if top_driver_ids == [101, 102, 103]:
        print(f"{GREEN}✅ FIFO Logic Passed: Earlier joiner is first{RESET}")
    else:
        print(f"{RED}❌ FIFO Logic Failed: Expected [101, 102, 103], got {top_driver_ids}{RESET}")

async def test_offer_locking():
    print(f"\n{YELLOW}--- TEST 2: Offer Locking (Double Booking Prevention) ---{RESET}")
    driver_id = 101
    order_id_1 = 5001
    order_id_2 = 5002
    
    # 1. Lock driver for Order 1
    print(f"Locking Driver {driver_id} for Order {order_id_1}...")
    success = await driver_queue.lock_driver_for_offer(driver_id, order_id_1)
    
    if success:
        print(f"{GREEN}✅ Locked successfully for Order 1{RESET}")
    else:
        print(f"{RED}❌ Failed to lock for Order 1!{RESET}")
        return

    # 2. Try to lock again for Order 2 (Should Fail)
    print(f"Attempting to lock Driver {driver_id} for Order {order_id_2} (Race Condition)...")
    success_2 = await driver_queue.lock_driver_for_offer(driver_id, order_id_2)
    
    if not success_2:
        print(f"{GREEN}✅ Blocked successfully! Driver is busy.{RESET}")
    else:
        print(f"{RED}❌ Logic Failed! Driver was double-booked!{RESET}")

    # 3. Unlock
    await driver_queue.unlock_driver_offer(driver_id)
    print("Unlocked driver.")
    
    # 4. Try again (Should Succeed)
    success_3 = await driver_queue.lock_driver_for_offer(driver_id, order_id_2)
    if success_3:
         print(f"{GREEN}✅ Re-lock successful after unlock.{RESET}")
    else:
         print(f"{RED}❌ Failed to re-lock after unlock!{RESET}")

async def test_dynamic_messages():
    print(f"\n{YELLOW}--- TEST 3: Dynamic Messages ---{RESET}")
    
    async with get_session() as session:
        # Fetch dynamic message
        msg_key = "msg_trip_started_passenger"
        msg = await get_setting(session, msg_key)
        
        print(f"Message Key: {msg_key}")
        print(f"Value: {msg}")
        
        if msg and "Safar boshlandi" in msg:
             print(f"{GREEN}✅ Dynamic Message content verified.{RESET}")
        else:
             print(f"{RED}❌ Dynamic Message missing or incorrect!{RESET}")

async def main():
    print(f"{GREEN}🚀 STARTING FULL SYSTEM VERIFICATION...{RESET}")
    
    # Init
    await init_redis()
    await init_database()
    
    try:
        await test_fifo_logic()
        await test_offer_locking()
        await test_dynamic_messages()
    finally:
        await redis_client.close()
        # Close DB connection if needed (pool handles it generally)

    print(f"\n{GREEN}✨ VERIFICATION COMPLETE ✨{RESET}")

if __name__ == "__main__":
    asyncio.run(main())
