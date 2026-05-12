"""Profile service — read/write `users.strategy_profile` JSONB column.

Per plan v1.2 §7 + §9.9 + §17 M1.17.

Two operations:

  get_profile(session, user_id) -> UserStrategyProfile | None
      Returns the user's profile from `users.strategy_profile`. None
      when the column is `{}` (empty JSONB — the M0.2 default for new
      users who haven't customized).

  replace_profile(session, user_id, profile) -> UserStrategyProfile
      UPDATE users SET strategy_profile = :profile WHERE id = :user_id.
      Returns the persisted profile (echo of input on success).

The engine's `UserStrategyProfile` (Pydantic BaseModel, `engine.profiles`)
is the source of truth for the shape AND validation rules; this module
serializes via `model_dump(mode="json")` and parses back via the same
model. No re-implemented defaults here.

Defaults: the engine package owns them via Pydantic Field defaults on
`UserStrategyProfile`. When a row's `strategy_profile` is empty (`{}`),
`get_profile` returns None — the router converts that to a freshly-
constructed default `UserStrategyProfile()` for the GET response.
"""

from __future__ import annotations

import json

from engine.profiles import UserStrategyProfile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_profile(
    *,
    session: AsyncSession,
    user_id: str,
) -> UserStrategyProfile | None:
    """Return the user's persisted strategy profile, or None if unset.

    `unset` means `users.strategy_profile = '{}'::jsonb` (the M0.2
    default). The router converts None to a default-constructed
    `UserStrategyProfile` for the response — this lets a fresh user
    GET `/profile` and see sensible defaults rather than 404.
    """
    result = await session.execute(
        text("SELECT strategy_profile FROM users WHERE id = :user_id;"),
        {"user_id": user_id},
    )
    row = result.first()
    if row is None:
        return None
    raw = row[0]
    if not raw:  # empty dict {} or null
        return None
    # The JSONB column round-trips as a Python dict via psycopg's default codec.
    if isinstance(raw, str):
        raw = json.loads(raw)
    return UserStrategyProfile(**raw)


async def replace_profile(
    *,
    session: AsyncSession,
    user_id: str,
    profile: UserStrategyProfile,
) -> UserStrategyProfile:
    """Persist `profile` as the user's strategy profile (full replacement).

    Returns the input on success. Idempotent — calling twice with the
    same profile produces the same persisted JSONB.

    Raises:
        ValueError: When the user_id doesn't exist in `users`. The
            router maps this to 404.
    """
    payload = profile.model_dump(mode="json")
    result = await session.execute(
        text(
            """
            UPDATE users
            SET strategy_profile = CAST(:payload AS jsonb)
            WHERE id = :user_id
            RETURNING id;
            """
        ),
        {"user_id": user_id, "payload": json.dumps(payload)},
    )
    if result.first() is None:
        raise ValueError(f"user_id {user_id} not found")
    await session.commit()
    return profile
