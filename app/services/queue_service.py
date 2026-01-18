"""
app/services/queue_service.py

DRIVER QUEUE MANAGER - Priority Queue

BU SERVICE NIMA QILADI:
1. Haydovchilarni navbatga qo'shish (Redis Sorted Set)
2. Priority score hisoblash (rating + waiting time)
3. Eng yaxshi haydovchini topish
4. Geo-lokatsiya filtrlash

ISHLATISH:
    from app.services.queue_service import driver_queue
    
    # Navbatga qo'shish
    await driver_queue.add_driver(driver_id=123, route_id=1)
    
    # Eng yaxshi haydovchini olish
    driver_id = await driver_queue.get_next_driver(
        route_id=1,
        passenger_location={'lat': 41.311, 'lon': 69.249}
    )
"""

from typing import Optional, List, Dict
from datetime import datetime
from loguru import logger

from app.core.redis_client import redis_client
from app.core.database import get_session
from app.models.driver import Driver, get_driver_by_id
from app.models.system_settings import get_pricing_settings
from app.utils.geo import calculate_distance
from config.settings import settings


class DriverQueueManager:
    """
    Driver Priority Queue Manager
    
    PRIORITY FORMULA:
    score = (rating * 10) + (min(waiting_hours, 6) * 5)
    
    Max score: 50 (rating) + 30 (waiting) = 80
    """
    
    # Constants
    MAX_WAITING_HOURS = 6  # Maksimum 6 soat hisoblanadi
    RATING_WEIGHT = 10     # Reyting og'irligi
    WAITING_WEIGHT = 5     # Kutish og'irligi
    
    def __init__(self):
        self.redis = redis_client
    
    # ========================================
    # PRIORITY SCORE
    # ========================================
    
    async def calculate_priority_score(
        self, 
        driver_id: int, 
        route_id: int
    ) -> float:
        """
        Priority score hisoblash
        
        Returns:
            Float score (0-80)
        """
        async with get_session() as session:
            driver = await get_driver_by_id(session, driver_id)
            
            if not driver:
                return 0.0
            
            # 1. Reyting balli (0-50)
            rating_score = float(driver.rating) * self.RATING_WEIGHT
            
            # 2. Kutish vaqti (cap bilan)
            waiting_hours = await self.get_waiting_time_hours(driver_id, route_id)
            capped_waiting = min(waiting_hours, self.MAX_WAITING_HOURS)
            waiting_score = capped_waiting * self.WAITING_WEIGHT
            
            # 3. Jami ball
            total_score = rating_score + waiting_score
            
            return round(total_score, 2)
    
    async def get_waiting_time_hours(
        self, 
        driver_id: int, 
        route_id: int
    ) -> float:
        """
        Haydovchi qancha vaqtdan beri kutayotgani
        
        Returns:
            Soatlar (float)
        """
        join_time_key = f"driver_join_time:{driver_id}:{route_id}"
        join_time_str = await self.redis.get(join_time_key)
        
        if not join_time_str:
            # Yangi haydovchi - hozirgi vaqtni saqlash
            now = datetime.now().isoformat()
            await self.redis.set(join_time_key, now, ex=86400)  # 24 soat
            return 0.0
        
        # Kutish vaqtini hisoblash
        join_datetime = datetime.fromisoformat(join_time_str)
        waiting_delta = datetime.now() - join_datetime
        waiting_hours = waiting_delta.total_seconds() / 3600
        
        return waiting_hours
    
    # ========================================
    # QUEUE OPERATIONS
    # ========================================
    
    async def add_driver(
        self, 
        driver_id: int, 
        route_id: int
    ) -> Dict:
        """
        Haydovchini navbatga qo'shish
        
        Returns:
            {
                'success': bool,
                'priority_score': float,
                'position': int
            }
        """
        try:
            queue_key = f"driver_queue:{route_id}"
            
            # Priority score hisoblash
            priority_score = await self.calculate_priority_score(
                driver_id, 
                route_id
            )
            
            # Redis Sorted Set'ga qo'shish
            # Score yuqori bo'lgan birinchi chiqadi
            await self.redis.client.zadd(
                queue_key,
                {str(driver_id): priority_score}
            )
            
            # Expire (24 soat)
            await self.redis.expire(queue_key, 86400)
            
            # Position olish
            position = await self.get_queue_position(driver_id, route_id)
            
            logger.info(
                f"Driver {driver_id} added to queue: "
                f"route={route_id}, score={priority_score}, position={position}"
            )
            
            return {
                'success': True,
                'priority_score': priority_score,
                'position': position
            }
        
        except Exception as e:
            logger.error(f"Failed to add driver to queue: {e}")
            return {'success': False, 'error': str(e)}
    
    async def remove_driver(
        self, 
        driver_id: int, 
        route_id: int
    ) -> bool:
        """
        Haydovchini navbatdan o'chirish
        """
        try:
            queue_key = f"driver_queue:{route_id}"
            
            # Sorted Set'dan o'chirish
            await self.redis.client.zrem(queue_key, str(driver_id))
            
            # Join time tozalash
            join_time_key = f"driver_join_time:{driver_id}:{route_id}"
            await self.redis.delete(join_time_key)
            
            logger.info(f"Driver {driver_id} removed from queue: route={route_id}")
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to remove driver from queue: {e}")
            return False
    
    async def get_queue_position(
        self, 
        driver_id: int, 
        route_id: int
    ) -> int:
        """
        Haydovchining navbatdagi o'rni
        
        Returns:
            Position (1 = birinchi, -1 = navbatda yo'q)
        """
        try:
            queue_key = f"driver_queue:{route_id}"
            
            # Reverse rank (yuqori score = 1-o'rin)
            rank = await self.redis.client.zrevrank(queue_key, str(driver_id))
            
            if rank is None:
                return -1
            
            return rank + 1  # 0-index'dan 1-index'ga
        
        except Exception as e:
            logger.error(f"Failed to get queue position: {e}")
            return -1
    
    async def get_queue_length(self, route_id: int) -> int:
        """Navbatdagi haydovchilar soni"""
        try:
            queue_key = f"driver_queue:{route_id}"
            return await self.redis.client.zcard(queue_key)
        except:
            return 0
    
    # ========================================
    # SKIP & REJECT TRACKING
    # ========================================
    
    async def skip_driver_for_order(self, driver_id: int, order_id: int, ttl: int = 300):
        """Haydovchini ma'lum buyurtma uchun vaqtincha skip ro'yxatiga qo'shish"""
        skip_key = f"order_skip:{order_id}:{driver_id}"
        await self.redis.set(skip_key, "1", ex=ttl)
    
    async def is_driver_skipped(self, driver_id: int, order_id: int) -> bool:
        """Haydovchi bu buyurtma uchun skip qilinganmi?"""
        skip_key = f"order_skip:{order_id}:{driver_id}"
        return await self.redis.exists(skip_key)
    
    async def track_driver_reject(self, driver_id: int):
        """Haydovchining rad etishlarini hisoblash"""
        day_str = datetime.now().strftime("%Y-%m-%d")
        reject_key = f"driver_rejects:{day_str}:{driver_id}"
        await self.redis.incr(reject_key)
        await self.redis.expire(reject_key, 86400) # 24 soat
        
    async def get_driver_reject_count(self, driver_id: int) -> int:
        """Haydovchining bugungi rad etishlari soni"""
        day_str = datetime.now().strftime("%Y-%m-%d")
        reject_key = f"driver_rejects:{day_str}:{driver_id}"
        val = await self.redis.get(reject_key)
        return int(val) if val else 0
    
    # ========================================
    # MATCHING
    # ========================================
    
    async def get_next_driver(
        self,
        route_id: int,
        passenger_location: Dict[str, float],
        passenger_count: int = 1,
        max_distance_km: float = 50,
        order_id: Optional[int] = None,
        enforce_distance: bool = True
    ) -> Optional[int]:
        """
        Keyingi eng yaxshi haydovchini topish
        
        Args:
            route_id: Marshrut ID
            passenger_location: {'lat': float, 'lon': float}
            passenger_count: Yo'lovchilar soni
            max_distance_km: Maksimal masofa
        
        Returns:
            driver_id yoki None
        
        ALGORITM:
        1. Top 20 haydovchini olish (priority bo'yicha)
        2. Har birini tekshirish:
           - Aktiv va bo'sh
           - Balans yetarli
           - Masofa yaqin (agar enforce_distance=True)
           - Bo'sh joylar yetarli
        3. Birinchi mos kelganini qaytarish
        """
        try:
            queue_key = f"driver_queue:{route_id}"
            
            # Top 20 haydovchilarni olish (yuqori priority)
            top_drivers = await self.redis.client.zrevrange(
                queue_key,
                0,
                19,  # Top 20
                withscores=True
            )
            
            if not top_drivers:
                logger.warning(f"No drivers in queue for route {route_id}")
                return None
            
            logger.info(f"Checking {len(top_drivers)} drivers for matching...")
            
            # Har bir haydovchini tekshirish
            async with get_session() as session:
                for driver_id_str, score in top_drivers:
                    driver_id = int(driver_id_str)
                    
                    # Driver ma'lumotlarini olish
                    driver = await get_driver_by_id(session, driver_id)
                    
                    if not driver:
                        continue
                    
                    # 0. Skip tekshiruvi (agar order_id berilgan bo'lsa)
                    if order_id and await self.is_driver_skipped(driver_id, order_id):
                        logger.debug(f"Driver {driver_id}: skipped for order {order_id}")
                        continue
                    
                    # 1. Aktiv va bo'sh
                    if not driver.is_active or driver.is_on_trip:
                        logger.debug(f"Driver {driver_id}: not active or on trip")
                        continue
                    
                    # 2. Bloklangan emas
                    if driver.is_blocked:
                        logger.debug(f"Driver {driver_id}: blocked")
                        continue
                    
                    # 3. Balans yetarli (dynamic)
                    pricing = await get_pricing_settings(session)
                    commission = pricing['commission_amount']
                    if driver.balance < commission:
                        logger.debug(f"Driver {driver_id}: insufficient balance")
                        continue
                    
                    # 4. Bo'sh joylar yetarli
                    if driver.available_seats < passenger_count:
                        logger.debug(f"Driver {driver_id}: not enough seats")
                        continue
                    
                    # 5. Lokatsiya mavjud
                    if not driver.last_location_lat or not driver.last_location_lon:
                        logger.debug(f"Driver {driver_id}: location missing")
                        continue
                    
                    # 6. Geo-masofa tekshiruvi (ixtiyoriy)
                    distance_km = None
                    if enforce_distance:
                        distance_km = calculate_distance(
                            float(driver.last_location_lat),
                            float(driver.last_location_lon),
                            passenger_location['lat'],
                            passenger_location['lon']
                        )
                        
                        if distance_km > max_distance_km:
                            logger.debug(
                                f"Driver {driver_id}: too far "
                                f"({distance_km:.1f} km > {max_distance_km} km)"
                            )
                            continue
                    
                    # ✅ TOPILDI!
                    logger.success(
                        f"✅ Driver {driver_id} matched! "
                        f"score={score:.2f}, "
                        f"distance={(distance_km if distance_km is not None else 'skip')}km, "
                        f"seats={driver.available_seats}"
                    )
                    
                    # MUHIM: Navbatdan O'CHIRMAYMIZ!
                    # Agar haydovchida hali bo'sh o'rinlar bo'lsa,
                    # keyingi buyurtmalar ham unga berilishi mumkin.
                    # Faqat o'rinlar to'lganda navbatdan o'chiriladi.
                    
                    return driver_id
            
            # Hech kim topilmadi
            logger.warning(
                f"No suitable driver found for route {route_id} "
                f"(checked {len(top_drivers)} drivers)"
            )
            return None
        
        except Exception as e:
            logger.error(f"Error in get_next_driver: {e}")
            return None
    
    # ========================================
    # QUEUE STATISTICS
    # ========================================
    
    async def get_queue_stats(self, route_id: int) -> Dict:
        """
        Navbat statistikasi
        
        Returns:
            {
                'total_drivers': int,
                'avg_score': float,
                'top_drivers': list
            }
        """
        try:
            queue_key = f"driver_queue:{route_id}"
            
            # Total
            total = await self.redis.client.zcard(queue_key)
            
            if total == 0:
                return {
                    'total_drivers': 0,
                    'avg_score': 0,
                    'top_drivers': []
                }
            
            # Top 5
            top_5 = await self.redis.client.zrevrange(
                queue_key,
                0,
                4,
                withscores=True
            )
            
            top_drivers = [
                {'driver_id': int(did), 'score': float(score)}
                for did, score in top_5
            ]
            
            # Average score
            all_scores = await self.redis.client.zrange(
                queue_key,
                0,
                -1,
                withscores=True
            )
            
            avg_score = sum(s for _, s in all_scores) / len(all_scores) if all_scores else 0
            
            return {
                'total_drivers': total,
                'avg_score': round(avg_score, 2),
                'top_drivers': top_drivers
            }
        
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {
                'total_drivers': 0,
                'avg_score': 0,
                'top_drivers': []
            }


# ============================================
# GLOBAL INSTANCE
# ============================================

driver_queue = DriverQueueManager()


__all__ = ['driver_queue', 'DriverQueueManager']
