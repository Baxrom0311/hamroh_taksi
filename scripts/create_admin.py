#!/usr/bin/env python3
"""
scripts/create_admin.py

ADMIN USER YARATISH

BU SCRIPT NIMA QILADI:
- Yangi admin user yaratadi
- Password hash qiladi
- Database'ga saqlaydi

ISHLATISH:
    python scripts/create_admin.py
"""

import asyncio
import sys
from pathlib import Path

# Root path qo'shish
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))

from loguru import logger
from app.core.database import init_database, get_session
from app.models.user import User, UserRole, create_user, get_user_by_phone
from app.admin.auth import get_password_hash
from app.models.driver import Driver      # SHU QATORNI QO'SHING
from app.models.passenger import Passenger # SHU QATORNI QO'SHING
from app.models.order import Order        # SHU QATORNI QO'SHING
from app.models.route import Route          # <--- BU SHART!

# ============================================
# ADMIN DATA
# ============================================

async def create_admin_user(
    phone_number: str,
    password: str,
    username: str = "admin",
    first_name: str = "Admin",
    telegram_id: int = 999999999,
    role: UserRole = UserRole.GLAVNI_ADMIN
):
    """
    Admin user yaratish
    
    Args:
        phone_number: Telefon raqam (+998901234567)
        password: Parol (hash qilinadi)
        username: Username
        first_name: Ism
        telegram_id: Telegram ID (unique)
        role: User roli (ADMIN yoki GLAVNI_ADMIN)
    """
    
    logger.info(f"Creating admin user: {username} ({phone_number})")

    if not phone_number:
        raise ValueError("Telefon raqam bo'sh bo'lishi mumkin emas")

    # Bcrypt 72 byte cheklovi
    if len(password.encode("utf-8")) > 72:
        logger.warning("Parol 72 baytdan uzun, avtomatik qisqartirildi")
        password = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    
    # Database init
    await init_database()
    
    async with get_session() as session:
        # Mavjudligini tekshirish
        existing = await get_user_by_phone(session, phone_number)
        
        if existing:
            logger.warning(f"⚠️  User already exists: {phone_number}")
            logger.info(f"   User ID: {existing.user_id}")
            logger.info(f"   Role: {existing.role.value}")
            return
        
        # Password hash
        password_hash = get_password_hash(password)
        logger.info(f"Password hashed: {password_hash[:20]}...")
        
        # Admin user yaratish
        admin = await create_user(
            session,
            user_id=telegram_id,
            phone_number=phone_number,
            first_name=first_name,
            username=username,
            role=role
        )
        
        # TODO: Password'ni alohida jadvalda saqlash
        # Hozircha faqat user yaratamiz
        
        await session.commit()
        
        logger.success("✅ Admin user created successfully!")
        logger.info(f"   User ID: {admin.user_id}")
        logger.info(f"   Phone: {admin.phone_number}")
        logger.info(f"   Username: {admin.username}")
        logger.info(f"   Role: {admin.role.value}")
        logger.info(f"   Password: {password} (SAVE THIS!)")


# ============================================
# INTERACTIVE MODE
# ============================================

async def interactive_create():
    """
    Interactive admin yaratish
    """
    print("\n" + "=" * 60)
    print("👨‍💼 CREATE ADMIN USER")
    print("=" * 60 + "\n")
    
    # Input
    phone = input("📱 Telefon raqam (+998901234567): ").strip()
    username = input("👤 Username (default: admin): ").strip() or "admin"
    first_name = input("📝 Ism (default: Admin): ").strip() or "Admin"
    password = input("🔐 Parol (default: admin123): ").strip() or "admin123"

    if not phone:
        print("❌ Telefon raqam bo'sh bo'lishi mumkin emas.")
        return
    
    # Role
    print("\n🎭 Rol tanlang:")
    print("  1. GLAVNI_ADMIN (barcha huquqlar)")
    print("  2. ADMIN (cheklangan huquqlar)")
    role_choice = input("Tanlang (1/2, default: 1): ").strip() or "1"
    
    role = UserRole.GLAVNI_ADMIN if role_choice == "1" else UserRole.ADMIN
    
    # Confirm
    print("\n" + "━" * 60)
    print("📋 TASDIQLASH:")
    print(f"   Telefon: {phone}")
    print(f"   Username: {username}")
    print(f"   Ism: {first_name}")
    print(f"   Parol: {password}")
    print(f"   Rol: {role.value}")
    print("━" * 60)
    
    confirm = input("\n✅ Tasdiqlaysizmi? (yes/no): ").strip().lower()
    
    if confirm not in ['yes', 'y', 'ha']:
        print("❌ Bekor qilindi")
        return
    
    # Create
    await create_admin_user(
        phone_number=phone,
        password=password,
        username=username,
        first_name=first_name,
        role=role
    )


# ============================================
# MAIN
# ============================================

async def main():
    """Main function"""
    try:
        await interactive_create()
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Failed to create admin: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
    print("\n✅ Done!\n")
