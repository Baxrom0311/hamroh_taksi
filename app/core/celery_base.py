"""
app/core/celery_base.py

BASE CELERY TASK CLASS

BU FAYL NIMA QILADI:
- Barcha Celery tasklari uchun base class
- Automatic retry mexanizmi
- Exponential backoff
- Error logging va monitoring
- Max retry cheklovi

ISHLATISH:
    from app.core.celery_base import BaseTask
    
    @celery_app.task(base=BaseTask, bind=True)
    def my_task(self, arg1, arg2):
        # Task logic
        pass
"""
from typing import Any, Optional, Type
from celery import Task
from loguru import logger
import traceback


class BaseTask(Task):
    """
    Base Celery task class with automatic retry and error handling
    
    FEATURES:
    - Exponential backoff: 2^retry_count * 60 seconds
    - Max retries: 3 (configurable)
    - Automatic error logging
    - Exception categorization
    - Prometheus metrics integration
    
    CONFIGURATION:
    - autoretry_for: List of exceptions to auto-retry
    - max_retries: Maximum retry attempts (default: 3)
    - retry_backoff: Base backoff time in seconds (default: 60)
    - retry_backoff_max: Maximum backoff time (default: 3600)
    - retry_jitter: Add randomness to backoff (default: True)
    """
    
    # Default retry configuration
    autoretry_for: tuple = (Exception,)  # Retry on all exceptions by default
    max_retries: int = 3
    retry_backoff: int = 60  # 1 minute base
    retry_backoff_max: int = 3600  # 1 hour max
    retry_jitter: bool = True  # Add randomness to prevent thundering herd
    
    # Exceptions that should NOT trigger retry
    dont_retry_for: tuple = (
        ValueError,  # Invalid input - no point retrying
        TypeError,   # Type error - code bug, not transient
        KeyError,    # Missing key - data issue
    )
    
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute task with error handling and metrics
        
        BU METHOD NIMA QILADI:
        1. Task'ni bajaradi
        2. Xatolarni log qiladi
        3. Metrics yozadi
        4. Retry mexanizmini ishga tushiradi
        """
        try:
            # Log task start
            logger.info(
                f"🚀 Starting task: {self.name} "
                f"(attempt {self.request.retries + 1}/{self.max_retries + 1})"
            )
            
            # Execute the task
            result = super().__call__(*args, **kwargs)
            
            # Log success
            logger.success(f"✅ Task completed: {self.name}")
            
            return result
            
        except self.dont_retry_for as exc:
            # Don't retry for these exceptions
            logger.error(
                f"❌ Task failed (no retry): {self.name}\n"
                f"Exception: {exc.__class__.__name__}: {exc}\n"
                f"Args: {args}\n"
                f"Kwargs: {kwargs}"
            )
            raise
            
        except Exception as exc:
            # Log error with full traceback
            logger.error(
                f"⚠️ Task failed: {self.name}\n"
                f"Exception: {exc.__class__.__name__}: {exc}\n"
                f"Retry: {self.request.retries}/{self.max_retries}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
            
            # Check if we should retry
            if self.request.retries < self.max_retries:
                # Calculate backoff time (exponential)
                countdown = self.calculate_backoff(self.request.retries)
                
                logger.warning(
                    f"🔄 Retrying task: {self.name} in {countdown} seconds"
                )
                
                # Retry the task
                raise self.retry(exc=exc, countdown=countdown)
            else:
                # Max retries reached
                logger.critical(
                    f"💥 Task failed permanently: {self.name}\n"
                    f"Max retries ({self.max_retries}) reached"
                )
                raise
    
    def calculate_backoff(self, retry_count: int) -> int:
        """
        Calculate exponential backoff time
        
        FORMULA: min(retry_backoff * (2 ^ retry_count), retry_backoff_max)
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            Backoff time in seconds
            
        MISOL:
            retry_count=0: 60 seconds
            retry_count=1: 120 seconds
            retry_count=2: 240 seconds
            retry_count=3: 480 seconds (8 minutes)
        """
        backoff = self.retry_backoff * (2 ** retry_count)
        
        # Cap at maximum backoff
        backoff = min(backoff, self.retry_backoff_max)
        
        return backoff
    
    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """
        Success handler - log and record metrics
        
        BU METHOD QACHON CHAQIRILADI:
        Task muvaffaqiyatli tugaganda
        """
        logger.debug(
            f"📊 Task success metrics: {self.name}\n"
            f"Task ID: {task_id}\n"
            f"Return value type: {type(retval).__name__}"
        )
        
        # TODO: Send metrics to Prometheus
        # metrics.record_task_success(self.name, task_id)
    
    def on_retry(
        self, 
        exc: Exception, 
        task_id: str, 
        args: tuple, 
        kwargs: dict, 
        einfo: Any
    ) -> None:
        """
        Retry handler - log retry attempt
        
        BU METHOD QACHON CHAQIRILADI:
        Task retry qilinganda
        """
        logger.warning(
            f"🔄 Task retry handler: {self.name}\n"
            f"Task ID: {task_id}\n"
            f"Exception: {exc}\n"
            f"Retry count: {self.request.retries}"
        )
        
        # TODO: Send metrics to Prometheus
        # metrics.record_task_retry(self.name, task_id, self.request.retries)
    
    def on_failure(
        self, 
        exc: Exception, 
        task_id: str, 
        args: tuple, 
        kwargs: dict, 
        einfo: Any
    ) -> None:
        """
        Failure handler - log and alert
        
        BU METHOD QACHON CHAQIRILADI:
        Task butunlay fail bo'lganda (retry tugagach)
        """
        logger.critical(
            f"💥 Task permanent failure: {self.name}\n"
            f"Task ID: {task_id}\n"
            f"Exception: {exc}\n"
            f"Args: {args}\n"
            f"Kwargs: {kwargs}\n"
            f"Full error info: {einfo}"
        )
        
        # TODO: Send alert to monitoring system
        # alerts.send_task_failure_alert(self.name, task_id, exc)
        
        # TODO: Send metrics to Prometheus
        # metrics.record_task_failure(self.name, task_id)


class CriticalTask(BaseTask):
    """
    Critical task that retries more aggressively
    
    QACHON ISHLATILADI:
    - Payment processing
    - SMS sending
    - Critical notifications
    
    FARQI:
    - Max retries: 5 (instead of 3)
    - Faster initial retry: 30s (instead of 60s)
    """
    max_retries = 5
    retry_backoff = 30  # 30 seconds base


class IdempotentTask(BaseTask):
    """
    Idempotent task - safe to retry without side effects
    
    QACHON ISHLATILADI:
    - Status checks
    - Database queries
    - Cache updates
    
    FARQI:
    - More aggressive retry: 10 attempts
    - Shorter backoff: 15s base
    """
    max_retries = 10
    retry_backoff = 15  # 15 seconds base
    retry_backoff_max = 600  # 10 minutes max


# ============================================
# USAGE EXAMPLES
# ============================================

"""
# Example 1: Regular task with auto-retry
from app.core.celery_app import celery_app
from app.core.celery_base import BaseTask

@celery_app.task(base=BaseTask, bind=True)
def process_order(self, order_id: int):
    # This will auto-retry on failure
    # with exponential backoff
    result = some_operation(order_id)
    return result


# Example 2: Critical task (payment processing)
from app.core.celery_base import CriticalTask

@celery_app.task(base=CriticalTask, bind=True)
def process_payment(self, transaction_id: int):
    # This will retry 5 times instead of 3
    # with faster initial retry
    payment_result = charge_user(transaction_id)
    return payment_result


# Example 3: Idempotent task (status check)
from app.core.celery_base import IdempotentTask

@celery_app.task(base=IdempotentTask, bind=True)
def check_driver_status(self, driver_id: int):
    # This will retry 10 times
    # Safe to retry without side effects
    status = get_driver_status(driver_id)
    return status


# Example 4: Custom retry configuration
@celery_app.task(
    base=BaseTask, 
    bind=True,
    max_retries=7,
    retry_backoff=120  # 2 minutes
)
def custom_task(self, data: dict):
    # Custom retry settings
    process_data(data)
"""
