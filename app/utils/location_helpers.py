"""
app/utils/location_helpers.py

LOCATION HELPER FUNCTIONS

BU FAYL NIMA QILADI:
- Google Maps link yaratish
- Telegram location format
- Location xabarlarini formatlash
"""

from typing import Optional


def get_google_maps_link(lat: Optional[float], lon: Optional[float], label: Optional[str] = None) -> Optional[str]:
    """
    Google Maps link yaratish
    
    Args:
        lat: Latitude (None bo'lishi mumkin)
        lon: Longitude (None bo'lishi mumkin)
        label: Xarita label (ixtiyoriy)
    
    Returns:
        Google Maps URL yoki None (agar koordinatalar bo'lmasa)
    """
    if lat is None or lon is None:
        return None  # ✅ GPS yo'q - link yo'q
    return f"https://www.google.com/maps?q={lat},{lon}"


def get_telegram_location_link(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    """
    Telegram location link yaratish
    
    Args:
        lat: Latitude (None bo'lishi mumkin)
        lon: Longitude (None bo'lishi mumkin)
    
    Returns:
        Telegram location URL yoki None
    """
    if lat is None or lon is None:
        return None  # ✅ GPS yo'q - link yo'q
    return f"tg://location?lat={lat}&lon={lon}"


def format_location_with_links(
    location_text: str,
    lat: Optional[float],
    lon: Optional[float],
    label: Optional[str] = None
) -> str:
    """
    Lokatsiya matnini linklar bilan formatlash
    
    Args:
        location_text: Lokatsiya matni
        lat: Latitude (None bo'lishi mumkin)
        lon: Longitude (None bo'lishi mumkin)
        label: Label (ixtiyoriy)
    
    Returns:
        HTML formatdagi matn (Google Maps va Telegram linklari bilan yoki linklar)
    """
    if lat is None or lon is None:
        # ✅ GPS yo'q - faqat matn
        return f"{location_text}\n\n⚠️ GPS lokatsiya yo'q - faqat matn manzil"
    
    google_link = get_google_maps_link(lat, lon, label)
    telegram_link = get_telegram_location_link(lat, lon)
    
    return f"""
{location_text}

📍 <a href="{google_link}">Google Maps'da ko'rish</a>
📍 <a href="{telegram_link}">Telegram xaritada ko'rish</a>
    """.strip()




def format_location_message(
    location_text: str,
    lat: Optional[float],
    lon: Optional[float],
    show_links: bool = True
) -> str:
    """
    Lokatsiya xabari formatlash
    
    Args:
        location_text: Lokatsiya matni
        lat: Latitude (None bo'lishi mumkin)
        lon: Longitude (None bo'lishi mumkin)
        show_links: Linklarni ko'rsatish
    
    Returns:
        Formatlangan xabar
    """
    if show_links:
        return format_location_with_links(location_text, lat, lon)
    else:
        return location_text
