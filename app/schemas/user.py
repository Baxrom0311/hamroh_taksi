"""
app/schemas/user.py

USER PYDANTIC SCHEMAS

BU FAYL NIMA QILADI:
- User ma'lumotlari uchun Pydantic models
- Request/Response validation
- API endpoints uchun data serialization

ISHLATISH:
    from app.schemas.user import UserResponse, UserCreate
    
    user = UserResponse(
        user_id=123,
        phone_number="+998901234567",
        first_name="Ali"
    )
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


# ============================================
# ENUMS
# ============================================

class UserRoleEnum(str, Enum):
    """User rollari"""
    GLAVNI_ADMIN = "glavni_admin"
    ADMIN = "admin"
    DRIVER = "driver"
    PASSENGER = "passenger"


# ============================================
# BASE SCHEMAS
# ============================================

class UserBase(BaseModel):
    """User base schema (umumiy maydonlar)"""
    
    phone_number: str = Field(
        ...,
        description="Telefon raqam"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "phone_number": "+998901234567"
            }
        }
    )
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Ism"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "Ali"
            }
        }
    )
    last_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Familiya",
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "last_name": "Valiyev"
            }
        }
    )
    username: Optional[str] = Field(
        None,
        max_length=255,
        description="Telegram username",
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "@bakhromdev"
            }
        }
    )
    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Telefon raqam validatsiya"""
        from app.utils.validators import validate_phone
        
        is_valid, formatted = validate_phone(v)
        
        if not is_valid or formatted is None:
            raise ValueError('Noto\'g\'ri telefon format')
        
        return formatted


# ============================================
# CREATE SCHEMAS
# ============================================

class UserCreate(UserBase):
    """User yaratish uchun schema"""
    
    user_id: int = Field(
        ...,
        description="Telegram user ID",
    )
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 123456789,
            }
        }
    )
    role: UserRoleEnum = Field(
        default=UserRoleEnum.PASSENGER,
        description="Foydalanuvchi roli"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 123456789,
                "phone_number": "+998935580311",
                "first_name": "Ali",
                "last_name": "Valiyev",
                "username": "@bakhromdev",
                "role": "passenger"
            }
        }
    )


# ============================================
# UPDATE SCHEMAS
# ============================================

class UserUpdate(BaseModel):
    """User yangilash uchun schema"""
    
    first_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255
    )
    
    last_name: Optional[str] = Field(
        None,
        max_length=255
    )
    
    username: Optional[str] = Field(
        None,
        max_length=255
    )
    
    is_blocked: Optional[bool] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "Alisher",
                "last_name": "Karimov",
                "is_blocked": False
            }
        }
    )


# ============================================
# RESPONSE SCHEMAS
# ============================================

class UserResponse(UserBase):
    """User response schema"""
    
    user_id: int
    role: UserRoleEnum
    is_blocked: bool
    registration_date: datetime
    last_active: Optional[datetime] = None
    
    model_config = ConfigDict(
        from_attributes=True,  # ORM mode
        json_schema_extra={
            "example": {
                "user_id": 123456789,
                "phone_number": "+998901234567",
                "first_name": "Ali",
                "last_name": "Valiyev",
                "username": "@alidev",
                "role": "passenger",
                "is_blocked": False,
                "registration_date": "2025-01-01T12:00:00",
                "last_active": "2025-01-03T15:30:00"
            }
        }
    )


class UserShortResponse(BaseModel):
    """User qisqa response (list'lar uchun)"""
    
    user_id: int
    full_name: str
    phone_number: str
    role: UserRoleEnum
    is_blocked: bool
    
    model_config = ConfigDict(
        from_attributes=True
    )


# ============================================
# LOGIN SCHEMAS
# ============================================

class LoginRequest(BaseModel):
    """Login request schema"""
    
    phone_number: str = Field(
        ...,
        description="Telefon raqam"
    )
    
    sms_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="SMS kod (6 raqam)"
    )
    
    @field_validator('sms_code')
    @classmethod
    def validate_code(cls, v: str) -> str:
        """SMS kod faqat raqamlardan"""
        if not v.isdigit():
            raise ValueError('SMS kod faqat raqamlardan iborat bo\'lishi kerak')
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "phone_number": "+998901234567",
                "sms_code": "123456"
            }
        }
    )


class LoginResponse(BaseModel):
    """Login response schema"""
    
    success: bool
    user: Optional[UserResponse] = None
    is_new_user: bool = False
    session_token: Optional[str] = None
    message: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "user": {
                    "user_id": 123456789,
                    "phone_number": "+998901234567",
                    "first_name": "Ali",
                    "role": "passenger",
                    "is_blocked": False,
                    "registration_date": "2025-01-01T12:00:00"
                },
                "is_new_user": False,
                "session_token": "abc123...",
                "message": "Xush kelibsiz!"
            }
        }
    )


# ============================================
# SMS SCHEMAS
# ============================================

class SMSRequest(BaseModel):
    """SMS kod so'rash"""
    
    phone_number: str = Field(
        ...,
        description="Telefon raqam"
    )
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        from app.utils.validators import validate_phone
        
        is_valid, formatted = validate_phone(v)
        if not is_valid or formatted is None:
            raise ValueError('Noto\'g\'ri telefon format')
        
        return formatted


class SMSResponse(BaseModel):
    """SMS yuborish javobi"""
    
    success: bool
    message: str
    phone: Optional[str] = None
    retry_after: Optional[int] = None  # seconds
    remaining_today: Optional[int] = None


# ============================================
# BLOCK/UNBLOCK SCHEMAS
# ============================================

class BlockUserRequest(BaseModel):
    """User bloklash"""
    
    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Bloklash sababi"
    )
    
    duration_hours: Optional[int] = Field(
        None,
        ge=1,
        le=720,  # Maksimal 30 kun
        description="Necha soatga (None = doimiy)"
    )


class BlockUserResponse(BaseModel):
    """Bloklash javobi"""
    
    success: bool
    message: str
    blocked_until: Optional[datetime] = None


# ============================================
# STATISTICS SCHEMAS
# ============================================

class UserStatsResponse(BaseModel):
    """User statistikasi"""
    
    total_users: int
    total_drivers: int
    total_passengers: int
    total_admins: int
    blocked_users: int
    active_today: int
    new_users_this_week: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_users": 1000,
                "total_drivers": 150,
                "total_passengers": 840,
                "total_admins": 10,
                "blocked_users": 5,
                "active_today": 250,
                "new_users_this_week": 45
            }
        }
    )


__all__ = [
    'UserRoleEnum',
    'UserBase',
    'UserCreate',
    'UserUpdate',
    'UserResponse',
    'UserShortResponse',
    'LoginRequest',
    'LoginResponse',
    'SMSRequest',
    'SMSResponse',
    'BlockUserRequest',
    'BlockUserResponse',
    'UserStatsResponse'
]