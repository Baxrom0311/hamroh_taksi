"""
app/bot/keyboards/common.py

UMUMIY KEYBOARD'LAR — registratsiya va support
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_registration_choice_keyboard():
    """
    Ro'yxatdan o'tishda rol tanlash
    
    Layout: [🚗 Haydovchi | 👤 Yo'lovchi] — horizontal
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚗 Haydovchi sifatida", style="primary"),
                KeyboardButton(text="👤 Yo'lovchi sifatida", style="success"),
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


def get_back_keyboard():
    """Orqaga tugmasi — universal"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↩️ Orqaga")]],
        resize_keyboard=True
    )
