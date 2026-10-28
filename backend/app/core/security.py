"""Password hashing, token generation and constant-time comparison helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date, datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Argon2id is the argon2-cffi default type; set explicit, production-minded cost.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


# --------------------------------------------------------------------------- #
# Opaque tokens (session tokens, telegram link tokens)
# --------------------------------------------------------------------------- #
def generate_token(nbytes: int = 32) -> str:
    """Return a cryptographically secure, URL-safe token (never stored in clear)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Hash an opaque token for storage (SHA-256 is sufficient: tokens are 256-bit random)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# --------------------------------------------------------------------------- #
# Payment reference generator
# --------------------------------------------------------------------------- #
def generate_payment_reference(payment_date: date) -> str:
    return f"PAY-{payment_date.strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
