"""M1.17 smoke tests — profile + outcomes + CSV import + market.

These run against the live uvicorn + real Postgres in the CI smoke job.
Skipped when SMOKE_API_URL is unset.

Scope:
  - Profile PUT → GET round-trip
  - CSV upload happy paths (positions + iv with enough rows)
  - §22.12: iv upload with < 30 rows → 422
  - /market/MSFT/latest happy path after seeding chain + iv
  - End-to-end: upload CSVs → /market/MSFT/latest returns coherent snapshot
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
            "SMOKE_API_URL not set; M1.17 smoke tests need a live API. "
            "Run via the CI smoke job."
        ),
    ),
]

_TEST_USER_ID = "00000000-0000-0000-0000-000000001717"
_JWT_SECRET = os.environ.get("JWT_SECRET")


def _psycopg_url() -> str:
    assert DATABASE_URL
    return DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _create_test_user_sql() -> str:
    return (
        "INSERT INTO users (id, email, password_hash, strategy_profile, "
        "disclaimer_accepted_at) VALUES "
        f"('{_TEST_USER_ID}', "
        "'smoke-m117@example.test', 'unused', '{}'::jsonb, now()) "
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
        # Shared tables — clean up the synthetic MSFT-SMOKE rows we seed.
        f"DELETE FROM option_chain_snapshots WHERE source = 'm1_17_smoke'; "
        f"DELETE FROM iv_history WHERE ticker = 'MSFT_SMOKE'; "
        f"DELETE FROM hv_history WHERE ticker = 'MSFT_SMOKE'; "
        f"DELETE FROM events WHERE source = 'm1_17_smoke'; "
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
    async with httpx.AsyncClient(base_url=SMOKE_API_URL, timeout=20.0) as c:
        yield c


# ----------------------------------------------------------------------
# Profile round-trip
# ----------------------------------------------------------------------


async def test_profile_round_trip_smoke(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    _ = db_setup
    # GET initially → returns defaults
    r = await http.get("/profile", headers=auth_headers)
    assert r.status_code == 200, r.text
    initial = r.json()

    # PUT a customized profile
    custom = {**initial, "max_position_pct": 0.25, "min_iv_rank_for_short_premium": 60}
    r = await http.put("/profile", json=custom, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["max_position_pct"] == 0.25

    # GET again → returns the customized profile
    r = await http.get("/profile", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["min_iv_rank_for_short_premium"] == 60


# ----------------------------------------------------------------------
# CSV import — positions
# ----------------------------------------------------------------------


async def test_positions_csv_upload_smoke(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    _ = db_setup
    csv_data = (
        "ticker,qty,avg_cost,opened_at\n"
        "MSFT,5000,400.12,2025-08-15T00:00:00Z\n"
    )
    files = {"file": ("positions.csv", csv_data, "text/csv")}
    r = await http.post(
        "/data/positions/import-csv", files=files, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 1
    assert body["updated"] == 0
    assert body["errors"] == []

    # Re-upload → 0 inserts, 1 update (idempotency)
    r2 = await http.post(
        "/data/positions/import-csv", files=files, headers=auth_headers
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["inserted"] == 0
    assert body2["updated"] == 1


# ----------------------------------------------------------------------
# CSV import — iv history with §22.12 validation
# ----------------------------------------------------------------------


def _iv_csv_rows(ticker: str, n: int) -> str:
    """Generate `n` daily iv_history rows for a synthetic ticker."""
    header = "ticker,ts,atm_iv_30d,iv_rank,iv_percentile,hv_30,high,low,close\n"
    start = date(2025, 1, 1)
    rows = []
    for i in range(n):
        d = start + timedelta(days=i)
        rows.append(
            f"{ticker},{d.isoformat()}T00:00:00Z,0.28,0.55,0.60,0.22,420.0,410.0,415.0\n"
        )
    return header + "".join(rows)


async def test_iv_csv_below_30_returns_422_smoke(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """§22.12: < 30 iv_history rows after upload → 422."""
    _ = db_setup
    csv_data = _iv_csv_rows("MSFT_SMOKE", 20)
    files = {"file": ("iv.csv", csv_data, "text/csv")}
    r = await http.post("/data/iv/import-csv", files=files, headers=auth_headers)
    assert r.status_code == 422, r.text
    assert "insufficient_iv_history" in r.text


async def test_iv_csv_30_to_59_warns_smoke(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """§22.12: 30 ≤ count < 60 → 200 with validation_warnings."""
    _ = db_setup
    csv_data = _iv_csv_rows("MSFT_SMOKE", 45)
    files = {"file": ("iv.csv", csv_data, "text/csv")}
    r = await http.post("/data/iv/import-csv", files=files, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 45
    assert len(body["validation_warnings"]) >= 1
    assert any("60 days" in w or "less reliable" in w for w in body["validation_warnings"])


# ----------------------------------------------------------------------
# /market/{ticker}/latest happy path after seeding
# ----------------------------------------------------------------------


async def test_market_latest_after_seeding_smoke(
    http: httpx.AsyncClient,
    db_setup: None,
    auth_headers: dict[str, str],
) -> None:
    """Seed 30 iv_history rows + minimal chain → /market/{ticker}/latest 200."""
    _ = db_setup
    # 1. Seed iv_history
    iv_csv = _iv_csv_rows("MSFT_SMOKE", 30)
    r = await http.post(
        "/data/iv/import-csv",
        files={"file": ("iv.csv", iv_csv, "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # 2. Seed a minimal chain (1 ATM call + 1 ATM put)
    chain_csv = (
        "ticker,fetched_at,expiry,strike,kind,bid,ask,last,oi,volume,iv,source\n"
        "MSFT_SMOKE,2026-05-20T13:30:00Z,2026-06-19,415.0,CALL,4.25,4.30,4.275,3000,200,0.28,m1_17_smoke\n"
        "MSFT_SMOKE,2026-05-20T13:30:00Z,2026-06-19,415.0,PUT,4.10,4.20,4.15,2000,150,0.29,m1_17_smoke\n"
    )
    r = await http.post(
        "/data/chain/import-csv",
        files={"file": ("chain.csv", chain_csv, "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # 3. /market/{ticker}/latest now returns 200 with a coherent snapshot
    r = await http.get("/market/MSFT_SMOKE/latest")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticker"] == "MSFT_SMOKE"
    assert float(body["spot"]) == 415.0
    assert body["data_freshness"] is not None
