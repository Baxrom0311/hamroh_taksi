"""
app/admin/auth.py

ADMIN AUTHENTICATION & AUTHORIZATION

BU FAYL NIMA QILADI:
- JWT token yaratish va tekshirish
- Admin login
- Password hashing
- Current user dependency
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional
import jwt
from passlib.context import CryptContext
from loguru import logger
from fastapi import Request # Request import qiling

from config.settings import settings
from app.core.database import get_session
from app.models.user import User, UserRole
from sqlalchemy import select


# ============================================
# ROUTER & SECURITY
# ============================================

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================
# SCHEMAS
# ============================================

class LoginRequest(BaseModel):
    """Login so'rovi"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token javobi"""
    access_token: str
    token_type: str = "bearer"
    user: dict


class ChangePasswordRequest(BaseModel):
    """Parol o'zgartirish"""
    old_password: str
    new_password: str


# ============================================
# PASSWORD HASHING
# ============================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Parolni tekshirish
    
    Args:
        plain_password: Oddiy parol
        hashed_password: Hash qilingan parol
    
    Returns:
        True: Parol to'g'ri
        False: Parol noto'g'ri
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Parolni hash qilish
    
    ISHLATISH:
        hashed = get_password_hash("admin123")
        print(hashed)  # $2b$12$...
    """
    return pwd_context.hash(password)


# ============================================
# JWT TOKEN
# ============================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    JWT token yaratish
    
    Args:
        data: Token ichidagi ma'lumotlar (user_id, username, role)
        expires_delta: Token muddati
    
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(__import__('uuid').uuid4()),  # ✅ Unique token ID for revocation
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    JWT token'ni decode qilish + blacklist check
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # ✅ FIX: JWT revocation — blacklist check
        jti = payload.get("jti")
        if jti:
            import asyncio
            from app.core.redis_client import redis_client
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Sync context (FastAPI dependency) — check via sync helper
                    import threading
                    _blacklisted = [False]
                    def _check():
                        _loop = asyncio.new_event_loop()
                        _blacklisted[0] = _loop.run_until_complete(redis_client.exists(f"jwt_blacklist:{jti}"))
                        _loop.close()
                    t = threading.Thread(target=_check)
                    t.start()
                    t.join(timeout=1)
                    if _blacklisted[0]:
                        raise jwt.InvalidTokenError("Token revoked")
            except (RuntimeError, jwt.InvalidTokenError):
                raise
            except Exception:
                pass  # Redis unavailable — allow token
        
        return payload
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token muddati tugagan"
        )
    
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token noto'g'ri"
        )


# ============================================
# ADMIN USER DEPENDENCY
# ============================================

async def get_current_user(
    request: Request, # Request obyektini qo'shdik
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)) 
) -> dict:
    """
    Hozirgi foydalanuvchini olish (Header yoki Cookie'dan)
    """
    token = None
    
    # 1. Avval Header'dan qidiramiz
    if credentials:
        token = credentials.credentials
    
    # 2. Agar headerda bo'lmasa, Cookie'dan qidiramiz
    if not token:
        token = request.cookies.get("access_token")
    
    if not token:
        # Agar umuman token bo'lmasa, login sahifasiga redirect qilish tavsiya etiladi
        # Yoki 401 xatosi qaytarish
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tizimga kirmagansiz"
        )
    
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token noto'g'ri"
        )
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.user_id == int(user_id))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=401, detail="Foydalanuvchi topilmadi")
        
        # ROL TEKSHIRUVI (Muhim: Enum qiymatini tekshiring)
        # Bosh admin yoki Admin ekanligini string ko'rinishida ham tekshiramiz
        user_role_value = user.role.value if hasattr(user.role, 'value') else str(user.role)
        
        if user_role_value not in ["admin", "glavni_admin"]:
            logger.warning(f"Access denied for role: {user_role_value}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin huquqi yo'q"
            )
        
        if user.is_blocked:
            raise HTTPException(status_code=403, detail="Foydalanuvchi bloklangan")
        
        return {
            'user_id': user.user_id,
            'username': user.username or user.phone_number,
            'role': user_role_value,
            'full_name': user.full_name
        }


# ============================================
# LOGIN ENDPOINT
# ============================================

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Admin login
    
    DEMO CREDENTIALS:
    - username: admin
    - password: admin123
    
    PRODUCTION'DA:
    Database'dan user ma'lumotlarini olish kerak!
    """
    
    async with get_session() as session:
        # Username bo'yicha qidirish (phone_number yoki username)
        result = await session.execute(
            select(User).where(
                (User.username == request.username) |
                (User.phone_number == request.username)
            )
        )
        
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"❌ Login failed: user not found - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Noto'g'ri login yoki parol"
            )
        
        # Admin yoki Glavni Admin?
        if user.role not in [UserRole.ADMIN, UserRole.GLAVNI_ADMIN]:
            logger.warning(f"❌ Login failed: not admin - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin huquqi yo'q"
            )
        
        # Parolni tekshirish (hash majburiy)
        if not getattr(user, "password_hash", None):
            logger.warning(f"❌ Login failed: password hash missing - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Parol sozlanmagan. Admin bilan bog'laning."
            )

        if not verify_password(request.password, user.password_hash):  # type: ignore[attr-defined]
            logger.warning(f"❌ Login failed: wrong password - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Noto'g'ri login yoki parol"
            )
        
        # Token yaratish
        access_token = create_access_token(
            data={
                "sub": str(user.user_id),
                "username": user.username or user.phone_number,
                "role": user.role.value
            }
        )
        
        # Last active yangilash
        from app.models.user import update_last_active
        await update_last_active(session, user.user_id)
        await session.commit()
        
        logger.success(f"✅ Admin logged in: {request.username}")
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "user_id": user.user_id,
                "username": user.username or user.phone_number,
                "role": user.role.value,
                "full_name": user.full_name
            }
        }


