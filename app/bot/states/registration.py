from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    """
    Ro'yxatdan o'tish holatlari
    
    FLOW:
    choose_role → phone_number → sms_code → ma'lumotlar → done
    """
    
    # Rol tanlash
    choose_role = State()
    
    # Telefon va SMS
    phone_number = State()
    sms_code = State()
    
    # Haydovchi ma'lumotlari
    driver_full_name = State()
    driver_car_model = State()
    driver_car_color = State()
    driver_car_number = State()
    driver_license = State()  # Ixtiyoriy
    
    # Yo'lovchi ma'lumotlari
    passenger_full_name = State()
    passenger_gender = State()
    passenger_age = State()
