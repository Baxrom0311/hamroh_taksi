"""
app/bot/keyboards/driver.py
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


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


def get_seats_keyboard():
    """Bo'sh joylar"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1️⃣", callback_data="select_seats:1"),
            InlineKeyboardButton(text="2️⃣", callback_data="select_seats:2"),
            InlineKeyboardButton(text="3️⃣", callback_data="select_seats:3"),
        ],
        [
            InlineKeyboardButton(text="4️⃣", callback_data="select_seats:4"),
            InlineKeyboardButton(text="5️⃣", callback_data="select_seats:5"),
            InlineKeyboardButton(text="6️⃣", callback_data="select_seats:6"),
        ]
    ])


def get_driver_active_keyboard():
    """Aktiv haydovchi"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=" To'xtatish", callback_data="pause_driver")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="driver_stats")]
        ]
    )


def get_trip_confirmation_keyboard():
    """
    Safar qabul qilingandan keyin chiqadigan panel.
    'Yetib keldim' tugmasi shu yerda.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Yetib keldim")],
            [KeyboardButton(text="📞 Yo'lovchi bilan bog'lanish")],
            [KeyboardButton(text="❌ Buyurtmani bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )



def get_trip_active_keyboard():
    """Aktiv safar"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="To'lgach ketish")],
            [KeyboardButton(text="📞 Yo'lovchiga qo'ng'iroq")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )