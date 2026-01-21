"""
app/utils/validators.py

VALIDATORS - Ma'lumotlarni tekshirish

BU FAYL NIMA QILADI:
- Telefon raqam validatsiya
- Mashina raqami validatsiya
- Email validatsiya
- Password strength check
- Input sanitization

ISHLATISH:
    from app.utils.validators import validate_phone, validate_car_number
    
    is_valid = validate_phone("+998901234567")
    car_number = validate_car_number("01 A 123 BC")
"""

import re
from typing import Optional, Tuple


# ============================================
# TELEFON VALIDATSIYA
# ============================================

def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    """
    O'zbekiston telefon raqamini validatsiya qilish
    
    Args:
        phone: Telefon raqam (turli formatda)
    
    Returns:
        (is_valid: bool, formatted_phone: str | None)
    
    QABUL QILINADIGAN FORMATLAR:
        - +998901234567
        - 998901234567
        - 901234567
        - +998 90 123 45 67
        - 90-123-45-67
    
    MISOL:
        is_valid, formatted = validate_phone("+998 90 123 45 67")
        # (True, "+998901234567")
    """
    
    # Bo'sh joylarni olib tashlash
    phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    # + ni olib tashlash
    if phone.startswith('+'):
        phone = phone[1:]
    
    # 998 qo'shish (agar faqat 9 raqam bo'lsa)
    if len(phone) == 9 and phone.startswith(('90', '91', '93', '94', '95', '97', '98', '99', '20', '87', '71')):
        phone = '998' + phone

    
    # Regex pattern
    pattern = r'^998(9[012345789]|6[125679]|7[01234569])\d{7}$'
    
    if re.match(pattern, phone):
        return (True, f'+{phone}')
    
    return (False, None)


def is_valid_uzbek_phone(phone: str) -> bool:
    """
    Telefon to'g'ri yoki yo'q (sodda versiya)
    
    MISOL:
        is_valid_uzbek_phone("+998901234567")  # True
    """
    is_valid, _ = validate_phone(phone)
    return is_valid


# ============================================
# MASHINA RAQAMI VALIDATSIYA
# ============================================

def validate_car_number(car_number: str) -> Tuple[bool, Optional[str]]:
    """
    O'zbekiston mashina raqamini validatsiya qilish
    
    Args:
        car_number: Mashina raqami
    
    Returns:
        (is_valid: bool, formatted_number: str | None)
    
    O'ZBEKISTON FORMATLAR:
        - 01 A 123 BC
        - 75 X 777 XX
        - 10 K 001 AA
    
    PATTERN:
        [Viloyat: 2 raqam] [Seriya: 1 harf] [Raqam: 3 raqam] [Kod: 2 harf]
    
    MISOL:
        is_valid, formatted = validate_car_number("01A123BC")
        # (True, "01 A 123 BC")
        
        is_valid, formatted = validate_car_number("01 A 123 BC")
        # (True, "01 A 123 BC")
    """
    
    # Tozalash
    car_number = car_number.upper().replace(' ', '').replace('-', '')
    
    # Pattern: 01A123BC
    pattern = r'^(\d{2})([A-Z])(\d{3})([A-Z]{2})$'
    
    match = re.match(pattern, car_number)
    
    if match:
        region, letter, number, code = match.groups()
        formatted = f"{region} {letter} {number} {code}"
        return (True, formatted)
    
    return (False, None)


def is_valid_car_number(car_number: str) -> bool:
    """
    Mashina raqami to'g'ri yoki yo'q
    
    MISOL:
        is_valid_car_number("01 A 123 BC")  # True
    """
    is_valid, _ = validate_car_number(car_number)
    return is_valid


# ============================================
# MASHINA MODELI VALIDATSIYA
# ============================================

VALID_CAR_MODELS = [
    "Nexia", "Nexia 3", "Gentra", "Lacetti", "Spark",
    "Cobalt", "Malibu", "Captiva", "Tracker",
    "Damas", "Labo", "Matiz",
    "Toyota Camry", "Toyota Corolla", "Honda Accord",
    "Mercedes", "BMW", "Audi",
    "Hyundai Accent", "Hyundai Elantra",
    "Kia Rio", "Kia Sportage",
    "Other"  # Boshqa
]


def validate_car_model(model: str) -> bool:
    """
    Mashina modeli to'g'ri yoki yo'q
    
    MISOL:
        validate_car_model("Cobalt")  # True
        validate_car_model("Invalid")  # False
    """
    
    return model in VALID_CAR_MODELS


