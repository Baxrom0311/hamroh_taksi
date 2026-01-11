"""
app/schemas/order.py

ORDER PYDANTIC SCHEMAS

BU FAYL NIMA QILADI:
- Order (buyurtma) ma'lumotlari uchun Pydantic models
- Request/Response validation
- API endpoints uchun data serialization

ISHLATISH:
    from app.schemas.order import OrderResponse, OrderCreate
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ============================================
# ENUMS
# ============================================

class OrderStatusEnum(str, Enum):
    """Order statuslari"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ============================================
# BASE SCHEMAS
# ============================================

class OrderBase(BaseModel):
    """Order base schema"""
    
    route_id: int = Field(
        ...,
        description="Marshrut ID"
    )
    
    pickup_location: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Olish joyi (matn)"
    )
    
    pickup_lat: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Pickup latitude"
    )
    
    pickup_lon: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Pickup longitude"
    )
    
    passenger_count: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Yo'lovchilar soni"
    )
    
    has_luggage: bool = Field(
        default=False,
        description="Pochta bormi"
    )
    
    luggage_count: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Pochta soni"
    )
    
    luggage_description: Optional[str] = Field(
        None,
        max_length=500,
        description="Pochta tavsifi"
    )


# ============================================
# CREATE SCHEMAS
# ============================================

class OrderCreate(OrderBase):
    """Order yaratish"""
    
    passenger_id: int = Field(
        ...,
        description="Yo'lovchi ID"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "passenger_id": 1,
                "route_id": 1,
                "pickup_location": "Gurlan bozori yonida, 5-uy",
                "pickup_lat": 41.311512,
                "pickup_lon": 69.249512,
                "passenger_count": 2,
                "has_luggage": True,
                "luggage_count": 1,
                "luggage_description": "Kichik sumka"
            }
        }
    )


# ============================================
# UPDATE SCHEMAS
# ============================================

class OrderStatusUpdate(BaseModel):
    """Order statusini yangilash"""
    
    status: OrderStatusEnum = Field(
        ...,
        description="Yangi status"
    )
    
    cancellation_reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Bekor qilish sababi (agar cancelled bo'lsa)"
    )


class OrderAcceptRequest(BaseModel):
    """Order qabul qilish"""
    
    driver_id: int = Field(
        ...,
        description="Driver ID"
    )


# ============================================
# RESPONSE SCHEMAS
# ============================================

class OrderResponse(OrderBase):
    """Order full response"""
    
    order_id: int
    passenger_id: int
    driver_id: Optional[int] = None
    status: OrderStatusEnum
    commission_amount: Optional[Decimal] = None
    created_at: datetime
    accepted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    auto_confirmed: bool = False
    driver_arrived: bool = False
    
    # Computed fields
    duration_minutes: Optional[int] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "order_id": 123,
                "passenger_id": 1,
                "driver_id": 5,
                "route_id": 1,
                "pickup_location": "Gurlan bozori yonida",
                "pickup_lat": 41.311512,
                "pickup_lon": 69.249512,
                "passenger_count": 2,
                "has_luggage": False,
                "status": "in_progress",
                "commission_amount": 5000,
                "created_at": "2025-01-03T10:00:00",
                "accepted_at": "2025-01-03T10:02:00",
                "started_at": "2025-01-03T10:15:00"
            }
        }
    )


class OrderShortResponse(BaseModel):
    """Order qisqa response (list'lar uchun)"""
    
    order_id: int
    passenger_id: int
    driver_id: Optional[int] = None
    route_id: int
    status: OrderStatusEnum
    passenger_count: int
    created_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True
    )


class OrderListResponse(BaseModel):
    """Order list response"""
    
    total: int
    page: int
    page_size: int
    orders: list[OrderShortResponse]


class OrderWithDetailsResponse(OrderResponse):
    """Order with passenger and driver details"""
    
    passenger_name: Optional[str] = None
    passenger_phone: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    driver_car: Optional[str] = None
    route_name: Optional[str] = None


# ============================================
# TRIP CONFIRMATION SCHEMAS
# ============================================

class TripConfirmationRequest(BaseModel):
    """Safar tasdiqlash (yo'lovchi tomonidan)"""
    
    order_id: int
    confirmed: bool = Field(
        ...,
        description="True = tasdiqladi, False = rad etdi"
    )
    
    rejection_reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Rad etish sababi (agar confirmed=False)"
    )


class DriverArrivedRequest(BaseModel):
    """Haydovchi yetib keldi"""
    
    order_id: int
    latitude: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Hozirgi latitude"
    )
    longitude: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Hozirgi longitude"
    )


# ============================================
# STATISTICS SCHEMAS
# ============================================

class OrderStatsResponse(BaseModel):
    """Order statistikasi"""
    
    total_orders: int
    pending_orders: int
    active_orders: int
    completed_orders: int
    cancelled_orders: int
    total_revenue: Decimal
    average_commission: Decimal
    orders_today: int
    orders_this_week: int
    orders_this_month: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_orders": 1500,
                "pending_orders": 5,
                "active_orders": 12,
                "completed_orders": 1450,
                "cancelled_orders": 33,
                "total_revenue": 7250000,
                "average_commission": 5000,
                "orders_today": 45,
                "orders_this_week": 280,
                "orders_this_month": 1200
            }
        }
    )


class RouteOrderStatsResponse(BaseModel):
    """Marshrut bo'yicha statistika"""
    
    route_id: int
    route_name: str
    total_orders: int
    completed_orders: int
    cancelled_orders: int
    average_wait_time_minutes: Optional[float] = None
    total_revenue: Decimal


# ============================================
# RATING SCHEMAS
# ============================================

class OrderRatingRequest(BaseModel):
    """Order reytinglash"""
    
    order_id: int
    rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Reyting (1-5)"
    )
    comment: Optional[str] = Field(
        None,
        max_length=500,
        description="Izoh (ixtiyoriy)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "order_id": 123,
                "rating": 5,
                "comment": "Juda yaxshi xizmat!"
            }
        }
    )


# ============================================
# SEARCH/FILTER SCHEMAS
# ============================================

class OrderFilterParams(BaseModel):
    """Order filtrlash parametrlari"""
    
    status: Optional[OrderStatusEnum] = None
    route_id: Optional[int] = None
    passenger_id: Optional[int] = None
    driver_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "completed",
                "route_id": 1,
                "date_from": "2025-01-01T00:00:00",
                "date_to": "2025-01-31T23:59:59",
                "page": 1,
                "page_size": 50
            }
        }
    )


__all__ = [
    'OrderStatusEnum',
    'OrderBase',
    'OrderCreate',
    'OrderStatusUpdate',
    'OrderAcceptRequest',
    'OrderResponse',
    'OrderShortResponse',
    'OrderListResponse',
    'OrderWithDetailsResponse',
    'TripConfirmationRequest',
    'DriverArrivedRequest',
    'OrderStatsResponse',
    'RouteOrderStatsResponse',
    'OrderRatingRequest',
    'OrderFilterParams'
]