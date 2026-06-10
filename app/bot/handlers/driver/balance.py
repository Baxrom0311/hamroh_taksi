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


@router.callback_query(F.data == "balance_history")
@with_driver_session
async def balance_history_handler(callback: CallbackQuery, session: AsyncSession, driver: Driver):
    """
    Balans tarixi — so'nggi 10 ta tranzaksiya
    """
    from app.models.transaction import Transaction, TransactionType, TransactionStatus

    result = await session.execute(
        select(Transaction)
        .where(Transaction.driver_id == driver.driver_id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
    )
    transactions = result.scalars().all()

    if not transactions:
        await callback.answer("📊 Tranzaksiyalar tarixi bo'sh", show_alert=True)
        return

    # Tranzaksiyalarni formatlash
    import pytz

    history_text = "📊 <b>Balans tarixi</b>\n\n"
    history_text += f"💰 Joriy balans: <b>{driver.balance:,} so'm</b>\n\n"

    TYPE_EMOJI = {
        TransactionType.DEPOSIT: "💳",
        TransactionType.COMMISSION: "💸",
        TransactionType.WITHDRAWAL: "🔄",
    }

    for idx, tx in enumerate(transactions, 1):
        emoji = TYPE_EMOJI.get(tx.type, "📋")
        # Vaqtni formatlash
        try:
            tx_time = tx.created_at.astimezone(pytz.timezone('Asia/Tashkent'))
            time_str = tx_time.strftime("%H:%M, %d.%m.%Y")
        except Exception:
            time_str = str(tx.created_at)[:16] if tx.created_at else "N/A"

        # Summa belgisi
        if tx.type == TransactionType.COMMISSION:
            amount_str = f"-{tx.amount:,}"
        else:
            amount_str = f"+{tx.amount:,}"

        # Status
        if tx.status == TransactionStatus.APPROVED:
            status = "✅"
        elif tx.status == TransactionStatus.PENDING:
            status = "⏳"
        else:
            status = "❌"

        history_text += (
            f"{idx}. {emoji} {tx.type.value} {status}\n"
            f"   💵 {amount_str} so'm\n"
            f"   📅 {time_str}\n\n"
        )

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            history_text,
            parse_mode="HTML"
        )

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
@router.message(DriverStates.balance_receipt, F.text)
async def balance_receipt_text_fallback(message: Message, state: FSMContext):
    """balance_receipt state da text yuborilsa — rasm so'rash"""
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Balans to'ldirish bekor qilindi", reply_markup=get_driver_main_menu())
        return
    await message.answer(
        "📸 Iltimos, <b>chek rasmini</b> yuboring (text emas).\n"
        "Yoki bekor qilish uchun /cancel buyrug'ini yuboring.",
        parse_mode="HTML"
    )


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