# ============================================
# LOGOUT (Optional - Token'ni invalidate qilish)
# ============================================

@router.post("/logout")
async def logout(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Logout — ✅ FIX: Token'ni Redis blacklist'ga qo'shish
    """
    # Token'ni olish
    token = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("access_token")
    
    if token:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                import time
                from app.core.redis_client import redis_client
                ttl = max(int(exp - time.time()), 0)
                await redis_client.set(f"jwt_blacklist:{jti}", "1", ex=ttl or 7200)
        except Exception:
            pass  # Token already expired or invalid
    
    logger.info(f"Admin logged out: {current_user['username']}")
    return {'success': True, 'message': 'Logged out successfully'}


# ============================================
# CHANGE PASSWORD
# ============================================

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Parolni o'zgartirish
    
    Args:
        request: old_password va new_password
    
    Returns:
        success: bool
    """
    try:
        async with get_session() as session:
            # User'ni olish
            result = await session.execute(
                select(User).where(User.user_id == current_user['user_id'])
            )
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Foydalanuvchi topilmadi"
                )
            
            # Old password check (agar password_hash mavjud bo'lsa)
            if hasattr(user, "password_hash") and user.password_hash:
                if not verify_password(request.old_password, user.password_hash):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Eski parol noto'g'ri"
                    )
            
            # New password validation - ✅ FIX: Stronger policy
            pwd = request.new_password
            if len(pwd) < 8:
                raise HTTPException(status_code=400, detail="Parol kamida 8 ta belgidan iborat bo'lishi kerak")
            if not any(c.isupper() for c in pwd):
                raise HTTPException(status_code=400, detail="Parolda kamida 1 ta katta harf bo'lishi kerak")
            if not any(c.isdigit() for c in pwd):
                raise HTTPException(status_code=400, detail="Parolda kamida 1 ta raqam bo'lishi kerak")
            
            # Hash new password
            new_password_hash = get_password_hash(request.new_password)
            
            # Update password in database
            # Note: User model'da password_hash field bo'lishi kerak
            if hasattr(user, "password_hash"):
                user.password_hash = new_password_hash  # type: ignore[attr-defined]
                await session.commit()
                
                logger.success(f"✅ Password changed for user: {current_user['username']}")
                
                return {
                    'success': True,
                    'message': 'Parol muvaffaqiyatli o\'zgartirildi'
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="User model'da password_hash field yo'q. Migration kerak."
                )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parol o'zgartirishda xatolik"
        )


# ============================================
# CURRENT USER INFO
# ============================================

@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Hozirgi user ma'lumotlari
    """
    return {
        'success': True,
        'user': current_user
    }


__all__ = [
    'router',
    'get_current_user',
    'create_access_token',
    'verify_password',
    'get_password_hash'
]
