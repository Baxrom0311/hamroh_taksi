"""
app/admin/routes/admins.py

ADMIN MANAGEMENT (GLAVNI ADMIN UCHUN)

ENDPOINTS:
- GET /admins - Barcha adminlar
- POST /admins - Yangi admin qo'shish
- DELETE /admins/{user_id} - Admin'ni o'chirish
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from app.admin.auth import get_current_user, get_password_hash
from app.core.database import get_session, transaction
from app.models.user import User, UserRole
from sqlalchemy import select, update, delete

router = APIRouter(prefix="/admins", tags=["admins"])


# ============================================
# SCHEMAS
# ============================================

class CreateAdminRequest(BaseModel):
    """Yangi admin qo'shish"""
    user_id: Optional[int] = None  # Telegram user ID (agar mavjud bo'lsa)
    username: Optional[str] = None
    phone_number: str
    first_name: str
    last_name: Optional[str] = None
    password: str
    role: str = "admin"  # "admin" yoki "glavni_admin"


class AdminResponse(BaseModel):
    """Admin ma'lumotlari"""
    user_id: int
    username: Optional[str]
    phone_number: str
    full_name: str
    role: str
    is_blocked: bool
    created_at: str


# ============================================
# PERMISSION CHECK
# ============================================

def check_glavni_admin(current_user: dict):
    """
    Faqat Glavni Admin uchun
    
    Raises:
        HTTPException: Agar Glavni Admin bo'lmasa
    """
    if current_user.get('role') != 'glavni_admin':
        raise HTTPException(
            status_code=403,
            detail="Bu funksiya faqat Glavni Admin uchun"
        )


# ============================================
# GET ALL ADMINS
# ============================================

@router.get("/")
async def get_all_admins(
    current_user: dict = Depends(get_current_user)
):
    """
    Barcha adminlar ro'yxati
    
    DIQQAT: Faqat Glavni Admin ko'ra oladi
    """
    check_glavni_admin(current_user)
    
    try:
        async with get_session() as session:
            result = await session.execute(
                select(User).where(
                    User.role.in_([UserRole.ADMIN, UserRole.GLAVNI_ADMIN])
                ).order_by(User.created_at.desc())
            )
            admins = result.scalars().all()
            
            admins_list = [
                {
                    'user_id': admin.user_id,
                    'username': admin.username,
                    'phone_number': admin.phone_number,
                    'full_name': admin.full_name,
                    'role': admin.role.value,
                    'is_blocked': admin.is_blocked,
                    'created_at': admin.created_at.isoformat() if admin.created_at else None
                }
                for admin in admins
            ]
            
            return {
                'success': True,
                'admins': admins_list,
                'total': len(admins_list)
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to get admins: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CREATE ADMIN
# ============================================

@router.post("/")
async def create_admin(
    request: CreateAdminRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Yangi admin qo'shish
    
    DIQQAT: Faqat Glavni Admin qo'sha oladi
    
    FLOW:
    1. User mavjudligini tekshirish (user_id yoki phone_number)
    2. Agar mavjud bo'lsa - role'ni o'zgartirish
    3. Agar mavjud bo'lmasa - yangi user yaratish
    """
    check_glavni_admin(current_user)
    
    try:
        async with get_session() as session:
            # 1. Mavjudligini tekshirish
            existing_user = None
            
            if request.user_id:
                # Telegram user ID bo'yicha
                existing_user = await session.get(User, request.user_id)
            
            if not existing_user and request.phone_number:
                # Phone number bo'yicha
                result = await session.execute(
                    select(User).where(User.phone_number == request.phone_number)
                )
                existing_user = result.scalar_one_or_none()
            
            # 2. Agar mavjud bo'lsa - role'ni o'zgartirish
            if existing_user:
                async with transaction() as session:
                    # Role'ni o'zgartirish
                    new_role = UserRole.ADMIN if request.role == "admin" else UserRole.GLAVNI_ADMIN
                    
                    await session.execute(
                        update(User)
                        .where(User.user_id == existing_user.user_id)
                        .values(
                            role=new_role,
                            is_blocked=False,
                            first_name=request.first_name,
                            last_name=request.last_name,
                            username=request.username or existing_user.username
                        )
                    )
                    
                    logger.success(
                        f"User {existing_user.user_id} role changed to {new_role.value} "
                        f"by {current_user['username']}"
                    )
                    
                    return {
                        'success': True,
                        'message': f'User admin qilindi ({new_role.value})',
                        'admin': {
                            'user_id': existing_user.user_id,
                            'username': existing_user.username,
                            'phone_number': existing_user.phone_number,
                            'role': new_role.value
                        }
                    }
            
            # 3. Yangi user yaratish
            if not request.user_id:
                raise HTTPException(
                    status_code=400,
                    detail="Yangi admin uchun user_id kerak (Telegram user ID)"
                )
            
            # Password hash
            password_hash = get_password_hash(request.password)
            
            # Role
            role = UserRole.ADMIN if request.role == "admin" else UserRole.GLAVNI_ADMIN
            
            async with transaction() as session:
                new_user = User(
                    user_id=request.user_id,
                    username=request.username,
                    phone_number=request.phone_number,
                    first_name=request.first_name,
                    last_name=request.last_name,
                    role=role,
                    is_blocked=False
                    # password_hash - hozircha User model'da yo'q, keyinroq qo'shiladi
                )
                
                session.add(new_user)
                await session.flush()
                
                logger.success(
                    f"New admin created: {request.user_id} ({role.value}) "
                    f"by {current_user['username']}"
                )
                
                return {
                    'success': True,
                    'message': f'Yangi admin yaratildi ({role.value})',
                    'admin': {
                        'user_id': new_user.user_id,
                        'username': new_user.username,
                        'phone_number': new_user.phone_number,
                        'role': role.value
                    }
                }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to create admin: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# DELETE ADMIN
# ============================================

@router.delete("/{user_id}")
async def delete_admin(
    user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Admin'ni o'chirish (role'ni passenger yoki driver'ga o'zgartirish)
    
    DIQQAT: 
    - Faqat Glavni Admin o'chira oladi
    - O'zini o'chira olmaydi
    - Glavni Admin'ni o'chira olmaydi
    """
    check_glavni_admin(current_user)
    
    # O'zini o'chira olmaydi
    if user_id == current_user['user_id']:
        raise HTTPException(
            status_code=400,
            detail="O'zingizni o'chira olmaysiz"
        )
    
    try:
        async with get_session() as session:
            user = await session.get(User, user_id)
            
            if not user:
                raise HTTPException(
                    status_code=404,
                    detail="User topilmadi"
                )
            
            # Glavni Admin'ni o'chira olmaydi
            if user.role == UserRole.GLAVNI_ADMIN:
                raise HTTPException(
                    status_code=403,
                    detail="Glavni Admin'ni o'chira olmaysiz"
                )
            
            # Role'ni passenger'ga o'zgartirish
            async with transaction() as session:
                await session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(role=UserRole.PASSENGER)
                )
                
                logger.info(
                    f"Admin {user_id} removed by {current_user['username']}"
                )
                
                return {
                    'success': True,
                    'message': 'Admin o\'chirildi'
                }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to delete admin: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ['router']
