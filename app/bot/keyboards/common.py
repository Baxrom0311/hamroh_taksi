"""
app/bot/keyboards/common.py
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_cancel_keyboard():
    """Bekor qilish klaviaturasi"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )


def get_confirm_keyboard():
    """Tasdiqlash klaviaturasi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Tasdiqlash")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )