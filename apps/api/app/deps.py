"""FastAPI dependency-injection helpers.

`get_session`              — yields an AsyncSession (re-exported from db/session.py).
`get_optional_token`       — extracts a Bearer token from the Authorization header.
`get_current_user_id`      — JWT-decodes the token to a user_id (None if absent/invalid).
`get_authenticated_user_id`— same but raises 401 when missing.

Routes that require auth depend on `get_authenticated_user_id`; routes that
optionally surface user-scoped data (none yet in M0.3) depend on
`get_current_user_id`.

The current-user resolution stops at user_id (UUID string) for now. M0.6+
can layer a `get_current_user()` that loads the User ORM row when models exist.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.core.security import decode_access_token
from app.db.session import get_session  # re-export for routers

__all__ = [
    "get_session",
    "get_optional_token",
    "get_current_user_id",
    "get_authenticated_user_id",
]


def get_optional_token(authorization: str | None = Header(default=None)) -> str | None:
    """Return the Bearer token portion of the Authorization header, or None."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_current_user_id(token: str | None = Depends(get_optional_token)) -> str | None:
    """Decode the bearer token to a user_id (sub claim). None if absent or invalid."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


def get_authenticated_user_id(
    user_id: str | None = Depends(get_current_user_id),
) -> str:
    """Same as `get_current_user_id` but 401s when missing."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_id
