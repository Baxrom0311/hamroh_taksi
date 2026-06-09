"""
app/bot/keyboards/driver.py

HAYDOVCHI KEYBOARD'LARI — UX Best Practice

TAMOYILLAR:
- Asosiy amal = eng katta + yashil (success)
- Xavfli amal = kichik + qizil (danger)  
- Informatsion = ko'k (primary)
- Bir qatorda bir xil ahamiyatdagi tugmalar
- Compact layout (gorizontal imkon qadar)
- Har bir holatda faqat kerakli tugmalar
"""

from typing import Optional, List
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)


# ═══════════════════════════════════════════
# 1. ASOSIY MENYU
# ═══════════════════════════════════════════

def get_driver_main_menu():
    """
    Haydovchi asosiy menyusi
    
    Layout:
    [🚗 Buyurtma qabul qilish] ← GREEN (primary action)
    [💰 Balans | 📊 Statistika] ← horizontal (secondary)
    [📞 Support]               ← minimal
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Buyurtma qabul qilish", style="success")],
            [KeyboardButton(text="💰 Balans"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📞 Support")],
        ],
        resize_keyboard=True,
        is_persistent=True
    )


# ═══════════════════════════════════════════
# 2. LOKATSIYA SO'RASH
# ═══════════════════════════════════════════

def get_location_request_keyboard():
    """
    Layout:
    [📍 Lokatsiyani yuborish] ← GREEN (primary action)
    [↩️ Orqaga]              ← neutral (back navigation)
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True, style="success")],
            [KeyboardButton(text="↩️ Orqaga")],
        ],
        resize_keyboard=True
    )


# ═══════════════════════════════════════════
# 3. MARSHRUT TANLASH (inline)
# ═══════════════════════════════════════════

def get_route_selection_keyboard(routes):
    """Marshrut tanlash — har bir marshrut alohida ko'k tugma"""
    keyboard = []
    for route in routes:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📍 {route.from_location} → {route.to_location}",
                callback_data=f"select_route:{route.route_id}",
                style="primary"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ═══════════════════════════════════════════
# 4. BO'SH JOYLAR (inline, compact)
# ═══════════════════════════════════════════

def get_seats_keyboard():
    """
    Layout: [1][2][3][4] — bitta qatorda, kompakt
    (6 joy juda kam uchraydi, 4 yetarli. 5-6 qo'shimcha)
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="select_seats:1", style="primary"),
            InlineKeyboardButton(text="2", callback_data="select_seats:2", style="primary"),
            InlineKeyboardButton(text="3", callback_data="select_seats:3", style="primary"),
            InlineKeyboardButton(text="4", callback_data="select_seats:4", style="primary"),
        ],
    ])


# ═══════════════════════════════════════════
# 5. NAVBATDA KUTISH (inline)
# ═══════════════════════════════════════════

def get_driver_active_keyboard():
    """
    Haydovchi navbatda — buyurtma kutayapti
    
    Layout:
    [⚡ Shoshilinch jo'nash] ← PRIMARY (early departure)
    [🛑 Navbatdan chiqish]  ← DANGER (exit queue)
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="⚡ Shoshilinch jo'nash",
                callback_data="early_departure",
                style="primary"
            )],
            [InlineKeyboardButton(
                text="🛑 Navbatdan chiqish",
                callback_data="pause_driver",
                style="danger"
            )],
        ]
    )


# ═══════════════════════════════════════════
# 6. BUYURTMA QABUL QILINGANDAN KEYIN
# ═══════════════════════════════════════════

def get_trip_confirmation_keyboard(order_id: Optional[int] = None):
    """
    Buyurtma qabul qilingan, hali yo'lga chiqmagan
    
    Layout:
    [📞 Aloqa | 🚗 Yo'lga chiqdik] ← horizontal (GREEN = primary)
    [⚡ Tezkor jo'nash]            ← BLUE (early departure with warning)
    [❌ Rad etish]                 ← DANGER (destructive, separate)
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📞 Yo'lovchi bilan bog'lanish"),
                KeyboardButton(text="🚗 Yo'lga chiqdik", style="success"),
            ],
            [KeyboardButton(text="⚡ Tezkor jo'nash", style="primary")],
            [KeyboardButton(text="❌ Buyurtmani bekor qilish", style="danger")],
        ],
        resize_keyboard=True
    )


# ═══════════════════════════════════════════
# 7. SAFAR AKTIV (YO'LDA)
# ═══════════════════════════════════════════

def get_trip_active_keyboard(order_id: Optional[int] = None):
    """
    Safar boshlangan — yo'lda
    
    Layout:
    [✅ Safarni yakunlash]          ← GREEN (primary — eng kerakli)
    [📞 Yo'lovchi bilan bog'lanish] ← neutral (secondary)
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Safarni yakunlash", style="success")],
            [KeyboardButton(text="📞 Yo'lovchi bilan bog'lanish")],
        ],
        resize_keyboard=True
    )


# ═══════════════════════════════════════════
# 8. BALANS
# ═══════════════════════════════════════════

def get_balance_keyboard():
    """
    Layout: [💳 To'ldirish | 📊 Tarix] ← horizontal
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 To'ldirish", callback_data="topup_balance", style="success"),
            InlineKeyboardButton(text="📊 Tarix", callback_data="balance_history", style="primary"),
        ]
    ])


# ═══════════════════════════════════════════
# 9. BUYURTMA BEKOR QILISH
# ═══════════════════════════════════════════

def get_order_cancellation_keyboard(active_orders):
    """
    Bir nechta buyurtma bo'lganda — qaysini bekor qilish tanlash
    
    Layout:
    [❌ #1 - Ism]     ← per order
    [❌ #2 - Ism]
    [🗑 Barchasini]   ← DANGER
    """
    keyboard_buttons = []
    for order in active_orders:
        passenger_name = order.passenger.full_name if order.passenger else "Noma'lum"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"❌ #{order.order_id} — {passenger_name}",
                callback_data=f"cancel_order_select:{order.order_id}",
                style="danger"
            )
        ])
    
    if len(active_orders) > 1:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="🗑 Barchasini bekor qilish",
                callback_data="cancel_all_orders",
                style="danger"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


# ═══════════════════════════════════════════
# 10. EARLY DEPARTURE TASDIQLASH (inline)
# ═══════════════════════════════════════════

def get_early_departure_confirm_keyboard(remaining_seats: int):
    """
    Haydovchi shoshilinch jo'namoqchi — ogohlantirish bilan
    
    Layout:
    [✅ Ha, jo'nayman]  ← GREEN
    [↩️ Yo'q, kutaman] ← neutral (back)
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Ha, {remaining_seats} bo'sh joy bilan jo'nayman",
            callback_data="confirm_early_departure",
            style="success"
        )],
        [InlineKeyboardButton(
            text="↩️ Yo'q, kutaman",
            callback_data="cancel_early_departure",
        )],
    ])
