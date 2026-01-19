"""
config/settings.py

BU FAYL NIMA QILADI:
- .env fayldagi barcha o'zgaruvchilarni o'qiydi
- Pydantic orqali validatsiya qiladi (xato bo'lsa darhol bildiradi)
- Butun loyiha davomida settings.VARIABLE shaklida ishlatiladi

MASALAN:
    from config.settings import settings
    print(settings.BOT_TOKEN)  # Bot tokenini olish
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pathlib import Path


class Settings(BaseSettings):
    """
    Barcha muhit o'zgaruvchilari (environment variables)
    
    Pydantic avtomatik:
    1. .env fayldan o'qiydi
    2. Tip tekshiruvi qiladi (int bo'lishi kerak bo'lsa, string berib bo'lmaydi)
    3. Default qiymatlar beradi
    4. Xato bo'lsa aniq xabar beradi
    """
    
    # ============================================
    # BOT SOZLAMALARI
    # ============================================
    
    BOT_TOKEN: str  # Telegram bot token (majburiy)
    # QAYERDAN OLISH: @BotFather dan
    # MISOL: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
    
    BOT_ADMIN_IDS: str = ""  # Admin user ID'lar (vergul bilan)
    # MISOL: "123456789,987654321"
    # QANDAY TOPISH: @userinfobot ga /start yuboring
    
    @property
    def admin_ids_list(self) -> List[int]:
        """Admin ID'larni list'ga aylantirish"""
        if not self.BOT_ADMIN_IDS:
            return []
        return [int(id.strip()) for id in self.BOT_ADMIN_IDS.split(',')]
    
    # ============================================
    # DATABASE SOZLAMALARI
    # ============================================
    
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_NAME: str = "hamroh_bot"
    DB_USER: str = "hamroh_user"
    DB_PASSWORD: str  # Majburiy, xavfsizlik uchun
    
    @property
    def database_url(self) -> str:
        """
        PostgreSQL connection string yasash
        
        NATIJA: postgresql+asyncpg://user:password@host:port/dbname
        asyncpg = async PostgreSQL driver (tez ishlaydi)
        """
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
    
    @property
    def database_url_sync(self) -> str:
        """
        Alembic uchun sync URL (migration'larda kerak)
        """
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
    
    # ============================================
    # REDIS SOZLAMALARI
    # ============================================
    
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None  # Ixtiyoriy
    REDIS_DB: int = 0  # Database raqami (0-15)
    
    @property
    def redis_url(self) -> str:
        """
        Redis connection string
        
        NATIJA: redis://[:password]@host:port/db
        """
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # ============================================
    # CELERY SOZLAMALARI (Queue tizimi)
    # ============================================
    
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    
    @property
    def celery_broker(self) -> str:
        """Celery broker URL (default: Redis DB 0)"""
        return self.CELERY_BROKER_URL or f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    
    @property
    def celery_backend(self) -> str:
        """Celery result backend (default: Redis DB 1)"""
        return self.CELERY_RESULT_BACKEND or f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/1"
    
    # ============================================
    # JWT SOZLAMALARI (Admin panel uchun)
    # ============================================
    
    JWT_SECRET_KEY: str  # Majburiy, strong password
    # QANDAY GENERATSIYA QILISH:
    # Terminal: openssl rand -hex 32
    
    JWT_ALGORITHM: str = "HS256"  # Shifrlash algoritmi
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 soat
    
    # ============================================
    # ADMIN PANEL SOZLAMALARI
    # ============================================
    
    ADMIN_ALLOWED_IPS: str = "127.0.0.1"  # IP whitelist (vergul bilan)
    # MISOL: "127.0.0.1,192.168.1.100,10.0.0.5"
    # Bo'sh bo'lsa = barcha IP'larga ruxsat
    
    @property
    def admin_allowed_ips_list(self) -> List[str]:
        """IP'larni list'ga aylantirish"""
        if not self.ADMIN_ALLOWED_IPS:
            return []
        return [ip.strip() for ip in self.ADMIN_ALLOWED_IPS.split(',')]
    
    # ============================================
    # SMS PROVIDER SOZLAMALARI
    # ============================================
    
    SMS_PROVIDER: str = "eskiz"  # eskiz, playmobile, etc.
    SMS_API_URL: str = "https://notify.eskiz.uz/api"
    SMS_API_EMAIL: str = ""  # Eskiz.uz email
    SMS_API_PASSWORD: str = ""  # Eskiz.uz parol
    
    # ============================================
    # BIZNES LOGIKA SOZLAMALARI
    # ============================================

    COMMISSION_AMOUNT: int = 500 # Har bir safar uchun komissiya (so'm)
    # BU QIYMATNI O'ZGARTIRING: Komissiya miqdorini belgilash
    
    MAX_PICKUP_DISTANCE_KM: int = 50  # Maksimal masofa (km)
    # Haydovchi yo'lovchidan 50 km dan uzoqroq bo'lsa, buyurtma ko'rinmaydi
    
    AUTO_CONFIRM_DELAY_SECONDS: int = 120  # 2 daqiqa
    # Yo'lovchi tasdiqlash uchun kutish vaqti
    
    # ============================================
    # RATE LIMITING SOZLAMALARI
    # ============================================
    
    SMS_RATE_LIMIT_PER_DAY: int = 5  # Kuniga max 5 ta SMS
    SMS_RATE_LIMIT_PER_HOUR: int = 3  # Soatiga max 3 ta SMS
    MAX_DRIVER_REJECTS_PER_DAY: int = 50  # Kuniga max 50 ta rad etish
    
    # ============================================
    # DISTRIBUTED LOCK SOZLAMALARI
    # ============================================
    
    # Order acceptance lock (double booking prevention)
    ORDER_LOCK_TIMEOUT_SECONDS: int = 30  # Lock timeout (30s)
    ORDER_LOCK_MAX_RETRIES: int = 3  # Max retry count
    ORDER_LOCK_RETRY_DELAY_SECONDS: float = 0.2  # Retry delay
    
    # Generic lock defaults
    GENERIC_LOCK_TIMEOUT_SECONDS: int = 10
    GENERIC_LOCK_MAX_RETRIES: int = 3
    
    # ============================================
    # FSM STATE SOZLAMALARI
    # ============================================
    
    # State TTL (hanging state prevention)
    STATE_TTL_SECONDS: int = 3600  # 1 soat
    # Agar user 1 soat davomida hech narsa qilmasa, state avtomatik tozalanadi
    
    # ============================================
    # CELERY TASK SOZLAMALARI
    # ============================================
    
    # Auto-complete trip timer
    AUTO_COMPLETE_TRIP_SECONDS: int = 600  # 10 daqiqa
    AUTO_COMPLETE_TRIP_MAX_RETRIES: int = 3
    
    # Driver matching task
    DRIVER_MATCHING_TIMEOUT_SECONDS: int = 300  # 5 daqiqa
    DRIVER_MATCHING_MAX_RETRIES: int = 5
    
    # ============================================
    # LOGGING SOZLAMALARI
    # ============================================
    
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FILE_PATH: str = "logs/hamroh_{time:YYYY-MM-DD}.log"
    
    # ============================================
    # MUHIT SOZLAMALARI
    # ============================================
    
    ENVIRONMENT: str = "development"  # development, staging, production
    
    @property
    def is_production(self) -> bool:
        """Production muhitdami?"""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        """Development muhitdami?"""
        return self.ENVIRONMENT == "development"
    
    # ============================================
    # PYDANTIC CONFIG
    # ============================================
    
    model_config = SettingsConfigDict(
        env_file=".env",  # .env fayldan o'qish
        env_file_encoding="utf-8",  # UTF-8 encoding
        case_sensitive=False,  # Katta-kichik harf farqsiz
        extra="ignore"  # Ortiqcha o'zgaruvchilarni ignore qilish
    )


# ============================================
# GLOBAL SETTINGS INSTANCE
# ============================================

# BU OBJECT'NI HAMMA JOYDA ISHLATAMIZ!
settings = Settings() # type: ignore


# ============================================
# VALIDATSIYA (Faqat kerak bo'lganda)
# ============================================

def validate_settings():
    """
    Sozlamalarni tekshirish
    
    Agar muhim o'zgaruvchilar yo'q bo'lsa, xato beradi
    """
    errors = []
    
    # Bot token tekshiruvi
    if not settings.BOT_TOKEN:
        errors.append("BOT_TOKEN .env faylda yo'q!")
    
    # Database parol tekshiruvi
    if not settings.DB_PASSWORD:
        errors.append("DB_PASSWORD .env faylda yo'q!")
    
    # JWT secret tekshiruvi
    if not settings.JWT_SECRET_KEY:
        errors.append("JWT_SECRET_KEY .env faylda yo'q!")
    
    # Agar xatolar bo'lsa
    if errors:
        error_message = "\n".join(errors)
        raise ValueError(f"\n❌ SOZLAMALAR XATOSI:\n{error_message}\n\n.env faylni to'ldiring!")
    
    print("✅ Barcha sozlamalar to'g'ri!")


# ============================================
# FAYLNI TO'G'RIDAN-TO'G'RI ISHGA TUSHIRSANGIZ
# ============================================

if __name__ == "__main__":
    """
    Test qilish uchun:
    python config/settings.py
    """
    try:
        validate_settings()
        
        print("\n📋 SOZLAMALAR:")
        print(f"  Environment: {settings.ENVIRONMENT}")
        print(f"  Bot Token: {settings.BOT_TOKEN[:20]}...")
        print(f"  Database: {settings.DB_NAME}")
        print(f"  Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        print(f"  Komissiya: {settings.COMMISSION_AMOUNT:,} so'm")
        
    except ValueError as e:
        print(str(e))
