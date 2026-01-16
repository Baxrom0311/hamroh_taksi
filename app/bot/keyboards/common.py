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


def get_registration_choice_keyboard():
    """Ro'yxatdan o'tishda rol tanlash"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚗 Haydovchi sifatida"),
                KeyboardButton(text="👤 Yo'lovchi sifatida")
            ]
        ],
        resize_keyboard=True
    )


def get_support_keyboard():
    """Support tugmasi"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Support")]],
        resize_keyboard=True
    )