"""
app/core/locks.py

BU FAYL NIMA QILADI:
- Distributed lock (2 haydovchi bir vaqtda bitta buyurtma ololmasligi)
- Token-based lock (faqat owner o'chirishi mumkin)
- Lua script orqali atomic operation

MUAMMO:
    Haydovchi A: "Qabul qilish" bosadi
    Haydovchi B: Bir vaqtda "Qabul qilish" bosadi
    ❌ Ikkalasi ham qabul qilganga o'xshaydi!

YECHIM:
    Redis lock orqali faqat birinchi bosgan qabul qiladi.

ISHLATISH:
    from app.core.locks import acquire_order_lock
    
    async with acquire_order_lock(order_id=123) as locked:
        if locked:
            # Buyurtmani qabul qilish
            await accept_order()
        else:
            # Boshqa haydovchi oldi
            print("Bu buyurtma band!")
"""

import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from loguru import logger

from app.core.redis_client import redis_client


# ============================================
# LUA SCRIPT (ATOMIC DELETE)
# ============================================

# NIMA UCHUN LUA SCRIPT?
# Redis'da GET + DELETE 2 ta command = NOT ATOMIC
# Lua script = 1 ta atomic command

RELEASE_LOCK_SCRIPT = """
-- Key'ni tekshirish
if redis.call("get", KEYS[1]) == ARGV[1] then
    -- Faqat bizning tokenimiz bo'lsa o'chirish
    return redis.call("del", KEYS[1])
else
    -- Boshqa token - o'chirmaslik
    return 0
end
"""

# Script SHA (Redis'da cache qilish uchun)
# Har safar yubormaslik uchun birinchi marta load qilamiz
_script_sha: Optional[str] = None


async def _load_lua_script():
    """
    Lua script'ni Redis'ga yuklash
    
    NIMAGA KERAK:
    Har safar script yubormaslik, faqat SHA hash yuborish (tezroq)
    """
    global _script_sha
    
    if _script_sha is None:
        try:
            _script_sha = await redis_client.client.script_load(RELEASE_LOCK_SCRIPT)
            logger.debug(f"✅ Lua script loaded: {_script_sha[:8]}...") # type: ignore
        except Exception as e:
            logger.error(f"❌ Failed to load Lua script: {e}")
            _script_sha = None


# ============================================
# DISTRIBUTED LOCK
# ============================================

