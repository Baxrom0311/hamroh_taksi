"""
app/utils/auth_utils.py

AUTHENTICATION & AUTHORIZATION UTILITIES

BU FAYL NIMA QILADI:
- Centralized authentication checks
- Role-based access control (RBAC) helpers
- Token validation utilities
- Permission decorators

ISHLATISH:
    from app.utils.auth_utils import require_admin, check_user_permission
    
    @require_admin
    async def admin_only_function():
        pass
"""
from typing import Callable, Optional, Any, TypeVar, ParamSpec, Coroutine, Awaitable
from functools import wraps
from loguru import logger

from app.models.user import UserRole
# Import exceptions from app.core.exceptions (explicitly)
from app.core.exceptions import (
    HamrohBaseException, 
    ValidationError as CoreValidationError,
    PermissionError as CorePermissionError
)

# Alias for standard exceptions if needed, OR use Core exceptions
PermissionError = CorePermissionError
ValidationError = CoreValidationError

# Type hints for decorators
P = ParamSpec('P')
T = TypeVar('T')


# ============================================
# PERMISSION CHECKS
# ============================================

def check_user_permission(
    user_role: Optional[UserRole],
    required_role: UserRole
) -> bool:
    """
    User'ning permission borligini tekshirish
    
    Role Hierarchy (yuqoridan pastga):
    1. GLAVNI_ADMIN - Barcha huquqlar
    2. ADMIN - Ko'p huquqlar
    3. DRIVER - Driver huquqlari
    4. PASSENGER - Passenger huquqlari
    
    Args:
        user_role: User'ning roli
        required_role: Kerakli rol
    
    Returns:
        True: Permission bor
        False: Permission yo'q
    
    ISHLATISH:
        has_permission = check_user_permission(
            user_role=UserRole.ADMIN,
            required_role=UserRole.DRIVER
        )  # True (admin driver'dan yuqori)
    """
    # Role hierarchy
    role_hierarchy = {
        UserRole.GLAVNI_ADMIN: 4,
        UserRole.ADMIN: 3,
        UserRole.DRIVER: 2,
        UserRole.PASSENGER: 1
    }
    
    if user_role is None:
        return False
        
    user_level = role_hierarchy.get(user_role, 0)
    required_level = role_hierarchy.get(required_role, 0)
    
    return user_level >= required_level


def is_admin(user_role: Optional[UserRole]) -> bool:
    """
    Admin yoki Glavni Admin'mi?
    
    ISHLATISH:
        if is_admin(current_user.role):
            # Admin panel'ga kirish
            pass
    """
    if user_role is None:
        return False
    return user_role in [UserRole.GLAVNI_ADMIN, UserRole.ADMIN]


def is_glavni_admin(user_role: Optional[UserRole]) -> bool:
    """
    Bosh admin'mi?
    
    ISHLATISH:
        if is_glavni_admin(current_user.role):
            # Faqat bosh admin uchun
            pass
    """
    if user_role is None:
        return False
    return user_role == UserRole.GLAVNI_ADMIN


def is_driver(user_role: UserRole) -> bool:
    """
    Driver'mi?
    """
    return user_role == UserRole.DRIVER


def is_passenger(user_role: UserRole) -> bool:
    """
    Passenger'mi?
    """
    return user_role == UserRole.PASSENGER


# ============================================
# PERMISSION DECORATORS (FastAPI)
# ============================================

def require_role(required_role: UserRole):
    """
    Role-based access control decorator (FastAPI)
    
    Args:
        required_role: Kerakli rol
    
    ISHLATISH:
        from fastapi import Depends
        from app.admin.auth import get_current_user
        
        @router.get("/admin/users")
        @require_role(UserRole.ADMIN)
        async def get_users(current_user = Depends(get_current_user)):
            # Faqat admin kirishi mumkin
            pass
    """
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # current_user parametrni topish
            current_user = kwargs.get('current_user')
            
            if not current_user:
                raise PermissionError("Authentication required")
            
            user_role = current_user.get('role') if isinstance(current_user, dict) else getattr(current_user, 'role', None)
            
            if not user_role:
                raise PermissionError("User role not found")
            
            # String'dan UserRole'ga convert qilish
            if isinstance(user_role, str):
                try:
                    user_role = UserRole(user_role)
                except ValueError:
                    raise PermissionError(f"Invalid user role: {user_role}")

            if not isinstance(user_role, UserRole):
                 raise PermissionError("Invalid user role type")
            
            # Permission tekshiruvi
            if not check_user_permission(user_role, required_role):
                raise PermissionError(
                    f"Access denied. Required role: {required_role.value}, "
                    f"your role: {user_role.value}"
                )
            
            return await func(*args, **kwargs)
            
        return wrapper
    return decorator


