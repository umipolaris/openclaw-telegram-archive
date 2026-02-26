from app.core.security import validate_password_strength


def test_password_policy_accepts_strong_password():
    errors = validate_password_strength("StrongPass123!")
    assert errors == []


def test_password_policy_rejects_weak_password():
    errors = validate_password_strength("weakpass")
    assert len(errors) >= 3
    assert any("대문자" in item for item in errors)
    assert any("숫자" in item for item in errors)
    assert any("특수문자" in item for item in errors)


def test_password_policy_can_disable_character_requirements():
    errors = validate_password_strength(
        "simplepass123",
        min_length=10,
        require_uppercase=False,
        require_lowercase=True,
        require_digit=True,
        require_special=False,
    )
    assert errors == []
