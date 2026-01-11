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
from app.models.route import Route, create_route, get_all_active_routes
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
                    'commission_amount': settings_dict.get('commission_amount', config_settings.COMMISSION_AMOUNT),
                    'bot_is_free': settings_dict.get('bot_is_free', 'true'),
                    'ban_percentage_threshold': settings_dict.get('ban_percentage_threshold', '50'),
                    'ban_count_threshold': settings_dict.get('ban_count_threshold', '5'),
                    'max_driver_change_per_hour': settings_dict.get('max_driver_change_per_hour', '3'),
                    'max_pickup_distance_km': settings_dict.get('max_pickup_distance_km', str(config_settings.MAX_PICKUP_DISTANCE_KM)),
                    'auto_confirm_delay_seconds': settings_dict.get('auto_confirm_delay_seconds', str(config_settings.AUTO_CONFIRM_DELAY_SECONDS)),
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
        
        async with get_session() as session:
            # Database'da yangilash
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
    Barcha marshrutlar
    """
    try:
        async with get_session() as session:
            routes = await get_all_active_routes(session)
            
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
                distance_km=request.distance_km
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
            # Deactivate (delete emas, is_active = false)
            await session.execute(
                update(Route)
                .where(Route.route_id == route_id)
                .values(is_active=False)
            )
            
            await session.commit()
            
            logger.info(
                f"Route {route_id} deactivated by {current_user['username']}"
            )
            
            return {
                'success': True,
                'message': 'Marshrut o\'chirildi'
            }
    
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