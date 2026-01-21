"""
app/utils/error_handlers.py

CENTRALIZED ERROR HANDLING UTILITIES

BU FAYL NIMA QILADI:
- Error handling decorators
- Reusable error response formatters
- Common exception handlers
- DRY principle

ISHLATISH:
    from app.utils.error_handlers import handle_db_errors, format_error_response
    
    @handle_db_errors
    async def my_function():
        # Database operations
        pass
"""
from typing import Any, Callable, Optional, TypeVar, ParamSpec, Awaitable
from functools import wraps
import traceback
from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from redis.exceptions import RedisError
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ValidationError,
    DatabaseError,
    CacheError,
    PermissionError as CustomPermissionError
)

# Type hints for decorators
P = ParamSpec('P')
T = TypeVar('T')


# ============================================
# DATABASE ERROR HANDLER DECORATOR
# ============================================

def handle_db_errors(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """
    Database error handling decorator
    
    QANDAY ISHLAYDI:
    - Database xatolarni ushlaydi
    - User-friendly xabar qaytaradi
    - Detailed logging
    
    ISHLATISH:
        @handle_db_errors
        async def get_user(user_id: int):
            # Database query
            pass
    """
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await func(*args, **kwargs)
            
        except IntegrityError as e:
            logger.error(f"Database integrity error in {func.__name__}: {e}")
            
            # Extract error message
            error_msg = "Ma'lumot bazasi xatosi"
            if "UNIQUE constraint" in str(e):
                error_msg = "Bu ma'lumot allaqachon mavjud"
            elif "FOREIGN KEY constraint" in str(e):
                error_msg = "Bog'liq ma'lumot topilmadi"
            elif "NOT NULL constraint" in str(e):
                error_msg = "Majburiy maydon to'ldirilmagan"
            
            raise DatabaseError(error_msg)
            
        except SQLAlchemyError as e:
            logger.error(
                f"Database error in {func.__name__}: {e}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            raise DatabaseError("Ma'lumot bazasiga murojaat qilishda xatolik")
            
    return wrapper


# ============================================
# REDIS ERROR HANDLER DECORATOR
# ============================================

def handle_redis_errors(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """
    Redis error handling decorator
    
    ISHLATISH:
        @handle_redis_errors
        async def cache_data(key: str, value: Any):
            # Redis operations
            pass
    """
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await func(*args, **kwargs)
            
        except RedisError as e:
            logger.error(
                f"Redis error in {func.__name__}: {e}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            raise CacheError("Cache xizmatida xatolik")
            
    return wrapper


# ============================================
# RETRY DECORATOR
# ============================================

def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Generic retry decorator
    
    Args:
        max_retries: Maksimal retry soni
        delay: Boshlang'ich kechikish (soniya)
        backoff: Har retry'da kechikishni oshirish koeffitsienti
        exceptions: Qaysi xatolarni retry qilish
    
    ISHLATISH:
        @retry_on_failure(max_retries=3, delay=1.0)
        async def unstable_operation():
            # Operation that might fail
            pass
    """
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            import asyncio
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries} retries: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {current_delay}s: {e}"
                    )
                    
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            # Should not happen if exceptions is (Exception,)
            return await func(*args, **kwargs)
                    
        return wrapper
    return decorator


# ============================================
# ERROR RESPONSE FORMATTERS
# ============================================

def format_error_response(
    message: str,
    error_code: Optional[str] = None,
    details: Optional[dict] = None,
    status_code: int = status.HTTP_400_BAD_REQUEST
) -> JSONResponse:
    """
    Formatted error response yaratish (FastAPI uchun)
    
    Args:
        message: Xato xabari
        error_code: Error code (optional)
        details: Qo'shimcha ma'lumotlar (optional)
        status_code: HTTP status code
    
    Returns:
        JSONResponse
    
    ISHLATISH:
        return format_error_response(
            message="User topilmadi",
            error_code="USER_NOT_FOUND",
            status_code=404
        )
    """
    response_data: dict[str, Any] = {
        "success": False,
        "message": message
    }
    
    if error_code:
        response_data["error_code"] = error_code
    
    if details:
        response_data["details"] = details
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )


def format_success_response(
    message: str,
    data: Optional[Any] = None,
    meta: Optional[dict] = None
) -> dict[str, Any]:
    """
    Formatted success response yaratish
    
    Args:
        message: Success xabari
        data: Ma'lumotlar (optional)
        meta: Metadata (optional - pagination, etc.)
    
    Returns:
        Dict response
    
    ISHLATISH:
        return format_success_response(
            message="User yaratildi",
            data={"user_id": 123}
        )
    """
    response: dict[str, Any] = {
        "success": True,
        "message": message
    }
    
    if data is not None:
        response["data"] = data
    
    if meta:
        response["meta"] = meta
    
    return response


# ============================================
# EXCEPTION TO HTTP STATUS MAPPER
# ============================================

def map_exception_to_http(exception: Exception) -> tuple[int, str, str]:
    """
    Exception'dan HTTP status code va message olish
    
    Args:
        exception: Exception object
    
    Returns:
        Tuple: (status_code, error_code, message)
    
    ISHLATISH:
        status_code, code, message = map_exception_to_http(exc)
    """
    if isinstance(exception, ValidationError):
        return (
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            str(exception)
        )
    
    elif isinstance(exception, DatabaseError):
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DATABASE_ERROR",
            str(exception)
        )
    
    elif isinstance(exception, CacheError):
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CACHE_ERROR",
            str(exception)
        )
    
    elif isinstance(exception, CustomPermissionError):
        return (
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
            str(exception)
        )
    
    elif isinstance(exception, HTTPException):
        return (
            exception.status_code,
            "HTTP_EXCEPTION",
            exception.detail
        )
    
    else:
        # Unknown exception
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "Ichki xatolik yuz berdi"
        )


# ============================================
# SAFE EXECUTION WRAPPER
# ============================================

async def safe_execute(
    func: Callable[P, Awaitable[T]],
    *args: P.args,
    **kwargs: P.kwargs
) -> tuple[bool, Optional[T], Optional[str]]:
    """
    Xavfsiz funksiya bajarish (exception catch qilish)
    
    Args:
        func: Bajariladi funksiya
        *args: Pozitsion argumentlar
        **kwargs: Kalit argumentlar
    
    Returns:
        Tuple: (success: bool, result: Any | None, error: str | None)
    
    ISHLATISH:
        success, result, error = await safe_execute(
            my_db_function,
            user_id=123
        )
        
        if success:
            print(f"Result: {result}")
        else:
            print(f"Error: {error}")
    """
    try:
        result = await func(*args, **kwargs)
        return (True, result, None)
        
    except Exception as e:
        logger.error(
            f"Error executing {func.__name__}: {e}\n"
            f"Args: {args}\n"
            f"Kwargs: {kwargs}\n"
            f"Traceback: {traceback.format_exc()}"
        )
        return (False, None, str(e))


# ============================================
# VALIDATION ERROR COLLECTOR
# ============================================

class ValidationErrorCollector:
    """
    Multiple validation error'larni to'plash
    
    ISHLATISH:
        errors = ValidationErrorCollector()
        
        if not name:
            errors.add("name", "Ism kiritilmagan")
        
        if not phone:
            errors.add("phone", "Telefon kiritilmagan")
        
        if errors.has_errors():
            raise ValidationError(errors.format())
    """
    
    def __init__(self):
        self.errors: dict[str, list[str]] = {}
    
    def add(self, field: str, message: str) -> None:
        """Error qo'shish"""
        if field not in self.errors:
            self.errors[field] = []
        self.errors[field].append(message)
    
    def has_errors(self) -> bool:
        """Xatolar bormi?"""
        return len(self.errors) > 0
    
    def get_errors(self) -> dict[str, list[str]]:
        """Barcha xatolarni olish"""
        return self.errors
    
    def format(self) -> str:
        """Formatted error message"""
        if not self.has_errors():
            return ""
        
        messages = []
        for field, field_errors in self.errors.items():
            for error in field_errors:
                messages.append(f"{field}: {error}")
        
        return "\n".join(messages)
    
    def clear(self) -> None:
        """Xatolarni tozalash"""
        self.errors.clear()


# ============================================
# EXPORT
# ============================================

__all__ = [
    # Decorators
    'handle_db_errors',
    'handle_redis_errors',
    'retry_on_failure',
    
    # Formatters
    'format_error_response',
    'format_success_response',
    
    # Mappers
    'map_exception_to_http',
    
    # Utilities
    'safe_execute',
    'ValidationErrorCollector',
]
