"""
tests/unit/test_utils/test_validators.py

VALIDATORS UNIT TESTS

BU FAYL NIMA QILADI:
- validators.py funksiyalarini test qilish
- Edge case'larni tekshirish
- Error handling test qilish

ISHLATISH:
    pytest tests/unit/test_utils/test_validators.py -v
"""
import pytest
from app.utils.validators import (
    validate_phone,
    is_valid_uzbek_phone,
    validate_car_number,
    validate_age,
    validate_balance_amount,
    sanitize_input,
    validate_email
)


class TestPhoneValidation:
    """Telefon raqam validation testlari"""
    
    def test_valid_phone_with_plus(self):
        """To'g'ri telefon (+998 bilan)"""
        is_valid, formatted = validate_phone("+998901234567")
        assert is_valid is True
        assert formatted == "+998901234567"
    
    def test_valid_phone_without_plus(self):
        """To'g'ri telefon (+ siz)"""
        is_valid, formatted = validate_phone("998901234567")
        assert is_valid is True
        assert formatted == "+998901234567"
    
    def test_valid_phone_9_digits(self):
        """To'g'ri telefon (9 raqam - 998 qo'shiladi)"""
        is_valid, formatted = validate_phone("901234567")
        assert is_valid is True
        assert formatted == "+998901234567"
    
    def test_valid_phone_with_spaces(self):
        """To'g'ri telefon (bo'sh joylar bilan)"""
        is_valid, formatted = validate_phone("+998 90 123 45 67")
        assert is_valid is True
        assert formatted == "+998901234567"
    
    def test_valid_phone_with_dashes(self):
        """To'g'ri telefon (tire bilan)"""
        is_valid, formatted = validate_phone("998-90-123-45-67")
        assert is_valid is True
        assert formatted == "+998901234567"
    
    def test_invalid_phone_too_short(self):
        """Noto'g'ri telefon (juda qisqa)"""
        is_valid, formatted = validate_phone("12345")
        assert is_valid is False
        assert formatted is None
    
    def test_invalid_phone_wrong_operator(self):
        """Noto'g'ri telefon (noto'g'ri operator kodi)"""
        is_valid, formatted = validate_phone("998101234567")
        assert is_valid is False
        assert formatted is None
    
    def test_invalid_phone_letters(self):
        """Noto'g'ri telefon (harflar bilan)"""
        is_valid, formatted = validate_phone("998abcdefghi")
        assert is_valid is False
        assert formatted is None
    
    def test_is_valid_uzbek_phone_helper(self):
        """is_valid_uzbek_phone helper funksiyasi"""
        assert is_valid_uzbek_phone("+998901234567") is True
        assert is_valid_uzbek_phone("invalid") is False


class TestCarNumberValidation:
    """Mashina raqami validation testlari"""
    
    def test_valid_car_number_with_spaces(self):
        """To'g'ri mashina raqami (bo'sh joylar bilan)"""
        is_valid, formatted = validate_car_number("01 A 123 BC")
        assert is_valid is True
        assert formatted == "01 A 123 BC"
    
    def test_valid_car_number_without_spaces(self):
        """To'g'ri mashina raqami (bo'sh joysiz)"""
        is_valid, formatted = validate_car_number("01A123BC")
        assert is_valid is True
        assert formatted == "01 A 123 BC"
    
    def test_valid_car_number_lowercase(self):
        """To'g'ri mashina raqami (kichik harflar)"""
        is_valid, formatted = validate_car_number("01a123bc")
        assert is_valid is True
        assert formatted == "01 A 123 BC"
    
    def test_invalid_car_number_wrong_format(self):
        """Noto'g'ri mashina raqami (noto'g'ri format)"""
        is_valid, formatted = validate_car_number("invalid")
        assert is_valid is False
        assert formatted is None
    
    def test_invalid_car_number_missing_letters(self):
        """Noto'g'ri mashina raqami (harflar yo'q)"""
        is_valid, formatted = validate_car_number("01123456")
        assert is_valid is False
        assert formatted is None


class TestAgeValidation:
    """Yosh validation testlari"""
    
    def test_valid_age_minimum(self):
        """To'g'ri yosh (minimal: 14)"""
        is_valid, error = validate_age(14)
        assert is_valid is True
        assert error is None
    
    def test_valid_age_medium(self):
        """To'g'ri yosh (o'rtacha)"""
        is_valid, error = validate_age(25)
        assert is_valid is True
        assert error is None
    
    def test_valid_age_maximum(self):
        """To'g'ri yosh (maksimal: 100)"""
        is_valid, error = validate_age(100)
        assert is_valid is True
        assert error is None
    
    def test_invalid_age_too_young(self):
        """Noto'g'ri yosh (juda kichik)"""
        is_valid, error = validate_age(10)
        assert is_valid is False
        assert "Minimal yosh 14" in error
    
    def test_invalid_age_too_old(self):
        """Noto'g'ri yosh (juda katta)"""
        is_valid, error = validate_age(101)
        assert is_valid is False
        assert "Maksimal yosh 100" in error
    
    def test_custom_age_range(self):
        """Custom yosh range"""
        is_valid, error = validate_age(20, min_age=18, max_age=65)
        assert is_valid is True
        
        is_valid, error = validate_age(70, min_age=18, max_age=65)
        assert is_valid is False


