"""
app/schemas/driver.py

DRIVER PYDANTIC SCHEMAS

BU FAYL NIMA QILADI:
- Driver ma'lumotlari uchun Pydantic models
- Request/Response validation
- API endpoints uchun data serialization

ISHLATISH:
    from app.schemas.driver import DriverResponse, DriverCreate
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Tuple
from datetime import datetime
from decimal import Decimal


# ============================================
# BASE SCHEMAS
# ============================================

class DriverBase(BaseModel):
    """Driver base schema"""
    
    full_name: str = Field( ..., min_length=2, max_length=255, description="To'liq ism" )
    car_model: str = Field( ..., min_length=2, max_length=100, description="Mashina markasi")
    car_color: str = Field( ..., min_length=2, max_length=50, description="Mashina rangi")
    car_number: str = Field( ..., description="Mashina raqami")
    license_number: Optional[str] = Field( None, max_length=50, description="Haydovchilik guvohnomasi")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Alisher Karimov",
                "car_model": "Chevrolet Cobalt",
                "car_color": "Oq",
                "car_number": "01 A 123 BC",
                "license_number": "AA1234567"
            }
        }
    )

    @field_validator('car_number')
    @classmethod
    def validate_car_number(cls, v: str) -> str:
        """Mashina raqami validatsiya"""
        from app.utils.validators import validate_car_number
        
        is_valid, formatted = validate_car_number(v)
        
        if not is_valid or formatted is None:
            raise ValueError('Noto\'g\'ri mashina raqami format')
        
        return formatted


# ============================================
# CREATE SCHEMAS
# ============================================

class DriverCreate(DriverBase):
    """Driver yaratish"""
    
    user_id: int = Field(
        ...,
        description="User ID (Telegram)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 123456789,
                "full_name": "Alisher Karimov",
                "car_model": "Chevrolet Cobalt",
                "car_color": "Oq",
                "car_number": "01 A 123 BC",
                "license_number": "AA1234567"
            }
        }
    )


# ============================================
# UPDATE SCHEMAS
# ============================================

class DriverUpdate(BaseModel):
    """Driver yangilash"""
    
    full_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=255
    )
    
    car_model: Optional[str] = None
    car_color: Optional[str] = None
    car_number: Optional[str] = None
    license_number: Optional[str] = None
    
    @field_validator('car_number')
    @classmethod
    def validate_car_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        from app.utils.validators import validate_car_number
        is_valid, formatted = validate_car_number(v)
        
        if not is_valid:
            raise ValueError('Noto\'g\'ri mashina raqami format')
        
        return formatted


class DriverStatusUpdate(BaseModel):
    """Driver status yangilash"""
    
    is_active: Optional[bool] = None
    is_on_trip: Optional[bool] = None
    current_route_id: Optional[int] = None
    available_seats: Optional[int] = Field(
        None,
        ge=0,
        le=8
    )


class DriverLocationUpdate(BaseModel):
    """Driver lokatsiyasini yangilash"""
    
    latitude: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitude"
    )
    
    longitude: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitude"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "latitude": 41.311512,
                "longitude": 69.249512
            }
        }
    )


# ============================================
# RESPONSE SCHEMAS
# ============================================

class DriverResponse(DriverBase):
    """Driver full response"""
    
    driver_id: int
    user_id: int
    balance: Decimal
    total_trips: int
    rating: Decimal
    ban_count_today: int
    total_ban_count: int
    is_active: bool
    is_on_trip: bool
    is_blocked: bool
    blocked_until: Optional[datetime] = None
    block_reason: Optional[str] = None
    current_route_id: Optional[int] = None
    available_seats: int
    last_location_lat: Optional[Decimal] = None
    last_location_lon: Optional[Decimal] = None
    created_at: datetime
    last_trip_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "driver_id": 1,
                "user_id": 123456789,
                "full_name": "Alisher Karimov",
                "car_model": "Chevrolet Cobalt",
                "car_color": "Oq",
                "car_number": "01 A 123 BC",
                "balance": 50000,
                "total_trips": 25,
                "rating": 4.8,
                "is_active": True,
                "is_on_trip": False,
                "is_blocked": False,
                "available_seats": 3,
                "created_at": "2025-01-01T12:00:00"
            }
        }
    )


class DriverShortResponse(BaseModel):
    """Driver qisqa response (list'lar uchun)"""
    
    driver_id: int
    full_name: str
    car_model: str
    car_number: str
    rating: Decimal
    total_trips: int
    is_active: bool
    is_blocked: bool
    
    model_config = ConfigDict(
        from_attributes=True
    )


class DriverListResponse(BaseModel):
    """Driver list response"""
    
    total: int
    page: int
    page_size: int
    drivers: list[DriverShortResponse]


# ============================================
# BALANCE SCHEMAS
# ============================================

class BalanceTopupRequest(BaseModel):
    """Balans to'ldirish so'rovi"""
    
    amount: int = Field(
        ...,
        ge=10000,
        le=10000000,
        description="Miqdor (10,000 - 10,000,000)"
    )
    
    receipt_file_id: str = Field(
        ...,
        description="Chek file ID (Telegram)"
    )
    
    description: Optional[str] = Field(
        None,
        max_length=500
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 50000,
                "receipt_file_id": "AgACAgIAAxkBAAI...",
                "description": "Balans to'ldirish"
            }
        }
    )


