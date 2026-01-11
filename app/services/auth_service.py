"""
app/services/auth_service.py

AUTH SERVICE - Foydalanuvchi autentifikatsiyasi

BU SERVICE NIMA QILADI:
1. Telefon raqam validatsiya
2. SMS kod yuborish va tekshirish
3. User yaratish/login
4. Session management

ISHLATISH:
    from app.services.auth_service import auth_service
    
    # SMS yuborish
    result = await auth_service.send_verification_code("+998901234567")
    
    # Kodni tekshirish va login
    user = await auth_service.verify_and_login("+998901234567", "123456")
"""

from datetime import datetime, timezone
import re
from typing import Optional, Dict
from loguru import logger

from app.core.database import get_session
from app.core.redis_client import redis_client
from app.models.user import User, UserRole, get_user_by_phone, create_user
from app.services.sms_service import send_verification_sms, verify_sms_code
from app.core.exceptions import (
    InvalidPhoneNumberException,
    InvalidSMSCodeException,
    UserNotFoundException,
    SMSRateLimitException
)


class AuthService:
    """
    Authentication Service
    """
    
    # O'zbekiston telefon regex
    PHONE_REGEX = re.compile(r'^\+998\d{9}$')
    
    # ========================================
    # TELEFON VALIDATSIYA
    # ========================================
    
    @staticmethod
    def validate_phone_number(phone: str) -> str:
        """
        Telefon raqam validatsiya va format
        
        Args:
            phone: Telefon raqam (turli formatda)
        
        Returns:
            Formatted phone (+998901234567)
        
        Raises:
            InvalidPhoneNumberException
        
        QABUL QILADIGAN FORMATLAR:
        - +998901234567
        - 998901234567
        - 901234567
        - +998 90 123 45 67
        - 90 123 45 67
        """
        # Bo'sh joylarni olib tashlash
        phone = phone.replace(' ', '').replace('-', '')
        
        # + qo'shish (agar yo'q bo'lsa)
        if not phone.startswith('+'):
            if phone.startswith('998'):
                phone = f'+{phone}'
            elif len(phone) == 9:
                phone = f'+998{phone}'
            else:
                raise InvalidPhoneNumberException(
                    message="Noto'g'ri telefon format",
                    phone=phone
                )
        
        # Regex tekshirish
        if not AuthService.PHONE_REGEX.match(phone):
            raise InvalidPhoneNumberException(
                message="Telefon raqam O'zbekiston formatida bo'lishi kerak",
                expected_format="+998XXXXXXXXX",
                received=phone
            )
        
        return phone
    
    # ========================================
    # SMS KOD YUBORISH
    # ========================================
    
    async def send_verification_code(self, phone: str) -> Dict:
        """
        SMS tasdiqlash kodi yuborish
        
        Args:
            phone: Telefon raqam (har qanday formatda)
        
        Returns:
            {
                'success': bool,
                'message': str,
                'phone': str (formatted),
                'retry_after': int (optional)
            }
        
        FLOW:
        1. Telefon validatsiya
        2. Rate limit tekshirish
        3. SMS yuborish
        4. Redis'ga saqlash
        """
        try:
            # 1. Telefon validatsiya
            phone_formatted = self.validate_phone_number(phone)
            
            logger.info(f"Sending verification code to {phone_formatted}")
            
            # 2. SMS yuborish
            sms_result = await send_verification_sms(phone_formatted)
            
            if sms_result['success']:
                return {
                    'success': True,
                    'message': 'SMS kod yuborildi',
                    'phone': phone_formatted,
                    'remaining_today': sms_result.get('remaining_today', 0)
                }
            else:
                # Rate limit yoki boshqa xato
                if 'retry_after' in sms_result:
                    raise SMSRateLimitException(
                        message=sms_result['error'],
                        retry_after=sms_result['retry_after']
                    )
                
                return {
                    'success': False,
                    'message': sms_result.get('error', 'SMS yuborishda xatolik'),
                    'phone': phone_formatted
                }
        
        except InvalidPhoneNumberException as e:
            return {
                'success': False,
                'message': e.message,
                'details': e.details
            }
        
        except SMSRateLimitException as e:
            return {
                'success': False,
                'message': e.message,
                'retry_after': e.details.get('retry_after', 0)
            }
        
        except Exception as e:
            logger.error(f"Error sending verification code: {e}")
            return {
                'success': False,
                'message': 'Xatolik yuz berdi. Keyinroq urinib ko\'ring.'
            }
    
    # ========================================
    # KOD TEKSHIRISH VA LOGIN
    # ========================================
    
    async def verify_and_login(
        self,
        phone: str,
        code: str,
        telegram_user_id: Optional[int] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        username: Optional[str] = None
    ) -> Dict:
        """
        SMS kodni tekshirish va login/register
        
        Args:
            phone: Telefon raqam
            code: 6 raqamli SMS kod
            telegram_user_id: Telegram user ID (ro'yxatdan o'tish uchun)
            first_name: Ism (ro'yxatdan o'tish uchun)
            last_name: Familiya
            username: Telegram username
        
        Returns:
            {
                'success': bool,
                'user': User object (optional),
                'is_new_user': bool,
                'message': str
            }
        
        FLOW:
        1. Telefon validatsiya
        2. SMS kodni tekshirish
        3. User mavjudligini tekshirish
        4. Agar mavjud - login
        5. Agar yo'q - register qilish (agar telegram_user_id berilgan bo'lsa)
        """
        try:
            # 1. Telefon validatsiya
            phone_formatted = self.validate_phone_number(phone)
            
            # 2. SMS kod tekshirish
            verify_result = await verify_sms_code(phone_formatted, code)
            
            if not verify_result['valid']:
                raise InvalidSMSCodeException(
                    message=verify_result.get('error', 'SMS kod noto\'g\'ri')
                )
            
            # 3. User'ni qidirish
            async with get_session() as session:
                user = await get_user_by_phone(session, phone_formatted)
                
                if user:
                    # ✅ MAVJUD USER - LOGIN
                    logger.info(f"User logged in: {user.user_id}")
                    
                    # Last active yangilash
                    from app.models.user import update_last_active
                    await update_last_active(session, user.user_id)
                    await session.commit()
                    
                    return {
                        'success': True,
                        'user': user,
                        'is_new_user': False,
                        'message': 'Xush kelibsiz!'
                    }
                
                else:
                    # ❌ YANGI USER
                    
                    if not telegram_user_id:
                        # Telegram ma'lumotlari yo'q - xato
                        return {
                            'success': False,
                            'is_new_user': True,
                            'message': 'Iltimos, bot orqali ro\'yxatdan o\'ting'
                        }
                    
                    # ✅ RO'YXATDAN O'TISH
                    new_user = await create_user(
                        session,
                        user_id=telegram_user_id,
                        phone_number=phone_formatted,
                        first_name=first_name or "User",
                        last_name=last_name,
                        username=username,
                        role=UserRole.PASSENGER  # Default rol
                    )
                    
                    await session.commit()
                    
                    logger.success(f"New user registered: {new_user.user_id}")
                    
                    return {
                        'success': True,
                        'user': new_user,
                        'is_new_user': True,
                        'message': 'Ro\'yxatdan o\'tdingiz!'
                    }
        
        except InvalidPhoneNumberException as e:
            return {
                'success': False,
                'message': e.message
            }
        
        except InvalidSMSCodeException as e:
            return {
                'success': False,
                'message': e.message
            }
        
        except Exception as e:
            logger.error(f"Error in verify_and_login: {e}")
            return {
                'success': False,
                'message': 'Xatolik yuz berdi'
            }
    
    # ========================================
    # SESSION MANAGEMENT
    # ========================================
    
    async def create_session(
        self,
        user_id: int,
        ttl: int = 86400 * 7  # 7 kun
    ) -> str:
        """
        Foydalanuvchi session yaratish
        
        Args:
            user_id: User ID
            ttl: Session muddati (soniya)
        
        Returns:
            Session token (UUID)
        """
        import uuid
        
        session_token = str(uuid.uuid4())
        session_key = f"session:{session_token}"
        
        # Redis'ga saqlash
        await redis_client.set(
            session_key,
            {
                'user_id': user_id,
                'created_at': str(datetime.now())
            },
            ex=ttl
        )
        
        logger.info(f"Session created for user {user_id}: {session_token[:8]}...")
        
        return session_token
    
    async def get_session_user(self, session_token: str) -> Optional[int]:
        """
        Session'dan user ID olish
        
        Returns:
            user_id yoki None
        """
        session_key = f"session:{session_token}"
        session_data = await redis_client.get(session_key)
        
        if session_data:
            return session_data.get('user_id')
        
        return None
    
    async def delete_session(self, session_token: str) -> bool:
        """Session'ni o'chirish (logout)"""
        session_key = f"session:{session_token}"
        deleted = await redis_client.delete(session_key)
        
        if deleted:
            logger.info(f"Session deleted: {session_token[:8]}...")
        
        return deleted > 0
    
    # ========================================
    # USER INFO
    # ========================================
    
    async def get_user_info(self, user_id: int) -> Optional[Dict]:
        """
        User ma'lumotlarini olish
        
        Returns:
            User info dictionary
        """
        async with get_session() as session:
            from app.models.user import get_user_by_id
            user = await get_user_by_id(session, user_id)
            
            if not user:
                return None
            
            return user.to_dict()
    
    async def check_user_blocked(self, user_id: int) -> bool:
        """User bloklangan?"""
        async with get_session() as session:
            from app.models.user import get_user_by_id
            user = await get_user_by_id(session, user_id)
            
            if not user:
                return True  # Topilmasa - bloklangan deb hisoblaymiz
            
            return user.is_blocked


