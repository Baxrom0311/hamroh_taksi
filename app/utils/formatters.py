"""
app/utils/formatters.py

FORMATTERS - Ma'lumotlarni formatlash

BU FAYL NIMA QILADI:
- Pul formatlar (5000 → "5,000 so'm")
- Vaqt formatlar (datetime → "12:30")
- Telefon formatlar (+998901234567 → "+998 90 123 45 67")
- Text truncate (uzun matnlarni qisqartirish)

ISHLATISH:
    from app.utils.formatters import format_money, format_phone
    
    money = format_money(5000)  # "5,000 so'm"
    phone = format_phone("+998901234567")  # "+998 90 123 45 67"
"""

from typing import Optional, Union
from datetime import datetime, timedelta
from decimal import Decimal


# ============================================
# PUL FORMATLAR
# ============================================

def format_money(
    amount: Union[int, float, Decimal],
    currency: str = "so'm",
    show_currency: bool = True
) -> str:
    """
    Pul miqdorini formatlash
    
    Args:
        amount: Miqdor
        currency: Valyuta ("so'm", "USD", etc)
        show_currency: Valyutani ko'rsatish
    
    Returns:
        Formatted string
    
    MISOL:
        format_money(5000)  # "5,000 so'm"
        format_money(1234567)  # "1,234,567 so'm"
        format_money(5000, show_currency=False)  # "5,000"
    """
    
    # Decimal/float → int (agar butun bo'lsa)
    if isinstance(amount, (float, Decimal)):
        if amount == int(amount):
            amount = int(amount)
    
    # Vergul bilan formatlash
    formatted = f"{amount:,}"
    
    if show_currency:
        return f"{formatted} {currency}"
    
    return formatted


def format_money_short(amount: Union[int, float]) -> str:
    """
    Qisqa format (1000000 → "1M")
    
    MISOL:
        format_money_short(1500)  # "1.5K"
        format_money_short(1500000)  # "1.5M"
    """
    
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    else:
        return str(amount)


# ============================================
# TELEFON FORMATLAR
# ============================================

def format_phone(phone: str, style: str = "spaced") -> str:
    """
    Telefon raqamni formatlash
    
    Args:
        phone: Telefon raqam
        style: "spaced", "dashed", "plain"
    
    Returns:
        Formatted phone
    
    STYLES:
        spaced: "+998 90 123 45 67"
        dashed: "+998-90-123-45-67"
        plain: "+998901234567"
    
    MISOL:
        format_phone("+998901234567")  # "+998 90 123 45 67"
        format_phone("998901234567")  # "+998 90 123 45 67"
    """
    
    # Tozalash
    phone = phone.replace(' ', '').replace('-', '').replace('+', '')
    
    # +998 qo'shish
    if not phone.startswith('998'):
        phone = '998' + phone
    
    if style == "spaced":
        # +998 90 123 45 67
        return f"+{phone[:3]} {phone[3:5]} {phone[5:8]} {phone[8:10]} {phone[10:]}"
    
    elif style == "dashed":
        # +998-90-123-45-67
        return f"+{phone[:3]}-{phone[3:5]}-{phone[5:8]}-{phone[8:10]}-{phone[10:]}"
    
    else:  # plain
        # +998901234567
        return f"+{phone}"


def mask_phone(phone: str) -> str:
    """
    Telefon raqamni mask qilish (xavfsizlik)
    
    MISOL:
        mask_phone("+998901234567")  # "+998 ** *** ** 67"
    """
    
    formatted = format_phone(phone, style="spaced")
    parts = formatted.split()
    
    if len(parts) >= 5:
        return f"{parts[0]} ** *** ** {parts[-1]}"
    
    return formatted


# ============================================
# VAQT FORMATLAR
# ============================================

