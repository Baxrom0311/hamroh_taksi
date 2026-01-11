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
        "iat": datetime.utcnow()
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    JWT token'ni decode qilish
    
    Args:
        token: JWT token
    
    Returns:
        Token ichidagi ma'lumotlar
    
    Raises:
        HTTPException: Token noto'g'ri yoki muddati tugagan
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
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
    
    # ========================================
    # DEMO MODE (Development)
    # ========================================
    
    if settings.is_development:
        # Hardcoded admin (faqat development)
        if request.username == "admin" and request.password == "admin123":
            
            # Token yaratish
            access_token = create_access_token(
                data={
                    "sub": "999999999",  # Demo admin ID
                    "username": "admin",
                    "role": "glavni_admin"
                }
            )
            
            logger.info(f"✅ Admin logged in (DEMO): {request.username}")
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": {
                    "user_id": 999999999,
                    "username": "admin",
                    "role": "glavni_admin",
                    "full_name": "Demo Admin"
                }
            }
    
    # ========================================
    # PRODUCTION MODE
    # ========================================
    
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
        
        # Parolni tekshirish
        # DIQQAT: Production'da user.password_hash bo'lishi kerak!
        # Hozircha hardcoded password
        if request.password != "admin123":  # TODO: verify_password(request.password, user.password_hash)
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
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Logout (JWT invalidation)
    
    JWT stateless, shuning uchun logout faqat client-side
    Agar server-side logout kerak bo'lsa - Redis blacklist ishlatish kerak
    """
    logger.info(f"Admin logged out: {current_user['username']}")
    
    return {
        'success': True,
        'message': 'Logged out successfully'
    }


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
    
    TODO: Production'da implement qilish
    """
    # TODO: Implement password change
    
    return {
        'success': True,
        'message': 'Password changed (not implemented yet)'
    }


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