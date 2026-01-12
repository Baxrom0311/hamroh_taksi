"""
app/bot/handlers/registration.py
RO'YXATDAN O'TISH HANDLER (PYLANCE-CLEAN)
"""

from aiogram import Router, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.core.database import get_session
from app.models.user import UserRole, create_user
from app.models.driver import create_driver
from app.models.passenger import Gender, create_passenger
from app.bot.states.registration import RegistrationStates

router = Router()


# =========================================================
# HELPERS (TYPE SAFE)
# =========================================================

def require_text(message: Message) -> str:
    if message.text is None:
        raise ValueError("Message text is None")
    return message.text


def require_user(message: Message):
    if message.from_user is None:
        raise ValueError("Telegram user not found")
    return message.from_user


# =========================================================
# 1. ROLE SELECTION
# =========================================================

@router.message(
    RegistrationStates.choose_role,
    F.text & F.text.in_(["🚗 Haydovchi sifatida", "👤 Yo'lovchi sifatida"]),
)
async def choose_role(message: Message, state: FSMContext) -> None:
    text = require_text(message)

    role = "driver" if "Haydovchi" in text else "passenger"
    await state.update_data(role=role)

    await message.answer(
        "📱 <b>Telefon raqamingizni yuboring</b>\n\n"
        "Format: <code>+998901234567</code> yoki tugmani bosing:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="📱 Telefon raqamni yuborish",
                        request_contact=True,
                    )
                ]
            ],
            resize_keyboard=True,
        ),
    )

    await state.set_state(RegistrationStates.phone_number)


# =========================================================
# 2. PHONE (CONTACT)
# =========================================================

@router.message(RegistrationStates.phone_number, F.contact)
async def phone_contact(message: Message, state: FSMContext) -> None:
    contact = message.contact
    if contact is None:
        return

    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = f"+{phone}"

    await state.update_data(phone_number=phone)

    import random
    sms_code = "".join(str(random.randint(0, 9)) for _ in range(6))
    await state.update_data(sms_code=sms_code)

    await message.answer(
        f"📨 SMS kod yuborildi\n\n"
        f"Telefon: <code>{phone}</code>\n"
        f"<b>Demo kod: {sms_code}</b>\n\n"
        "Kodni kiriting:",
        reply_markup=ReplyKeyboardRemove(),
    )

    await state.set_state(RegistrationStates.sms_code)


# =========================================================
# 2.1 PHONE (TEXT)
# =========================================================

@router.message(RegistrationStates.phone_number, F.text)
async def phone_text(message: Message, state: FSMContext) -> None:
    text = require_text(message).strip()

    if not text.startswith("+998") or len(text) != 13:
        await message.answer(
            "❌ Noto'g'ri format\n"
            "To'g'ri: <code>+998901234567</code>"
        )
        return

    await state.update_data(phone_number=text)

    import random
    sms_code = "".join(str(random.randint(0, 9)) for _ in range(6))
    await state.update_data(sms_code=sms_code)

    await message.answer(
        f"📨 SMS kod: <b>{sms_code}</b> (Demo)\n\nKodni kiriting:"
    )

    await state.set_state(RegistrationStates.sms_code)


# =========================================================
# 3. SMS VERIFY
# =========================================================

@router.message(RegistrationStates.sms_code, F.text)
async def sms_code_verify(message: Message, state: FSMContext) -> None:
    text = require_text(message).strip()
    data = await state.get_data()

    if text != data.get("sms_code"):
        await message.answer("❌ Noto'g'ri kod, qayta urinib ko'ring:")
        return

    await message.answer("✅ Telefon tasdiqlandi")

    if data.get("role") == "driver":
        await message.answer("🚗 To'liq ismingizni kiriting:")
        await state.set_state(RegistrationStates.driver_full_name)
    else:
        await message.answer("👤 To'liq ismingizni kiriting:")
        await state.set_state(RegistrationStates.passenger_full_name)


