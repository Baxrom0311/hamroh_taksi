"""
app/services/geo_service.py

GEO SERVICE - Geo-lokatsiya xizmatlari

BU SERVICE NIMA QILADI:
1. GPS proximity check (haydovchi yaqinmi?)
2. Nearby drivers topish (PostGIS)
3. Route distance calculation
4. Location validation
5. Geo-based matching

ISHLATISH:
    from app.services.geo_service import geo_service
    
    # Proximity check
    result = await geo_service.check_driver_proximity(driver_id, order_id)
    
    # Nearby drivers
    drivers = await geo_service.find_nearby_drivers(
        lat=41.311512,
        lon=69.249512,
        route_id=1,
        max_distance_km=50
    )
"""

from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from loguru import logger

from app.utils.geo import (
    calculate_distance,
    validate_coordinates,
    is_in_uzbekistan,
    format_coordinates,
    calculate_bearing,
    bearing_to_direction
)
from app.core.database import get_session
from app.models.driver import Driver, get_driver_by_id
from app.models.order import Order, get_order_by_id
from app.models.system_settings import get_pricing_settings
from app.core.exceptions import (
    DriverNotFoundException,
    OrderNotFoundException,
    InvalidLocationException,
    LocationTooFarException
)
from sqlalchemy import select, text, func
from config.settings import settings


