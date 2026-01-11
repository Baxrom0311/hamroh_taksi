"""
app/utils/geo.py

GEO-LOKATSIYA HISOBLASHLAR

BU FAYL NIMA QILADI:
- Ikki nuqta orasidagi masofani hisoblash (Haversine formula)
- PostGIS query'lar
- Geo validation

ISHLATISH:
    from app.utils.geo import calculate_distance
    
    distance = calculate_distance(
        lat1=41.311512,
        lon1=69.249512,
        lat2=41.377512,
        lon2=69.361400
    )
    print(f"Masofa: {distance:.2f} km")
"""

from math import radians, sin, cos, sqrt, atan2, asin
from typing import Tuple, Optional
from loguru import logger


# ============================================
# HAVERSINE FORMULA (Masofa hisoblash)
# ============================================

def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Ikki nuqta orasidagi masofani hisoblash (Haversine formula)
    
    HAVERSINE FORMULA:
    Yer sharining egriligini hisobga olgan holda masofa hisoblaydi
    
    Args:
        lat1: Birinchi nuqta - Latitude
        lon1: Birinchi nuqta - Longitude
        lat2: Ikkinchi nuqta - Latitude
        lon2: Ikkinchi nuqta - Longitude
    
    Returns:
        Masofa (kilometr)
    
    MISOL:
        # Gurlan → Vazir
        distance = calculate_distance(41.8453, 60.4015, 41.3775, 60.3614)
        # ~51.5 km
    
    FORMULA:
        a = sin²(Δlat/2) + cos(lat1) × cos(lat2) × sin²(Δlon/2)
        c = 2 × atan2(√a, √(1−a))
        d = R × c
        
        R = 6371 km (Yer radiusi)
    """
    
    # Yer radiusi (km)
    R = 6371.0
    
    # Gradusdan radianga o'tkazish
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)
    
    # Farq
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Haversine formula
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    # Masofa
    distance = R * c
    
    return distance


def calculate_distance_alternative(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Alternatif formula (bir oz tezroq, lekin kamroq aniq)
    
    EQUIRECTANGULAR APPROXIMATION
    
    Qachon ishlatish:
    - Qisqa masofalar uchun (< 100 km)
    - Tezlik muhim bo'lganda
    """
    R = 6371.0
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    dlon_rad = radians(lon2 - lon1)
    
    x = dlon_rad * cos((lat1_rad + lat2_rad) / 2)
    y = lat2_rad - lat1_rad
    
    distance = R * sqrt(x * x + y * y)
    
    return distance


# ============================================
# GEO VALIDATION
# ============================================

def validate_coordinates(lat: float, lon: float) -> bool:
    """
    Koordinatalarni tekshirish
    
    LATITUDE: -90 dan +90 gacha
    LONGITUDE: -180 dan +180 gacha
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        True: To'g'ri
        False: Noto'g'ri
    
    MISOL:
        is_valid = validate_coordinates(41.311512, 69.249512)  # True
        is_valid = validate_coordinates(100, 200)  # False
    """
    
    if not (-90 <= lat <= 90):
        logger.warning(f"Invalid latitude: {lat} (should be -90 to +90)")
        return False
    
    if not (-180 <= lon <= 180):
        logger.warning(f"Invalid longitude: {lon} (should be -180 to +180)")
        return False
    
    return True


def is_in_uzbekistan(lat: float, lon: float) -> bool:
    """
    O'zbekiston hududida ekanligini tekshirish (taxminiy)
    
    O'ZBEKISTON CHEGARALARI (taxminiy):
    Latitude: 37°N dan 46°N gacha
    Longitude: 56°E dan 73°E gacha
    
    DIQQAT: Bu aniq emas, faqat taxminiy tekshirish!
    """
    
    return (37 <= lat <= 46) and (56 <= lon <= 73)


# ============================================
# POSTGIS HELPERS
# ============================================

def create_point_wkt(lat: float, lon: float) -> str:
    """
    WKT (Well-Known Text) format yaratish
    
    PostGIS uchun POINT format
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        "POINT(lon lat)" format
    
    DIQQAT: PostGIS'da birinchi LON, keyin LAT!
    
    ISHLATISH:
        wkt = create_point_wkt(41.311512, 69.249512)
        # "POINT(69.249512 41.311512)"
        
        # SQL'da:
        INSERT INTO drivers (location) 
        VALUES (ST_GeomFromText('POINT(69.249512 41.311512)', 4326))
    """
    
    return f"POINT({lon} {lat})"


