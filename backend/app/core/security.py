import re

from passlib.context import CryptContext


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_SPECIAL_CHARS_RE = re.compile(r"[^A-Za-z0-9]")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def validate_password_strength(
    password: str,
    *,
    min_length: int = 10,
    require_uppercase: bool = True,
    require_lowercase: bool = True,
    require_digit: bool = True,
    require_special: bool = True,
) -> list[str]:
    """Return unmet password requirements in Korean."""
    errors: list[str] = []
    if len(password) < min_length:
        errors.append(f"비밀번호는 최소 {min_length}자 이상이어야 합니다.")
    if require_uppercase and not any(ch.isupper() for ch in password):
        errors.append("영문 대문자를 1자 이상 포함해야 합니다.")
    if require_lowercase and not any(ch.islower() for ch in password):
        errors.append("영문 소문자를 1자 이상 포함해야 합니다.")
    if require_digit and not any(ch.isdigit() for ch in password):
        errors.append("숫자를 1자 이상 포함해야 합니다.")
    if require_special and not _SPECIAL_CHARS_RE.search(password):
        errors.append("특수문자를 1자 이상 포함해야 합니다.")
    return errors