class GeoService:
    """
    Geo-lokatsiya xizmatlari
    """
    
    # Constants
    PICKUP_RADIUS_METERS = 100  # Pickup radius (100m)
    MAX_SEARCH_DISTANCE_KM = 50  # Maksimal qidiruv radiusi
    UZBEKISTAN_BOUNDS = {
        'lat_min': 37.0,
        'lat_max': 46.0,
        'lon_min': 56.0,
        'lon_max': 73.0
    }
    
    # ========================================
    # GPS PROXIMITY CHECK
    # ========================================
    
    async def check_driver_proximity(
        self, 
        driver_id: int, 
        order_id: int
    ) -> Dict:
        """
        Haydovchi yo'lovchiga yaqinmi? (GPS tekshirish)
        
        Args:
            driver_id: Driver ID
            order_id: Order ID
        
        Returns:
            {
                'is_near': bool,
                'distance': float (meters),
                'allowed': bool,
                'pickup_location': dict,
                'driver_location': dict
            }
        
        Raises:
            DriverNotFoundException
            OrderNotFoundException
        
        MISOL:
            result = await geo_service.check_driver_proximity(1, 123)
            
            if result['is_near']:
                print("Driver yetib keldi!")
            else:
                print(f"Yana {result['distance']:.0f}m qoldi")
        """
        
        try:
            async with get_session() as session:
                # Driver olish
                driver = await get_driver_by_id(session, driver_id)
                
                if not driver:
                    raise DriverNotFoundException(driver_id=driver_id)
                
                # Order olish
                order = await get_order_by_id(session, order_id)
                
                if not order:
                    raise OrderNotFoundException(order_id=order_id)
                
                # Driver lokatsiyasi mavjudmi?
                if not driver.last_location_lat or not driver.last_location_lon:
                    logger.warning(f"Driver {driver_id} location missing")
                    return {
                        'is_near': False,
                        'distance': 9999,
                        'allowed': False,
                        'error': 'Driver lokatsiyasi mavjud emas',
                        'pickup_location': {
                            'lat': float(order.pickup_lat),
                            'lon': float(order.pickup_lon),
                            'address': order.pickup_location
                        },
                        'driver_location': None
                    }
                
                # Masofa hisoblash (Haversine)
                distance_km = calculate_distance(
                    float(driver.last_location_lat),
                    float(driver.last_location_lon),
                    float(order.pickup_lat),
                    float(order.pickup_lon)
                )
                
                distance_meters = distance_km * 1000
                
                # Yaqinlikni aniqlash
                is_near = distance_meters <= self.PICKUP_RADIUS_METERS
                
                # Yo'nalish (agar uzoq bo'lsa)
                bearing = None
                direction = None
                if not is_near:
                    bearing = calculate_bearing(
                        float(driver.last_location_lat),
                        float(driver.last_location_lon),
                        float(order.pickup_lat),
                        float(order.pickup_lon)
                    )
                    direction = bearing_to_direction(bearing)
                
                logger.info(
                    f"GPS check: driver={driver_id}, order={order_id}, "
                    f"distance={distance_meters:.0f}m, near={is_near}"
                )
                
                return {
                    'is_near': is_near,
                    'distance': distance_meters,
                    'allowed': is_near,
                    'pickup_location': {
                        'lat': float(order.pickup_lat),
                        'lon': float(order.pickup_lon),
                        'address': order.pickup_location,
                        'formatted': format_coordinates(
                            float(order.pickup_lat),
                            float(order.pickup_lon)
                        )
                    },
                    'driver_location': {
                        'lat': float(driver.last_location_lat),
                        'lon': float(driver.last_location_lon),
                        'formatted': format_coordinates(
                            float(driver.last_location_lat),
                            float(driver.last_location_lon)
                        )
                    },
                    'bearing': bearing,
                    'direction': direction
                }
        
        except (DriverNotFoundException, OrderNotFoundException):
            raise
        
        except Exception as e:
            logger.error(f"GPS proximity check error: {e}")
            return {
                'is_near': False,
                'distance': 9999,
                'allowed': False,
                'error': str(e)
            }
    
    # ========================================
    # NEARBY DRIVERS (PostGIS)
    # ========================================
    
    async def find_nearby_drivers(
        self,
        lat: float,
        lon: float,
        route_id: int,
        max_distance_km: float = 50,
        min_seats: int = 1,
        limit: int = 20
    ) -> List[Dict]:
        """
        Yaqin haydovchilarni topish (PostGIS orqali - juda tez!)
        
        Args:
            lat: Yo'lovchi latitude
            lon: Yo'lovchi longitude
            route_id: Marshrut ID
            max_distance_km: Maksimal masofa (km)
            min_seats: Minimal bo'sh joylar
            limit: Maksimal natijalar soni
        
        Returns:
            List of drivers with distance
        
        FEATURES:
        - PostGIS spatial index (< 50ms)
        - Distance calculation
        - Filtering (active, balance, seats)
        - Sorting by distance + rating
        
        MISOL:
            drivers = await geo_service.find_nearby_drivers(
                lat=41.311512,
                lon=69.249512,
                route_id=1,
                max_distance_km=30
            )
            
            for driver in drivers:
                print(f"{driver['full_name']}: {driver['distance_km']:.1f} km")
        """
        
        try:
            # Koordinata validatsiya
            if not validate_coordinates(lat, lon):
                raise InvalidLocationException(
                    message="Noto'g'ri koordinatalar",
                    latitude=lat,
                    longitude=lon
                )
            
            async with get_session() as session:
                pricing = await get_pricing_settings(session)
                min_balance_required = pricing['commission_amount']

                # PostGIS query
                query = text("""
                    SELECT 
                        driver_id,
                        user_id,
                        full_name,
                        car_model,
                        car_color,
                        car_number,
                        rating,
                        total_trips,
                        available_seats,
                        balance,
                        last_location_lat,
                        last_location_lon,
                        ST_Distance(
                            location::geography,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                        ) / 1000 as distance_km
                    FROM drivers
                    WHERE 
                        is_active = TRUE
                        AND is_on_trip = FALSE
                        AND is_blocked = FALSE
                        AND current_route_id = :route_id
                        AND available_seats >= :min_seats
                        AND balance >= :min_balance
                        AND location IS NOT NULL
                        AND ST_DWithin(
                            location::geography,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                            :max_distance_meters
                        )
                    ORDER BY 
                        distance_km ASC,
                        rating DESC
                    LIMIT :limit
                """)
                
                result = await session.execute(
                    query,
                    {
                        'lat': lat,
                        'lon': lon,
                        'route_id': route_id,
                        'min_seats': min_seats,
                        'min_balance': min_balance_required,
                        'max_distance_meters': max_distance_km * 1000,
                        'limit': limit
                    }
                )
                
                drivers = []
                
                for row in result:
                    # Yo'nalish hisoblash
                    bearing = calculate_bearing(
                        float(row.last_location_lat),
                        float(row.last_location_lon),
                        lat,
                        lon
                    )
                    
                    drivers.append({
                        'driver_id': row.driver_id,
                        'user_id': row.user_id,
                        'full_name': row.full_name,
                        'car_model': row.car_model,
                        'car_color': row.car_color,
                        'car_number': row.car_number,
                        'rating': float(row.rating),
                        'total_trips': row.total_trips,
                        'available_seats': row.available_seats,
                        'balance': float(row.balance),
                        'distance_km': float(row.distance_km),
                        'bearing': bearing,
                        'direction': bearing_to_direction(bearing),
                        'location': {
                            'lat': float(row.last_location_lat),
                            'lon': float(row.last_location_lon)
                        }
                    })
                
                logger.info(
                    f"Found {len(drivers)} nearby drivers "
                    f"(route={route_id}, radius={max_distance_km}km)"
                )
                
                return drivers
        
        except InvalidLocationException:
            raise
        
        except Exception as e:
            logger.error(f"Find nearby drivers error: {e}")
            return []
    
    # ========================================
    # LOCATION VALIDATION
    # ========================================
    
    async def validate_location(
        self,
        lat: float,
        lon: float,
        check_uzbekistan: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Lokatsiyani validatsiya qilish
        
        Args:
            lat: Latitude
            lon: Longitude
            check_uzbekistan: O'zbekiston hududida ekanligini tekshirish
        
        Returns:
            (is_valid: bool, error_message: str | None)
        
        MISOL:
            is_valid, error = await geo_service.validate_location(41.311, 69.249)
            
            if not is_valid:
                print(f"Xato: {error}")
        """
        
        # 1. Koordinata range tekshirish
        if not validate_coordinates(lat, lon):
            return (False, "Noto'g'ri koordinatalar (lat: -90/+90, lon: -180/+180)")
        
        # 2. O'zbekiston hududida ekanligini tekshirish
        if check_uzbekistan and not is_in_uzbekistan(lat, lon):
            return (False, "Lokatsiya O'zbekiston hududidan tashqarida")
        
        return (True, None)
    
    # ========================================
    # DISTANCE CALCULATION
    # ========================================
    
    async def calculate_route_distance(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float
    ) -> Dict:
        """
        Marshrut masofasini hisoblash
        
        Args:
            from_lat: Boshlanish latitude
            from_lon: Boshlanish longitude
            to_lat: Tugash latitude
            to_lon: Tugash longitude
        
        Returns:
            {
                'distance_km': float,
                'bearing': float,
                'direction': str,
                'estimated_time_minutes': int
            }
        
        MISOL:
            route = await geo_service.calculate_route_distance(
                41.311512, 69.249512,  # Gurlan
                41.377512, 69.361400   # Vazir
            )
            
            print(f"Masofa: {route['distance_km']:.1f} km")
            print(f"Yo'nalish: {route['direction']}")
        """
        
        try:
            # Validatsiya
            is_valid_from, error_from = await self.validate_location(from_lat, from_lon)
            is_valid_to, error_to = await self.validate_location(to_lat, to_lon)
            
            if not is_valid_from:
                raise InvalidLocationException(message=error_from or "Invalid from location")
            
            if not is_valid_to:
                raise InvalidLocationException(message=error_to or "Invalid to location")
            
            # Masofa
            distance_km = calculate_distance(from_lat, from_lon, to_lat, to_lon)
            
            # Yo'nalish
            bearing = calculate_bearing(from_lat, from_lon, to_lat, to_lon)
            direction = bearing_to_direction(bearing)
            
            # Taxminiy vaqt (60 km/h tezlik)
            estimated_time_minutes = int((distance_km / 60) * 60)
            
            return {
                'distance_km': round(distance_km, 2),
                'bearing': round(bearing, 1),
                'direction': direction,
                'estimated_time_minutes': estimated_time_minutes,
                'from_location': {
                    'lat': from_lat,
                    'lon': from_lon,
                    'formatted': format_coordinates(from_lat, from_lon)
                },
                'to_location': {
                    'lat': to_lat,
                    'lon': to_lon,
                    'formatted': format_coordinates(to_lat, to_lon)
                }
            }
        
        except InvalidLocationException:
            raise
        
        except Exception as e:
            logger.error(f"Route distance calculation error: {e}")
            return {
                'distance_km': 0,
                'bearing': 0,
                'direction': 'Unknown',
                'estimated_time_minutes': 0
            }
    
    # ========================================
    # UPDATE DRIVER LOCATION
    # ========================================
    
    async def update_driver_location(
        self,
        driver_id: int,
        latitude: float,
        longitude: float
    ) -> Dict:
        """
        Driver lokatsiyasini yangilash (PostGIS geometry)
        
        Args:
            driver_id: Driver ID
            latitude: Yangi latitude
            longitude: Yangi longitude
        
        Returns:
            {
                'success': bool,
                'message': str
            }
        
        MISOL:
            result = await geo_service.update_driver_location(
                driver_id=1,
                latitude=41.311512,
                longitude=69.249512
            )
        """
        
        try:
            # Validatsiya
            is_valid, error = await self.validate_location(latitude, longitude)
            
            if not is_valid:
                return {
                    'success': False,
                    'message': error or 'Invalid location'
                }
            
            async with get_session() as session:
                # PostGIS POINT geometry yaratish
                query = text("""
                    UPDATE drivers 
                    SET 
                        last_location_lat = :lat,
                        last_location_lon = :lon,
                        location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                        updated_at = NOW()
                    WHERE driver_id = :driver_id
                """)
                
                await session.execute(
                    query,
                    {
                        'driver_id': driver_id,
                        'lat': latitude,
                        'lon': longitude
                    }
                )
                
                await session.commit()
                
                logger.info(
                    f"Driver {driver_id} location updated: "
                    f"{latitude:.6f}, {longitude:.6f}"
                )
                
                return {
                    'success': True,
                    'message': 'Lokatsiya yangilandi',
                    'location': {
                        'lat': latitude,
                        'lon': longitude,
                        'formatted': format_coordinates(latitude, longitude)
                    }
                }
        
        except Exception as e:
            logger.error(f"Update driver location error: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    # ========================================
    # STATISTICS
    # ========================================
    
    async def get_coverage_stats(self, route_id: int) -> Dict:
        """
        Marshrut bo'yicha qamrov statistikasi
        
        Returns:
            {
                'total_drivers': int,
                'active_drivers': int,
                'average_distance_km': float,
                'coverage_areas': list
            }
        """
        
        try:
            async with get_session() as session:
                # Total drivers
                result = await session.execute(
                    select(func.count(Driver.driver_id))
                    .where(Driver.current_route_id == route_id)
                    .where(Driver.is_active == True)
                )
                
                active_drivers = result.scalar() or 0
                
                return {
                    'total_drivers': active_drivers,
                    'active_drivers': active_drivers,
                    'route_id': route_id
                }
        
        except Exception as e:
            logger.error(f"Coverage stats error: {e}")
            return {
                'total_drivers': 0,
                'active_drivers': 0,
                'route_id': route_id
            }


# ============================================
# GLOBAL INSTANCE
# ============================================

geo_service = GeoService()


__all__ = ['geo_service', 'GeoService']