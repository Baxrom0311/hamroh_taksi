"""
app/services/sms_service.py

SMS SERVICE - Tasdiqlash kodlari yuborish

PROVIDER'LAR:
- Eskiz.uz (default)
- PlayMobile.uz
- SMS.uz

RATE LIMITING:
- Kuniga 5 ta SMS (spam oldini olish)
- Soatiga 3 ta SMS

ISHLATISH:
    from app.services.sms_service import send_verification_sms
    
    result = await send_verification_sms("+998901234567")
    if result['success']:
        print(f"SMS yuborildi: {result['code']}")
"""

import aiohttp
import random
from typing import Optional
from loguru import logger

from app.core.redis_client import redis_client
from config.settings import settings


# ============================================
# SMS RATE LIMITER
# ============================================

class SMSRateLimiter:
    """
    SMS spam protection
    
    LIMITS:
    - 5 ta SMS / kun
    - 3 ta SMS / soat
    """
    
    MAX_SMS_PER_DAY = settings.SMS_RATE_LIMIT_PER_DAY
    MAX_SMS_PER_HOUR = settings.SMS_RATE_LIMIT_PER_HOUR
    
    @staticmethod
    async def check_rate_limit(phone_number: str) -> dict:
        """
        SMS yuborish mumkinligini tekshirish
        
        Returns:
            {
                'allowed': bool,
                'remaining_today': int,
                'remaining_hour': int,
                'retry_after': int  # seconds
            }
        """
        from datetime import datetime, timedelta
        
        today = datetime.now().strftime('%Y-%m-%d')
        current_hour = datetime.now().strftime('%Y-%m-%d-%H')
        
        # Daily counter
        daily_key = f"sms_daily:{phone_number}:{today}"
        daily_count = int((await redis_client.get(daily_key) or b'0').decode())

        
        # Hourly counter
        hourly_key = f"sms_hourly:{phone_number}:{current_hour}"
        hourly_count = int((await redis_client.get(hourly_key) or b'0').decode())
        
        # Check limits
        if daily_count >= SMSRateLimiter.MAX_SMS_PER_DAY:
            # Keyingi kun boshigacha
            tomorrow = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            retry_after = int((tomorrow - datetime.now()).total_seconds())
            
            return {
                'allowed': False,
                'reason': 'daily_limit_exceeded',
                'remaining_today': 0,
                'retry_after': retry_after
            }
        
        if hourly_count >= SMSRateLimiter.MAX_SMS_PER_HOUR:
            # Keyingi soatgacha
            next_hour = datetime.now().replace(minute=0, second=0) + timedelta(hours=1)
            retry_after = int((next_hour - datetime.now()).total_seconds())
            
            return {
                'allowed': False,
                'reason': 'hourly_limit_exceeded',
                'remaining_hour': 0,
                'retry_after': retry_after
            }
        
        # Allowed
        return {
            'allowed': True,
            'remaining_today': SMSRateLimiter.MAX_SMS_PER_DAY - daily_count,
            'remaining_hour': SMSRateLimiter.MAX_SMS_PER_HOUR - hourly_count
        }
    
    @staticmethod
    async def increment_counter(phone_number: str):
        """SMS yuborilgandan keyin counter'ni oshirish"""
        from datetime import datetime
        
        today = datetime.now().strftime('%Y-%m-%d')
        current_hour = datetime.now().strftime('%Y-%m-%d-%H')
        
        # Daily counter
        daily_key = f"sms_daily:{phone_number}:{today}"
        await redis_client.incr(daily_key)
        await redis_client.expire(daily_key, 86400)  # 24 hours
        
        # Hourly counter
        hourly_key = f"sms_hourly:{phone_number}:{current_hour}"
        await redis_client.incr(hourly_key)
        await redis_client.expire(hourly_key, 3600)  # 1 hour


# ============================================
# SMS PROVIDER - ESKIZ.UZ
# ============================================

class EskizSMSProvider:
    """
    Eskiz.uz SMS provider
    
    API: https://notify.eskiz.uz/api
    """
    
    def __init__(self):
        self.api_url = settings.SMS_API_URL
        self.email = settings.SMS_API_EMAIL
        self.password = settings.SMS_API_PASSWORD
        self._token: Optional[str] = None
    
    async def get_token(self) -> Optional[str]:
        """
        Auth token olish
        
        Token Redis'da cache qilinadi (24 soat)
        """
        # Cache'dan olish
        cached_token = await redis_client.get('eskiz_token')
        if cached_token:
            return cached_token
        
        # Yangi token olish
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.api_url}/auth/login",
                    json={
                        'email': self.email,
                        'password': self.password
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        token = data['data']['token']
                        
                        # Cache qilish (24 soat)
                        await redis_client.set('eskiz_token', token, ex=86400)
                        
                        logger.info("✅ Eskiz token obtained")
                        return token
                    else:
                        logger.error(f"Eskiz auth failed: {response.status}")
                        return None
            
            except Exception as e:
                logger.error(f"Eskiz auth error: {e}")
                return None
    
    async def send_sms(self, phone_number: str, message: str) -> dict:
        """
        SMS yuborish
        
        Args:
            phone_number: +998901234567
            message: SMS matni
        
        Returns:
            {
                'success': bool,
                'message_id': str (optional),
                'error': str (optional)
            }
        """
        token = await self.get_token()
        
        if not token:
            return {'success': False, 'error': 'Token olish xato'}
        
        # Phone format (998901234567 - + va bo'sh joysiz)
        phone_clean = phone_number.replace('+', '').replace(' ', '')
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.api_url}/message/sms/send",
                    headers={'Authorization': f'Bearer {token}'},
                    json={
                        'mobile_phone': phone_clean,
                        'message': message,
                        'from': '4546'  # Sender ID
                    }
                ) as response:
                    data = await response.json()
                    
                    if response.status == 200 and data.get('status') == 'success':
                        logger.info(f"✅ SMS sent to {phone_number}")
                        return {
                            'success': True,
                            'message_id': data.get('data', {}).get('id')
                        }
                    else:
                        error = data.get('message', 'Unknown error')
                        logger.error(f"SMS send failed: {error}")
                        return {'success': False, 'error': error}
            
            except Exception as e:
                logger.error(f"SMS send error: {e}")
                return {'success': False, 'error': str(e)}


