import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()  # Argon2id defaults


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    if not stored_hash or not password:
        return False
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


_DUMMY = hash_password("dummy-password-for-timing")


def dummy_verify(password: str) -> None:
    """Constant-ish work for unknown users (reduces user-enumeration timing signal)."""
    verify_password(_DUMMY, password)


def policy_errors(password: str, username: str = "", full_name: str = "") -> list[str]:
    s = get_settings()
    errs = []
    if len(password) < s.password_min_length:
        errs.append(f"at least {s.password_min_length} characters")
    if not re.search(r"[A-Z]", password):
        errs.append("an upper-case letter")
    if not re.search(r"[a-z]", password):
        errs.append("a lower-case letter")
    if not re.search(r"\d", password):
        errs.append("a digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        errs.append("a special character")
    low = password.lower()
    if username and username.lower() in low:
        errs.append("must not contain the username")
    for part in full_name.lower().split():
        if len(part) >= 4 and part in low:
            errs.append("must not contain your name")
            break
    return errs
