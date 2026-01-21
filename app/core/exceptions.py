"""
app/core/exceptions.py

BU FAYL NIMA QILADI:
- Custom exception'lar (maxsus xatolar)
- Xatolarni aniq va tushunarli qilish
- Error handling'ni soddalashtirish

NIMAGA KERAK:
    # ❌ YOMON:
    raise Exception("Balans yetarli emas")
    
    # ✅ YAXSHI:
    raise InsufficientBalanceError(
        required=5000,
        available=2000,
        driver_id=123
    )
    
    # Xatoni tutish oson:
    except InsufficientBalanceError as e:
        print(e.message)
        print(e.details)

ISHLATISH:
    from app.core.exceptions import InsufficientBalanceError
    
    if driver.balance < commission:
        raise InsufficientBalanceError(
            required=commission,
            available=driver.balance
        )
"""

from typing import Optional, Dict, Any


# ============================================
# BASE EXCEPTION (Barcha custom exception'lar bundan kelib chiqadi)
# ============================================

class HamrohBaseException(Exception):
    """
    Base exception (barcha custom exception'lar uchun)
    
    NIMA BERADI:
    - error_code: Xato kodi (masalan: "INSUFFICIENT_BALANCE")
    - message: Foydalanuvchiga ko'rsatiladigan xabar
    - details: Qo'shimcha ma'lumotlar (dict)
    - status_code: HTTP status kod (API uchun)
    """
    
    error_code: str = "UNKNOWN_ERROR"
    message: str = "Noma'lum xatolik yuz berdi"
    status_code: int = 500
    
    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Args:
            message: Custom xabar (default: class message)
            details: Qo'shimcha ma'lumotlar
            **kwargs: Qo'shimcha parametrlar (details'ga qo'shiladi)
        """
        self.message = message or self.message
        self.details = details or {}
        
        # **kwargs ni details'ga qo'shish
        if kwargs:
            self.details.update(kwargs)
        
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """String representation"""
        return f"[{self.error_code}] {self.message}"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message='{self.message}', details={self.details})"
    
    def to_dict(self) -> dict:
        """
        Dictionary'ga aylantirish (API response uchun)
        
        Returns:
            {
                'error_code': str,
                'message': str,
                'details': dict
            }
        """
        return {
            'error_code': self.error_code,
            'message': self.message,
            'details': self.details
        }


# ============================================
# USER & AUTHENTICATION EXCEPTIONS
# ============================================

class UserNotFoundException(HamrohBaseException):
    """Foydalanuvchi topilmadi"""
    error_code = "USER_NOT_FOUND"
    message = "Foydalanuvchi topilmadi"
    status_code = 404


class UserAlreadyExistsException(HamrohBaseException):
    """Foydalanuvchi allaqachon ro'yxatdan o'tgan"""
    error_code = "USER_ALREADY_EXISTS"
    message = "Bu telefon raqami allaqachon ro'yxatdan o'tgan"
    status_code = 409


class InvalidPhoneNumberException(HamrohBaseException):
    """Noto'g'ri telefon raqam"""
    error_code = "INVALID_PHONE_NUMBER"
    message = "Telefon raqam noto'g'ri formatda"
    status_code = 400


class InvalidSMSCodeException(HamrohBaseException):
    """Noto'g'ri SMS kod"""
    error_code = "INVALID_SMS_CODE"
    message = "SMS kod noto'g'ri yoki muddati tugagan"
    status_code = 400


class SMSRateLimitException(HamrohBaseException):
    """SMS rate limit oshgan"""
    error_code = "SMS_RATE_LIMIT_EXCEEDED"
    message = "Juda ko'p SMS yuborildi. Keyinroq urinib ko'ring."
    status_code = 429


# ============================================
# ORDER EXCEPTIONS
# ============================================

class OrderNotFoundException(HamrohBaseException):
    """Buyurtma topilmadi"""
    error_code = "ORDER_NOT_FOUND"
    message = "Buyurtma topilmadi"
    status_code = 404


class OrderAlreadyAcceptedException(HamrohBaseException):
    """Buyurtma allaqachon qabul qilingan"""
    error_code = "ORDER_ALREADY_ACCEPTED"
    message = "Bu buyurtma allaqachon boshqa haydovchi tomonidan qabul qilingan"
    status_code = 409


class OrderLockedError(HamrohBaseException):
    """Buyurtma lock'langan (boshqa haydovchi qabul qilmoqda)"""
    error_code = "ORDER_LOCKED"
    message = "Bu buyurtma boshqa haydovchi tomonidan qabul qilinmoqda"
    status_code = 423  # 423 Locked


class OrderCancellationLimitException(HamrohBaseException):
    """Buyurtma bekor qilish limiti tugagan"""
    error_code = "ORDER_CANCELLATION_LIMIT"
    message = "Siz juda ko'p buyurtma bekor qildingiz. 1 soatdan keyin urinib ko'ring."
    status_code = 429