def get_car_model_suggestions(query: str) -> list:
    """
    Mashina modeli bo'yicha tavsiyalar
    
    MISOL:
        get_car_model_suggestions("cob")  # ["Cobalt"]
        get_car_model_suggestions("nex")  # ["Nexia", "Nexia 3"]
    """
    
    query_lower = query.lower()
    
    return [
        model for model in VALID_CAR_MODELS
        if query_lower in model.lower()
    ]


# ============================================
# YOSH VALIDATSIYA
# ============================================

def validate_age(age: int, min_age: int = 14, max_age: int = 100) -> Tuple[bool, Optional[str]]:
    """
    Yosh validatsiya
    
    Args:
        age: Yosh
        min_age: Minimal yosh (default: 14)
        max_age: Maksimal yosh (default: 100)
    
    Returns:
        (is_valid: bool, error_message: str | None)
    
    MISOL:
        is_valid, error = validate_age(16)  # (True, None)
        is_valid, error = validate_age(10)  # (False, "Minimal yosh 14")
    """
    
    if age < min_age:
        return (False, f"Minimal yosh {min_age}")
    
    if age > max_age:
        return (False, f"Maksimal yosh {max_age}")
    
    return (True, None)


# ============================================
# BALANS VALIDATSIYA
# ============================================

def validate_balance_amount(
    amount: int,
    min_amount: int = 10000,
    max_amount: int = 10000000
) -> Tuple[bool, Optional[str]]:
    """
    Balans miqdorini validatsiya qilish
    
    Args:
        amount: Miqdor (so'm)
        min_amount: Minimal (default: 10,000)
        max_amount: Maksimal (default: 10,000,000)
    
    Returns:
        (is_valid: bool, error_message: str | None)
    
    MISOL:
        is_valid, error = validate_balance_amount(50000)  # (True, None)
        is_valid, error = validate_balance_amount(5000)  # (False, "Minimal: 10,000")
    """
    
    if amount < min_amount:
        return (False, f"Minimal summa: {min_amount:,} so'm")
    
    if amount > max_amount:
        return (False, f"Maksimal summa: {max_amount:,} so'm")
    
    return (True, None)


# ============================================
# MATN VALIDATSIYA
# ============================================

def validate_text_length(
    text: str,
    min_length: int = 1,
    max_length: int = 1000,
    field_name: str = "Matn"
) -> Tuple[bool, Optional[str]]:
    """
    Matn uzunligini validatsiya qilish
    
    Args:
        text: Matn
        min_length: Minimal uzunlik
        max_length: Maksimal uzunlik
        field_name: Maydon nomi (xato xabari uchun)
    
    Returns:
        (is_valid: bool, error_message: str | None)
    
    MISOL:
        is_valid, error = validate_text_length("Hello", min_length=3)
        # (True, None)
    """
    
    length = len(text.strip())
    
    if length < min_length:
        return (False, f"{field_name} kamida {min_length} belgi bo'lishi kerak")
    
    if length > max_length:
        return (False, f"{field_name} maksimal {max_length} belgi bo'lishi kerak")
    
    return (True, None)


def contains_only_letters(text: str, allow_spaces: bool = True) -> bool:
    """
    Faqat harflardan iborat ekanligini tekshirish
    
    Args:
        text: Matn
        allow_spaces: Bo'sh joyga ruxsat
    
    MISOL:
        contains_only_letters("Alisher")  # True
        contains_only_letters("Alisher123")  # False
    """
    
    if allow_spaces:
        text = text.replace(' ', '')
    
    return text.isalpha()


def contains_only_digits(text: str) -> bool:
    """
    Faqat raqamlardan iborat ekanligini tekshirish
    
    MISOL:
        contains_only_digits("12345")  # True
        contains_only_digits("123abc")  # False
    """
    
    return text.isdigit()


# ============================================
# INPUT SANITIZATION
# ============================================

