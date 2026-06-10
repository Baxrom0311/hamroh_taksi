
# ============================================
# PASSENGER STATES (Yo'lovchi)
# ============================================

from aiogram.fsm.state import State, StatesGroup


class PassengerStates(StatesGroup):
    """
    Yo'lovchi holatlari
    
    FLOW:
    main_menu → choose_route → send_location → wait_driver → trip
    """
    
    # Asosiy menyu
    main_menu = State()
    
    # Buyurtma berish
    choose_route = State()         # Marshrut tanlash
    send_location = State()        # Lokatsiya yuborish
    location_description = State() # Lokatsiya izohi
    add_details = State()          # Qo'shimcha ma'lumotlar (pochta, yo'lovchilar)
    # confirm_order — olib tashlandi (hech qayerda set_state qilinmagan)

    # Haydovchi kutish
    waiting_driver = State()       # Haydovchi topilmoqda
    # driver_found — olib tashlandi (hech qayerda set_state qilinmagan)
    
    # Safar
    trip_in_progress = State()     # Safar davom etmoqda
    trip_rating = State()          # Baholash
    
    # Tarix va buyurtmalar
    viewing_history = State()      # Safar tarixini ko'rish
    
    # Support
    support_complaint = State()    # Shikoyat yozish

    # Profil tahriri
    edit_name = State()            # Ismni o'zgartirish