class InvalidOrderStatusException(HamrohBaseException):
    """Noto'g'ri buyurtma holati"""
    error_code = "INVALID_ORDER_STATUS"
    message = "Buyurtmani shu holatda bajarib bo'lmaydi"
    status_code = 400


# ============================================
# DRIVER EXCEPTIONS
# ============================================

class DriverNotFoundException(HamrohBaseException):
    """Haydovchi topilmadi"""
    error_code = "DRIVER_NOT_FOUND"
    message = "Haydovchi topilmadi"
    status_code = 404


class DriverBlockedException(HamrohBaseException):
    """Haydovchi bloklangan"""
    error_code = "DRIVER_BLOCKED"
    message = "Sizning hisobingiz bloklangan. Admin bilan bog'laning."
    status_code = 403


class InsufficientBalanceError(HamrohBaseException):
    """
    Balans yetarli emas
    
    MISOL:
        raise InsufficientBalanceError(
            required=5000,
            available=2000,
            driver_id=123
        )
    """
    error_code = "INSUFFICIENT_BALANCE"
    message = "Balans yetarli emas"
    status_code = 402  # 402 Payment Required
    
    def __init__(self, required: int, available: int, **kwargs):
        details = {
            'required': required,
            'available': available,
            'shortage': required - available
        }
        
        message = f"Balans yetarli emas. Kerak: {required:,} so'm, Mavjud: {available:,} so'm"
        
        super().__init__(message=message, details=details, **kwargs)


class DriverRejectLimitException(HamrohBaseException):
    """Haydovchi juda ko'p rad etgan"""
    error_code = "DRIVER_REJECT_LIMIT"
    message = "Siz bugun juda ko'p buyurtma rad etdingiz. Vaqtincha cheklangansiz."
    status_code = 429


class NoDriversAvailableException(HamrohBaseException):
    """Bo'sh haydovchilar yo'q"""
    error_code = "NO_DRIVERS_AVAILABLE"
    message = "Hozirda bo'sh haydovchilar yo'q. Iltimos, keyinroq urinib ko'ring."
    status_code = 503  # 503 Service Unavailable


# ============================================
# PASSENGER EXCEPTIONS
# ============================================

class PassengerNotFoundException(HamrohBaseException):
    """Yo'lovchi topilmadi"""
    error_code = "PASSENGER_NOT_FOUND"
    message = "Yo'lovchi topilmadi"
    status_code = 404


class PassengerBlockedException(HamrohBaseException):
    """Yo'lovchi bloklangan"""
    error_code = "PASSENGER_BLOCKED"
    message = "Sizning hisobingiz bloklangan. Admin bilan bog'laning."
    status_code = 403


# ============================================
# ROUTE EXCEPTIONS
# ============================================

class RouteNotFoundException(HamrohBaseException):
    """Marshrut topilmadi"""
    error_code = "ROUTE_NOT_FOUND"
    message = "Marshrut topilmadi"
    status_code = 404


class InvalidRouteException(HamrohBaseException):
    """Noto'g'ri marshrut"""
    error_code = "INVALID_ROUTE"
    message = "Bu marshrut mavjud emas"
    status_code = 400


# ============================================
# PAYMENT EXCEPTIONS
# ============================================

class TransactionNotFoundException(HamrohBaseException):
    """Tranzaksiya topilmadi"""
    error_code = "TRANSACTION_NOT_FOUND"
    message = "Tranzaksiya topilmadi"
    status_code = 404


class TransactionAlreadyProcessedException(HamrohBaseException):
    """Tranzaksiya allaqachon ko'rib chiqilgan"""
    error_code = "TRANSACTION_ALREADY_PROCESSED"
    message = "Bu tranzaksiya allaqachon ko'rib chiqilgan"
    status_code = 409


class PaymentFailedException(HamrohBaseException):
    """To'lov xato"""
    error_code = "PAYMENT_FAILED"
    message = "To'lovda xatolik yuz berdi"
    status_code = 402


# ============================================
# GEO & LOCATION EXCEPTIONS
# ============================================

class InvalidLocationException(HamrohBaseException):
    """Noto'g'ri lokatsiya"""
    error_code = "INVALID_LOCATION"
    message = "Lokatsiya ma'lumotlari noto'g'ri"
    status_code = 400


class LocationTooFarException(HamrohBaseException):
    """
    Lokatsiya juda uzoq
    
    MISOL:
        raise LocationTooFarException(
            distance=75.5,
            max_distance=50,
            driver_id=123,
            passenger_location="Gurlan bozori"
        )
    """
    error_code = "LOCATION_TOO_FAR"
    message = "Siz hozirgi joyingizdan juda uzoqdasiz"
    status_code = 400
    
    def __init__(self, distance: float, max_distance: float, **kwargs):
        details = {
            'distance_km': round(distance, 2),
            'max_distance_km': max_distance
        }
        
        message = f"Masofa juda katta: {distance:.1f} km (maksimal: {max_distance} km)"
        
        super().__init__(message=message, details=details, **kwargs)


