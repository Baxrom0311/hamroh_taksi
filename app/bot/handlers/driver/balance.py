"""
app/bot/handlers/driver/balance.py
"""

from ..base import *
from app.models.transaction import create_transaction, TransactionType
from app.bot.states.driver import DriverStates
from app.bot.keyboards.driver import get_driver_main_menu, get_balance_keyboard
from aiogram.filters import StateFilter
router = Router()


@router.message(F.text == "💰 Balans")
@with_driver_session  # ✅ Decorator qo'shildi
async def show_balance(message: Message, session: AsyncSession, driver: Driver):
    """
    Balans ko'rsatish
    
    ✅ REFACTORED: Decorator ishlatadi, session va driver avtomatik
    """
    await message.answer(
        f"💰 <b>Balans</b>\n\n"
        f"Joriy balans: <b>{driver.balance:,} so'm</b>\n\n"
        f"💳 Balansni to'ldirish uchun:\n"
        f"'To'ldirish' tugmasini bosing",
        reply_markup=get_balance_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "topup_balance")
async def topup_balance_start(callback: CallbackQuery, state: FSMContext):
    """Balans to'ldirish boshlash"""
    await callback.message.edit_text( # type: ignore
        "💳 <b>Balans to'ldirish</b>\n\n"
        "Qadamlar:\n"
        "1. Quyidagi kartaga pul o'tkazing\n"
        "2. Chekni yuklang\n\n"
        "💳 Karta raqam:\n"
        "<code>9860 1901 0420 2980</code>\n\n"
        "👤 Ism: <b>Baxrom Reyimberganov</b>\n\n"
        "Summani kiriting (so'm):"
    )
    await state.set_state(DriverStates.balance_topup)
    await callback.answer()


@router.message(DriverStates.balance_topup, F.text)
async def topup_amount_entered(message: Message, state: FSMContext):
    """Summa kiritildi"""
    try:
        if message.text is None or not message.text.isdigit():
            await message.answer("❌ Iltimos, summa kiriting")
            return
        amount = int(message.text.replace(" ", "").replace(",", ""))
        
        if amount < 10000:
            await message.answer("❌ Minimal summa: 10,000 so'm")
            return
        
        await state.update_data(topup_amount=amount)
        
        await message.answer(
            f"✅ Summa: <b>{amount:,} so'm</b>\n\n"
            f"📸 Chekni yuboring:"
        )
        
        await state.set_state(DriverStates.balance_receipt)
    
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting")


@router.message(DriverStates.balance_receipt, F.photo)
@with_driver_session  # ✅ Decorator
async def receipt_uploaded(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    """
    Chek yuklandi
    
    ✅ REFACTORED: 15 qator → 5 qator
    """
    if message.photo is None:
        await message.answer("Xatolik: rasm topilmadi")
        return
    
    photo = message.photo[-1]
    data = await state.get_data()
    amount = data['topup_amount']
    
    # Transaction yaratish
    transaction = await create_transaction(
        session,
        driver_id=driver.driver_id,
        amount=amount,
        type=TransactionType.DEPOSIT,
        receipt_file_id=photo.file_id,
        description=f"Balans to'ldirish: {amount:,} so'm"
    )
    
    await session.commit()
    
    await message.answer(
        f"✅ <b>So'rov yuborildi!</b>\n\n"
        f"Summa: <b>{amount:,} so'm</b>\n"
        f"So'rov ID: #{transaction.transaction_id}\n\n"
        f"⏳ Admin ko'rib chiqadi (odatda 1 soat ichida)\n\n"
        f"Holat haqida xabar beramiz!",
        reply_markup=get_driver_main_menu(),
        parse_mode="HTML"
    )
    
    logger.info(
        f"Balance topup request: driver={driver.driver_id}, "
        f"amount={amount}, transaction={transaction.transaction_id}"
    )
    
    await state.clear()




@router.message(
    StateFilter(
        DriverStates.balance_topup,
        DriverStates.balance_receipt
    ),
    F.text == "❌ Bekor qilish"
)
async def cancel_balance_topup(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Balans to‘ldirish bekor qilindi",
        reply_markup=get_driver_main_menu()
    )


# Fallback cancel — balansdan tashqari hollarda faqat holatni tozalaymiz
@router.message(StateFilter("*"), F.text == "❌ Bekor qilish")
@with_driver_session
async def cancel_fallback(message: Message, session: AsyncSession, driver: Driver, state: FSMContext):
    state_name = await state.get_state()
    if state_name in (
        DriverStates.balance_topup.state,
        DriverStates.balance_receipt.state
    ):
        # Balans cancel maxsus handlerga tegishli
        return
    await state.clear()
    await message.answer("❌ Bekor qilindi", reply_markup=get_driver_main_menu())

__all__ = ['router']
