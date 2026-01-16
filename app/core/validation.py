"""
app/core/validation.py

INPUT VALIDATION - Barcha kiruvchi ma'lumotlarni tekshirish

VALIDATIONS:
- Phone number (UZ format)
- Full name
- Car number
- Location coordinates
- Age, passenger count
"""

import re
from typing import Optional, Tuple
from decimal import Decimal


class ValidationError(Exception):
    """Custom validation error"""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_phone_number(phone: str) -> Tuple[bool, Optional[str]]:
    """
    Telefon raqamni tekshirish (O'zbekiston)
    
    FORMAT: +998XXXXXXXXX (13 ta belgi)
    
    Returns:
        (is_valid, error_message)
    
    Examples:
        +998901234567 ✅
        +998 90 123 45 67 ✅ (probel bilan)
        998901234567 ❌ (+ yo'q)
        +998801234567 ❌ (80 noto'g'ri operator)
    """
    if not phone:
        return False, "Telefon raqam bo'sh"
    
    # Probellarni olib tashlash
    phone_clean = phone.replace(" ", "").replace("-", "")
    
    # Format tekshirish - ✅ 20 (Beeline) qo'shildi
    pattern = r'^\+998(9[0-9]|8[8]|7[1]|3[3]|5[0]|6[6]|2[0])\d{7}$'
    
    if not re.match(pattern, phone_clean):
        return False, (
            "❌ Noto'g'ri format!\n\n"
            "✅ To'g'ri: +998901234567\n"
            "Operator kodlari: 90, 91, 93, 94, 95, 97, 98, 99, 88, 71, 33, 50, 66, 20"
        )
    
    return True, None


def validate_full_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    To'liq ismni tekshirish
    
    QOIDALAR:
    - Kamida 2 ta so'z
    - Faqat harflar va probel
    - 3-50 belgi
    
    Examples:
        "Alisher Karimov" ✅
        "Alisher" ❌ (1 ta so'z)
        "123 Test" ❌ (raqam bor)
    """
    if not name or not name.strip():
        return False, "Ism bo'sh"
    
    name = name.strip()
    
    # Uzunlik
    if len(name) < 3:
        return False, "Ism juda qisqa (kamida 3 ta harf)"
    
    if len(name) > 50:
        return False, "Ism juda uzun (maksimal 50 ta harf)"
    
    # Faqat harflar va probel
    if not re.match(r"^[a-zA-Zа-яА-ЯўғҚқҲҳ'\s-]+$", name):
        return False, "Ismda faqat harflar bo'lishi kerak"
    
    # Kamida 2 ta so'z
    words = name.split()
    if len(words) < 2:
        return False, "To'liq ism va familiya kiriting (masalan: Alisher Karimov)"
    
    return True, None


def validate_car_number(car_number: str) -> Tuple[bool, Optional[str]]:
    """
    Mashina raqamini tekshirish (O'zbekiston)
    
    FORMAT: 01 A 123 BC
    
    Examples:
        "01 A 123 BC" ✅
        "01A123BC" ✅
        "01 123 ABC" ❌
    """
    if not car_number:
        return False, "Mashina raqami bo'sh"
    
    # Probellarni olib tashlash
    car_clean = car_number.replace(" ", "").upper()
    
    # Format: 01A123BC
    pattern = r'^\d{2}[A-Z]\d{3}[A-Z]{2}$'
    
    if not re.match(pattern, car_clean):
        return False, (
            "❌ Noto'g'ri format!\n\n"
            "✅ To'g'ri: 01 A 123 BC"
        )
    
    return True, None


def validate_coordinates(lat: float, lon: float) -> Tuple[bool, Optional[str]]:
    """
    Koordinatalarni tekshirish
    
    O'zbekiston:
    - Latitude: 37°-46°
    - Longitude: 56°-73°
    """
    if not (37 <= lat <= 46):
        return False, f"Noto'g'ri latitude: {lat} (37-46 orasida bo'lishi kerak)"
    
    if not (56 <= lon <= 73):
        return False, f"Noto'g'ri longitude: {lon} (56-73 orasida bo'lishi kerak)"
    
    return True, None


def validate_age(age: int) -> Tuple[bool, Optional[str]]:
    """
    Yoshni tekshirish
    
    QOIDALAR:
    - 18-80 yosh
    """
    if age < 18:
        return False, "Yosh 18 dan kichik bo'lishi mumkin emas"
    
    if age > 80:
        return False, "Yosh 80 dan katta bo'lishi mumkin emas"
    
    return True, None


def validate_passenger_count(count: int) -> Tuple[bool, Optional[str]]:
    """
    Yo'lovchilar sonini tekshirish
    
    QOIDALAR:
    - 1-4 kishi
    """
    if count < 1:
        return False, "Kamida 1 yo'lovchi bo'lishi kerak"
    
    if count > 4:
        return False, "Maksimal 4 yo'lovchi"
    
    return True, None


def validate_balance_amount(amount: Decimal) -> Tuple[bool, Optional[str]]:
    """
    Balans miqdorini tekshirish
    
    QOIDALAR:
    - Musbat son
    - Maksimal 10,000,000 so'm
    """
    if amount <= 0:
        return False, "Miqdor musbat bo'lishi kerak"
    
    if amount > Decimal('10000000'):
        return False, "Maksimal miqdor: 10,000,000 so'm"
    
    return True, None


def sanitize_text(text: str, max_length: int = 500) -> str:
    """
    Matnni tozalash
    
    - HTML teglarini olib tashlash
    - SQL injection oldini olish
    - XSS protection
    """
    if not text:
        return ""
    
    # HTML teglarni olib tashlash
    text = re.sub(r'<[^>]+>', '', text)
    
    # SQL keywords (paranoid mode)
    dangerous_words = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'SELECT', 'UNION', '--', ';']
    for word in dangerous_words:
        text = text.replace(word, '')
    
    # Maksimal uzunlik
    if len(text) > max_length:
        text = text[:max_length]
    
    return text.strip()


__all__ = [
    'ValidationError',
    'validate_phone_number',
    'validate_full_name',
    'validate_car_number',
    'validate_coordinates',
    'validate_age',
    'validate_passenger_count',
    'validate_balance_amount',
    'sanitize_text'
]