# ============================================
# LOCK & CONCURRENCY EXCEPTIONS
# ============================================

class ResourceLockedException(HamrohBaseException):
    """Resource lock'langan"""
    error_code = "RESOURCE_LOCKED"
    message = "Bu resurs boshqa jarayonda ishlatilmoqda"
    status_code = 423


class ConcurrencyException(HamrohBaseException):
    """
    Concurrent update muammosi
    
    MISOL:
        # 2 ta request bir vaqtda bitta balansni yangilayapti
        raise ConcurrencyException(
            resource="driver:balance:123",
            message="Balans yangilanmoqda, qayta urinib ko'ring"
        )
    """
    error_code = "CONCURRENCY_ERROR"
    message = "Concurrent update muammosi. Iltimos, qayta urinib ko'ring."
    status_code = 409


# ============================================
# VALIDATION EXCEPTIONS
# ============================================

class ValidationException(HamrohBaseException):
    """
    Validatsiya xatosi
    
    MISOL:
        raise ValidationException(
            field="car_number",
            message="Mashina raqami noto'g'ri formatda",
            expected="01 A 123 BC",
            received="123ABC"
        )
    """
    error_code = "VALIDATION_ERROR"
    message = "Ma'lumotlar noto'g'ri"
    status_code = 400


class MissingFieldException(HamrohBaseException):
    """Majburiy maydon yo'q"""
    error_code = "MISSING_FIELD"
    message = "Majburiy maydon kiritilmagan"
    status_code = 400


# ============================================
# EXTERNAL SERVICE EXCEPTIONS
# ============================================

class SMSServiceException(HamrohBaseException):
    """SMS service xatosi"""
    error_code = "SMS_SERVICE_ERROR"
    message = "SMS yuborishda xatolik yuz berdi"
    status_code = 503


class DatabaseException(HamrohBaseException):
    """Database xatosi"""
    error_code = "DATABASE_ERROR"
    message = "Database xatosi"
    status_code = 500


class RedisException(HamrohBaseException):
    """Redis xatosi"""
    error_code = "REDIS_ERROR"
    message = "Redis xatosi"
    status_code = 500


# ============================================
# ADMIN EXCEPTIONS
# ============================================

class UnauthorizedException(HamrohBaseException):
    """Ruxsat yo'q"""
    error_code = "UNAUTHORIZED"
    message = "Sizda bu amalni bajarish uchun ruxsat yo'q"
    status_code = 401


class ForbiddenException(HamrohBaseException):
    """Taqiqlangan"""
    error_code = "FORBIDDEN"
    message = "Bu amalga ruxsat berilmagan"
    status_code = 403


# ============================================
# ALIASES (Compatibility)
# ============================================

ValidationError = ValidationException
PermissionError = ForbiddenException
DatabaseError = DatabaseException
CacheError = RedisException


# ============================================
# UTILITY FUNCTIONS
# ============================================

def handle_exception(e: Exception) -> dict:
    """
    Exception'ni dict'ga aylantirish (API response uchun)
    
    Args:
        e: Exception
    
    Returns:
        {
            'success': False,
            'error_code': str,
            'message': str,
            'details': dict
        }
    
    ISHLATISH:
        try:
            await some_function()
        except HamrohBaseException as e:
            return handle_exception(e)
    """
    if isinstance(e, HamrohBaseException):
        return {
            'success': False,
            'error_code': e.error_code,
            'message': e.message,
            'details': e.details
        }
    else:
        # Noma'lum xato
        return {
            'success': False,
            'error_code': 'UNKNOWN_ERROR',
            'message': str(e),
            'details': {}
        }


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.core.exceptions
    """
    
    print("\n🧪 Testing Custom Exceptions...\n")
    
    # Test 1: InsufficientBalanceError
    print(" 📝 Test 1: InsufficientBalanceError")
    try:
        raise InsufficientBalanceError(
            required=5000,
            available=2000,
            driver_id=123
        )
    except InsufficientBalanceError as e:
        print(f"   Error: {e}")
        print(f"   Code: {e.error_code}")
        print(f"   Details: {e.details}")
        print(f"   Dict: {e.to_dict()}")
    
    print()
    
    # Test 2: LocationTooFarException
    print(" 📝 Test 2: LocationTooFarException")
    try:
        raise LocationTooFarException(
            distance=75.5,
            max_distance=50,
            driver_id=456,
            passenger_location="Gurlan bozori"
        )
    except LocationTooFarException as e:
        print(f"   Error: {e}")
        print(f"   Details: {e.details}")
    
    print()
    
    # Test 3: handle_exception
    print(" 📝 Test 3: handle_exception")
    try:
        raise OrderNotFoundException(order_id=789)
    except Exception as e:
        result = handle_exception(e)
        print(f"   Result: {result}")
    
    print("\n✅ All exception tests passed!\n")