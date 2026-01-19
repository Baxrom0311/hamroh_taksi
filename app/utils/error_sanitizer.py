"""
app/utils/error_sanitizer.py

ERROR SANITIZATION UTILITY

BU FAYL NIMA QILADI:
- Database error'larni user'ga ko'rsatishni oldini oladi
- System error'larni generic message'ga aylantiradi
- Xavfsizlik riski (information leakage) ni kamaytiradi

ISHLATISH:
    from app.utils.error_sanitizer import sanitize_error_for_user
    
    try:
        result = await some_database_operation()
    except Exception as e:
        safe_message = sanitize_error_for_user(str(e))
        await message.answer(f"❌ {safe_message}")
"""

import re
from typing import Optional
from loguru import logger


# ============================================
# XAVFLI PATTERN'LAR
# ============================================

# Bu pattern'lar user'ga ko'rsatilmasligi kerak
SENSITIVE_PATTERNS = [
    # Database errors
    r'psycopg',
    r'sqlalchemy',
    r'database',
    r'connection',
    r'pool',
    r'constraint',
    r'foreign key',
    r'unique',
    r'duplicate key',
    
    # System errors
    r'traceback',
    r'file not found',
    r'permission denied',
    r'access denied',
    r'no such file',
    
    # Redis errors
    r'redis',
    r'connection refused',
    r'timeout',
    
    # Python internal
    r'exception',
    r'error in',
    r'failed to',
    r'cannot',
    
    # Network errors
    r'http',
    r'network',
    r'socket',
    r'timed out',
]


# ============================================
# SANITIZATION FUNCTION
# ============================================

def sanitize_error_for_user(error_message: str, context: Optional[str] = None) -> str:
    """
    Error message'ni user uchun xavfsiz qilish
    
    Args:
        error_message: Original error message
        context: Qo'shimcha context (masalan: "order_creation", "payment")
    
    Returns:
        User uchun xavfsiz error message
    
    MISOL:
        >>> sanitize_error_for_user("psycopg2.OperationalError: connection timeout")
        "Tizim xatoligi. Iltimos qayta urinib ko'ring."
        
        >>> sanitize_error_for_user("Buyurtma topilmadi")
        "Buyurtma topilmadi"  # Safe message - user'ga ko'rsatilishi mumkin
    """
    
    # Null check
    if not error_message:
        return "Noma'lum xatolik yuz berdi"
    
    # Lowercase'ga aylantirish (pattern matching uchun)
    error_lower = error_message.lower()
    
    # Xavfli pattern bor mi tekshirish
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, error_lower, re.IGNORECASE):
            logger.warning(f"🔐 Sensitive error sanitized: {error_message[:100]}...")
            
            # Context bo'yicha generic message
            if context == "order_creation":
                return "Buyurtma yaratishda xatolik. Iltimos qayta urinib ko'ring."
            elif context == "payment":
                return "To'lov amalga oshmadi. Iltimos qayta urinib ko'ring."
            elif context == "balance":
                return "Balans operatsiyasida xatolik. Iltimos qayta urinib ko'ring."
            else:
                return "Tizim xatoligi. Iltimos qayta urinib ko'ring."
    
    # Agar xavfli emas bo'lsa, original message'ni qaytarish
    return error_message


def sanitize_error_dict(error_dict: dict) -> dict:
    """
    Error dict'ni sanitize qilish (API response uchun)
    
    Args:
        error_dict: {'success': False, 'message': 'error...'}
    
    Returns:
        Sanitized dict
    
    MISOL:
        >>> sanitize_error_dict({
        ...     'success': False,
        ...     'message': 'psycopg2.Error: database connection failed'
        ... })
        {'success': False, 'message': 'Tizim xatoligi...'}
    """
    if 'message' in error_dict:
        error_dict['message'] = sanitize_error_for_user(error_dict['message'])
    
    return error_dict


# ============================================
# SPECIFIC ERROR MESSAGES (O'zbek tilida)
# ============================================

class ErrorMessages:
    """
    User-friendly error messages (O'zbek tilida)
    """
    
    # Generic
    GENERIC = "Tizim xatoligi. Iltimos qayta urinib ko'ring."
    UNKNOWN = "Noma'lum xatolik yuz berdi. Admin bilan bog'laning."
    
    # Network
    NETWORK_ERROR = "Internet bilan aloqa yo'q. Iltimos qayta urinib ko'ring."
    TIMEOUT = "Jarayon juda uzoq davom etdi. Qayta urinib ko'ring."
    
    # Database
    DATABASE_ERROR = "Ma'lumotlar bazasi xatoligi. Iltimos qayta urinib ko'ring."
    NOT_FOUND = "Ma'lumot topilmadi."
    ALREADY_EXISTS = "Bu ma'lumot allaqachon mavjud."
    
    # Permission
    PERMISSION_DENIED = "Sizda bu amalni bajarish uchun ruxsat yo'q."
    UNAUTHORIZED = "Iltimos avval ro'yxatdan o'ting."
    
    # Validation
    INVALID_INPUT = "Noto'g'ri ma'lumot kiritildi. Qaytadan kiriting."
    REQUIRED_FIELD = "Barcha maydonlarni to'ldiring."
    
    # Business logic
    INSUFFICIENT_BALANCE = "Balans yetarli emas."
    ORDER_NOT_FOUND = "Buyurtma topilmadi."
    DRIVER_NOT_AVAILABLE = "Haydovchi mavjud emas."


# ============================================
# EXCEPTION WRAPPER
# ============================================

def safe_error_message(func):
    """
    Decorator: Function exception'larini sanitize qiladi
    
    ISHLATISH:
        @safe_error_message
        async def my_handler(message: Message):
            # Agar exception bo'lsa, user'ga xavfsiz message ko'rsatiladi
            result = await database_operation()
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            
            # User'ga xavfsiz message
            safe_msg = sanitize_error_for_user(str(e))
            
            # Agar Message yoki CallbackQuery bor bo'lsa, xabar yuborish
            from aiogram.types import Message, CallbackQuery
            
            for arg in args:
                if isinstance(arg, Message):
                    await arg.answer(f"❌ {safe_msg}")
                    break
                elif isinstance(arg, CallbackQuery):
                    await arg.answer(f"❌ {safe_msg}", show_alert=True)
                    break
            
            raise  # Original exception'ni qayta raise qilish (logging uchun)
    
    return wrapper


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.utils.error_sanitizer
    """
    
    print("\n🧪 Testing Error Sanitizer...\n")
    
    # Test 1: Database error
    db_error = "psycopg2.OperationalError: could not connect to server: Connection refused"
    print(f"Original: {db_error}")
    print(f"Sanitized: {sanitize_error_for_user(db_error)}")
    print()
    
    # Test 2: Safe error
    safe_error = "Buyurtma topilmadi"
    print(f"Original: {safe_error}")
    print(f"Sanitized: {sanitize_error_for_user(safe_error)}")
    print()
    
    # Test 3: Redis error
    redis_error = "redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379"
    print(f"Original: {redis_error}")
    print(f"Sanitized: {sanitize_error_for_user(redis_error, context='payment')}")
    print()
    
    # Test 4: Dict sanitization
    error_dict = {
        'success': False,
        'message': 'SQLAlchemy IntegrityError: duplicate key value violates unique constraint'
    }
    print(f"Original: {error_dict}")
    print(f"Sanitized: {sanitize_error_dict(error_dict)}")
    print()
    
    print("✅ All tests completed!\n")


__all__ = [
    'sanitize_error_for_user',
    'sanitize_error_dict',
    'ErrorMessages',
    'safe_error_message'
]
