from aiogram.fsm.state import State, StatesGroup

# ============================================
# ADMIN STATES (Admin)
# ============================================

class AdminStates(StatesGroup):
    """
    Admin holatlari
    """
    
    # Dashboard
    dashboard = State()
    
    # Tranzaksiyalar
    review_transaction = State()
    
    # Foydalanuvchilar
    manage_users = State()
    block_user = State()
    
    # Sozlamalar
    edit_settings = State()

