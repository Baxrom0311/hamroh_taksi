from .user import User, UserRole
from .driver import Driver
from .passenger import Passenger
from .route import Route
from .order import Order, OrderStatus
from .trip import Trip, TripStatus  # ✅ Yangi
from .transaction import Transaction, TransactionLog
from .system_settings import SystemSettings

# Barcha modellarni bitta ro'yxatga yig'ish
__all__ = [
    "User", "UserRole", 
    "Driver", 
    "Passenger", 
    "Route", 
    "Order", "OrderStatus",
    "Trip", "TripStatus",  # ✅ Yangi
    "Transaction", "TransactionLog",
    "SystemSettings"
]