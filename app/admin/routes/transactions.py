"""
app/admin/routes/transactions.py

TRANSACTIONS MANAGEMENT

ENDPOINTS:
- GET /transactions - Barcha tranzaksiyalar
- GET /transactions/pending - Kutayotgan tranzaksiyalar
- POST /transactions/{id}/approve - Tasdiqlash
- POST /transactions/{id}/reject - Rad etish
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel
from loguru import logger

from app.admin.auth import get_current_user
from app.core.database import get_session
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
    get_pending_transactions
)
from app.services.payment_service import payment_service
from sqlalchemy import select, func, or_


router = APIRouter(prefix="/transactions", tags=["transactions"])


# ============================================
# SCHEMAS
# ============================================

class TransactionResponse(BaseModel):
    transaction_id: int
    driver_id: int
    driver_name: str
    amount: float
    type: str
    status: str
    receipt_file_id: Optional[str]
    description: Optional[str]
    created_at: str
    processed_at: Optional[str]
    
    class Config:
        from_attributes = True


class ApproveRequest(BaseModel):
    """Tasdiqlash so'rovi"""
    amount: Optional[float] = None  # Admin kiritgan summa (chekdagi summa)


class RejectRequest(BaseModel):
    """Rad etish so'rovi"""
    reason: str


# ============================================
# ENDPOINTS
# ============================================

@router.get("/pending")
async def get_pending_transactions_list(
    current_user: dict = Depends(get_current_user)
):
    """
    Kutayotgan tranzaksiyalar
    """
    try:
        async with get_session() as session:
            transactions = await get_pending_transactions(session)
            
            # Driver ma'lumotlarini qo'shish
            result = []
            
            for trans in transactions:
                from app.models.driver import get_driver_by_id
                driver = await get_driver_by_id(session, trans.driver_id)
                
                result.append({
                    'transaction_id': trans.transaction_id,
                    'driver_id': trans.driver_id,
                    'driver_name': driver.full_name if driver else 'Unknown',
                    'driver_phone': driver.phone_number if driver else None,
                    'amount': float(trans.amount),
                    'type': trans.type.value,
                    'status': trans.status.value,
                    'receipt_file_id': trans.receipt_file_id,
                    'description': trans.description,
                    'created_at': trans.created_at.isoformat()
                })
            
            return {
                'success': True,
                'transactions': result,
                'total': len(result)
            }
    
    except Exception as e:
        logger.error(f"Failed to get pending transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def get_transactions(
    status: Optional[TransactionStatus] = None,
    type: Optional[TransactionType] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """
    Barcha tranzaksiyalar (filtrlash bilan)
    """
    try:
        async with get_session() as session:
            # Query builder
            query = select(Transaction)
            
            # Filters
            if status:
                query = query.where(Transaction.status == status)
            
            if type:
                query = query.where(Transaction.type == type)
            
            # Pagination
            query = query.order_by(Transaction.created_at.desc())
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            transactions = result.scalars().all()
            
            # Count
            count_query = select(func.count(Transaction.transaction_id))
            if status:
                count_query = count_query.where(Transaction.status == status)
            if type:
                count_query = count_query.where(Transaction.type == type)
            
            total_result = await session.execute(count_query)
            total = total_result.scalar()
            
            # Response
            trans_list = []
            for trans in transactions:
                from app.models.driver import get_driver_by_id
                driver = await get_driver_by_id(session, trans.driver_id)
                
                trans_list.append({
                    'transaction_id': trans.transaction_id,
                    'driver_id': trans.driver_id,
                    'driver_name': driver.full_name if driver else 'Unknown',
                    'amount': float(trans.amount),
                    'type': trans.type.value,
                    'status': trans.status.value,
                    'description': trans.description,
                    'created_at': trans.created_at.isoformat(),
                    'processed_at': trans.processed_at.isoformat() if trans.processed_at else None
                })
            
            return {
                'success': True,
                'transactions': trans_list,
                'total': total,
                'limit': limit,
                'offset': offset
            }
    
    except Exception as e:
        logger.error(f"Failed to get transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{transaction_id}/approve")
async def approve_transaction(
    transaction_id: int,
    request: ApproveRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Tranzaksiyani tasdiqlash
    
    Admin chekdagi summani kiritadi va shu summa driver balansiga qo'shiladi
    """
    try:
        from decimal import Decimal
        
        # Admin kiritgan summa (yoki None - transaction'dagi summa ishlatiladi)
        approved_amount = Decimal(str(request.amount)) if request.amount is not None else None
        
        result = await payment_service.process_deposit_request(
            transaction_id=transaction_id,
            admin_id=current_user['user_id'],
            approve=True,
            approved_amount=approved_amount
        )
        
        if result['success']:
            logger.success(
                f"✅ Transaction {transaction_id} approved by {current_user['username']}"
            )
            
            return {
                'success': True,
                'message': 'Transaction tasdiqlandi',
                'new_balance': result.get('new_balance')
            }
        else:
            raise HTTPException(status_code=400, detail=result.get('error'))
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to approve transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{transaction_id}/reject")
async def reject_transaction(
    transaction_id: int,
    request: RejectRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Tranzaksiyani rad etish
    """
    try:
        result = await payment_service.process_deposit_request(
            transaction_id=transaction_id,
            admin_id=current_user['user_id'],
            approve=False,
            rejection_reason=request.reason
        )
        
        if result['success']:
            logger.info(
                f"❌ Transaction {transaction_id} rejected by {current_user['username']}"
            )
            
            return {
                'success': True,
                'message': 'Transaction rad etildi'
            }
        else:
            raise HTTPException(status_code=400, detail=result.get('error'))
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to reject transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_transaction_statistics(
    current_user: dict = Depends(get_current_user)
):
    """
    Tranzaksiya statistikasi
    """
    try:
        async with get_session() as session:
            from datetime import datetime, timedelta
            
            today_start = datetime.now().replace(hour=0, minute=0, second=0)
            week_start = today_start - timedelta(days=7)
            
            # Bugungi statistika
            today_query = select(
                func.count(Transaction.transaction_id).label('count'),
                func.sum(Transaction.amount).label('total')
            ).where(
                Transaction.created_at >= today_start
            ).where(
                Transaction.status == TransactionStatus.APPROVED
            )
            
            today_result = await session.execute(today_query)
            today_data = today_result.first()
            
            # Haftalik statistika
            week_query = select(
                func.count(Transaction.transaction_id).label('count'),
                func.sum(Transaction.amount).label('total')
            ).where(
                Transaction.created_at >= week_start
            ).where(
                Transaction.status == TransactionStatus.APPROVED
            )
            
            week_result = await session.execute(week_query)
            week_data = week_result.first()
            
            # Pending count
            pending_query = select(func.count(Transaction.transaction_id)).where(
                Transaction.status == TransactionStatus.PENDING
            )
            
            pending_result = await session.execute(pending_query)
            pending_count = pending_result.scalar()
            
            return {
                'success': True,
                'today': {
                    'count': today_data.count or 0, # type: ignore
                    'total': float(today_data.total or 0) # type: ignore
                },
                'week': {
                    'count': week_data.count or 0, # type: ignore
                    'total': float(week_data.total or 0) # type: ignore
                },
                'pending': pending_count or 0
            }
    
    except Exception as e:
        logger.error(f"Failed to get transaction statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ['router']