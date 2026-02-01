import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.queue_service import driver_queue

async def main():
    print("🧹 Cleaning up queues for migration...")
    # Initialize redis if needed lazy connection works
    try:
        count = await driver_queue.remove_all_drivers_from_queues()
        print(f"✅ Successfully cleared {count} queues and related data.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
