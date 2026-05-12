"""M1.14 end-to-end smoke tests for `/engine/*` endpoints.

These tests exercise the live FastAPI process + real Postgres,
matching the M0.7 smoke pattern in `tests/test_smoke_e2e.py`.

Activation:
  - Skipped when `SMOKE_API_URL` is unset.
  - Run via `make smoke` locally or via the `smoke` CI job.

Setup the smoke test performs on each run (no external fixtures):
  1. INSERT a test user row directly via the smoke API's DB connection
     (we need a valid user_id for the JWT subject; the FK on
     `daily_decisions.user_id` requires the user to exist).
  2. Issue a JWT for that user via app.core.security.create_access_token.
  3. POST /engine/daily-plan with persist=True.
  4. Verify 200 + a fresh `daily_decisions` row.
  5. POST the same body again. Verify 200 + `is_new_row=False`
     (idempotent ON CONFLICT hit) + same `decision_id`.
  6. Verify the persisted row matches the decision payload's
     `inputs_hash` / `engine_version` / `weights_version`.

The smoke test relies on the M1.14 migration `0002_daily_decisions_unique_inputs_hash`
having been applied (the CI smoke job runs `alembic upgrade head`).

Cleanup: tests insert their own user with a deterministic test UUID
and clean up rows on teardown (via the post-test SQL block). This
keeps subsequent runs deterministic.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from typing import Any

import httpx
import psycopg
import pytest

# When SMOKE_API_URL is unset, the whole module skips.
SMOKE_API_URL = os.environ.get("SMOKE_API_URL")
DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE_API_URL,
        reason=(
            "SMOKE_API_URL not set; M1.14 smoke tests need a live API. "
            "Run `make smoke` or set SMOKE_API_URL=http://localhost:8000/api/v1"
        ),
    ),
]


# A deterministic test-user UUID — fixed so the cleanup phase can find it.
_TEST_USER_ID = "00000000-0000-0000-0000-000000005514"
# JWT must use the API's secret. CI sets JWT_SECRET on the uvicorn process;
# the smoke test reads the same env var to issue a matching token.
_JWT_SECRET = os.environ.get("JWT_SECRET")


def _create_test_user_sql() -> str:
    return (
        "INSERT INTO users (id, email, password_hash, strategy_profile, "
        "disclaimer_accepted_at) VALUES "
        f"('{_TEST_USER_ID}', "
        "'smoke-m114@example.test', 'unused-not-a-real-hash', "
        "'{}'::jsonb, now()) "
        "ON CONFLICT (email) DO UPDATE SET disclaimer_accepted_at = now();"
    )


def _cleanup_sql() -> str:
    return (
        f"DELETE FROM daily_decisions WHERE user_id = '{_TEST_USER_ID}'; "
        f"DELETE FROM users WHERE id = '{_TEST_USER_ID}';"
    )


def _psycopg_url() -> str:
    """Translate `postgresql+psycopg://...` (SQLAlchemy URL) to `postgresql://...` (psycopg URL)."""
    assert DATABASE_URL, "DATABASE_URL must be set for smoke tests"
    return DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def db_setup() -> AsyncIterator[None]:
    """Insert a deterministic test user; yield; clean up."""
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_create_test_user_sql())
    yield
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_cleanup_sql())


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Issue a JWT for the deterministic test user (matches the API's secret)."""
    from datetime import UTC, timedelta

    from jose import jwt

    assert _JWT_SECRET, "JWT_SECRET must be set; CI passes it to the uvicorn process"
    now = datetime.now(UTC)
    payload = {
        "sub": _TEST_USER_ID,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=1)).timestamp()),
    }
    token = jwt.encode(payload, _JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    assert SMOKE_API_URL
    async with httpx.AsyncClient(base_url=SMOKE_API_URL, timeout=15.0) as client:
        yield client


# ----------------------------------------------------------------------
# Request body fixtures (must match production engine input shapes)
# ----------------------------------------------------------------------


def _inputs_payload() -> dict[str, Any]:
    return {
        "chain_snapshot": {
            "underlying": "MSFT",
            "spot": 415.0,
            "as_of": date(2026, 5, 20).isoformat(),
            "contracts": [
                {
                    "underlying": "MSFT",
                    "expiry": date(2026, 6, 19).isoformat(),
                    "strike": 415.0,
                    "option_type": "CALL",
                    "bid": 4.25,
                    "ask": 4.30,
                    "mid": 4.275,
                    "iv": 0.28,
                    "open_interest": 3000,
                    "volume": 200,
                },
            ],
        },
        "positions": {"underlying_shares": 100},
        "profile": {
            "risk_tolerance": "moderate",
            "income_need": "medium",
            "max_position_pct": 0.50,
            "max_coverage_pct": 0.75,
            "min_iv_rank_for_short_premium": 40,
            "prefer_collars_over_covered_calls": False,
            "drawdown_tolerance": 0.15,
            "style": "balanced",
        },
        "market_state": {
            "regime": "HIGH_IV_PIN",
            "regime_score": 0.75,
            "all_scores": {
                "HIGH_IV_EVENT": 0.30, "HIGH_IV_PIN": 0.75,
                "LOW_IV_TREND": 0.10, "LOW_IV_RANGE": 0.15,
                "BREAKOUT": 0.05, "POST_EVENT_REPRICE": 0.10,
            },
            "tags": [],
            "spot": 415.0, "iv_rank": 0.65, "iv_percentile": 0.60,
            "hv_30": 0.22, "expected_move_pct": 0.04,
            "max_pain": 415.0, "max_pain_delta_pct": 0.0,
            "pcr_volume": 0.50, "pcr_oi": 0.50,
            "trend_strength": 0.30, "realized_vs_implied": 1.0,
            "breakout_signal": 0.0, "oi_concentration_at_max_pain": 0.20,
            "days_to_next_event": 14, "next_event_kind": "earnings",
            "days_since_event": None, "days_to_nearest_opex": None,
            "iv_rank_change_1d": 0.0, "gap_pct": None,
        },
        "flow_score": {
            "score": 40.0, "bullish_score": 55.0, "bearish_score": 15.0,
            "bias": "BULLISH", "recommended_action": "SELL_CALL_PARTIAL",
            "pin_probability": 0.30, "gamma_risk": 0.20, "gamma_sign": 0,
            "confidence": 0.70, "explanation": "(smoke)",
            "breakdown": {},
        },
    }


def _daily_plan_body(*, persist: bool = True) -> dict[str, Any]:
    return {
        "ticker": "MSFT",
        "as_of": datetime(2026, 5, 20, 14, 30, tzinfo=timezone.utc).isoformat(),  # noqa: UP017
        "inputs": _inputs_payload(),
        "persist": persist,
    }


# ----------------------------------------------------------------------
# Smoke tests
# ----------------------------------------------------------------------


async def test_daily_plan_persists_and_returns_dailydecision(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """Full path: POST /engine/daily-plan with persist=True → 200 + DB row."""
    _ = db_setup  # ensures user row exists + cleanup runs

    r = await http.post(
        "/engine/daily-plan",
        json=_daily_plan_body(persist=True),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_row"] is True
    decision = body["decision"]
    assert decision["inputs_hash"].startswith("sha256:")
    assert decision["weights_version"] == "v2.0"
    assert decision["engine_version"]

    # Verify the row exists in Postgres
    with psycopg.connect(_psycopg_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT inputs_hash, engine_version, weights_version, confidence "
                "FROM daily_decisions WHERE user_id = %s ORDER BY as_of DESC LIMIT 1;",
                (_TEST_USER_ID,),
            )
            row = cur.fetchone()
    assert row is not None, "daily_decisions row not found after POST"
    inputs_hash, engine_version, weights_version, confidence = row
    assert inputs_hash == decision["inputs_hash"]
    assert engine_version == decision["engine_version"]
    assert weights_version == decision["weights_version"]
    assert float(confidence) == pytest.approx(decision["confidence"], abs=1e-3)


async def test_daily_plan_idempotency_on_retry(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """Same body twice → second call returns is_new_row=False, same decision_id."""
    _ = db_setup
    body = _daily_plan_body(persist=True)

    r1 = await http.post("/engine/daily-plan", json=body, headers=auth_headers)
    assert r1.status_code == 200
    first = r1.json()
    assert first["is_new_row"] is True

    r2 = await http.post("/engine/daily-plan", json=body, headers=auth_headers)
    assert r2.status_code == 200
    second = r2.json()
    assert second["is_new_row"] is False, (
        "Second identical-input call should hit ON CONFLICT and return is_new_row=False"
    )
    assert second["decision"]["decision_id"] == first["decision"]["decision_id"]
    assert second["decision"]["inputs_hash"] == first["decision"]["inputs_hash"]

    # Verify only ONE row exists for this user (ON CONFLICT prevented the duplicate)
    with psycopg.connect(_psycopg_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM daily_decisions WHERE user_id = %s;",
                (_TEST_USER_ID,),
            )
            count_row = cur.fetchone()
    assert count_row is not None
    assert count_row[0] == 1, f"expected 1 row after idempotent retry; got {count_row[0]}"


async def test_daily_plan_unauthenticated_returns_401(http: httpx.AsyncClient) -> None:
    r = await http.post("/engine/daily-plan", json=_daily_plan_body())
    assert r.status_code == 401, r.text


async def test_recommend_endpoint_returns_200_in_smoke(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """/engine/recommend works against the live process (no persistence)."""
    _ = db_setup
    body = {
        "ticker": "MSFT",
        "market_state": _inputs_payload()["market_state"],
        "flow_score": _inputs_payload()["flow_score"],
        "positions": {"underlying_shares": 100},
        "profile": _inputs_payload()["profile"],
    }
    r = await http.post("/engine/recommend", json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    rec = r.json()["recommendation"]
    assert rec["regime"] == "HIGH_IV_PIN"
    assert len(rec["actions"]) >= 1


async def test_engine_routes_in_smoke_openapi(http: httpx.AsyncClient) -> None:
    """The smoke API's OpenAPI schema includes the M1.14 routes."""
    r = await http.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/engine/daily-plan" in paths
    assert "/api/v1/engine/recommend" in paths
