"""
app/utils/session_utils.py

SESSION MANAGEMENT UTILITIES

BU FAYL NIMA QILADI:
- Session refresh after updates
- Bulk model refresh
- Session state management
- Auto-refresh decorators

MUAMMO:
SQLAlchemy model'lari database update'dan keyin stale (eski) data ko'rsatadi.
Masalan: balance yechilgandan keyin ham eski balance ko'rsatiladi.

YECHIM:
session.refresh() ni avtomatik chaqirish
"""
from typing import List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeMeta
from functools import wraps
from loguru import logger


async def refresh_model(session: AsyncSession, model: Any) -> None:
    """
    Bitta modelni refresh qilish
    
    Args:
        session: Database session
        model: Refresh qilinadigan model instance
    
    ISHLATISH:
        driver = await get_driver(session, driver_id)
        # ... balance update ...
        await refresh_model(session, driver)  # Fresh data
    """
    try:
        await session.refresh(model)
        logger.debug(f"Refreshed model: {model.__class__.__name__}")
    except Exception as e:
        logger.warning(f"Failed to refresh model {model.__class__.__name__}: {e}")


async def refresh_models(session: AsyncSession, *models: Any) -> None:
    """
    Bir nechta modellarni refresh qilish
    
    Args:
        session: Database session
        *models: Refresh qilinadigan model instance'lar
    
    ISHLATISH:
        await refresh_models(session, driver, order, trip)
    """
    for model in models:
        if model is not None:
            await refresh_model(session, model)


async def refresh_and_get_attr(
    session: AsyncSession,
    model: Any,
    attr_name: str
) -> Any:
    """
    Modelni refresh qilib, attribute'ni olish
    
    Args:
        session: Database session
        model: Model instance
        attr_name: Attribute nomi
    
    Returns:
        Fresh attribute value
    
    ISHLATISH:
        new_balance = await refresh_and_get_attr(session, driver, 'balance')
    """
    await session.refresh(model)
    return getattr(model, attr_name)


def auto_refresh(*model_params):
    """
    Decorator: Function'dan keyin model'larni avtomatik refresh qilish
    
    Args:
        *model_params: Refresh qilinadigan parameter nomlari
    
    ISHLATISH:
        @auto_refresh('driver', 'order')
        async def update_order(session, driver, order):
            # ... update logic ...
            pass
        
        # Function tugagandan keyin driver va order avtomatik refresh bo'ladi
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Function'ni chaqirish
            result = await func(*args, **kwargs)
            
            # Session topish
            session = kwargs.get('session')
            if not session:
                # Args ichidan session topish
                for arg in args:
                    if isinstance(arg, AsyncSession):
                        session = arg
                        break
            
            if not session:
                logger.warning(f"Cannot refresh models in {func.__name__}: session not found")
                return result
            
            # Specified model'larni refresh qilish
            for param_name in model_params:
                model = kwargs.get(param_name)
                if model:
                    try:
                        await session.refresh(model)
                        logger.debug(f"Auto-refreshed {param_name} in {func.__name__}")
                    except Exception as e:
                        logger.warning(f"Failed to auto-refresh {param_name}: {e}")
            
            return result
        return wrapper
    return decorator


class SessionRefreshContext:
    """
    Context manager for automatic model refresh
    
    ISHLATISH:
        async with SessionRefreshContext(session, driver, order):
            # ... database operations ...
            pass
        # driver va order avtomatik refresh bo'ladi
    """
    
    def __init__(self, session: AsyncSession, *models: Any):
        self.session = session
        self.models = models
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Xato bo'lmasa, model'larni refresh qilish
        if exc_type is None:
            for model in self.models:
                if model is not None:
                    try:
                        await self.session.refresh(model)
                    except Exception as e:
                        logger.warning(f"Failed to refresh model in context: {e}")
        return False


async def get_fresh_value(
    session: AsyncSession,
    model: Any,
    attr_name: str,
    default: Any = None
) -> Any:
    """
    Fresh qiymat olish (xato bo'lsa default qaytarish)
    
    Args:
        session: Database session
        model: Model instance
        attr_name: Attribute nomi
        default: Default qiymat
    
    Returns:
        Fresh value or default
    """
    try:
        await session.refresh(model)
        return getattr(model, attr_name, default)
    except Exception as e:
        logger.warning(f"Failed to get fresh value for {attr_name}: {e}")
        return default


__all__ = [
    'refresh_model',
    'refresh_models',
    'refresh_and_get_attr',
    'auto_refresh',
    'SessionRefreshContext',
    'get_fresh_value'
]
