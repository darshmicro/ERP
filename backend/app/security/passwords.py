import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_ph_cache: dict = {}


def _hasher() -> PasswordHasher:
    # Argon2id; cost parameters come from settings (tests lower them for speed; production keeps defaults).
    if "ph" not in _ph_cache:
        cfg = get_settings()
        _ph_cache["ph"] = PasswordHasher(time_cost=cfg.argon2_time_cost, memory_cost=cfg.argon2_memory_kib,
                                         parallelism=cfg.argon2_parallelism)
    return _ph_cache["ph"]


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    if not stored_hash or not password:
        return False
    try:
        return _hasher().verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def dummy_verify(password: str) -> None:
    """Constant-ish work for unknown users (reduces user-enumeration timing signal)."""
    if "dummy" not in _ph_cache:
        _ph_cache["dummy"] = hash_password("dummy-password-for-timing")
    verify_password(_ph_cache["dummy"], password)


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
