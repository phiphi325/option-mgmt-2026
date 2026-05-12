"""Outcome service — CRUD on the `outcomes` table (M1.17).

Per plan v1.2 §7 + §9.10 + §17 M1.17.

Three operations:

  list_outcomes(session, user_id, since=None, limit=50, cursor=None)
      Cursor-paginated. Cursor encodes `(evaluated_at, id)` of the last
      row in the previous page. Filtered by ownership (rows must belong
      to the authenticated user via the `daily_decisions.user_id` FK).

  create_outcome(session, user_id, request)
      Inserts a new outcome row. Verifies the referenced
      `daily_decision_id` belongs to the user (else 403). Returns 409
      via ValueError when an outcome for that decision already exists
      (the table has UNIQUE on `daily_decision_id` from 0001_init).

  update_outcome(session, user_id, outcome_id, patch)
      Partial update. Verifies ownership transitively. 404 via
      ValueError when the outcome doesn't exist or doesn't belong to
      the user.

Cursor format: base64-encoded JSON `{"evaluated_at": ISO, "id": UUID}`.
Opaque to callers — encoding/decoding lives entirely in this module.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.outcome import (
    OutcomeCreateRequest,
    OutcomePatchRequest,
    OutcomeResponse,
)

# ----------------------------------------------------------------------
# Cursor encoding (opaque to callers)
# ----------------------------------------------------------------------


def _encode_cursor(evaluated_at: datetime, outcome_id: UUID) -> str:
    payload = json.dumps(
        {"evaluated_at": evaluated_at.isoformat(), "id": str(outcome_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode an opaque cursor back to (evaluated_at, id). Raises ValueError on bad input."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        return datetime.fromisoformat(payload["evaluated_at"]), UUID(payload["id"])
    except Exception as exc:
        raise ValueError(f"invalid cursor: {exc}") from exc


# ----------------------------------------------------------------------
# Internals — row → response projection
# ----------------------------------------------------------------------


_OUTCOME_COLUMNS = (
    "o.id, o.daily_decision_id, o.evaluated_at, o.horizon_days, "
    "o.pnl_realized, o.pnl_unrealized, o.decision_quality, o.error_type, "
    "o.actual_regime_realized, o.regime_match, o.notes, o.source"
)


def _row_to_response(row: tuple[Any, ...]) -> OutcomeResponse:
    return OutcomeResponse(
        id=row[0],
        daily_decision_id=row[1],
        evaluated_at=row[2],
        horizon_days=row[3],
        pnl_realized=row[4],
        pnl_unrealized=row[5],
        decision_quality=row[6],
        error_type=row[7] or "none",
        actual_regime_realized=row[8],
        regime_match=row[9],
        notes=row[10],
        source=row[11],
    )


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


async def list_outcomes(
    *,
    session: AsyncSession,
    user_id: str,
    since: datetime | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[OutcomeResponse], str | None]:
    """Cursor-paginated outcome list, filtered to the authenticated user.

    Returns `(outcomes, next_cursor)`. `next_cursor` is None when this
    page is the last.

    Ordering: `(evaluated_at DESC, id DESC)`. The DESC + id tiebreak
    guarantees stable cursor semantics even when two rows share the
    same `evaluated_at`.
    """
    params: dict[str, object] = {"user_id": user_id, "limit": limit + 1}
    where_clauses = [
        "dd.user_id = :user_id",
    ]
    if since is not None:
        where_clauses.append("o.evaluated_at >= :since")
        params["since"] = since
    if cursor is not None:
        cursor_at, cursor_id = _decode_cursor(cursor)
        where_clauses.append(
            "(o.evaluated_at, o.id) < (:cursor_at, :cursor_id)"
        )
        params["cursor_at"] = cursor_at
        params["cursor_id"] = cursor_id

    sql = text(
        f"""
        SELECT {_OUTCOME_COLUMNS}
        FROM outcomes o
        JOIN daily_decisions dd ON dd.id = o.daily_decision_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY o.evaluated_at DESC, o.id DESC
        LIMIT :limit;
        """
    )
    result = await session.execute(sql, params)
    rows = result.fetchall()

    has_next = len(rows) > limit
    rows = rows[:limit]
    outcomes = [_row_to_response(tuple(r)) for r in rows]
    next_cursor = (
        _encode_cursor(outcomes[-1].evaluated_at, outcomes[-1].id)
        if has_next and outcomes
        else None
    )
    return outcomes, next_cursor


async def create_outcome(
    *,
    session: AsyncSession,
    user_id: str,
    request: OutcomeCreateRequest,
) -> OutcomeResponse:
    """Insert a new outcome row. The `source` is set to "manual" server-side.

    Raises:
        ValueError("not_found")     — the referenced daily_decision_id does
                                      not exist OR doesn't belong to the user.
                                      Router maps to 404 (we don't leak which).
        ValueError("conflict")      — an outcome for that decision_id already
                                      exists (UNIQUE constraint). Router → 409.
    """
    # 1. Verify ownership of the referenced daily_decision.
    owns_check = await session.execute(
        text(
            "SELECT 1 FROM daily_decisions "
            "WHERE id = :dd_id AND user_id = :user_id;"
        ),
        {"dd_id": str(request.daily_decision_id), "user_id": user_id},
    )
    if owns_check.first() is None:
        raise ValueError("not_found")

    # 2. Insert with ON CONFLICT to detect the duplicate case explicitly.
    result = await session.execute(
        text(
            f"""
            INSERT INTO outcomes (
                daily_decision_id, horizon_days,
                pnl_realized, pnl_unrealized,
                decision_quality, error_type,
                actual_regime_realized, regime_match,
                notes, source
            )
            VALUES (
                :dd_id, :horizon_days,
                :pnl_realized, :pnl_unrealized,
                :decision_quality, :error_type,
                :actual_regime_realized, :regime_match,
                :notes, 'manual'
            )
            ON CONFLICT (daily_decision_id) DO NOTHING
            RETURNING {_OUTCOME_COLUMNS.replace('o.', '')};
            """
        ),
        {
            "dd_id": str(request.daily_decision_id),
            "horizon_days": request.horizon_days,
            "pnl_realized": request.pnl_realized,
            "pnl_unrealized": request.pnl_unrealized,
            "decision_quality": request.decision_quality,
            "error_type": request.error_type,
            "actual_regime_realized": request.actual_regime_realized,
            "regime_match": request.regime_match,
            "notes": request.notes,
        },
    )
    row = result.first()
    if row is None:
        # ON CONFLICT fired
        raise ValueError("conflict")
    await session.commit()
    return _row_to_response(tuple(row))


async def update_outcome(
    *,
    session: AsyncSession,
    user_id: str,
    outcome_id: UUID,
    patch: OutcomePatchRequest,
) -> OutcomeResponse:
    """Partial update an existing outcome owned by the user.

    Raises:
        ValueError("not_found") — outcome doesn't exist or isn't owned
                                  by this user.
    """
    # Build a sparse UPDATE — only fields present in the patch get applied.
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        # Nothing to update — just return the current row.
        return await _fetch_outcome(session=session, user_id=user_id, outcome_id=outcome_id)

    set_clauses = ", ".join(f"{k} = :{k}" for k in fields)
    params: dict[str, object] = {**fields, "outcome_id": str(outcome_id), "user_id": user_id}

    result = await session.execute(
        text(
            f"""
            UPDATE outcomes o
            SET {set_clauses}
            FROM daily_decisions dd
            WHERE o.id = :outcome_id
              AND o.daily_decision_id = dd.id
              AND dd.user_id = :user_id
            RETURNING {_OUTCOME_COLUMNS};
            """
        ),
        params,
    )
    row = result.first()
    if row is None:
        raise ValueError("not_found")
    await session.commit()
    return _row_to_response(tuple(row))


async def _fetch_outcome(
    *,
    session: AsyncSession,
    user_id: str,
    outcome_id: UUID,
) -> OutcomeResponse:
    """Look up a single outcome by id, verifying user ownership."""
    result = await session.execute(
        text(
            f"""
            SELECT {_OUTCOME_COLUMNS}
            FROM outcomes o
            JOIN daily_decisions dd ON dd.id = o.daily_decision_id
            WHERE o.id = :outcome_id AND dd.user_id = :user_id;
            """
        ),
        {"outcome_id": str(outcome_id), "user_id": user_id},
    )
    row = result.first()
    if row is None:
        raise ValueError("not_found")
    return _row_to_response(tuple(row))