class TestBalanceValidation:
    """Balans validation testlari"""
    
    def test_valid_balance(self):
        """To'g'ri balans"""
        is_valid, error = validate_balance_amount(50000)
        assert is_valid is True
        assert error is None
    
    def test_invalid_balance_too_small(self):
        """Noto'g'ri balans (juda oz)"""
        is_valid, error = validate_balance_amount(5000)
        assert is_valid is False
        assert "Minimal summa" in error
    
    def test_invalid_balance_too_large(self):
        """Noto'g'ri balans (juda ko'p)"""
        is_valid, error = validate_balance_amount(20000000)
        assert is_valid is False
        assert "Maksimal summa" in error
    
    def test_custom_balance_range(self):
        """Custom balans range"""
        is_valid, error = validate_balance_amount(
            15000,
            min_amount=10000,
            max_amount=100000
        )
        assert is_valid is True


class TestInputSanitization:
    """Input sanitization testlari"""
    
    def test_sanitize_html_tags(self):
        """HTML tag'larni olib tashlash"""
        dangerous = "<script>alert('xss')</script>Hello"
        safe = sanitize_input(dangerous)
        assert "<script>" not in safe
        assert "alert('xss')" in safe
    
    def test_sanitize_sql_injection(self):
        """SQL injection oldini olish"""
        dangerous = "'; DROP TABLE users; --"
        safe = sanitize_input(dangerous)
        assert "DROP TABLE" not in safe
        assert "--" not in safe
    
    def test_sanitize_keeps_clean_text(self):
        """Toza text'ni o'zgartirmaydi"""
        clean = "Hello World"
        safe = sanitize_input(clean)
        assert safe == "Hello World"
    
    def test_sanitize_removes_quotes(self):
        """Quotes olib tashlash"""
        text = "Hello 'World' \"Test\""
        safe = sanitize_input(text)
        assert "'" not in safe
        assert '"' not in safe
    
    def test_sanitize_trims_whitespace(self):
        """Bo'sh joylarni tozalash"""
        text = "   Hello    World   "
        safe = sanitize_input(text)
        assert safe == "Hello World"


class TestEmailValidation:
    """Email validation testlari"""
    
    def test_valid_email(self):
        """To'g'ri email"""
        is_valid, formatted = validate_email("user@example.com")
        assert is_valid is True
        assert formatted == "user@example.com"
    
    def test_valid_email_with_subdomain(self):
        """To'g'ri email (subdomain bilan)"""
        is_valid, formatted = validate_email("user@mail.example.com")
        assert is_valid is True
    
    def test_valid_email_uppercase(self):
        """To'g'ri email (katta harflar)"""
        is_valid, formatted = validate_email("USER@EXAMPLE.COM")
        assert is_valid is True
        assert formatted == "user@example.com"  # Lowercase'ga convert
    
    def test_invalid_email_no_at(self):
        """Noto'g'ri email (@ yo'q)"""
        is_valid, formatted = validate_email("userexample.com")
        assert is_valid is False
        assert formatted is None
    
    def test_invalid_email_no_domain(self):
        """Noto'g'ri email (domain yo'q)"""
        is_valid, formatted = validate_email("user@")
        assert is_valid is False
        assert formatted is None
    
    def test_invalid_email_no_extension(self):
        """Noto'g'ri email (extension yo'q)"""
        is_valid, formatted = validate_email("user@example")
        assert is_valid is False
        assert formatted is None


# ============================================
# PARAMETRIZED TESTS
# ============================================

@pytest.mark.parametrize("phone,expected_valid", [
    ("+998901234567", True),
    ("998901234567", True),
    ("901234567", True),
    ("+998 90 123 45 67", True),
    ("invalid", False),
    ("12345", False),
    ("998101234567", False),
])
def test_phone_validation_parametrized(phone: str, expected_valid: bool):
    """Parametrized phone validation test"""
    is_valid, _ = validate_phone(phone)
    assert is_valid == expected_valid


@pytest.mark.parametrize("car_number,expected_valid", [
    ("01 A 123 BC", True),
    ("01A123BC", True),
    ("75X777XX", True),
    ("invalid", False),
    ("123456", False),
])
def test_car_number_parametrized(car_number: str, expected_valid: bool):
    """Parametrized car number validation test"""
    is_valid, _ = validate_car_number(car_number)
    assert is_valid == expected_valid


# ============================================
# RUN TESTS
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