def format_datetime(
    dt: datetime,
    format: str = "full"
) -> str:
    """
    Datetime formatlash
    
    Args:
        dt: Datetime object
        format: "full", "date", "time", "short"
    
    FORMATS:
        full: "01.01.2025 12:30:45"
        date: "01.01.2025"
        time: "12:30"
        short: "01.01 12:30"
    
    MISOL:
        dt = datetime.now()
        format_datetime(dt, "full")  # "01.01.2025 12:30:45"
    """
    
    if format == "full":
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    
    elif format == "date":
        return dt.strftime("%d.%m.%Y")
    
    elif format == "time":
        return dt.strftime("%H:%M")
    
    elif format == "short":
        return dt.strftime("%d.%m %H:%M")
    
    else:
        return dt.isoformat()


def format_time_ago(dt: datetime) -> str:
    """
    "X vaqt oldin" formatda
    
    MISOL:
        format_time_ago(datetime.now() - timedelta(minutes=5))  # "5 daqiqa oldin"
        format_time_ago(datetime.now() - timedelta(hours=2))  # "2 soat oldin"
    """
    
    now = datetime.now()
    delta = now - dt
    
    seconds = int(delta.total_seconds())
    
    if seconds < 60:
        return "Hozir"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} daqiqa oldin"
    
    hours = minutes // 60
    if hours < 24:
        return f"{hours} soat oldin"
    
    days = hours // 24
    if days < 7:
        return f"{days} kun oldin"
    
    weeks = days // 7
    if weeks < 4:
        return f"{weeks} hafta oldin"
    
    months = days // 30
    if months < 12:
        return f"{months} oy oldin"
    
    years = days // 365
    return f"{years} yil oldin"


def format_duration(seconds: int) -> str:
    """
    Davomiylikni formatlash
    
    MISOL:
        format_duration(65)  # "1 daqiqa 5 soniya"
        format_duration(3665)  # "1 soat 1 daqiqa"
    """
    
    if seconds < 60:
        return f"{seconds} soniya"
    
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    
    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes} daqiqa {remaining_seconds} soniya"
        return f"{minutes} daqiqa"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes > 0:
        return f"{hours} soat {remaining_minutes} daqiqa"
    
    return f"{hours} soat"


# ============================================
# MATN FORMATLAR
# ============================================

def truncate(
    text: str,
    length: int = 50,
    suffix: str = "..."
) -> str:
    """
    Matnni qisqartirish
    
    Args:
        text: Asl matn
        length: Maksimal uzunlik
        suffix: Qo'shimcha ("...", "→", etc)
    
    MISOL:
        truncate("Bu juda uzun matn", 10)  # "Bu juda uz..."
    """
    
    if len(text) <= length:
        return text
    
    return text[:length - len(suffix)] + suffix


