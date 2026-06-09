"""
app/bot/keyboards/passenger.py

YO'LOVCHI KEYBOARD'LARI — UX Best Practice

TAMOYILLAR:
- Asosiy amal = eng katta + yashil
- Compact (gorizontal) where possible
- Xavfli amal alohida qatorda + qizil
- Minimal tugmalar — foydalanuvchini chalkashtimaslik
"""

from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)


# ═══════════════════════════════════════════
# 1. ASOSIY MENYU
# ═══════════════════════════════════════════

def get_passenger_main_menu():
    """
    Layout:
    [🚖 Taksi chaqirish]   ← GREEN (primary action)
    [📋 Faol | 📜 Tarix]  ← horizontal (secondary)
    [📞 Support]           ← minimal
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Taksi chaqirish", style="success")],
            [KeyboardButton(text="📋 Faol buyurtmalar"), KeyboardButton(text="📜 Safar tarixi")],
            [KeyboardButton(text="📞 Support")],
        ],
        resize_keyboard=True,
        is_persistent=True
    )


# ═══════════════════════════════════════════
# 2. MARSHRUT TANLASH (inline)
# ═══════════════════════════════════════════

def get_route_selection_keyboard(routes):
    """Har bir marshrut alohida ko'k tugma"""
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
# 3. LOKATSIYA YUBORISH
# ═══════════════════════════════════════════

def get_passenger_location_keyboard():
    """
    Layout:
    [📍 Lokatsiyani yuborish] ← GREEN
    [↩️ Orqaga]              ← back navigation
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True, style="success")],
            [KeyboardButton(text="↩️ Orqaga")],
        ],
        resize_keyboard=True
    )


# ═══════════════════════════════════════════
# 4. YO'LOVCHILAR SONI (inline, compact)
# ═══════════════════════════════════════════

def get_passenger_count_keyboard():
    """
    Layout: [1][2][3][4][📦] — bitta qatorda, kompakt
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="passenger_count:1", style="primary"),
            InlineKeyboardButton(text="2", callback_data="passenger_count:2", style="primary"),
            InlineKeyboardButton(text="3", callback_data="passenger_count:3", style="primary"),
            InlineKeyboardButton(text="4", callback_data="passenger_count:4", style="primary"),
            InlineKeyboardButton(text="📦", callback_data="passenger_count:0", style="success"),
        ]
    ])


# ═══════════════════════════════════════════
# 5. BUYURTMA BEKOR QILISH (inline)
# ═══════════════════════════════════════════

def get_passenger_cancel_keyboard(order_id: int):
    """Faqat bitta bekor qilish tugmasi — qizil"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Buyurtmani bekor qilish",
            callback_data=f"passenger_cancel:{order_id}",
            style="danger"
        )]
    ])


# ═══════════════════════════════════════════
# 6. HAYDOVCHI TOPILDI (inline)
# ═══════════════════════════════════════════

def get_driver_found_keyboard(order_id: int, driver_phone: str = ""):
    """
    Haydovchi topilganda yo'lovchiga ko'rsatiladigan tugmalar
    
    Layout:
    [📋 Raqamni nusxalash | 📞 Qo'ng'iroq] ← utility (agar telefon bor)
    [❌ Bekor qilish]                       ← DANGER
    """
    from aiogram.types import CopyTextButton
    
    buttons = []
    
    if driver_phone and driver_phone != "N/A":
        buttons.append([
            InlineKeyboardButton(
                text="📋 Raqamni nusxalash",
                copy_text=CopyTextButton(text=driver_phone),
                style="primary"
            ),
            InlineKeyboardButton(
                text="📞 Qo'ng'iroq",
                url=f"tel:{driver_phone}",
                style="success"
            ),
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"passenger_cancel:{order_id}",
            style="danger"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══════════════════════════════════════════
# 7. HAYDOVCHI HAQIDA AMALLAR (admin/support)
# ═══════════════════════════════════════════

def get_driver_action_keyboard(driver_user_id, order_id):
    """Admin/yo'lovchi uchun haydovchiga amallar"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 O'zgartirish",
                callback_data=f"change_driver:{order_id}",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🚫 Ban",
                callback_data=f"ban_driver:{order_id}",
                style="danger"
            ),
        ]
    ])


def get_driver_selection_keyboard(available_drivers, order_id):
    """Mavjud haydovchilar ro'yxati"""
    keyboard_buttons = []
    for driver in available_drivers[:10]:
        driver_info = f"{driver.car_model} ({driver.car_color}) — {driver.car_number}"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"🚗 {driver_info}",
                callback_data=f"select_new_driver:{order_id}:{driver.driver_id}",
                style="primary"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
