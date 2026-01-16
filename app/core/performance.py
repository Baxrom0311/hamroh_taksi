"""
app/core/performance.py

PERFORMANCE OPTIMIZATION UTILITIES

- Database query optimization
- Redis caching
- Query result caching
"""

from functools import wraps
import json
import hashlib
from typing import Optional, Callable, Any
from loguru import logger

from app.core.redis_client import redis_client


def cache_result(
    key_prefix: str,
    ttl: int = 3600,  # 1 hour default
    key_builder: Optional[Callable] = None
):
    """
    Decorator to cache function results in Redis
    
    Usage:
        @cache_result("pricing_settings", ttl=3600)
        async def get_pricing_settings():
            ...  # Expensive query
    
    Args:
        key_prefix: Redis key prefix
        ttl: Time to live in seconds
        key_builder: Custom key building function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
            else:
                # Default: hash arguments
                args_str = str(args) + str(kwargs)
                args_hash = hashlib.md5(args_str.encode()).hexdigest()[:8]
                cache_key = f"{key_prefix}:{args_hash}"
            
            # Try to get from cache
            cached = await redis_client.get(cache_key)
            
            if cached is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                try:
                    return json.loads(cached)
                except:
                    # If not JSON, return as is
                    return cached
            
            # Cache MISS - execute function
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Store in cache
            try:
                if isinstance(result, (dict, list)):
                    await redis_client.set(cache_key, json.dumps(result), ex=ttl)
                else:
                    await redis_client.set(cache_key, str(result), ex=ttl)
            except Exception as e:
                logger.error(f"Failed to cache result: {e}")
            
            return result
        
        return wrapper
    return decorator


async def invalidate_cache(key_pattern: str):
    """
    Cache'ni tozalash
    
    Usage:
        await invalidate_cache("pricing_settings:*")
    """
    try:
        keys = []
        async for key in redis_client.client.scan_iter(match=key_pattern):
            keys.append(key)
        
        if keys:
            await redis_client.client.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache keys matching '{key_pattern}'")
    
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")


# ============================================
# DATABASE OPTIMIZATION
# ============================================

class QueryOptimizer:
    """
    Database query optimization helpers
    """
    
    @staticmethod
    def build_bulk_insert_values(records: list[dict], columns: list[str]) -> tuple:
        """
        Bulk insert uchun values yaratish
        
        Example:
            records = [
                {'name': 'A', 'age': 20},
                {'name': 'B', 'age': 25}
            ]
            columns = ['name', 'age']
            
            → "VALUES (:name_0, :age_0), (:name_1, :age_1)"
        """
        values_list = []
        params = {}
        
        for idx, record in enumerate(records):
            placeholders = []
            for col in columns:
                param_name = f"{col}_{idx}"
                placeholders.append(f":{param_name}")
                params[param_name] = record.get(col)
            
            values_list.append(f"({', '.join(placeholders)})")
        
        values_sql = ", ".join(values_list)
        
        return values_sql, params
    
    @staticmethod
    def paginate(query, page: int = 1, per_page: int = 20):
        """
        Pagination helper
        
        Usage:
            query = select(Order).where(...)
            paginated = QueryOptimizer.paginate(query, page=2, per_page=10)
        """
        offset = (page - 1) * per_page
        return query.limit(per_page).offset(offset)


 # ============================================
# MONITORING HELPERS
# ============================================

async def track_slow_queries(threshold_seconds: float = 1.0):
    """
    Sekin querylarni aniqlash
    
    TODO: Middleware sifatida implement qilish
    """
    pass


__all__ = [
    'cache_result',
    'invalidate_cache',
    'QueryOptimizer'
]
