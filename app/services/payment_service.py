"""
app/services/payment_service.py

PAYMENT SERVICE - To'lov va balans boshqaruvi

BU SERVICE NIMA QILADI:
1. Balansdan komissiya yechish (atomic)
2. To'lov so'rovlarini qayta ishlash
3. Refund (qaytarish)
4. Transaction log

ISHLATISH:
    from app.services.payment_service import payment_service
    
    # Komissiya yechish
    result = await payment_service.deduct_commission(
        driver_id=123,
        order_id=456,
        amount=5000
    )
"""

from decimal import Decimal
from typing import Optional, Dict
from datetime import datetime
from loguru import logger

from app.core.database import get_session, transaction
from app.core.exceptions import (
    InsufficientBalanceError,
    DriverNotFoundException,
    TransactionNotFoundException
)
from app.models.driver import Driver, get_driver_by_id
from app.models.transaction import (
    Transaction,
    TransactionType,
    TransactionStatus,
    create_transaction,
    approve_transaction,
    reject_transaction,
    log_balance_change
)
from sqlalchemy import update, select


class PaymentService:
    """
    Payment and Balance Management Service
    """
    
    # ========================================
    # KOMISSIYA YECHISH (ATOMIC)
    # ========================================
    
    async def deduct_commission(
        self,
        session,
        driver_id: int,
        order_id: int,
        amount: Decimal
    ) -> Dict:
        """
        Balansdan komissiya yechish (100% atomic)
        
        Args:
            driver_id: Driver ID
            order_id: Order ID
            amount: Komissiya miqdori
        
        Returns:
            {
                'success': bool,
                'old_balance': Decimal,
                'new_balance': Decimal,
                'log_id': int
            }
        
        GARANTIYA:
        - Agar biror narsa xato bo'lsa - ROLLBACK
        - Database transaction + FOR UPDATE
        - Transaction log avtomatik yoziladi
        """
        try:
            # 1. Driver'ni olish (FOR UPDATE - row lock)
            result = await session.execute(
                select(Driver)
                .where(Driver.driver_id == driver_id)
                .with_for_update()
            )
            
            driver = result.scalar_one_or_none()
            
            if not driver:
                raise DriverNotFoundException(driver_id=driver_id)
            
            # 2. Balans tekshirish
            if driver.balance < amount:
                raise InsufficientBalanceError(
                    required=int(amount),
                    available=int(driver.balance),
                    driver_id=driver_id
                )
            
            old_balance = driver.balance
            
            # 3. Balansdan yechish (ATOMIC)
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .where(Driver.balance >= amount)  # Extra check
                .values(balance=Driver.balance - amount)
            )
            
            # Yangi balansni olish
            await session.refresh(driver)
            new_balance = driver.balance
            
            # 4. Transaction log
            log = await log_balance_change(
                session,
                driver_id=driver_id,
                order_id=order_id,
                amount=-amount,
                type=TransactionType.COMMISSION,
                old_balance=old_balance,
                new_balance=new_balance,
                description=f"Safar #{order_id} uchun komissiya"
            )
            
            # AUTO COMMIT (transaction context manager)
            
            logger.success(
                f"✅ Commission deducted: driver={driver_id}, "
                f"amount={amount}, new_balance={new_balance}"
            )
            
            return {
                'success': True,
                'old_balance': old_balance,
                'new_balance': new_balance,
                'log_id': log.log_id
            }
        
        except InsufficientBalanceError:
            raise  # Re-raise
        
        except DriverNotFoundException:
            raise  # Re-raise
        
        except Exception as e:
            logger.error(f"Failed to deduct commission: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    # ========================================
    # BALANS QO'SHISH
    # ========================================
    
    async def add_balance(
        self,
        session,
        driver_id: int,
        amount: Decimal,
        transaction_id: Optional[int] = None,
        description: Optional[str] = None
    ) -> Dict:
        """
        Balansga pul qo'shish
        
        Args:
            session: DB session
            driver_id: Driver ID
            amount: Miqdor
            transaction_id: Transaction ID (optional)
            description: Tavsif
        
        Returns:
            {
                'success': bool,
                'new_balance': Decimal
            }
        """
        try:
            # Driver'ni olish
            result = await session.execute(
                select(Driver)
                .where(Driver.driver_id == driver_id)
                .with_for_update()
            )
            
            driver = result.scalar_one_or_none()
            
            if not driver:
                raise DriverNotFoundException(driver_id=driver_id)
            
            old_balance = driver.balance
            
            # Balansga qo'shish
            await session.execute(
                update(Driver)
                .where(Driver.driver_id == driver_id)
                .values(balance=Driver.balance + amount)
            )
            
            await session.refresh(driver)
            new_balance = driver.balance
            
            # Transaction log
            await log_balance_change(
                session,
                driver_id=driver_id,
                amount=amount,
                type=TransactionType.DEPOSIT,
                old_balance=old_balance,
                new_balance=new_balance,
                description=description or f"Balans to'ldirish: {amount} so'm"
            )
            
            logger.success(
                f"✅ Balance added: driver={driver_id}, "
                f"amount={amount}, new_balance={new_balance}"
            )
            
            return {
                'success': True,
                'old_balance': old_balance,
                'new_balance': new_balance
            }
        
        except Exception as e:
            logger.error(f"Failed to add balance: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    # ========================================
    # TO'LOV SO'ROVI QAYTA ISHLASH
    # ========================================
    
    async def process_deposit_request(
        self,
        transaction_id: int,
        admin_id: int,
        approve: bool,
        rejection_reason: Optional[str] = None,
        approved_amount: Optional[Decimal] = None  # Admin kiritgan summa (chekdagi summa)
    ) -> Dict:
        """
        To'lov so'rovini qayta ishlash (Admin)
        
        Args:
            transaction_id: Transaction ID
            admin_id: Admin user ID
            approve: True = Tasdiqlash, False = Rad etish
            rejection_reason: Rad etish sababi
        
        Returns:
            {
                'success': bool,
                'status': 'approved' | 'rejected'
            }
        """
        try:
            async with transaction() as session:
                # Transaction'ni olish
                result = await session.execute(
                    select(Transaction)
                    .where(Transaction.transaction_id == transaction_id)
                    .with_for_update()
                )
                
                trans = result.scalar_one_or_none()
                
                if not trans:
                    raise TransactionNotFoundException(
                        transaction_id=transaction_id
                    )
                
                # Faqat PENDING bo'lishi kerak
                if trans.status != TransactionStatus.PENDING:
                    return {
                        'success': False,
                        'error': f'Transaction allaqachon {trans.status.value}'
                    }
                
                if approve:
                    # ✅ TASDIQLASH
                    
                    # Admin kiritgan summa yoki transaction'dagi summa
                    deposit_amount = approved_amount if approved_amount is not None else trans.amount
                    
                    # Transaction amount'ni yangilash (agar admin boshqa summa kiritgan bo'lsa)
                    if approved_amount is not None and approved_amount != trans.amount:
                        await session.execute(
                            update(Transaction)
                            .where(Transaction.transaction_id == transaction_id)
                            .values(amount=deposit_amount)
                        )
                    
                    # Transaction statusini yangilash
                    success = await approve_transaction(
                        session,
                        transaction_id,
                        admin_id
                    )
                    
                    if not success:
                        return {
                            'success': False,
                            'error': 'Failed to approve transaction'
                        }
                    
                    # Balansga qo'shish (admin kiritgan summa bilan)
                    balance_result = await self.add_balance(
                        session,
                        driver_id=trans.driver_id,
                        amount=deposit_amount,
                        transaction_id=transaction_id,
                        description=f"Balans to'ldirish (Transaction #{transaction_id}) - Chekdagi summa: {deposit_amount:,} so'm"
                    )
                    
                    if not balance_result['success']:
                        # ROLLBACK avtomatik
                        return balance_result
                    
                    logger.success(
                        f"✅ Deposit approved: transaction={transaction_id}, "
                        f"driver={trans.driver_id}, amount={trans.amount}"
                    )
                    
                    # Haydovchiga xabar
                    from app.tasks.notifications import send_telegram_message
                    send_telegram_message.delay( # type: ignore
                        trans.driver_id,
                        f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
                        f"💰 Balansga qo'shildi: <b>{deposit_amount:,} so'm</b>\n"
                        f"📊 Yangi balans: <b>{balance_result['new_balance']:,} so'm</b>"
                    )
                    
                    return {
                        'success': True,
                        'status': 'approved',
                        'new_balance': balance_result['new_balance']
                    }
                
                else:
                    # ❌ RAD ETISH
                    
                    success = await reject_transaction(
                        session,
                        transaction_id,
                        admin_id,
                        rejection_reason
                    )
                    
                    if not success:
                        return {
                            'success': False,
                            'error': 'Failed to reject transaction'
                        }
                    
                    logger.info(
                        f"❌ Deposit rejected: transaction={transaction_id}, "
                        f"reason={rejection_reason}"
                    )
                    
                    # Haydovchiga xabar
                    from app.tasks.notifications import send_telegram_message
                    send_telegram_message.delay( # type: ignore
                        trans.driver_id,
                        f"❌ <b>To'lov rad etildi</b>\n\n"
                        f"Sabab: {rejection_reason or 'Noma\'lum'}\n\n"
                        f"Iltimos, admin bilan bog'laning."
                    )
                    
                    return {
                        'success': True,
                        'status': 'rejected'
                    }
        
        except TransactionNotFoundException:
            raise
        
        except Exception as e:
            logger.error(f"Failed to process deposit request: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    # ========================================
    # REFUND (QAYTARISH)
    # ========================================
    
    async def refund_commission(
        self,
        session,
        driver_id: int,
        order_id: int,
        amount: Decimal,
        reason: str
    ) -> Dict:
        """
        Komissiyani qaytarish (bekor qilingan safar uchun)
        
        Args:
            driver_id: Driver ID
            order_id: Order ID
            amount: Qaytariladigan miqdor
            reason: Sabab
        
        Returns:
            {
                'success': bool,
                'new_balance': Decimal
            }
        """
        try:
            result = await self.add_balance(
                session,
                driver_id=driver_id,
                amount=amount,
                description=f"Komissiya qaytarish: Safar #{order_id} - {reason}"
            )
            
            if result['success']:
                logger.info(
                    f"💰 Refund processed: driver={driver_id}, "
                    f"amount={amount}, order={order_id}"
                )
                
                # Haydovchiga xabar
                from app.tasks.notifications import send_telegram_message
                send_telegram_message.delay( # type: ignore
                    driver_id,
                    f"💰 <b>Komissiya qaytarildi</b>\n\n"
                    f"Safar: #{order_id}\n"
                    f"Miqdor: <b>{amount:,} so'm</b>\n"
                    f"Sabab: {reason}\n\n"
                    f"📊 Yangi balans: <b>{result['new_balance']:,} so'm</b>"
                )
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to refund commission: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    # ========================================
    # BALANS TEKSHIRISH
    # ========================================
    
    async def check_sufficient_balance(
        self,
        driver_id: int,
        required_amount: Decimal
    ) -> bool:
        """
        Balans yetarlimi?
        
        Returns:
            True: Yetarli
            False: Yetarli emas
        """
        async with get_session() as session:
            driver = await get_driver_by_id(session, driver_id)
            
            if not driver:
                return False
            
            return driver.balance >= required_amount
    
    async def get_balance(self, driver_id: int) -> Optional[Decimal]:
        """Driver balansini olish"""
        async with get_session() as session:
            driver = await get_driver_by_id(session, driver_id)
            
            if not driver:
                return None
            
            return driver.balance


# ============================================
# GLOBAL INSTANCE
# ============================================

payment_service = PaymentService()


__all__ = ['payment_service', 'PaymentService']