"""Auth request/response schemas.

The schemas are defined in M0.3 so the URL surface is fully documented in
OpenAPI from day one. Real implementations (argon2 verify + JWT issuance +
user creation) land in M1.x — see plan v1.2 §3 / §7 / §15 / §22.

`email` is `str` rather than `EmailStr` here to avoid pulling in the
`email-validator` package; M1.x tightens to `EmailStr` alongside the real
auth flow (when proper validation matters).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """Body for POST /auth/register."""

    email: str  # tightened to EmailStr in M1.x
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Body for POST /auth/login. No length constraints on password — bad
    credentials should reach the verify step (and 401), not 422 at validation."""

    email: str
    password: str


class AuthResponse(BaseModel):
    """Response shape for both /auth/login and /auth/register."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user_id: str
    expires_in_seconds: int