# ============================================
# MAIN SMS SERVICE
# ============================================

# Global provider instance
_sms_provider = EskizSMSProvider()


async def send_verification_sms(phone_number: str) -> dict:
    """
    Tasdiqlash SMS yuborish
    
    Args:
        phone_number: +998901234567
    
    Returns:
        {
            'success': bool,
            'code': str (6 raqam),
            'error': str (optional),
            'retry_after': int (seconds, optional)
        }
    
    ISHLATISH:
        result = await send_verification_sms("+998901234567")
        
        if result['success']:
            # SMS yuborildi
            print(f"SMS kod: {result['code']}")
        else:
            # Xato
            print(f"Xato: {result['error']}")
    """
    
    # 1. Rate limit tekshirish
    rate_check = await SMSRateLimiter.check_rate_limit(phone_number)
    
    if not rate_check['allowed']:
        logger.warning(f"SMS rate limit exceeded: {phone_number}")
        
        error_msg = "Juda ko'p SMS yuborildi."
        if rate_check['reason'] == 'daily_limit_exceeded':
            error_msg = "Kunlik limit (5 SMS) tugadi. Ertaga urinib ko'ring."
        elif rate_check['reason'] == 'hourly_limit_exceeded':
            minutes = rate_check['retry_after'] // 60
            error_msg = f"{minutes} daqiqadan keyin urinib ko'ring."
        
        return {
            'success': False,
            'error': error_msg,
            'retry_after': rate_check['retry_after']
        }
    
    # 2. SMS kodni generatsiya qilish
    code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    # 3. Redis'ga saqlash (5 daqiqa)
    code_key = f"sms_code:{phone_number}"
    await redis_client.set(code_key, code, ex=300)  # 5 minutes
    
    # 4. SMS yuborish
    message = f"Hamroh Bot tasdiqlash kodi: {code}\n\nKodni hech kimga bermang!"
    
    try:
        result = await _sms_provider.send_sms(phone_number, message)
        
        if result['success']:
            # Counter'ni oshirish
            await SMSRateLimiter.increment_counter(phone_number)
            
            logger.info(f"✅ Verification SMS sent: {phone_number}")
            
            return {
                'success': True,
                'code': code,  # ⚠️ Production'da o'chirish!
                'remaining_today': rate_check['remaining_today'] - 1
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'SMS yuborishda xatolik')
            }
    
    except Exception as e:
        logger.error(f"SMS send exception: {e}")
        return {
            'success': False,
            'error': 'SMS yuborishda xatolik. Keyinroq urinib ko\'ring.'
        }


async def verify_sms_code(phone_number: str, code: str) -> dict:
    """
    SMS kodni tekshirish
    
    Args:
        phone_number: +998901234567
        code: 6 raqamli kod
    
    Returns:
        {
            'valid': bool,
            'error': str (optional)
        }
    
    ISHLATISH:
        result = await verify_sms_code("+998901234567", "123456")
        
        if result['valid']:
            # Kod to'g'ri
            print("Tasdiqlandi!")
        else:
            # Kod noto'g'ri
            print(f"Xato: {result['error']}")
    """
    
    code_key = f"sms_code:{phone_number}"
    stored_code = await redis_client.get(code_key)
    
    if not stored_code:
        return {
            'valid': False,
            'error': 'Kod muddati tugagan yoki topilmadi'
        }
    
    if str(stored_code) != str(code):
        return {
            'valid': False,
            'error': 'Kod noto\'g\'ri'
        }
    
    # Kod to'g'ri - o'chirish
    await redis_client.delete(code_key)
    
    logger.info(f"✅ SMS code verified: {phone_number}")
    
    return {'valid': True}


async def resend_sms_code(phone_number: str) -> dict:
    """
    SMS kodni qayta yuborish
    
    60 soniya oralig'i bo'lishi kerak
    """
    
    # Oxirgi yuborish vaqtini tekshirish
    last_send_key = f"sms_last_send:{phone_number}"
    last_send = await redis_client.get(last_send_key)
    
    if last_send:
        return {
            'success': False,
            'error': 'Iltimos, 60 soniya kuting',
            'retry_after': 60
        }
    
    # Yangi SMS yuborish
    result = await send_verification_sms(phone_number)
    
    if result['success']:
        # 60 soniya oralig'i
        await redis_client.set(last_send_key, '1', ex=60)
    
    return result


__all__ = [
    'send_verification_sms',
    'verify_sms_code',
    'resend_sms_code',
    'SMSRateLimiter',
    'EskizSMSProvider'
]