def require_admin(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """
    Admin-only decorator
    
    ISHLATISH:
        @router.post("/admin/settings")
        @require_admin
        async def update_settings(current_user = Depends(get_current_user)):
            # Faqat admin
            pass
    """
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        current_user = kwargs.get('current_user')
        
        if not current_user:
            raise PermissionError("Authentication required")
        
        user_role = current_user.get('role') if isinstance(current_user, dict) else getattr(current_user, 'role', None)
        
        if isinstance(user_role, str):
            user_role = UserRole(user_role)
        
        if not is_admin(user_role):
            raise PermissionError("Admin access required")
        
        return await func(*args, **kwargs)
        
    return wrapper


def require_glavni_admin(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """
    Glavni Admin-only decorator
    
    ISHLATISH:
        @router.delete("/admin/users/{user_id}")
        @require_glavni_admin
        async def delete_user(current_user = Depends(get_current_user)):
            # Faqat bosh admin
            pass
    """
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        current_user = kwargs.get('current_user')
        
        if not current_user:
            raise PermissionError("Authentication required")
        
        user_role = current_user.get('role') if isinstance(current_user, dict) else getattr(current_user, 'role', None)
        
        if isinstance(user_role, str):
            user_role = UserRole(user_role)
        
        if not is_glavni_admin(user_role):
            raise PermissionError("Glavni Admin access required")
        
        return await func(*args, **kwargs)
        
    return wrapper


# ============================================
# BOT PERMISSION DECORATORS
# ============================================

def bot_require_role(required_role: UserRole):
    """
    Role-based access control decorator (Bot handlers)
    
    ISHLATISH:
        from aiogram.types import Message
        
        @router.message(F.text == "Admin Panel")
        @bot_require_role(UserRole.ADMIN)
        async def admin_panel(message: Message, user_role: UserRole):
            # Faqat admin
            pass
    """
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Typechecking imports inside wrapper to avoid circular deps if any
            from aiogram.types import Message, CallbackQuery, TelegramObject
            
            # user_role parametrni topish
            user_role = kwargs.get('user_role')
            
            if not user_role:
                logger.warning(f"No user_role found in {func.__name__}")
                return None  # type: ignore
            
            # String'dan UserRole'ga convert qilish
            if isinstance(user_role, str):
                try:
                    user_role = UserRole(user_role)
                except ValueError:
                    logger.error(f"Invalid user role: {user_role}")
                    return None  # type: ignore
            
            # Handle potential 'Any' or 'object' type for user_role by ensuring it is UserRole (or close enough) before passing
            if not isinstance(user_role, UserRole):
                 raise PermissionError("Invalid user role type")

            # Permission tekshiruvi
            # We explicitly cast or check if it matches expectations
            if not check_user_permission(user_role, required_role):
                logger.warning(
                    f"Permission denied for {func.__name__}: "
                    f"required={required_role.value}, current={user_role.value}"
                )
                
                # Bot'da xabar yuborish (args'dan Message topish)
                message: Optional[Message] = None
                
                for arg in args:
                    if isinstance(arg, Message):
                        message = arg
                        break
                    elif isinstance(arg, CallbackQuery):
                        if isinstance(arg.message, Message):
                            message = arg.message
                        break
                
                if message:
                    await message.answer(
                        "⛔️ Sizda bu funksiyaga kirish huquqi yo'q!"
                    )
                
                return None  # type: ignore
            
            return await func(*args, **kwargs)
            
        return wrapper
    return decorator


# ============================================
# RESOURCE OWNERSHIP CHECKS
# ============================================

async def check_resource_ownership(
    user_id: Any,
    resource_owner_id: Any,
    user_role: Optional[UserRole]
) -> bool:
    """
    Resource ownership tekshirish
    
    QOIDA:
    - Admin'lar barcha resource'larga kirishi mumkin
    - Oddiy user'lar faqat o'z resource'lariga
    
    Args:
        user_id: Current user ID
        resource_owner_id: Resource egasining ID'si
        user_role: Current user'ning roli
    
    Returns:
        True: Access bor
        False: Access yo'q
    
    ISHLATISH:
        can_access = await check_resource_ownership(
            user_id=current_user_id,
            resource_owner_id=order.passenger_id,
            user_role=current_user.role
        )
        
        if not can_access:
            raise PermissionError("Bu buyurtmaga kirish huquqingiz yo'q")
    """
    # Admin'lar hamma narsaga kirishi mumkin
    if is_admin(user_role):
        return True
    
    # Oddiy user'lar faqat o'z resource'lariga
    return user_id == resource_owner_id


def require_ownership(
    resource_owner_key: str = 'resource_owner_id'
):
    """
    Ownership decorator
    
    Args:
        resource_owner_key: Kwargs'dagi owner ID kaliti
    
    ISHLATISH:
        @require_ownership(resource_owner_key='passenger_id')
        async def get_order(
            order_id: int,
            passenger_id: int,
            current_user = Depends(get_current_user)
        ):
            # Faqat owner yoki admin
            pass
    """
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            current_user = kwargs.get('current_user')
            resource_owner_id = kwargs.get(resource_owner_key)
            
            if not current_user or resource_owner_id is None:
                raise PermissionError("Authentication or ownership check failed")
            
            user_id = current_user.get('user_id') if isinstance(current_user, dict) else getattr(current_user, 'user_id', None)
            user_role = current_user.get('role') if isinstance(current_user, dict) else getattr(current_user, 'role', None)
            
            if isinstance(user_role, str):
                user_role = UserRole(user_role)
            
            can_access = await check_resource_ownership(
                user_id=user_id,
                resource_owner_id=resource_owner_id,
                user_role=user_role
            )
            
            if not can_access:
                raise PermissionError("Bu resource'ga kirish huquqingiz yo'q")
            
            return await func(*args, **kwargs)
            
        return wrapper
    return decorator


# ============================================
# EXPORT
# ============================================

__all__ = [
    # Permission checks
    'check_user_permission',
    'is_admin',
    'is_glavni_admin',
    'is_driver',
    'is_passenger',
    
    # FastAPI decorators
    'require_role',
    'require_admin',
    'require_glavni_admin',
    
    # Bot decorators
    'bot_require_role',
    
    # Ownership
    'check_resource_ownership',
    'require_ownership',
]
