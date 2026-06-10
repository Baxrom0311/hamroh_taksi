"""
app/admin/routes/settings.py

SYSTEM SETTINGS MANAGEMENT

ENDPOINTS:
- GET /settings - Barcha sozlamalar
- PUT /settings/{key} - Sozlamani o'zgartirish
- GET /settings/routes - Marshrutlar
- POST /settings/routes - Yangi marshrut
- DELETE /settings/routes/{id} - Marshrutni o'chirish
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from loguru import logger

from app.admin.auth import get_current_user
from app.core.database import get_session
from app.core.redis_client import redis_client
from app.models.route import Route, create_route, get_all_active_routes, get_all_routes
from sqlalchemy import select, update, delete


router = APIRouter(prefix="/settings", tags=["settings"])


# ============================================
# SCHEMAS
# ============================================

class SystemSettingsResponse(BaseModel):
    """Tizim sozlamalari"""
    commission_amount: int
    max_pickup_distance_km: int
    auto_confirm_delay_seconds: int
    sms_rate_limit_per_day: int
    max_driver_rejects_per_day: int


class UpdateSettingRequest(BaseModel):
    """Sozlamani o'zgartirish"""
    value: str


class CreateRouteRequest(BaseModel):
    """Yangi marshrut"""
    from_location: str
    to_location: str
    from_location_lat: Optional[float] = None
    from_location_lon: Optional[float] = None
    to_location_lat: Optional[float] = None
    to_location_lon: Optional[float] = None
    distance_km: Optional[float] = None
    fare_amount: Optional[float] = None


class UpdateRouteRequest(BaseModel):
    """Marshrutni yangilash (faqat kerakli maydonlar)"""
    distance_km: Optional[float] = None
    fare_amount: Optional[float] = None


# ============================================
# SYSTEM SETTINGS
# ============================================

