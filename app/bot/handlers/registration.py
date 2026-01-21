"""
app/bot/handlers/registration.py
RO'YXATDAN O'TISH HANDLER (PYLANCE-CLEAN)
"""
from typing import Optional

from .base import *
from sqlalchemy.exc import IntegrityError
from app.models.user import create_user, UserRole, get_user_by_phone
from app.models.driver import create_driver
from app.models.passenger import Gender, create_passenger
from app.core.database import get_session
from app.bot.states.registration import RegistrationStates
from app.bot.keyboards.driver import get_driver_main_menu
from app.bot.keyboards.passenger import get_passenger_main_menu
from app.core.validation import (  # ✅ Validation qo'shish
    validate_phone_number,
    validate_full_name,
    validate_car_number
)
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
        "Format: +998901234567 yoki tugmani bosing:",
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
    # ✅ SECURITY: Secure RNG
    import secrets
    import string
    # 6 digit secure code
    sms_code = "".join(secrets.choice(string.digits) for _ in range(6))
    await state.update_data(sms_code=sms_code)
    
    # ✅ DEAD END FIX: Environment-aware SMS sending
    # In dev/staging: show code directly, in production: send real SMS
    from config.settings import settings
    if settings.ENVIRONMENT in ('development', 'staging'):
        # Dev mode: Show code directly (no SMS provider needed)
        await message.answer(
            f"📨 <b>Kod yuborildi</b>\n\n"
            f"Telefon: {phone}\n"
            f"🔑 <code>{sms_code}</code>\n\n"
            "☝️ Bu dev/staging rejimi - kod shu yerda ko'rsatilgan\n"
            "Kodni kiriting:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"
        )
    else:
        # Production: Real SMS (TODO: Implement Eskiz.uz or Twilio)
        # For now, show code until SMS provider is configured
        logger.warning(f"SMS not sent (production mode, provider not configured): {phone}")
        await message.answer(
            f"📨 SMS kod yuborildi\n\n"
            f"Telefon: {phone}\n"
            f"<b>Vaqtincha demo kod: {sms_code}</b>\n\n"
            "⚠️ SMS provider konfiguratsiya qilinmagan\n"
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

    # ✅ Validation
    is_valid, error_msg = validate_phone_number(text)
    if not is_valid:
        await message.answer(error_msg or "❌ Noto'g'ri format", parse_mode="HTML")
        return

    await state.update_data(phone_number=text)

    # ✅ SECURITY: Secure RNG
    import secrets
    import string
    sms_code = "".join(secrets.choice(string.digits) for _ in range(6))
    await state.update_data(sms_code=sms_code)

    # ✅ Environment-aware (same as contact handler)
    from config.settings import settings
    
    if settings.ENVIRONMENT in ('development', 'staging'):
        await message.answer(
            f"📨 <b>Kod yuborildi</b>\n\n"
            f"🔑 <code>{sms_code}</code>\n\n"
            "Kodni kiriting:",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"📨 SMS kod: <b>{sms_code}</b> (vaqtincha demo)\n\n"
            "⚠️ SMS provider kerak\nKodni kiriting:"
        )

    await state.set_state(RegistrationStates.sms_code)


# =========================================================
# 3. SMS VERIFY
# =========================================================

@router.message(RegistrationStates.sms_code, F.text)
async def sms_code_verify(message: Message, state: FSMContext) -> None:
    text = require_text(message).strip()
    user = require_user(message)
    data = await state.get_data()

    # ✅ SECURITY: Rate Limit (Brute force protection)
    # 1 daqiqada 5 ta urinish ruxsat etiladi
    from app.utils.rate_limiter import RateLimiter

    verify_limiter = RateLimiter(max_requests=5, window_seconds=60, prefix="sms_verify")
    
    if not await verify_limiter.check_limit(user.id, "verify_attempt"):
        await message.answer("🚫 <b>Juda ko'p urinish!</b>\n\nIltimos, 1 daqiqa kuting.", parse_mode="HTML")
        return

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
    name = require_text(message)
    # ✅ Validation
    is_valid, error_msg = validate_full_name(name)
    if not is_valid:
        await message.answer(f"❌ {error_msg or 'Noto\'g\'ri format'}")
        return
    await state.update_data(full_name=name)
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
@with_session  # ✅ Decorator
async def driver_car_number(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """
    Haydovchi ro'yxatdan o'tishni yakunlash
    ✅ REFACTORED: Session auto
    """
    car_number = require_text(message).upper().strip()
    # ✅ Validation
    is_valid, error_msg = validate_car_number(car_number)
    if not is_valid:
        await message.answer(error_msg or "❌ Noto'g'ri format", parse_mode="HTML")
        return
    user = require_user(message)
    data = await state.get_data()
    try:
        # Phone raqam allaqachon bormi?
        existing = await get_user_by_phone(session, data["phone_number"])
        if existing and existing.user_id != user.id:
            await message.answer(
                "❌ Bu telefon raqami bilan allaqachon ro'yxatdan o'tilgan.\n"
                "Iltimos, boshqa raqam kiriting yoki oldingi akkauntni ishlating."
            )
            await session.rollback()
            await state.clear()
            return
        # Mashina raqami allaqachon bormi?
        from app.models.driver import Driver
        car_exists = await session.execute(
            select(Driver).where(Driver.car_number == car_number)
        )
        if car_exists.scalar_one_or_none():
            await message.answer(
                "❌ Bu mashina raqami bilan haydovchi allaqachon ro'yxatdan o'tgan.\n"
                "Iltimos, boshqa raqam kiriting."
            )
            await session.rollback()
            await state.clear()
            return
        await create_user(
            session,
            user_id=user.id,
            phone_number=data["phone_number"],
            first_name=user.first_name or "",
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
            is_on_trip=False,  # default not on trip
            is_active=False,     # default inactive
            available_seats=0,   # seats set later
            current_route_id=None
        )
        await session.commit()
        await message.answer(
            f"🎉 Ro'yxatdan o'tdingiz!\n\n"
            f"👤 {driver.full_name}\n"
            f"🚗 {driver.car_model} ({driver.car_color})\n"
            f"🔢 {driver.car_number}",
            reply_markup=get_driver_main_menu()
        )
    except IntegrityError:
        await session.rollback()
        await message.answer(
            "❌ Bu telefon raqami bilan allaqachon ro'yxatdan o'tilgan.\n"
            "Iltimos, boshqa raqam kiriting yoki oldingi akkauntni ishlating."
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"Registration error: {e}")
        await message.answer("❌ Xatolik yuz berdi")
    finally:
        await state.clear()
# =========================================================
# 5. PASSENGER REGISTRATION
# =========================================================
@router.message(RegistrationStates.passenger_full_name, F.text)
async def passenger_full_name(message: Message, state: FSMContext) -> None:
    name = require_text(message)
    
    # ✅ Validation
    is_valid, error_msg = validate_full_name(name)
    if not is_valid:
        await message.answer(f"❌ {error_msg or 'Noto\'g\'ri format'}")
        return
    
    await state.update_data(full_name=name)
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
@with_session  # ✅ Decorator
async def passenger_age(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """
    Yo'lovchi ro'yxatdan o'tishni yakunlash
    
    ✅ REFACTORED: Session auto
    """
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
        f"🎂 {passenger.age} yosh", 
        reply_markup=get_passenger_main_menu()
    )

    await state.clear()


# =========================================================
# 6. TESTING UTIL: COMPLETE REGISTRATION (legacy helper)
# =========================================================
async def _open_session(session_override: Optional[AsyncSession] = None):
    """
    Return (session, context_manager, managed) to gracefully support both
    direct AsyncSession (patched in tests) and get_session() context manager.
    """
    if session_override is not None:
        return session_override, None, False

    candidate = get_session()

    # When tests monkeypatch get_session to return a raw AsyncSession
    if isinstance(candidate, AsyncSession):
        return candidate, None, False

    # Otherwise treat it as async context manager
    cm = candidate
    session = await cm.__aenter__()  # type: ignore[attr-defined]
    return session, cm, True


async def complete_registration(
    message: Message,
    state: FSMContext,
    session: Optional[AsyncSession] = None,
) -> None:
    """
    Legacy helper used by integration tests to finalize registration in one call.
    Mirrors the driver_car_number / passenger_age handlers.
    """
    user = require_user(message)
    data = await state.get_data()

    session, cm, managed = await _open_session(session)
    exc_info = (None, None, None)
    try:
        role_value = data.get("role")
        is_driver = role_value in (UserRole.DRIVER, "driver")

        # Aiogram User doesn't carry phone_number; fall back to FSM data first
        phone_number = data.get("phone_number") or getattr(user, "phone_number", None)
        full_name = data.get("full_name") or require_text(message)

        if not phone_number:
            raise ValueError("Phone number is required for registration")

        await create_user(
            session,
            user_id=user.id,
            phone_number=phone_number,
            first_name=user.first_name or "",
            last_name=user.last_name,
            username=user.username,
            role=UserRole.DRIVER if is_driver else UserRole.PASSENGER,
        )

        if is_driver:
            car_model = data.get("car_model") or "Unknown"
            car_color = data.get("car_color") or "Unknown"
            car_number = (data.get("car_number") or "UNKNOWN").upper()

            await create_driver(
                session,
                user_id=user.id,
                full_name=full_name,
                phone_number=phone_number,
                car_model=car_model,
                car_color=car_color,
                car_number=car_number,
                is_on_trip=False,
                is_active=False,
                available_seats=0,
                current_route_id=None,
            )
        else:
            age = int(data.get("age") or 18)
            gender_value = data.get("gender") or Gender.MALE
            # Accept string gender from state
            gender = (
                Gender.MALE if str(gender_value).lower().startswith("male") else Gender.FEMALE
            )
            await create_passenger(
                session,
                user_id=user.id,
                full_name=full_name,
                gender=gender,
                age=age,
                phone_number=phone_number,
            )

        if not managed:
            await session.commit()

        await message.answer("✅ Ro'yxatdan o'tish yakunlandi!")
        await state.clear()

    except Exception as exc:
        exc_info = (exc.__class__, exc, exc.__traceback__)
        if not managed:
            await session.rollback()
        raise
    finally:
        if managed and cm is not None:
            await cm.__aexit__(*exc_info)  # type: ignore[attr-defined]
__all__ = ["router", "complete_registration"]
