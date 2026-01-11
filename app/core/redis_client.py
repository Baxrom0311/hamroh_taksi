"""
app/core/redis_client.py

BU FAYL NIMA QILADI:
- Redis'ga ulanadi (in-memory database)
- Cache (tez ma'lumot saqlash)
- Lock (race condition oldini olish)
- Queue (Celery broker)
- Rate limiting (spam oldini olish)

REDIS NIMA:
- Juda tez in-memory database (< 1ms)
- Key-value storage
- Expire qilish mumkin (10 sek keyin o'chadi)
- Distributed lock uchun ideal

ISHLATISH:
    from app.core.redis_client import redis_client
    
    await redis_client.set("key", "value", ex=60)  # 60 sek
    value = await redis_client.get("key")
"""

import redis.asyncio as redis
from redis.asyncio import Redis
from typing import Optional, Any
import json
from loguru import logger

from config.settings import settings

# ============================================
# REDIS CLIENT CLASS
# ============================================

class RedisClient:
    """
    Redis bilan ishlash uchun wrapper class
    
    NIMAGA KERAK:
    1. Connection pool boshqarish
    2. Serialization (Python object → Redis)
    3. Error handling
    4. Helper methods (cache, lock, counter)
    """
    
    def __init__(self):
        self._client: Optional[Redis] = None
    
    async def connect(self):
        """
        Redis'ga ulanish
        
        CONNECTION POOL:
        - max_connections: Maksimal ulanishlar (default: 50)
        - decode_responses: String qaytarish (default: bytes)
        """
        
        try:
            self._client = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,  # bytes emas, string qaytaradi
                max_connections=50,     # Connection pool
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            
            # Test ping
            await self._client.ping()
            
            logger.success(f"✅ Redis connected: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        
        except redis.ConnectionError as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
    
    async def close(self):
        """Redis connection'ni yopish"""
        if self._client:
            await self._client.close()
            logger.info("🔌 Redis connection closed")
    
    @property
    def client(self) -> Redis:
        """Redis client'ni olish"""
        if self._client is None:
            raise RuntimeError("Redis client initialized emas! connect() ni chaqiring.")
        return self._client
    
    # ============================================
    # BASIC OPERATIONS
    # ============================================
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ex: Optional[int] = None,
        nx: bool = False
    ) -> bool:
        """
        Key-value saqlash
        
        Args:
            key: Kalit (masalan: "user:123")
            value: Qiymat (str, int, dict, list)
            ex: Expire vaqti (soniya)
            nx: Faqat mavjud bo'lmasa set qilish (lock uchun)
        
        Returns:
            True: Muvaffaqiyatli
            False: Xato yoki nx=True va key mavjud
        
        MISOL:
            # 60 soniya uchun saqlash
            await redis_client.set("session:123", "active", ex=60)
            
            # Lock (faqat mavjud bo'lmasa)
            locked = await redis_client.set("lock:order:1", "locked", ex=10, nx=True)
        """
        try:
            # Dict yoki list bo'lsa → JSON
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            
            result = await self.client.set(key, value, ex=ex, nx=nx)
            return bool(result)
        
        except Exception as e:
            logger.error(f"Redis SET error: {key} - {e}")
            return False
    
    async def get(self, key: str, default: Any = None) -> Optional[Any]:
        """
        Key bo'yicha qiymatni olish
        
        Args:
            key: Kalit
            default: Agar topilmasa qaytariladigan qiymat
        
        Returns:
            Qiymat yoki default
        
        MISOL:
            value = await redis_client.get("user:123")
            if value:
                print(f"User session: {value}")
        """
        try:
            value = await self.client.get(key)
            
            if value is None:
                return default
            
            # JSON parse qilish (agar dict/list bo'lsa)
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        
        except Exception as e:
            logger.error(f"Redis GET error: {key} - {e}")
            return default
    
    async def delete(self, *keys: str) -> int:
        """
        Key(lar)ni o'chirish
        
        Returns:
            O'chirilgan key'lar soni
        
        MISOL:
            deleted = await redis_client.delete("user:123", "user:456")
            print(f"{deleted} ta key o'chirildi")
        """
        try:
            return await self.client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE error: {keys} - {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """
        Key mavjudligini tekshirish
        
        MISOL:
            if await redis_client.exists("lock:order:1"):
                print("Lock band!")
        """
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS error: {key} - {e}")
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """
        Key'ga expire vaqti qo'yish
        
        MISOL:
            await redis_client.set("temp", "data")
            await redis_client.expire("temp", 300)  # 5 daqiqa
        """
        try:
            return bool(await self.client.expire(key, seconds))
        except Exception as e:
            logger.error(f"Redis EXPIRE error: {key} - {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """
        Key'ning qolgan vaqti (soniya)
        
        Returns:
            Soniya (-1: expire yo'q, -2: key yo'q)
        
        MISOL:
            remaining = await redis_client.ttl("session:123")
            print(f"{remaining} soniya qoldi")
        """
        try:
            return await self.client.ttl(key)
        except Exception as e:
            logger.error(f"Redis TTL error: {key} - {e}")
            return -2
    
    # ============================================
    # COUNTER OPERATIONS (Rate limiting uchun)
    # ============================================
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """
        Counter'ni oshirish (atomic)
        
        Returns:
            Yangi qiymat
        
        MISOL - SMS Rate Limiting:
            count = await redis_client.incr("sms:+998901234567")
            
            if count == 1:
                # Birinchi SMS - expire qo'yish
                await redis_client.expire("sms:+998901234567", 86400)  # 1 kun
            
            if count > 5:
                print("Kunlik limit tugadi!")
        """
        try:
            return await self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR error: {key} - {e}")
            return 0
    
    async def decr(self, key: str, amount: int = 1) -> int:
        """
        Counter'ni kamaytirish
        
        MISOL:
            await redis_client.decr("driver:balance:123", 5000)
        """
        try:
            return await self.client.decrby(key, amount)
        except Exception as e:
            logger.error(f"Redis DECR error: {key} - {e}")
            return 0
    
    # ============================================
    # HASH OPERATIONS (Object storage)
    # ============================================
    
    async def hset(self, name: str, key: str, value: Any) -> bool:
        """
        Hash ichiga key-value qo'yish
        
        HASH NIMA:
        Redis'da object saqlash usuli
        
        MISOL - User session:
            await redis_client.hset("session:123", "user_id", 123)
            await redis_client.hset("session:123", "username", "Alisher")
            await redis_client.hset("session:123", "role", "driver")
        """
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            
            return bool(await self.client.hset(name, key, value)) # type: ignore
        except Exception as e:
            logger.error(f"Redis HSET error: {name}:{key} - {e}")
            return False
    
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """
        Hash'dan qiymat olish
        
        MISOL:
            username = await redis_client.hget("session:123", "username")
        """
        try:
            value = await self.client.hget(name, key) # type: ignore
            
            if value is None:
                return None
            
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        
        except Exception as e:
            logger.error(f"Redis HGET error: {name}:{key} - {e}")
            return None
    
    async def hgetall(self, name: str) -> dict:
        """
        Hash'dan barcha qiymatlarni olish
        
        Returns:
            Dictionary
        
        MISOL:
            session = await redis_client.hgetall("session:123")
            # {'user_id': '123', 'username': 'Alisher', 'role': 'driver'}
        """
        try:
            data = await self.client.hgetall(name) # type: ignore
            
            # JSON parse (agar kerak bo'lsa)
            parsed = {}
            for key, value in data.items():
                try:
                    parsed[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    parsed[key] = value
            
            return parsed
        
        except Exception as e:
            logger.error(f"Redis HGETALL error: {name} - {e}")
            return {}
    
    # ============================================
    # LIST OPERATIONS (Queue uchun)
    # ============================================
    
    async def lpush(self, key: str, *values: Any) -> int:
        """
        List boshiga qo'shish
        
        MISOL - Driver queue:
            await redis_client.lpush("queue:drivers:route_1", 123, 456, 789)
        """
        try:
            return await self.client.lpush(key, *values) # type: ignore
        except Exception as e:
            logger.error(f"Redis LPUSH error: {key} - {e}")
            return 0
    
    async def rpop(self, key: str) -> Optional[str]:
        """
        List oxiridan olish (FIFO)
        
        MISOL:
            driver_id = await redis_client.rpop("queue:drivers:route_1")
        """
        try:
            return await self.client.rpop(key)  # type: ignore
        except Exception as e:
            logger.error(f"Redis RPOP error: {key} - {e}")
            return None
    
    async def llen(self, key: str) -> int:
        """
        List uzunligi
        
        MISOL:
            queue_length = await redis_client.llen("queue:drivers:route_1")
            print(f"Navbatda {queue_length} haydovchi")
        """
        try:
            return await self.client.llen(key) # type: ignore
        except Exception as e:
            logger.error(f"Redis LLEN error: {key} - {e}")
            return 0
    
    # ============================================
    # SORTED SET (Priority queue uchun)
    # ============================================
    
    async def zadd(self, name: str, mapping: dict, nx: bool = False) -> int:
        """
        Sorted set'ga qo'shish (score bilan)
        
        SORTED SET NIMA:
        Score bo'yicha tartiblangan list
        
        Args:
            name: Set nomi
            mapping: {member: score} dictionary
            nx: Faqat yangi member'larni qo'shish
        
        MISOL - Driver priority queue:
            await redis_client.zadd(
                "driver_queue:route_1",
                {
                    "driver:123": 85.5,  # 85.5 ball
                    "driver:456": 92.0,  # 92.0 ball (yuqori)
                }
            )
        """
        try:
            return await self.client.zadd(name, mapping, nx=nx)
        except Exception as e:
            logger.error(f"Redis ZADD error: {name} - {e}")
            return 0
    
    async def zrevrange(
        self, 
        name: str, 
        start: int, 
        end: int,
        withscores: bool = False
    ):
        """
        Sorted set'dan olish (yuqori score birinchi)
        
        Args:
            start: Boshlanish index (0 = birinchi)
            end: Oxirgi index (-1 = oxirigacha)
            withscores: Score'larni ham qaytarish
        
        Returns:
            List yoki [(member, score), ...] agar withscores=True
        
        MISOL - Top 10 driver:
            top_drivers = await redis_client.zrevrange(
                "driver_queue:route_1",
                0, 9,  # Top 10
                withscores=True
            )
            
            for driver_id, score in top_drivers:
                print(f"{driver_id}: {score} ball")
        """
        try:
            return await self.client.zrevrange(name, start, end, withscores=withscores)
        except Exception as e:
            logger.error(f"Redis ZREVRANGE error: {name} - {e}")
            return []
    
    async def zrem(self, name: str, *members) -> int:
        """
        Sorted set'dan o'chirish
        
        MISOL:
            await redis_client.zrem("driver_queue:route_1", "driver:123")
        """
        try:
            return await self.client.zrem(name, *members)
        except Exception as e:
            logger.error(f"Redis ZREM error: {name} - {e}")
            return 0
    
    # ============================================
    # HEALTH CHECK
    # ============================================
    
    async def ping(self) -> bool:
        """
        Redis sog'ligini tekshirish
        
        Returns:
            True: OK
            False: Muammo bor
        """
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis PING failed: {e}")
            return False
    
    async def info(self) -> dict:
        """
        Redis info (memory, connections, etc)
        
        MISOL:
            info = await redis_client.info()
            print(f"Memory: {info['used_memory_human']}")
        """
        try:
            return await self.client.info()
        except Exception as e:
            logger.error(f"Redis INFO error: {e}")
            return {}


# ============================================
# GLOBAL REDIS CLIENT
# ============================================

# BU OBJECT BUTUN LOYIHADA ISHLATILADI
redis_client = RedisClient()


# ============================================
# INITIALIZATION FUNCTIONS
# ============================================

async def init_redis():
    """
    Redis'ni ishga tushirish
    
    QACHON: Bot start bo'lganda
    """
    logger.info("🔄 Initializing Redis...")
    await redis_client.connect()


async def close_redis():
    """
    Redis'ni yopish
    
    QACHON: Bot o'chganda
    """
    logger.info("🔄 Closing Redis connection...")
    await redis_client.close()


# ============================================
# HELPER FUNCTIONS (Qulaylik uchun)
# ============================================

async def cache_set(key: str, value: Any, ttl: int = 300):
    """
    Cache qilish (5 daqiqa default)
    
    MISOL:
        await cache_set("driver:123", driver_data, ttl=600)
    """
    return await redis_client.set(key, value, ex=ttl)


async def cache_get(key: str, default: Any = None):
    """
    Cache'dan olish
    
    MISOL:
        driver = await cache_get("driver:123")
    """
    return await redis_client.get(key, default)


# ============================================
# TEST
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.core.redis_client
    """
    import asyncio
    
    async def test_redis():
        print("\n🧪 Testing Redis connection...\n")
        
        # Connect
        await init_redis()
        
        # Test SET/GET
        await redis_client.set("test_key", "test_value", ex=10)
        value = await redis_client.get("test_key")
        print(f"✅ SET/GET: {value}")
        
        # Test Counter
        count = await redis_client.incr("test_counter")
        print(f"✅ INCR: {count}")
        
        # Test Hash
        await redis_client.hset("test_hash", "name", "Alisher")
        name = await redis_client.hget("test_hash", "name")
        print(f"✅ HSET/HGET: {name}")
        
        # Test Sorted Set
        await redis_client.zadd("test_zset", {"item1": 10, "item2": 20})
        items = await redis_client.zrevrange("test_zset", 0, -1, withscores=True)
        print(f"✅ ZADD/ZREVRANGE: {items}")
        
        # Clean up
        await redis_client.delete("test_key", "test_counter", "test_hash", "test_zset")
        
        # Ping
        is_alive = await redis_client.ping()
        print(f"✅ PING: {is_alive}")
        
        # Close
        await close_redis()
        
        print("\n✅ Redis test completed!\n")
    
    asyncio.run(test_redis())