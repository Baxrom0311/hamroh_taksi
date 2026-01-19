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


def get_passenger_main_menu():
    """Yo'lovchi asosiy menyusi"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Taksi chaqirish")],
            [KeyboardButton(text="📋 Faol buyurtmalar"), KeyboardButton(text="📜 Safar tarixi")],
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="📞 Support")],
        ],
        resize_keyboard=True
    )


def get_passenger_location_keyboard():
    """Lokatsiya yuborish tugmasi"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )


def get_passenger_count_keyboard():
    """Yo'lovchilar soni (1-4) va Pochta"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1️⃣", callback_data="passenger_count:1"),
            InlineKeyboardButton(text="2️⃣", callback_data="passenger_count:2"),
        ],
        [
            InlineKeyboardButton(text="3️⃣", callback_data="passenger_count:3"),
            InlineKeyboardButton(text="4️⃣", callback_data="passenger_count:4"),
        ],
        [
            InlineKeyboardButton(text="📦 Pochta", callback_data="passenger_count:0")
        ]
    ])



def get_driver_selection_keyboard(available_drivers, order_id):
    """Mavjud haydovchilar ro'yxati"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard_buttons = []
    
    for driver in available_drivers[:10]:
        driver_info = f"{driver.car_model} ({driver.car_color}) - {driver.car_number}"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"🚗 {driver_info}",
                callback_data=f"select_new_driver:{order_id}:{driver.driver_id}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def get_driver_action_keyboard(driver_user_id, order_id):
    """Haydovchi haqida ma'lumot ko'rishdagi amallar"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Mashinani o'zgartirish",
                callback_data=f"change_driver:{order_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🚫 Ban tashlash",
                callback_data=f"ban_driver:{order_id}"
            )
        ]
    ])