@asynccontextmanager
async def acquire_order_lock(
    order_id: int,
    timeout: int = 10,
    retry_delay: float = 0.1,
    max_retries: int = 3
) -> AsyncGenerator[bool, None]:
    """
    Buyurtma uchun distributed lock
    
    BU FUNCTION NIMA QILADI:
    1. Redis'da lock ochishga harakat qiladi
    2. Agar band bo'lsa - retry qiladi
    3. Lock olinsa - tokenni qaytaradi
    4. Ishlar tugagach - lock'ni ochadi (faqat owner)
    
    Args:
        order_id: Buyurtma ID
        timeout: Lock timeout (soniya) - avtomatik ochiladi
        retry_delay: Retry orasidagi kutish (soniya)
        max_retries: Maksimal retry soni
    
    Returns:
        (bool): Lock olinganmi?
    
    ISHLATISH:
        async with acquire_order_lock(order_id=123) as locked:
            if locked:
                # Lock olindi - buyurtmani qabul qilish
                await db.update_order(order_id, driver_id=driver_id)
                print("✅ Buyurtma qabul qilindi!")
            else:
                # Lock olinmadi - boshqa haydovchi oldi
                print("⚠️ Bu buyurtma boshqa haydovchi tomonidan qabul qilinmoqda")
    
    RACE CONDITION MUAMMOSI (Lock'siz):
        
        VAQT    HAYDOVCHI A              HAYDOVCHI B
        ----    ------------              ------------
        00:00   "Qabul qilish" bosadi
        00:00   DB: order.status check    "Qabul qilish" bosadi
        00:01   status = "pending" ✅     DB: order.status check
        00:01   UPDATE order ...          status = "pending" ✅
        00:02   ✅ Qabul qilindi!         UPDATE order ...
        00:02                             ✅ Qabul qilindi!
        
        ❌ NATIJA: Ikkalasi ham qabul qildi!
    
    LOCK BILAN:
        
        VAQT    HAYDOVCHI A              HAYDOVCHI B
        ----    ------------              ------------
        00:00   "Qabul qilish" bosadi
        00:00   Lock olish ✅             "Qabul qilish" bosadi
        00:01   DB: order.status check    Lock olish ❌ (band!)
        00:01   UPDATE order ...          ⚠️ "Bu buyurtma band"
        00:02   Lock ochish               
        00:02   ✅ Qabul qilindi!         
        
        ✅ NATIJA: Faqat A qabul qildi!
    """
    
    lock_key = f"lock:order:{order_id}"
    token = str(uuid.uuid4())  # Unique token
    lock_acquired = False
    
    # Lua script'ni yuklash (birinchi marta)
    await _load_lua_script()
    
    # Lock olishga harakat
    for attempt in range(max_retries):
        try:
            # Redis SETNX (SET if Not eXists)
            lock_acquired = await redis_client.set(
                lock_key,
                token,
                ex=timeout,  # Timeout (soniya)
                nx=True      # Faqat mavjud bo'lmasa
            )
            
            if lock_acquired:
                logger.debug(f"🔒 Lock acquired: order:{order_id}, token:{token[:8]}...")
                break
            else:
                # Lock band - retry
                if attempt < max_retries - 1:
                    logger.debug(f"⏳ Lock busy, retrying... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.warning(f"❌ Failed to acquire lock: order:{order_id} (max retries)")
        
        except Exception as e:
            logger.error(f"❌ Lock error: order:{order_id} - {e}")
            break
    
    try:
        # Lock holatini yield qilish
        yield lock_acquired
    
    finally:
        # Lock'ni ochish (faqat owner)
        if lock_acquired:
            try:
                # Lua script orqali atomic delete
                if _script_sha:
                    # SHA orqali (tezroq)
                    deleted = await redis_client.client.evalsha(
                        _script_sha,
                        1,
                        lock_key, # type: ignore # type: ignore # type: ignore 
                        token # type: ignore
                    )
                else:
                    # Fallback: script'ni to'g'ridan-to'g'ri yuborish
                    deleted = await redis_client.client.eval(
                        RELEASE_LOCK_SCRIPT,
                        1,
                        lock_key, # type: ignore
                        token # type: ignore
                    )
                
                if deleted:
                    logger.debug(f"🔓 Lock released: order:{order_id}")
                else:
                    logger.warning(f"⚠️ Lock already released or timeout: order:{order_id}")
            
            except Exception as e:
                logger.error(f"❌ Lock release error: order:{order_id} - {e}")


# ============================================
# GENERIC LOCK (Boshqa joylar uchun)
# ============================================

@asynccontextmanager
async def acquire_lock(
    resource: str,
    timeout: int = 10,
    retry_delay: float = 0.1,
    max_retries: int = 3
) -> AsyncGenerator[bool, None]:
    """
    Umumiy distributed lock (istalgan resource uchun)
    
    Args:
        resource: Resource nomi (masalan: "driver:123", "payment:456")
        timeout: Lock timeout (soniya)
        retry_delay: Retry orasidagi kutish
        max_retries: Maksimal retry soni
    
    ISHLATISH:
        # Driver balansini yangilash (concurrent issue oldini olish)
        async with acquire_lock(f"driver:balance:{driver_id}") as locked:
            if locked:
                driver = await db.get_driver(driver_id)
                driver.balance -= 5000
                await db.commit()
    """
    
    lock_key = f"lock:{resource}"
    token = str(uuid.uuid4())
    lock_acquired = False
    
    await _load_lua_script()
    
    for attempt in range(max_retries):
        try:
            lock_acquired = await redis_client.set(
                lock_key,
                token,
                ex=timeout,
                nx=True
            )
            
            if lock_acquired:
                logger.debug(f"🔒 Lock acquired: {resource}")
                break
            else:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        except Exception as e:
            logger.error(f"❌ Lock error: {resource} - {e}")
            break
    
    try:
        yield lock_acquired
    
    finally:
        if lock_acquired:
            try:
                if _script_sha:
                    await redis_client.client.evalsha(_script_sha, 1, lock_key, token) # type: ignore
                else:
                    await redis_client.client.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, token) # type: ignore
                
                logger.debug(f"🔓 Lock released: {resource}")
            
            except Exception as e:
                logger.error(f"❌ Lock release error: {resource} - {e}")


# ============================================
# LOCK CHECK (Lock tekshirish)
# ============================================

async def is_locked(resource: str) -> bool:
    """
    Resource lock'langanmi tekshirish
    
    Args:
        resource: Resource nomi
    
    Returns:
        True: Lock'langan
        False: Bo'sh
    
    ISHLATISH:
        if await is_locked(f"order:{order_id}"):
            print("Bu buyurtma band!")
    """
    lock_key = f"lock:{resource}"
    return await redis_client.exists(lock_key)


