"""
app/bot/states/registration.py
app/bot/states/driver.py  
app/bot/states/passenger.py

FSM (Finite State Machine) STATES

BU NIMA:
- Bot'dagi holatlar (state)
- Multi-step conversation uchun

ISHLATISH:
    await state.set_state(RegistrationStates.phone_number)
"""

from aiogram.fsm.state import State, StatesGroup

# ============================================
# DRIVER STATES (Haydovchi)
# ============================================

class DriverStates(StatesGroup):
    """
    Haydovchi holatlari
    
    FLOW:
    main_menu → choose_route → enter_seats → accept_orders → trip
    """
    
    # Asosiy menyu
    main_menu = State()
    # Buyurtma qabul qilish
    send_location = State()        # Jonli joylashuv yuborish
    choose_route = State()        # Marshrut tanlash
    enter_seats = State()          # Bo'sh joylar kiritish
    waiting_orders = State()       # Buyurtmalarni kutish
    
    # Safar
    trip_in_progress = State()     # Safar davom etmoqda
    trip_confirmation = State()    # Yo'lovchi tasdiqlashi kutilmoqda
    confirming_trip_cancellation = State()  # Tripni to'liq bekor qilish tasdiqlash
    confirming_cancellation = State()  # <<< bu qo‘shildi
    
    # Balans
    balance_topup = State()        # Balans to'ldirish
    balance_receipt = State()      # Chek yuklash
    
    # Support
    support_receipt_amount = State()  # Chek summa kiritish
    support_receipt_photo = State()  # Chek rasm yuklash
    support_complaint = State()       # Shikoyat yozish
    
    # settings_edit — olib tashlandi (hech qayerda set_state qilinmagan)
