"""Auth endpoints — STUB implementations until M1.x.

Per plan v1.2 §3 (MVP scope) and §7 (API design):
    POST /auth/login    — returns AuthResponse (JWT + user_id)
    POST /auth/register — creates user, returns AuthResponse

These stubs reserve the URL surface and return RFC 7807 envelopes with
status 501 (Not Implemented). M1.x replaces them with real flows that:
  - hash incoming passwords via app.core.security.hash_password (argon2id)
  - look up users via the SQLAlchemy session (M0.6+ models)
  - issue tokens via app.core.security.create_access_token (HS256, 30d TTL)

Pydantic validation runs before the handler, so a malformed body still
returns 422 (request validation error) rather than 501 (handler reached
but unimplemented). Tests verify this precedence.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])

_NOT_IMPLEMENTED_DETAIL = (
    "auth/{op} is reserved for M1.x; M0.3 ships only the URL surface and OpenAPI "
    "schema. Real implementation arrives once user-creation flow is wired."
)


@router.post(
    "/login",
    response_model=AuthResponse,
    responses={
        501: {"description": "Not implemented (M0.3 stub; M1.x ships real impl)."},
        401: {"description": "Invalid credentials (returned by M1.x impl)."},
    },
)
async def login(req: LoginRequest) -> AuthResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_NOT_IMPLEMENTED_DETAIL.format(op="login"),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    responses={
        501: {"description": "Not implemented (M0.3 stub; M1.x ships real impl)."},
        409: {"description": "Email already registered (returned by M1.x impl)."},
    },
)
async def register(req: RegisterRequest) -> AuthResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_NOT_IMPLEMENTED_DETAIL.format(op="register"),
    )
