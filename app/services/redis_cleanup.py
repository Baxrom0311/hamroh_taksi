"""
app/services/redis_cleanup.py

REDIS CLEANUP UTILITIES

✅ PRODUCTION FIX: Redis key cleanup helpers for order cancellation
"""

from loguru import logger
from app.core.redis_client import redis_client


async def cleanup_skip_keys_for_order(order_id: int) -> int:
    """
    Remove all driver skip keys for cancelled order
    
    Args:
        order_id: Order ID
    
    Returns:
        Number of keys deleted
    
    ISHLATISH:
        from app.services.redis_cleanup import cleanup_skip_keys_for_order
        
        # When order is cancelled
        deleted_count = await cleanup_skip_keys_for_order(order_id)
        logger.info(f"Cleaned up {deleted_count} skip keys for order {order_id}")
    
    ✅ BENEFIT:
    - Prevents Redis key accumulation
    - Allows rejected drivers to see new orders sooner
    - Keeps Redis memory clean
    
    NOTE:
    - This is nice-to-have since TTL (300s) handles cleanup automatically
    - But immediate cleanup is better for UX (driver can get same route order sooner)
    """
    
    pattern = f"driver_skip:{order_id}:*"
    deleted_count = 0
    
    try:
        async for key in redis_client.client.scan_iter(match=pattern):
            await redis_client.client.delete(key)
            deleted_count += 1
        
        if deleted_count > 0:
            logger.info(
                f"✅ Cleaned up {deleted_count} skip keys for order {order_id}"
            )
        
        return deleted_count
    
    except Exception as e:
        logger.error(f"Failed to cleanup skip keys for order {order_id}: {e}")
        return 0


async def cleanup_rate_limit_keys_for_user(user_id: int) -> int:
    """
    Remove all rate limit keys for a user (admin tool)
    
    Args:
        user_id: User ID
    
    Returns:
        Number of keys deleted
    """
    
    patterns = [
        f"rate:{user_id}:*",
        f"tg_rate:{user_id}",
        f"sms_rate:{user_id}:*"
    ]
    
    deleted_count = 0
    
    try:
        for pattern in patterns:
            async for key in redis_client.client.scan_iter(match=pattern):
                await redis_client.client.delete(key)
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"✅ Cleaned up {deleted_count} rate limit keys for user {user_id}")
        
        return deleted_count
    
    except Exception as e:
        logger.error(f"Failed to cleanup rate limit keys for user {user_id}: {e}")
        return 0


__all__ = ['cleanup_skip_keys_for_order', 'cleanup_rate_limit_keys_for_user']