@router.get("/")
async def get_system_settings(
    current_user: dict = Depends(get_current_user)
):
    """
    Barcha tizim sozlamalari (Database'dan)
    
    DIQQAT: Database'dan o'qiladi, .env emas
    """
    try:
        from app.models.system_settings import get_all_settings
        
        async with get_session() as session:
            settings_dict = await get_all_settings(session)
            
            # Default qiymatlar (agar database'da yo'q bo'lsa)
            from config.settings import settings as config_settings
            
            return {
                'success': True,
                'settings': {
                    # Tarif va Komissiya
                    'commission_amount': settings_dict.get('commission_amount', config_settings.COMMISSION_AMOUNT),
                    'bot_is_free': settings_dict.get('bot_is_free', 'false'),
                    
                    # Ban va Cheklovlar
                    'ban_percentage_threshold': settings_dict.get('ban_percentage_threshold', '50'),
                    'ban_count_threshold': settings_dict.get('ban_count_threshold', '5'),
                    'max_driver_change_per_hour': settings_dict.get('max_driver_change_per_hour', '3'),
                    'max_pickup_distance_km': settings_dict.get('max_pickup_distance_km', str(config_settings.MAX_PICKUP_DISTANCE_KM)),
                    'auto_confirm_delay_seconds': settings_dict.get('auto_confirm_delay_seconds', str(config_settings.AUTO_CONFIRM_DELAY_SECONDS)),
                    
                    # Rate Limiting
                    'sms_rate_limit_per_day': settings_dict.get('sms_rate_limit_per_day', str(config_settings.SMS_RATE_LIMIT_PER_DAY)),
                    'sms_rate_limit_per_hour': settings_dict.get('sms_rate_limit_per_hour', str(config_settings.SMS_RATE_LIMIT_PER_HOUR)),
                    'max_driver_rejects_per_day': settings_dict.get('max_driver_rejects_per_day', str(config_settings.MAX_DRIVER_REJECTS_PER_DAY)),
                    'driver_inactivity_threshold': settings_dict.get('driver_inactivity_threshold', str(config_settings.DRIVER_INACTIVITY_THRESHOLD)),
                    
                    # Support
                    'support_phone': settings_dict.get('support_phone', config_settings.SUPPORT_PHONE),
                    'support_username': settings_dict.get('support_username', config_settings.SUPPORT_USERNAME),
                    'working_hours': settings_dict.get('working_hours', config_settings.WORKING_HOURS),
                    
                    # Celery Timing
                    'auto_complete_trip_seconds': settings_dict.get('auto_complete_trip_seconds', str(config_settings.AUTO_COMPLETE_TRIP_SECONDS)),
                    'auto_reject_order_seconds': settings_dict.get('auto_reject_order_seconds', str(config_settings.AUTO_REJECT_ORDER_SECONDS)),
                    'auto_confirm_trip_seconds': settings_dict.get('auto_confirm_trip_seconds', str(config_settings.AUTO_CONFIRM_TRIP_SECONDS)),
                    'driver_matching_timeout_seconds': settings_dict.get('driver_matching_timeout_seconds', str(config_settings.DRIVER_MATCHING_TIMEOUT_SECONDS)),
                    'driver_matching_max_retries': settings_dict.get('driver_matching_max_retries', str(config_settings.DRIVER_MATCHING_MAX_RETRIES)),
                    'driver_matching_retry_delay_seconds': settings_dict.get('driver_matching_retry_delay_seconds', str(config_settings.DRIVER_MATCHING_RETRY_DELAY_SECONDS)),
                    'auto_start_trip_delay_seconds': settings_dict.get('auto_start_trip_delay_seconds', str(config_settings.AUTO_START_TRIP_DELAY_SECONDS)),
                    'task_retry_delay_seconds': settings_dict.get('task_retry_delay_seconds', str(config_settings.TASK_RETRY_DELAY_SECONDS)),
                    
                    # Lock Settings
                    'order_lock_timeout_seconds': settings_dict.get('order_lock_timeout_seconds', str(config_settings.ORDER_LOCK_TIMEOUT_SECONDS)),
                    'generic_lock_timeout_seconds': settings_dict.get('generic_lock_timeout_seconds', str(config_settings.GENERIC_LOCK_TIMEOUT_SECONDS)),
                    
                    # State Management
                    'state_ttl_seconds': settings_dict.get('state_ttl_seconds', str(config_settings.STATE_TTL_SECONDS)),
                    
                    # Environment info
                    'environment': config_settings.ENVIRONMENT,
                    'is_production': config_settings.is_production
                }
            }
    
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{setting_key}")
async def update_system_setting(
    setting_key: str,
    request: UpdateSettingRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Sozlamani o'zgartirish (Database'da)
    
    DIQQAT: Faqat Glavni Admin o'zgartira oladi
    
    FLOW:
    1. Database'da yangilash
    2. Redis cache'ni tozalash
    """
    # Faqat Glavni Admin
    if current_user.get('role') != 'glavni_admin':
        raise HTTPException(
            status_code=403,
            detail="Bu funksiya faqat Glavni Admin uchun"
        )
    
    try:
        from app.models.system_settings import update_setting
        from app.core.database import transaction
        
        # ✅ Faqat transaction ishlatamiz (get_session kerak emas)
        async with transaction() as session:
            await update_setting(session, setting_key, request.value)

            # Redis cache'ni tozalash
            cache_key = f"system_settings:{setting_key}"
            await redis_client.delete(cache_key)

            logger.info(
                f"Setting updated: {setting_key} = {request.value} "
                f"by {current_user['username']}"
            )

            return {
                'success': True,
                'message': 'Sozlama yangilandi',
                'key': setting_key,
                'value': request.value
            }
    
    except Exception as e:
        logger.error(f"Failed to update setting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# ROUTES (MARSHRUTLAR)
# ============================================

@router.get("/routes")
async def get_routes_list(
    current_user: dict = Depends(get_current_user)
):
    """
    Barcha marshrutlar (aktiv va nofaol)
    """
    try:
        async with get_session() as session:
            routes = await get_all_routes(session)
            
            routes_list = [
                {
                    'route_id': route.route_id,
                    'from_location': route.from_location,
                    'to_location': route.to_location,
                    'route_name': route.route_name,
                    'from_location_lat': float(route.from_location_lat) if route.from_location_lat else None,
                    'from_location_lon': float(route.from_location_lon) if route.from_location_lon else None,
                    'to_location_lat': float(route.to_location_lat) if route.to_location_lat else None,
                    'to_location_lon': float(route.to_location_lon) if route.to_location_lon else None,
                    'distance_km': float(route.distance_km) if route.distance_km else None,
                    'fare_amount': float(route.fare_amount) if route.fare_amount is not None else None,
                    'is_active': route.is_active,
                    'created_at': route.created_at.isoformat()
                }
                for route in routes
            ]
            
            return {
                'success': True,
                'routes': routes_list,
                'total': len(routes_list)
            }
    
    except Exception as e:
        logger.error(f"Failed to get routes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes")
async def create_new_route(
    request: CreateRouteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Yangi marshrut yaratish
    """
    try:
        async with get_session() as session:
            # Mavjudligini tekshirish
            existing_query = select(Route).where(
                Route.from_location == request.from_location
            ).where(
                Route.to_location == request.to_location
            )
            
            existing_result = await session.execute(existing_query)
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Bu marshrut allaqachon mavjud"
                )
            
            # Yangi marshrut
            route = await create_route(
                session,
                from_location=request.from_location,
                to_location=request.to_location,
                from_location_lat=request.from_location_lat,
                from_location_lon=request.from_location_lon,
                to_location_lat=request.to_location_lat,
                to_location_lon=request.to_location_lon,
                distance_km=request.distance_km,
                fare_amount=request.fare_amount
            )
            
            await session.commit()
            
            logger.success(
                f"Route created: {route.route_name} "
                f"by {current_user['username']}"
            )
            
            return {
                'success': True,
                'message': 'Marshrut yaratildi',
                'route': {
                    'route_id': route.route_id,
                    'route_name': route.route_name
                }
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to create route: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/routes/{route_id}")
async def update_route(
    route_id: int,
    request: UpdateRouteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Marshrut ma'lumotlarini yangilash (masofa, yo'l haqi)
    """
    try:
        async with get_session() as session:
            from app.models.route import get_route_by_id
            route = await get_route_by_id(session, route_id)
            if not route:
                raise HTTPException(status_code=404, detail="Marshrut topilmadi")

            values = {}
            if request.distance_km is not None:
                values['distance_km'] = request.distance_km
            if request.fare_amount is not None:
                values['fare_amount'] = request.fare_amount

            if not values:
                return {'success': False, 'message': 'Yangilash uchun maʼlumot berilmagan'}

            await session.execute(
                update(Route)
                .where(Route.route_id == route_id)
                .values(**values)
            )
            await session.commit()

            logger.info(
                f"Route {route_id} updated by {current_user['username']}"
            )
            return {'success': True, 'message': 'Marshrut yangilandi'}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update route: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/routes/{route_id}/toggle")
async def toggle_route_status(
    route_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Marshrut holatini o'zgartirish (enable/disable)
    """
    try:
        async with get_session() as session:
            # Route'ni olish
            from app.models.route import get_route_by_id
            route = await get_route_by_id(session, route_id)
            
            if not route:
                raise HTTPException(
                    status_code=404,
                    detail="Marshrut topilmadi"
                )
            
            # Holatni o'zgartirish
            new_status = not route.is_active
            await session.execute(
                update(Route)
                .where(Route.route_id == route_id)
                .values(is_active=new_status)
            )
            
            await session.commit()
            
            logger.info(
                f"Route {route_id} {'activated' if new_status else 'deactivated'} "
                f"by {current_user['username']}"
            )
            
            return {
                'success': True,
                'message': f"Marshrut {'faollashtirildi' if new_status else 'nofaollashtirildi'}",
                'is_active': new_status
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle route status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/routes/{route_id}")
async def delete_route(
    route_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Marshrutni o'chirish (is_active = false)
    """
    try:
        async with get_session() as session:
            from app.models.order import Order, OrderStatus
            from sqlalchemy import func as sqlfunc

            # Aktiv buyurtmalar borligini tekshirish (CASCADE xavfini oldini olish)
            active_count_result = await session.execute(
                select(sqlfunc.count(Order.order_id))
                .where(Order.route_id == route_id)
                .where(Order.status.in_([
                    OrderStatus.PENDING,
                    OrderStatus.ACCEPTED,
                    OrderStatus.IN_PROGRESS
                ]))
            )
            active_count = active_count_result.scalar() or 0

            if active_count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Bu marshrutda {active_count} ta faol buyurtma bor. "
                           f"Avval buyurtmalarni yakunlang yoki bekor qiling."
                )

            # Hard Delete (Databazadan butunlay o'chirish)
            await session.execute(
                delete(Route)
                .where(Route.route_id == route_id)
            )

            await session.commit()

            logger.info(
                f"Route {route_id} PERMANENTLY deleted by {current_user['username']}"
            )

            return {
                'success': True,
                'message': 'Marshrut butunlay o\'chirildi'
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete route: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SYSTEM INFO
# ============================================

@router.get("/system-info")
async def get_system_info(
    current_user: dict = Depends(get_current_user)
):
    """
    Tizim ma'lumotlari
    """
    try:
        import platform
        import psutil
        from datetime import datetime
        
        # System info
        info = {
            'platform': platform.system(),
            'platform_release': platform.release(),
            'architecture': platform.machine(),
            'hostname': platform.node(),
            'python_version': platform.python_version(),
            
            # CPU
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=1),
            
            # Memory
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'percent': psutil.virtual_memory().percent
            },
            
            # Disk
            'disk': {
                'total': psutil.disk_usage('/').total,
                'used': psutil.disk_usage('/').used,
                'free': psutil.disk_usage('/').free,
                'percent': psutil.disk_usage('/').percent
            },
            
            # Timestamp
            'timestamp': datetime.now().isoformat()
        }
        
        return {
            'success': True,
            'system_info': info
        }
    
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        return {
            'success': False,
            'error': str(e)
        }


__all__ = ['router']
