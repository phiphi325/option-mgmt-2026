"""JWT and password-hash helpers.

Per plan v1.2 §15:
  - argon2-cffi for password hashing (preferred over bcrypt).
  - HS256 JWT with 30-day TTL; jwt_secret rotated annually.

The actual /auth/login + /auth/register routes land in M1.x once user
creation flow exists. M0.3 ships only the helpers + JWT scaffolding so
downstream modules (deps.py, routers/health.py) can depend on them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time-ish verify; returns False on mismatch (no exception)."""
    try:
        _hasher.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(*, subject: str, extra: dict[str, Any] | None = None) -> str:
    """Create a signed JWT with the configured TTL.

    `subject` is the user UUID (placed in `sub` claim).
    `extra` is merged into the payload (e.g. role claims). Reserved claims
    (sub, iat, exp) cannot be overridden via extra.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = dict(extra or {})
    payload.update(
        {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=settings.jwt_access_token_ttl_seconds)).timestamp()),
        }
    )
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode + verify a JWT. Returns None on any failure (expired, invalid, malformed)."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