class BalanceResponse(BaseModel):
    """Balans ma'lumoti"""
    
    driver_id: int
    current_balance: Decimal
    total_deposits: Decimal
    total_commissions: Decimal
    pending_transactions: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "driver_id": 1,
                "current_balance": 50000,
                "total_deposits": 200000,
                "total_commissions": 150000,
                "pending_transactions": 1
            }
        }
    )


# ============================================
# STATISTICS SCHEMAS
# ============================================

class DriverStatsResponse(BaseModel):
    """Driver statistikasi"""
    
    driver_id: int
    total_trips: int
    total_earnings: Decimal
    total_commissions: Decimal
    average_rating: Decimal
    trips_this_week: int
    trips_this_month: int
    best_route: Optional[str] = None
    total_distance_km: Optional[Decimal] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "driver_id": 1,
                "total_trips": 150,
                "total_earnings": 1500000,
                "total_commissions": 750000,
                "average_rating": 4.8,
                "trips_this_week": 12,
                "trips_this_month": 45,
                "best_route": "Gurlan → Vazir",
                "total_distance_km": 7500
            }
        }
    )


class DriverQueueInfoResponse(BaseModel):
    """Driver navbat ma'lumoti"""
    
    driver_id: int
    route_id: int
    priority_score: float
    queue_position: int
    waiting_time_hours: float
    estimated_wait_time: Optional[str] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "driver_id": 1,
                "route_id": 1,
                "priority_score": 85.5,
                "queue_position": 3,
                "waiting_time_hours": 2.5,
                "estimated_wait_time": "15-20 daqiqa"
            }
        }
    )


# ============================================
# BLOCK SCHEMAS
# ============================================

class BlockDriverRequest(BaseModel):
    """Driver bloklash"""
    
    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Bloklash sababi"
    )
    
    duration_hours: int = Field(
        ...,
        ge=1,
        le=720,
        description="Necha soatga (1-720)"
    )


class UnblockDriverRequest(BaseModel):
    """Driver blokdan ochish"""
    
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Ochish sababi"
    )


__all__ = [
    'DriverBase',
    'DriverCreate',
    'DriverUpdate',
    'DriverStatusUpdate',
    'DriverLocationUpdate',
    'DriverResponse',
    'DriverShortResponse',
    'DriverListResponse',
    'BalanceTopupRequest',
    'BalanceResponse',
    'DriverStatsResponse',
    'DriverQueueInfoResponse',
    'BlockDriverRequest',
    'UnblockDriverRequest'
]