def escape_html(text: str) -> str:
    """
    HTML maxsus belgilarni escape qilish
    
    TELEGRAM HTML MODE UCHUN:
    - < → &lt;
    - > → &gt;
    - & → &amp;
    
    MISOL:
        escape_html("5 < 10")  # "5 &lt; 10"
    """
    
    return (
        text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def escape_markdown(text: str) -> str:
    """
    Markdown maxsus belgilarni escape qilish
    
    TELEGRAM MARKDOWN MODE UCHUN:
    """
    
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


# ============================================
# RAQAM FORMATLAR
# ============================================

def format_percent(
    value: float,
    decimals: int = 1
) -> str:
    """
    Foizni formatlash
    
    MISOL:
        format_percent(0.756)  # "75.6%"
        format_percent(0.5, decimals=0)  # "50%"
    """
    
    percent = value * 100
    return f"{percent:.{decimals}f}%"


def format_rating(rating: Union[float, Decimal]) -> str:
    """
    Reytingni formatlash
    
    MISOL:
        format_rating(4.5)  # "⭐ 4.5/5.0"
    """
    
    stars = "⭐" * int(rating)
    return f"{stars} {float(rating):.1f}/5.0"


# ============================================
# LIST FORMATLAR
# ============================================

def format_list(
    items: list,
    separator: str = ", ",
    last_separator: str = " va "
) -> str:
    """
    List'ni matn ko'rinishida formatlash
    
    MISOL:
        format_list(["Olma", "Nok", "Banan"])  # "Olma, Nok va Banan"
        format_list(["A", "B"], last_separator=" yoki ")  # "A yoki B"
    """
    
    if not items:
        return ""
    
    if len(items) == 1:
        return str(items[0])
    
    if len(items) == 2:
        return f"{items[0]}{last_separator}{items[1]}"
    
    return separator.join(str(i) for i in items[:-1]) + last_separator + str(items[-1])


# ============================================
# USER INFO FORMAT
# ============================================

def format_user_mention(
    user_id: int,
    first_name: str,
    last_name: Optional[str] = None,
    username: Optional[str] = None
) -> str:
    """
    User mention formatlash (Telegram HTML)
    
    MISOL:
        format_user_mention(123, "Ali", "Valiyev")
        # '<a href="tg://user?id=123">Ali Valiyev</a>'
    """
    
    full_name = first_name
    if last_name:
        full_name += f" {last_name}"
    
    if username:
        return f'<a href="https://t.me/{username}">{full_name}</a>'
    else:
        return f'<a href="tg://user?id={user_id}">{full_name}</a>'


# ============================================
# FILE SIZE FORMAT
# ============================================

def format_file_size(bytes: int) -> str:
    """
    Fayl hajmini formatlash
    
    MISOL:
        format_file_size(1024)  # "1.0 KB"
        format_file_size(1048576)  # "1.0 MB"
    """
    
    if bytes < 1024:
        return f"{bytes} B"
    
    kb = bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    
    gb = mb / 1024
    return f"{gb:.1f} GB"


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.utils.formatters
    """
    
    print("\n🧪 Testing Formatters...\n")
    
    # Test 1: Money
    print("📝 Test 1: Money formatting")
    print(f"   {format_money(5000)}")
    print(f"   {format_money(1234567)}")
    print(f"   {format_money_short(1500000)}")
    
    print()
    
    # Test 2: Phone
    print("📝 Test 2: Phone formatting")
    print(f"   {format_phone('+998901234567')}")
    print(f"   {format_phone('998901234567', style='dashed')}")
    print(f"   {mask_phone('+998901234567')}")
    
    print()
    
    # Test 3: DateTime
    print("📝 Test 3: DateTime formatting")
    now = datetime.now()
    print(f"   Full: {format_datetime(now, 'full')}")
    print(f"   Date: {format_datetime(now, 'date')}")
    print(f"   Time: {format_datetime(now, 'time')}")
    
    print()
    
    # Test 4: Time ago
    print("📝 Test 4: Time ago")
    past = datetime.now() - timedelta(minutes=30)
    print(f"   {format_time_ago(past)}")
    
    print()
    
    # Test 5: Duration
    print("📝 Test 5: Duration")
    print(f"   {format_duration(65)}")
    print(f"   {format_duration(3665)}")
    
    print()
    
    # Test 6: Text
    print("📝 Test 6: Text formatting")
    print(f"   {truncate('Bu juda uzun matn ekan', 15)}")
    print(f"   {escape_html('5 < 10 & 10 > 5')}")
    
    print()
    
    # Test 7: List
    print("📝 Test 7: List formatting")
    print(f"   {format_list(['Olma', 'Nok', 'Banan'])}")
    
    print("\n✅ All formatter tests passed!\n")


__all__ = [
    'format_money',
    'format_money_short',
    'format_phone',
    'mask_phone',
    'format_datetime',
    'format_time_ago',
    'format_duration',
    'truncate',
    'escape_html',
    'escape_markdown',
    'format_percent',
    'format_rating',
    'format_list',
    'format_user_mention',
    'format_file_size'
]