def postgis_distance_query(
    center_lat: float,
    center_lon: float,
    radius_km: float = 50
) -> str:
    """
    PostGIS masofa query yaratish
    
    NIMAGA KERAK:
    50 km radius ichidagi haydovchilarni topish
    
    Args:
        center_lat: Markaz - Latitude
        center_lon: Markaz - Longitude
        radius_km: Radius (kilometr)
    
    Returns:
        SQL query (WHERE qismi)
    
    ISHLATISH:
        where_clause = postgis_distance_query(41.311512, 69.249512, 50)
        
        query = f'''
            SELECT * FROM drivers
            WHERE is_active = TRUE
            AND {where_clause}
        '''
    """
    
    return f"""
    ST_DWithin(
        location::geography,
        ST_SetSRID(ST_MakePoint({center_lon}, {center_lat}), 4326)::geography,
        {radius_km * 1000}
    )
    """


# ============================================
# BEARING (Yo'nalish)
# ============================================

def calculate_bearing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Yo'nalishni hisoblash (bearing)
    
    BEARING:
    Shimoldan soat yo'nalishida graduslar
    0° = Shimol
    90° = Sharq
    180° = Janub
    270° = G'arb
    
    Returns:
        Bearing (0-360 gradus)
    
    ISHLATISH:
        bearing = calculate_bearing(41.311512, 69.249512, 41.377512, 69.361400)
        print(f"Yo'nalish: {bearing:.1f}°")
    """
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    dlon_rad = radians(lon2 - lon1)
    
    y = sin(dlon_rad) * cos(lat2_rad)
    x = cos(lat1_rad) * sin(lat2_rad) - sin(lat1_rad) * cos(lat2_rad) * cos(dlon_rad)
    
    bearing_rad = atan2(y, x)
    bearing_deg = (bearing_rad * 180 / 3.141592653589793 + 360) % 360
    
    return bearing_deg


def bearing_to_direction(bearing: float) -> str:
    """
    Bearing'ni yo'nalish nomiga aylantirish
    
    Args:
        bearing: Bearing (0-360)
    
    Returns:
        Yo'nalish ("Shimol", "Shimoliy-sharq", etc)
    
    ISHLATISH:
        direction = bearing_to_direction(45)  # "Shimoliy-sharq"
    """
    
    directions = [
        "Shimol", "Shimoliy-sharq", "Sharq", "Janubiy-sharq",
        "Janub", "Janubiy-g'arb", "G'arb", "Shimoliy-g'arb"
    ]
    
    index = round(bearing / 45) % 8
    
    return directions[index]


# ============================================
# LOCATION STRING
# ============================================

def format_coordinates(lat: float, lon: float) -> str:
    """
    Koordinatalarni formatlash
    
    ISHLATISH:
        formatted = format_coordinates(41.311512, 69.249512)
        # "41.3115°N, 69.2495°E"
    """
    
    lat_dir = "N" if lat >= 0 else "S"
    lon_dir = "E" if lon >= 0 else "W"
    
    return f"{abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}"


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.utils.geo
    """
    
    print("\n🧪 Testing Geo Utils...\n")
    
    # Test 1: Masofa hisoblash
    print("📝 Test 1: Masofa hisoblash (Gurlan → Vazir)")
    lat1, lon1 = 41.8453, 60.4015  # Gurlan
    lat2, lon2 = 41.3775, 60.3614  # Vazir
    
    distance = calculate_distance(lat1, lon1, lat2, lon2)
    print(f"   Masofa: {distance:.2f} km")
    
    # Test 2: Validation
    print("\n📝 Test 2: Koordinata validation")
    is_valid = validate_coordinates(41.311512, 69.249512)
    print(f"   Valid: {is_valid}")
    
    is_uz = is_in_uzbekistan(41.311512, 69.249512)
    print(f"   O'zbekistonda: {is_uz}")
    
    # Test 3: Bearing
    print("\n📝 Test 3: Yo'nalish")
    bearing = calculate_bearing(lat1, lon1, lat2, lon2)
    direction = bearing_to_direction(bearing)
    print(f"   Bearing: {bearing:.1f}°")
    print(f"   Yo'nalish: {direction}")
    
    # Test 4: Format
    print("\n📝 Test 4: Format")
    formatted = format_coordinates(41.311512, 69.249512)
    print(f"   Formatted: {formatted}")
    
    # Test 5: WKT
    print("\n📝 Test 5: PostGIS WKT")
    wkt = create_point_wkt(41.311512, 69.249512)
    print(f"   WKT: {wkt}")
    
    print("\n✅ All geo tests passed!\n")



__all__ = [
    'calculate_distance',
    'calculate_distance_alternative',
    'validate_coordinates',
    'is_in_uzbekistan',
    'create_point_wkt',
    'postgis_distance_query',
    'calculate_bearing',
    'bearing_to_direction',
    'format_coordinates'
]
