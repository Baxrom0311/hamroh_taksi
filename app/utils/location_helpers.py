"""
app/utils/location_helpers.py

LOCATION HELPER FUNCTIONS

BU FAYL NIMA QILADI:
- Google Maps link yaratish
- Telegram location format
- Location xabarlarini formatlash
"""

from typing import Optional


def get_google_maps_link(lat: float, lon: float, label: Optional[str] = None) -> str:
    """
    Google Maps link yaratish
    
    Args:
        lat: Latitude
        lon: Longitude
        label: Xarita label (ixtiyoriy)
    
    Returns:
        Google Maps URL
    """
    if label:
        # Label bilan
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}&query_place_id={label}"
    else:
        # Oddiy koordinatalar
        return f"https://www.google.com/maps?q={lat},{lon}"


def get_telegram_location_link(lat: float, lon: float) -> str:
    """
    Telegram location link yaratish
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        Telegram location URL (tg://location?lat=...&lon=...)
    """
    return f"tg://location?lat={lat}&lon={lon}"


def format_location_with_links(
    location_text: str,
    lat: float,
    lon: float,
    label: Optional[str] = None
) -> str:
    """
    Lokatsiya matnini linklar bilan formatlash
    
    Args:
        location_text: Lokatsiya matni
        lat: Latitude
        lon: Longitude
        label: Label (ixtiyoriy)
    
    Returns:
        HTML formatdagi matn (Google Maps va Telegram linklari bilan)
    """
    google_link = get_google_maps_link(lat, lon, label)
    telegram_link = get_telegram_location_link(lat, lon)
    
    return f"""
{location_text}

📍 <a href="{google_link}">Google Maps'da ko'rish</a>
📍 <a href="{telegram_link}">Telegram xaritada ko'rish</a>
    """.strip()


def format_location_message(
    location_text: str,
    lat: float,
    lon: float,
    show_links: bool = True
) -> str:
    """
    Lokatsiya xabari formatlash
    
    Args:
        location_text: Lokatsiya matni
        lat: Latitude
        lon: Longitude
        show_links: Linklarni ko'rsatish
    
    Returns:
        Formatlangan xabar
    """
    if show_links:
        return format_location_with_links(location_text, lat, lon)
    else:
        return location_text
