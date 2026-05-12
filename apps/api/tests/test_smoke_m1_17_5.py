"""M1.17.5 smoke tests — `DailyPlanRequest.inputs` optional + DB hydration.

These run against the live uvicorn + real Postgres in the CI smoke job.
Skipped when SMOKE_API_URL is unset.

Scope:
  1. Missing prerequisites → 422 with the expected error tag:
     - missing_positions    (no positions rows seeded)
     - missing_chain        (no option_chain_snapshots rows seeded)
     - insufficient_iv_history (< 30 iv_history rows seeded)
  2. Full happy path: upload all the CSVs the engine needs, then call
     POST /engine/daily-plan WITHOUT `inputs` in the body, expect 200
     with a persisted daily_decisions row.
  3. Determinism: calling the no-inputs path twice with the same DB
     state produces identical inputs_hash + idempotent persistence.

All seed data uses a synthetic ticker `MSFT_HYD` to avoid colliding with
the M1.14 / M1.17 smoke fixtures (which use MSFT / MSFT_SMOKE).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta

import httpx
import psycopg
import pytest

SMOKE_API_URL = os.environ.get("SMOKE_API_URL")
DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE_API_URL,
        reason=(
            "SMOKE_API_URL not set; M1.17.5 smoke tests need a live API. "
            "Run via the CI smoke job."
        ),
    ),
]

_TEST_USER_ID = "00000000-0000-0000-0000-000000017175"
_JWT_SECRET = os.environ.get("JWT_SECRET")
_TICKER = "MSFT_HYD"


def _psycopg_url() -> str:
    assert DATABASE_URL
    return DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _create_test_user_sql() -> str:
    return (
        "INSERT INTO users (id, email, password_hash, strategy_profile, "
        "disclaimer_accepted_at) VALUES "
        f"('{_TEST_USER_ID}', "
        "'smoke-m1175@example.test', 'unused', '{}'::jsonb, now()) "
        "ON CONFLICT (email) DO UPDATE SET disclaimer_accepted_at = now();"
    )


def _cleanup_sql() -> str:
    return (
        f"DELETE FROM outcomes WHERE daily_decision_id IN "
        f"  (SELECT id FROM daily_decisions WHERE user_id = '{_TEST_USER_ID}'); "
        f"DELETE FROM daily_decisions WHERE user_id = '{_TEST_USER_ID}'; "
        f"DELETE FROM positions WHERE user_id = '{_TEST_USER_ID}'; "
        f"DELETE FROM option_positions WHERE user_id = '{_TEST_USER_ID}'; "
        f"DELETE FROM users WHERE id = '{_TEST_USER_ID}'; "
        f"DELETE FROM option_chain_snapshots WHERE ticker = '{_TICKER}'; "
        f"DELETE FROM iv_history WHERE ticker = '{_TICKER}'; "
        f"DELETE FROM hv_history WHERE ticker = '{_TICKER}'; "
        f"DELETE FROM events WHERE ticker = '{_TICKER}'; "
    )


@pytest.fixture
def db_setup() -> AsyncIterator[None]:
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_create_test_user_sql())
    yield
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_cleanup_sql())


@pytest.fixture
def auth_headers() -> dict[str, str]:
    from datetime import UTC
    from datetime import timedelta as _td

    from jose import jwt

    assert _JWT_SECRET
    now = datetime.now(UTC)
    payload = {
        "sub": _TEST_USER_ID,
        "iat": int(now.timestamp()),
        "exp": int((now + _td(days=1)).timestamp()),
    }
    token = jwt.encode(payload, _JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    assert SMOKE_API_URL
    async with httpx.AsyncClient(base_url=SMOKE_API_URL, timeout=30.0) as c:
        yield c


# ----------------------------------------------------------------------
# CSV fixtures
# ----------------------------------------------------------------------


def _positions_csv() -> str:
    return (
        "ticker,qty,avg_cost,opened_at\n"
        f"{_TICKER},5000,400.12,2025-08-15T00:00:00Z\n"
    )


def _iv_csv(n: int = 60) -> str:
    """`n` daily iv_history rows for the synthetic ticker."""
    header = "ticker,ts,atm_iv_30d,iv_rank,iv_percentile,hv_30,high,low,close\n"
    start = date(2025, 1, 1)
    rows = [
        f"{_TICKER},{(start + timedelta(days=i)).isoformat()}T00:00:00Z,"
        "0.28,0.55,0.60,0.22,420.0,410.0,415.0\n"
        for i in range(n)
    ]
    return header + "".join(rows)


def _chain_csv() -> str:
    return (
        "ticker,fetched_at,expiry,strike,kind,bid,ask,last,oi,volume,iv\n"
        f"{_TICKER},2026-05-20T13:30:00Z,2026-06-19,410.0,CALL,8.10,8.20,8.15,1500,100,0.30\n"
        f"{_TICKER},2026-05-20T13:30:00Z,2026-06-19,415.0,CALL,4.25,4.30,4.275,3000,200,0.28\n"
        f"{_TICKER},2026-05-20T13:30:00Z,2026-06-19,420.0,CALL,2.40,2.50,2.45,2500,180,0.27\n"
        f"{_TICKER},2026-05-20T13:30:00Z,2026-06-19,415.0,PUT,4.10,4.20,4.15,2000,150,0.29\n"
        f"{_TICKER},2026-05-20T13:30:00Z,2026-06-19,410.0,PUT,2.00,2.10,2.05,1500,100,0.30\n"
    )


# ----------------------------------------------------------------------
# Failure cases — hydration prerequisites missing → 422
# ----------------------------------------------------------------------


async def test_daily_plan_no_inputs_missing_chain_returns_422(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """No CSVs uploaded → hydration raises missing_chain → 422."""
    _ = db_setup
    body = {"ticker": _TICKER, "persist": False}
    r = await http.post("/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    assert "missing_chain" in r.text or "chain_not_yet_ingested" in r.text


async def test_daily_plan_no_inputs_insufficient_iv_returns_422(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """Chain uploaded but iv_history < 30 rows → 422."""
    _ = db_setup
    # Chain only (no iv rows)
    r = await http.post(
        "/data/chain/import-csv",
        files={"file": ("chain.csv", _chain_csv(), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    body = {"ticker": _TICKER, "persist": False}
    r = await http.post("/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    assert "insufficient_iv_history" in r.text


async def test_daily_plan_no_inputs_missing_positions_returns_422(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """Chain + iv uploaded but no positions → 422 missing_positions."""
    _ = db_setup
    # Seed chain + 30 iv rows but skip positions
    r = await http.post(
        "/data/chain/import-csv",
        files={"file": ("chain.csv", _chain_csv(), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    r = await http.post(
        "/data/iv/import-csv",
        files={"file": ("iv.csv", _iv_csv(60), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    body = {"ticker": _TICKER, "persist": False}
    r = await http.post("/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    assert "missing_positions" in r.text


# ----------------------------------------------------------------------
# Happy path + idempotency
# ----------------------------------------------------------------------


async def test_daily_plan_no_inputs_full_csv_flow_smoke(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """End-to-end: upload all CSVs → POST /daily-plan WITHOUT inputs → 200 + persisted row."""
    _ = db_setup

    # 1. Seed positions
    r = await http.post(
        "/data/positions/import-csv",
        files={"file": ("positions.csv", _positions_csv(), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # 2. Seed chain
    r = await http.post(
        "/data/chain/import-csv",
        files={"file": ("chain.csv", _chain_csv(), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # 3. Seed iv_history (≥ 30 rows)
    r = await http.post(
        "/data/iv/import-csv",
        files={"file": ("iv.csv", _iv_csv(60), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # 4. Call daily-plan WITHOUT inputs → hydration → engine → persist.
    #    IMPORTANT: pin `as_of` to a fixed value so the idempotency check
    #    in step 5 isn't defeated by clock drift. Without `as_of` the
    #    service defaults to datetime.now(UTC), which differs by ~ms
    #    between calls — distinct inputs_hash per call, no ON CONFLICT.
    #    Same pattern as the M1.14 _daily_plan_body() fixture.
    body = {
        "ticker": _TICKER,
        "as_of": "2026-05-20T14:30:00+00:00",
        "persist": True,
    }
    r = await http.post("/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    body1 = r.json()
    assert body1["is_new_row"] is True
    decision = body1["decision"]
    assert decision["ticker"] == _TICKER
    assert decision["inputs_hash"].startswith("sha256:")
    assert decision["engine_version"]
    assert decision["weights_version"] == "v2.0"

    # 5. Idempotency: call again with same body (same as_of → same inputs_hash
    #    → ON CONFLICT fires → is_new_row=False).
    r = await http.post("/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    body2 = r.json()
    assert body2["is_new_row"] is False
    assert body2["decision"]["inputs_hash"] == decision["inputs_hash"]
    assert body2["decision"]["decision_id"] == decision["decision_id"]

    # 6. Verify exactly one row persisted
    with psycopg.connect(_psycopg_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM daily_decisions WHERE user_id = %s AND ticker = %s;",
                (_TEST_USER_ID, _TICKER),
            )
            count_row = cur.fetchone()
    assert count_row is not None
    assert count_row[0] == 1