# =========================================================
# 4. DRIVER REGISTRATION
# =========================================================

@router.message(RegistrationStates.driver_full_name, F.text)
async def driver_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=require_text(message))
    await message.answer("🚙 Mashina modeli:")
    await state.set_state(RegistrationStates.driver_car_model)


@router.message(RegistrationStates.driver_car_model, F.text)
async def driver_car_model(message: Message, state: FSMContext) -> None:
    await state.update_data(car_model=require_text(message))
    await message.answer("🎨 Mashina rangi:")
    await state.set_state(RegistrationStates.driver_car_color)


@router.message(RegistrationStates.driver_car_color, F.text)
async def driver_car_color(message: Message, state: FSMContext) -> None:
    await state.update_data(car_color=require_text(message))
    await message.answer("🔢 Mashina raqami (01 A 123 BC):")
    await state.set_state(RegistrationStates.driver_car_number)


@router.message(RegistrationStates.driver_car_number, F.text)
async def driver_car_number(message: Message, state: FSMContext) -> None:
    car_number = require_text(message).upper().strip()
    user = require_user(message)

    data = await state.get_data()

    try:
        async with get_session() as session:
            await create_user(
                session,
                user_id=user.id,
                phone_number=data["phone_number"],
                first_name=user.first_name,
                last_name=user.last_name,
                username=user.username,
                role=UserRole.DRIVER,
            )

            driver = await create_driver(
                session,
                user_id=user.id,
                full_name=data["full_name"],
                phone_number=data["phone_number"],
                car_model=data["car_model"],
                car_color=data["car_color"],
                car_number=car_number,
            )

            await session.commit()

            await message.answer(
                f"🎉 Ro'yxatdan o'tdingiz!\n\n"
                f"👤 {driver.full_name}\n"
                f"🚗 {driver.car_model} ({driver.car_color})\n"
                f"🔢 {driver.car_number}"
            )

    except Exception as e:
        logger.error(e)
        await message.answer("❌ Xatolik yuz berdi")

    finally:
        await state.clear()


# =========================================================
# 5. PASSENGER REGISTRATION
# =========================================================

@router.message(RegistrationStates.passenger_full_name, F.text)
async def passenger_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=require_text(message))
    await message.answer(
        "🚻 Jinsingiz:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="👨 Erkak"), KeyboardButton(text="👩 Ayol")]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(RegistrationStates.passenger_gender)


@router.message(
    RegistrationStates.passenger_gender,
    F.text & F.text.in_(["👨 Erkak", "👩 Ayol"]),
)
async def passenger_gender(message: Message, state: FSMContext) -> None:
    text = require_text(message)
    gender = Gender.MALE if "Erkak" in text else Gender.FEMALE
    await state.update_data(gender=gender)

    await message.answer("🎂 Yoshingiz:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegistrationStates.passenger_age)


@router.message(RegistrationStates.passenger_age, F.text)
async def passenger_age(message: Message, state: FSMContext) -> None:
    text = require_text(message)

    if not text.isdigit():
        await message.answer("❌ Faqat raqam kiriting")
        return

    age = int(text)
    if not 14 <= age <= 100:
        await message.answer("❌ Yosh 14-100 oralig'ida bo'lishi kerak")
        return

    user = require_user(message)
    data = await state.get_data()

    async with get_session() as session:
        await create_user(
            session,
            user_id=user.id,
            phone_number=data["phone_number"],
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            role=UserRole.PASSENGER,
        )

        passenger = await create_passenger(
            session,
            user_id=user.id,
            full_name=data["full_name"],
            gender=data["gender"],
            age=age,
            phone_number=data["phone_number"],
        )

        await session.commit()

        await message.answer(
            f"🎉 Ro'yxatdan o'tdingiz!\n\n"
            f"👤 {passenger.full_name}\n"
            f"🎂 {passenger.age} yosh"
        )

    await state.clear()


__all__ = ["router"]
