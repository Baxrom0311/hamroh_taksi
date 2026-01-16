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


from typing import Optional


def get_trip_confirmation_keyboard(order_id: Optional[int] = None):
    """
    Safar qabul qilingandan keyin chiqadigan panel.
    Haydovchida: Yo'lovchi bilan bog'lanish, Yo'lga chiqdik va bekor qilish tugmalari.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Yo'lovchi bilan bog'lanish")],
            [KeyboardButton(text="🚗 Yo'lga chiqdik")],
            [KeyboardButton(text="❌ Buyurtmani bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )



def get_trip_active_keyboard(order_id: Optional[int] = None):
    """Aktiv safar (10 daqiqalik taymer paytida)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Yo'lovchi bilan bog'lanish")],
            [KeyboardButton(text="✅ Safarni yakunlash")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_driver_main_menu():
    """Driver asosiy menyusi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Buyurtma qabul qilish")],
            [KeyboardButton(text="💰 Balans"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="📞 Support")]
        ],
        resize_keyboard=True
    )


def get_balance_keyboard():
    """Balans menyusi"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 To'ldirish", callback_data="topup_balance")],
        [InlineKeyboardButton(text="📊 Tarix", callback_data="balance_history")]
    ])


def get_location_request_keyboard():
    """Lokatsiya so'rash"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_passenger_contact_keyboard(active_orders):
    """Yo'lovchilar bilan bog'lanish uchun keyboard"""
    keyboard_buttons = []
    
    for order in active_orders:
        if order.passenger and order.passenger.user:
            passenger_name = order.passenger.full_name
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"💬 {passenger_name}",
                    url=f"tg://user?id={order.passenger.user.user_id}"
                )
            ])
            
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None


def get_order_cancellation_keyboard(active_orders):
    """Buyurtmani bekor qilish uchun keyboard"""
    keyboard_buttons = []
    for order in active_orders:
        passenger_name = order.passenger.full_name if order.passenger else "Noma'lum"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"❌ #{order.order_id} - {passenger_name}",
                callback_data=f"cancel_order_select:{order.order_id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="❌ Barchasini bekor qilish",
            callback_data="cancel_all_orders"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
