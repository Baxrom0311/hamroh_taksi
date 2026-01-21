
## 📁 3. `app/utils/metrics.py` - MONITORING VA METRICS
"""
app/utils/metrics.py

METRICS - Performance monitoring

BU FAYL NIMA QILADI:
- Function execution time tracking
- Query performance monitoring
- Memory usage tracking
- API call metrics

ISHLATISH:
    from app.utils.metrics import track_time, log_slow_query
    
    @track_time("my_function")
    async def my_function():
        # code...
        pass
"""
 
import time
import functools
from typing import Callable, Any
from loguru import logger
from typing import Optional


# ============================================
# TIME TRACKING DECORATOR
# ============================================

def track_time(name: Optional[str] = None, log_slow: float = 1.0):
    """
    Function execution time'ni track qilish
    
    Args:
        name: Function nomi (log uchun)
        log_slow: Qaysi vaqtdan keyin slow deb hisoblanadi (soniya)
    
    ISHLATISH:
        @track_time("process_order")
        async def process_order(order_id):
            # code...
            pass
        
        # Log:
        # ✅ process_order completed in 0.15s
        # ⚠️ process_order slow: 2.5s (threshold: 1.0s)
    """
    
    def decorator(func: Callable) -> Callable:
        func_name = name or func.__name__
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                return result
            
            finally:
                elapsed = time.time() - start_time
                
                if elapsed > log_slow:
                    logger.warning(
                        f"⚠️ {func_name} slow: {elapsed:.2f}s "
                        f"(threshold: {log_slow}s)"
                    )
                else:
                    logger.debug(f"✅ {func_name} completed in {elapsed:.2f}s")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                return result
            
            finally:
                elapsed = time.time() - start_time
                
                if elapsed > log_slow:
                    logger.warning(
                        f"⚠️ {func_name} slow: {elapsed:.2f}s "
                        f"(threshold: {log_slow}s)"
                    )
                else:
                    logger.debug(f"✅ {func_name} completed in {elapsed:.2f}s")
        
        # Async yoki sync?
        import inspect
        import asyncio
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# ============================================
# QUERY METRICS
# ============================================

def log_slow_query(query: str, duration: float, threshold: float = 0.5):
    """
    Sekin query'larni log qilish
    
    Args:
        query: SQL query
        duration: Execution time (soniya)
        threshold: Sekin deb hisoblanadigan vaqt
    
    ISHLATISH:
        start = time.time()
        result = await session.execute(query)
        duration = time.time() - start
        
        log_slow_query(str(query), duration)
    """
    
    if duration > threshold:
        # Query'ni qisqartirish
        query_short = query[:200] + "..." if len(query) > 200 else query
        
        logger.warning(
            f"🐢 Slow query ({duration:.2f}s): {query_short}"
        )


# ============================================
# MEMORY TRACKING
# ============================================

def get_memory_usage() -> dict:
    """
    Hozirgi memory usage
    
    Returns:
        {
            'rss': int,  # Resident Set Size (bytes)
            'vms': int,  # Virtual Memory Size (bytes)
            'percent': float  # Memory %
        }
    
    ISHLATISH:
        memory = get_memory_usage()
        print(f"Memory: {memory['rss'] / 1024 / 1024:.1f} MB")
    """
    
    try:
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        return {
            'rss': memory_info.rss,  # Resident Set Size
            'vms': memory_info.vms,  # Virtual Memory Size
            'percent': process.memory_percent()
        }
    
    except ImportError:
        logger.warning("psutil not installed, memory tracking disabled")
        return {'rss': 0, 'vms': 0, 'percent': 0}
    except Exception as e:
        logger.warning(f"Memory tracking failed: {e}")
        return {'rss': 0, 'vms': 0, 'percent': 0}


def log_memory_usage():
    """Memory usage'ni log qilish"""
    
    memory = get_memory_usage()
    
    rss_mb = memory['rss'] / 1024 / 1024
    vms_mb = memory['vms'] / 1024 / 1024
    
    logger.info(
        f"📊 Memory: RSS={rss_mb:.1f}MB, "
        f"VMS={vms_mb:.1f}MB, "
        f"Percent={memory['percent']:.1f}%"
    )


# ============================================
# API CALL METRICS
# ============================================

class APIMetrics:
    """
    API call metrics tracker
    
    ISHLATISH:
        metrics = APIMetrics()
        
        with metrics.track("telegram_api"):
            await bot.send_message(...)
        
        print(metrics.get_stats())
    """
    
    def __init__(self):
        self.calls = {}
    
    def track(self, name: str):
        """Context manager - API call tracking"""
        
        class Tracker:
            def __init__(self, metrics, name):
                self.metrics = metrics
                self.name = name
                self.start_time = None
            
            def __enter__(self):
                self.start_time = time.time()
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - (self.start_time or 0)
                
                if self.name not in self.metrics.calls:
                    self.metrics.calls[self.name] = {
                        'count': 0,
                        'total_time': 0,
                        'min_time': float('inf'),
                        'max_time': 0
                    }
                
                stats = self.metrics.calls[self.name]
                stats['count'] += 1
                stats['total_time'] += duration
                stats['min_time'] = min(stats['min_time'], duration)
                stats['max_time'] = max(stats['max_time'], duration)
        
        return Tracker(self, name)
    
    def get_stats(self) -> dict:
        """Barcha metrics'larni olish"""
        
        stats = {}
        
        for name, data in self.calls.items():
            avg_time = data['total_time'] / data['count'] if data['count'] > 0 else 0
            
            stats[name] = {
                'total_calls': data['count'],
                'avg_time': round(avg_time, 3),
                'min_time': round(data['min_time'], 3),
                'max_time': round(data['max_time'], 3),
                'total_time': round(data['total_time'], 3)
            }
        
        return stats
    
    def reset(self):
        """Metrics'larni reset qilish"""
        self.calls = {}


# ============================================
# GLOBAL METRICS INSTANCE
# ============================================

api_metrics = APIMetrics()


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.utils.metrics
    """
    
    import asyncio
    
    print("\n🧪 Testing Metrics...\n")
    
    # Test 1: Time tracking
    print("📝 Test 1: Time tracking")
    
    @track_time("test_function")
    async def test_function():
        await asyncio.sleep(0.1)
    
    asyncio.run(test_function())
    
    print()
    
    # Test 2: Memory
    print("📝 Test 2: Memory usage")
    log_memory_usage()
    
    print()
    
    # Test 3: API metrics
    print("📝 Test 3: API metrics")
    
    with api_metrics.track("test_api"):
        time.sleep(0.05)
    
    with api_metrics.track("test_api"):
        time.sleep(0.1)
    
    stats = api_metrics.get_stats()
    print(f"   Stats: {stats}")
    
    print("\n✅ All metric tests passed!\n")


__all__ = [
    'track_time',
    'log_slow_query',
    'get_memory_usage',
    'log_memory_usage',
    'APIMetrics',
    'api_metrics'
]