async def get_lock_ttl(resource: str) -> int:
    """
    Lock'ning qolgan vaqti
    
    Returns:
        Soniya (-1: expire yo'q, -2: lock yo'q)
    
    ISHLATISH:
        ttl = await get_lock_ttl(f"order:{order_id}")
        if ttl > 0:
            print(f"Lock {ttl} soniyadan keyin ochiladi")
    """
    lock_key = f"lock:{resource}"
    return await redis_client.ttl(lock_key)


# ============================================
# LOCK STATISTICS (Monitoring uchun)
# ============================================

async def get_active_locks(pattern: str = "lock:*") -> list:
    """
    Aktiv lock'lar ro'yxati
    
    Args:
        pattern: Lock pattern (Redis SCAN uchun)
    
    Returns:
        List of lock keys
    
    ISHLATISH:
        # Barcha order lock'lari
        order_locks = await get_active_locks("lock:order:*")
        print(f"Aktiv order lock'lar: {len(order_locks)}")
    
    DIQQAT:
    SCAN operatsiyasi sekin bo'lishi mumkin (ko'p key bo'lsa)
    Production'da ehtiyotkorlik bilan ishlating!
    """
    try:
        locks = []
        async for key in redis_client.client.scan_iter(match=pattern):
            locks.append(key)
        return locks
    
    except Exception as e:
        logger.error(f"❌ Failed to get active locks: {e}")
        return []


async def clear_expired_locks(pattern: str = "lock:*"):
    """
    Muddati o'tgan lock'larni tozalash
    
    DIQQAT:
    Redis avtomatik tozalaydi (expire), bu faqat manual tozalash uchun
    """
    try:
        count = 0
        async for key in redis_client.client.scan_iter(match=pattern):
            ttl = await redis_client.ttl(key)
            if ttl == -1:  # Expire yo'q (xato)
                await redis_client.delete(key)
                count += 1
        
        if count > 0:
            logger.info(f"🧹 Cleared {count} expired locks")
        
        return count
    
    except Exception as e:
        logger.error(f"❌ Failed to clear expired locks: {e}")
        return 0


# ============================================
# TESTING HELPER
# ============================================

async def test_lock_race_condition():
    """
    Lock'ni test qilish - 2 coroutine bir vaqtda bitta resource'ni olishga harakat qiladi
    
    NATIJA:
    Faqat bitta muvaffaqiyatli bo'lishi kerak!
    """
    
    async def worker(worker_id: int, order_id: int):
        """Test worker"""
        print(f"Worker {worker_id}: Buyurtma {order_id}ni olishga harakat...")
        
        async with acquire_order_lock(order_id) as locked:
            if locked:
                print(f"✅ Worker {worker_id}: Lock olindi!")
                await asyncio.sleep(2)  # Ishlarni simulyatsiya qilish
                print(f"✅ Worker {worker_id}: Ish tugadi")
                return True
            else:
                print(f"❌ Worker {worker_id}: Lock olinmadi (boshqa worker band)")
                return False
    
    # 2 ta worker'ni parallel ishga tushirish
    order_id = 999
    results = await asyncio.gather(
        worker(1, order_id),
        worker(2, order_id)
    )
    
    success_count = sum(results)
    print(f"\n📊 Natija: {success_count} ta worker muvaffaqiyatli")
    print(f"Expected: 1 (faqat bitta worker lock olishi kerak)")
    
    if success_count == 1:
        print("✅ TEST PASSED: Lock to'g'ri ishlayapti!")
    else:
        print("❌ TEST FAILED: Lock muammoli!")


# ============================================
# MAIN TEST
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.core.locks
    """
    import asyncio
    from app.core.redis_client import init_redis, close_redis
    
    async def main():
        print("\n🧪 Testing Distributed Lock System...\n")
        
        # Redis'ni ishga tushirish
        await init_redis()
        
        # Test 1: Oddiy lock
        print("📝 Test 1: Oddiy lock\n")
        async with acquire_lock("test_resource") as locked:
            if locked:
                print("✅ Lock olindi")
                await asyncio.sleep(1)
                print("✅ Lock avtomatik ochilinadi")
        
        print()
        
        # Test 2: Race condition
        print("📝 Test 2: Race condition test\n")
        await test_lock_race_condition()
        
        print()
        
        # Test 3: Lock statistics
        print("📝 Test 3: Lock statistics\n")
        locks = await get_active_locks()
        print(f"Aktiv lock'lar: {len(locks)}")
        
        # Redis'ni yopish
        await close_redis()
        
        print("\n✅ All tests completed!\n")
    
    asyncio.run(main())