# ============================================
# GLOBAL INSTANCE
# ============================================

auth_service = AuthService()


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    """
    Test qilish:
    python -m app.services.auth_service
    """
    import asyncio
    from app.core.redis_client import init_redis, close_redis
    from app.core.database import init_database, close_database
    
    async def test_auth():
        print("\n🧪 Testing Auth Service...\n")
        
        await init_redis()
        await init_database()
        
        # Test 1: Telefon validatsiya
        print("📝 Test 1: Phone validation")
        
        test_phones = [
            "+998901234567",
            "998901234567",
            "901234567",
            "+998 90 123 45 67",
            "90-123-45-67",
            "invalid"
        ]
        
        for phone in test_phones:
            try:
                formatted = auth_service.validate_phone_number(phone)
                print(f"  ✅ {phone} → {formatted}")
            except Exception as e:
                print(f"  ❌ {phone} → {e}")
        
        print()
        
        # Test 2: SMS yuborish
        print("📝 Test 2: Send SMS")
        result = await auth_service.send_verification_code("+998901234567")
        print(f"  Result: {result}")
        
        print()
        
        await close_redis()
        await close_database()
        
        print("✅ Auth tests completed!\n")
    
    asyncio.run(test_auth())


__all__ = ['auth_service', 'AuthService']