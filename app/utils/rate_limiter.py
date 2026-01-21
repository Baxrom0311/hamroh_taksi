"""
app/utils/rate_limiter.py

RATE LIMITING UTILITIES

BU FAYL NIMA QILADI:
- Redis-based rate limiting
- User-specific limits
- Flexible time windows
- Auto cleanup

ISHLATISH:
    from app.utils.rate_limiter import RateLimiter
    
    limiter = RateLimiter(redis_client, max_requests=3, window=60)
    
    if not await limiter.check_limit(user_id, "order_creation"):
        await message.answer("⏳ Juda ko'p so'rov! Biroz kuting...")
        return
"""
import time
from typing import Optional, Any, cast
from loguru import logger
from app.core.redis_client import redis_client


class RateLimiter:
    """
    Redis-based rate limiter
    
    ALGORITHM:
    - Sliding window counter
    - Key format: ratelimit:{action}:{user_id}
    - Value: timestamp:count
    - TTL: window duration
     
    FEATURES:
    - User-specific limits
    - Action-specific limits  
    - Automatic cleanup via Redis TTL
    - Thread-safe (Redis atomic operations)
    """
    
    def __init__(
        self,
        max_requests: int = 3,
        window_seconds: int = 60,
        prefix: str = "ratelimit"
    ):
        """
        Args:
            max_requests: Maximum soniy oralig'ida
            window_seconds: Vaqt oralig'i (soniyalarda)
            prefix: Redis key prefixi
        """
        self.max_requests = max_requests
        self.window = window_seconds
        self.prefix = prefix
        self.redis = redis_client
    
    def _get_key(self, user_id: int, action: str) -> str:
        """Redis key yaratish"""
        return f"{self.prefix}:{action}:{user_id}"
    
    async def check_limit(
        self,
        user_id: int,
        action: str,
        cost: int = 1
    ) -> bool:
        """
        Rate limit tekshirish
        
        Args:
            user_id: User ID
            action: Action nomi (masalan "order_creation")
            cost: Har bir requestning "qiymati" (default 1)
        
       Returns:
            True - ruxsat etilgan
            False - limit oshgan
        
        ISHLATISH:
            if not await limiter.check_limit(user_id, "order"):
                await message.answer("Juda tez!")
                return
        """
        key = self._get_key(user_id, action)
        current_time = time.time()
        window_start = current_time - self.window
        
        try:
            # Current count olish
            current_count = await self._get_count(key, window_start)
            
            # Limit check
            if current_count + cost > self.max_requests:
                # Qolgan vaqtni hisoblash
                ttl = await self.redis.client.ttl(key)
                logger.warning(
                    f"Rate limit exceeded: user={user_id}, action={action}, "
                    f"count={current_count}/{self.max_requests}, retry_after={ttl}s"
                )
                return False
            
            # Counter increment
            await self._increment(key, current_time, cost)
            
            logger.debug(
                f"Rate limit OK: user={user_id}, action={action}, "
                f"count={current_count + cost}/{self.max_requests}"
            )
            return True
        
        except Exception as e:
            # Redis error - fail open (ruxsat berish)
            logger.error(f"Rate limiter error: {e}. Allowing request.")
            return True
    
    async def _get_count(self, key: str, window_start: float) -> int:
        """
        Current window ichidagi request'lar sonini olish
        """
        client = cast(Any, self.redis.client)
        entries = await client.lrange(key, 0, -1)

        if not entries:
            return 0

        count = 0
        for entry in entries:
            try:
                raw = entry.decode() if hasattr(entry, "decode") else str(entry)
                timestamp, req_cost = raw.split(":")
                if float(timestamp) >= window_start:
                    count += int(req_cost)
            except (ValueError, AttributeError):
                # Ignore malformed entry but continue counting others
                continue

        return count
    
    async def _increment(self, key: str, timestamp: float, cost: int):
        """
        Request counter'ni oshirish
        """
        entry = f"{timestamp}:{cost}"
        client = cast(Any, self.redis.client)
        await client.rpush(key, entry)
        
        # TTL set qilish (faqat birinchi marta)
        ttl = await client.ttl(key)
        if ttl == -1:  # TTL yo'q
            await client.expire(key, self.window)
        
        # Eski entry'larni tozalash (optimization)
        await self._cleanup_old_entries(key, timestamp - self.window)
    
    async def _cleanup_old_entries(self, key: str, cutoff_time: float):
        """
        Eski entry'larni o'chirish
        """
        client = cast(Any, self.redis.client)
        entries = await client.lrange(key, 0, -1)

        for entry in entries:
            try:
                raw = entry.decode() if hasattr(entry, "decode") else str(entry)
                timestamp_str = raw.split(":")[0]
                if float(timestamp_str) < cutoff_time:
                    await client.lrem(key, 1, entry)
            except (ValueError, AttributeError):
                continue
    
    async def reset(self, user_id: int, action: str):
        """
        Limitni reset qilish (admin uchun)
        """
        key = self._get_key(user_id, action)
        client = cast(Any, self.redis.client)
        await client.delete(key)
        logger.info(f"Rate limit reset: user={user_id}, action={action}")
    
    async def get_remaining(self, user_id: int, action: str) -> int:
        """
        Qolgan request'lar sonini olish
        """
        key = self._get_key(user_id, action)
        current_time = time.time()
        window_start = current_time - self.window
        
        current_count = await self._get_count(key, window_start)
        return max(0, self.max_requests - current_count)


# Global instance
order_rate_limiter = RateLimiter(
    max_requests=3,  # 3 ta order
    window_seconds=60,  # 1 daqiqada
    prefix="ratelimit"
)


__all__ = ['RateLimiter', 'order_rate_limiter']
