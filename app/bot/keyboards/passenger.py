"""
app/bot/keyboards/passenger.py
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_route_selection_keyboard(routes):
    """Marshrut tanlash"""
    keyboard = []
    for route in routes:
        keyboard.append([
            InlineKeyboardButton(
                text=f"{route.from_location} → {route.to_location}",
                callback_data=f"select_route:{route.route_id}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)