def sanitize_input(text: str) -> str:
    """
    Kiruvchi ma'lumotni tozalash (XSS, SQL injection oldini olish)
    
    NIMALAR OLIB TASHLANADI:
    - HTML teglar
    - SQL maxsus belgilar
    - Script teglar
    
    MISOL:
        sanitize_input("<script>alert('xss')</script>")  # "alert('xss')"
    """
    
    orig_text = text
    had_html = bool(re.search(r'<[^>]+>', orig_text))
    text = re.sub(r'<[^>]+>', '', text)
    # SQL injektsiya kalit so'zlarini olib tashlash
    text = re.sub(r'(?i)drop\s+table', '', text)
    # Comment markerlarni olib tashlash
    text = text.replace('--', '').replace('/*', '').replace('*/', '')
    # Nokas semikolonlarni bo'shliq bilan almashtirish
    text = text.replace(';', ' ')
    # Qo'shtirnoq belgilarini olib tashlash (faqat HTML bo'lmasa)
    if not had_html:
        text = text.replace("'", "").replace('"', '')
    # Bo'sh joylarni normalize qilish
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def sanitize_filename(filename: str) -> str:
    """
    Fayl nomini xavfsiz qilish
    
    XAVFLI BELGILARNI OLIB TASHLASH:
    - / \\ : * ? " < > |
    
    MISOL:
        sanitize_filename("file/name?.txt")  # "filename.txt"
    """
    
    # Xavfli belgilarni olib tashlash
    dangerous = r'[\/\\:*?"<>|]'
    filename = re.sub(dangerous, '', filename)
    
    # Bo'sh joylarni _ bilan almashtirish
    filename = filename.replace(' ', '_')
    
    return filename


# ============================================
# EMAIL VALIDATSIYA (OPTIONAL)
# ============================================

def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Email validatsiya (agar kerak bo'lsa)
    
    PATTERN:
        username@domain.extension
    
    MISOL:
        is_valid, formatted = validate_email("user@example.com")
        # (True, "user@example.com")
    """
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    email = email.strip().lower()
    
    if re.match(pattern, email):
        return (True, email)
    
    return (False, None)


# ============================================
# PASSWORD STRENGTH (OPTIONAL - Admin uchun)
# ============================================

def check_password_strength(password: str) -> Tuple[str, int]:
    """
    Parol kuchini tekshirish
    
    Returns:
        (strength: "weak" | "medium" | "strong", score: 0-100)
    
    KRITERIALAR:
    - Uzunlik (min 8)
    - Katta harf
    - Kichik harf
    - Raqamlar
    - Maxsus belgilar
    
    MISOL:
        strength, score = check_password_strength("MyPass123!")
        # ("strong", 90)
    """
    
    score = 0
    
    # Uzunlik
    if len(password) >= 8:
        score += 20
    if len(password) >= 12:
        score += 10
    
    # Katta harf
    if re.search(r'[A-Z]', password):
        score += 20
    
    # Kichik harf
    if re.search(r'[a-z]', password):
        score += 20
    
    # Raqamlar
    if re.search(r'\d', password):
        score += 15
    
    # Maxsus belgilar
    if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        score += 15
    
    # Strength
    if score < 40:
        strength = "weak"
    elif score < 70:
        strength = "medium"
    else:
        strength = "strong"
    
    return (strength, score)


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.utils.validators
    """

    print("\n🧪 Testing Validators...\n")

    # Test 1: Phone
    print("📝 Test 1: Phone validation")
    test_phones = [
        "+998901234567",
        "998901234567",
        "901234567",
        "+998 90 123 45 67",
        "invalid123"
    ]

    for phone in test_phones:
        is_valid, formatted = validate_phone(phone)
        print(f"   {phone} → Valid: {is_valid}, Formatted: {formatted}")

    print()

    # Test 2: Car number
    print("📝 Test 2: Car number validation")
    test_cars = [
        "01 A 123 BC",
        "01A123BC",
        "75X777XX",
        "invalid"
    ]

    for car in test_cars:
        is_valid, formatted = validate_car_number(car)
        print(f"   {car} → Valid: {is_valid}, Formatted: {formatted}")

    print()

    # Test 3: Age
    print("📝 Test 3: Age validation")
    test_ages = [16, 10, 25, 101]

    for age in test_ages:
        is_valid, error = validate_age(age)
        print(f"   {age} → Valid: {is_valid}, Error: {error}")

    print()

    # Test 4: Sanitization
    print("📝 Test 4: Input sanitization")
    dangerous = "<script>alert('xss')</script>Hello"
    safe = sanitize_input(dangerous)
    print(f"   Dangerous: {dangerous}")
    print(f"   Safe: {safe}")

    print("\n✅ All validator tests passed!\n")



__all__ = [
    'validate_phone',
    'is_valid_uzbek_phone',
    'validate_car_number',
    'is_valid_car_number',
    'validate_car_model',
    'get_car_model_suggestions',
    'validate_age',
    'validate_balance_amount',
    'validate_text_length',
    'contains_only_letters',
    'contains_only_digits',
    'sanitize_input',
    'sanitize_filename',
    'validate_email',
    'check_password_strength'
]
