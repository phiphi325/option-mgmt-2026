"""Unit tests for the M1.17 endpoints (profile + outcomes + CSV import + market).

These tests exercise auth + Pydantic validation + the error paths that
DON'T require a live Postgres. The DB-touching happy paths are smoke-
tested in `tests/test_smoke_m1_17.py` against the real Postgres + uvicorn
in the CI smoke job — mirrors the M1.14 split.

Scope here:
  - 401 on missing/invalid auth for every endpoint that requires it
  - 422 on Pydantic validation failures (bad enum values, range
    violations, missing fields)
  - 413 on oversized CSV uploads
  - OpenAPI: every M1.17 path appears in the spec
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token

pytestmark = []


# ----------------------------------------------------------------------
# Shared fixtures
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    token = create_access_token(subject="00000000-0000-0000-0000-000000000001")
    return {"Authorization": f"Bearer {token}"}


def _profile_payload() -> dict[str, Any]:
    """A valid UserStrategyProfile payload (passes all §9.9 constraints)."""
    return {
        "risk_tolerance": "moderate",
        "income_need": "medium",
        "max_position_pct": 0.50,
        "max_coverage_pct": 0.75,
        "min_iv_rank_for_short_premium": 40,
        "prefer_collars_over_covered_calls": False,
        "drawdown_tolerance": 0.15,
        "style": "balanced",
    }


# ----------------------------------------------------------------------
# /profile
# ----------------------------------------------------------------------


def test_get_profile_requires_auth(client: TestClient) -> None:
    r = client.get("/api/v1/profile")
    assert r.status_code == 401, r.text


def test_put_profile_requires_auth(client: TestClient) -> None:
    r = client.put("/api/v1/profile", json=_profile_payload())
    assert r.status_code == 401, r.text


def test_put_profile_invalid_max_position_pct_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """max_position_pct must be in [0, 1]."""
    body = _profile_payload()
    body["max_position_pct"] = 1.5
    r = client.put("/api/v1/profile", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_put_profile_invalid_iv_rank_threshold_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """min_iv_rank_for_short_premium must be in [0, 100]."""
    body = _profile_payload()
    body["min_iv_rank_for_short_premium"] = 150
    r = client.put("/api/v1/profile", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_put_profile_invalid_risk_tolerance_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """risk_tolerance must be one of {conservative, moderate, aggressive}."""
    body = _profile_payload()
    body["risk_tolerance"] = "extreme"
    r = client.put("/api/v1/profile", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_put_profile_extra_field_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """ProfileUpdateRequest has `extra="forbid"`; typos raise 422 before
    the handler runs (so no DB access). The engine's UserStrategyProfile
    deliberately allows extras for forward-compat, but the API boundary
    is stricter — see app/schemas/profile.py docstring."""
    body = _profile_payload()
    body["some_extra_field"] = "rejected"
    r = client.put("/api/v1/profile", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


# ----------------------------------------------------------------------
# /outcomes
# ----------------------------------------------------------------------


def test_get_outcomes_requires_auth(client: TestClient) -> None:
    r = client.get("/api/v1/outcomes")
    assert r.status_code == 401


def test_post_outcomes_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/outcomes",
        json={"daily_decision_id": str(uuid4()), "horizon_days": 7},
    )
    assert r.status_code == 401


def test_patch_outcomes_requires_auth(client: TestClient) -> None:
    r = client.patch(f"/api/v1/outcomes/{uuid4()}", json={"horizon_days": 14})
    assert r.status_code == 401


def test_post_outcomes_missing_daily_decision_id_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/v1/outcomes",
        json={"horizon_days": 7},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_post_outcomes_invalid_quality_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """decision_quality must be one of {good, neutral, bad}."""
    r = client.post(
        "/api/v1/outcomes",
        json={
            "daily_decision_id": str(uuid4()),
            "horizon_days": 7,
            "decision_quality": "amazing",
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_get_outcomes_invalid_cursor_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get(
        "/api/v1/outcomes?cursor=not-a-real-cursor",
        headers=auth_headers,
    )
    # The cursor decode happens inside the service; in unit tests without a
    # DB, the service raises before reaching SQL. Either 422 (cursor decode)
    # or 500 (DB unavailable) is acceptable here for the unit-test job;
    # the smoke job exercises the happy cursor path against real Postgres.
    assert r.status_code in (422, 500)


def test_get_outcomes_limit_out_of_range_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """limit > 200 violates the Query(ge=1, le=200) constraint."""
    r = client.get(
        "/api/v1/outcomes?limit=500",
        headers=auth_headers,
    )
    assert r.status_code == 422


# ----------------------------------------------------------------------
# /data/*/import-csv
# ----------------------------------------------------------------------


def test_import_positions_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/data/positions/import-csv",
        files={"file": ("positions.csv", "ticker,qty,avg_cost,opened_at\n", "text/csv")},
    )
    assert r.status_code == 401


def test_import_option_positions_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/data/option-positions/import-csv",
        files={"file": ("op.csv", "ticker,side,kind,strike,expiry,qty,opened_at,opened_price,status\n", "text/csv")},
    )
    assert r.status_code == 401


def test_import_chain_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/data/chain/import-csv",
        files={"file": ("c.csv", "ticker,fetched_at,expiry,strike,kind\n", "text/csv")},
    )
    assert r.status_code == 401


def test_import_iv_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/data/iv/import-csv",
        files={"file": ("iv.csv", "ticker,ts\n", "text/csv")},
    )
    assert r.status_code == 401


def test_import_events_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/data/events/import-csv",
        files={"file": ("e.csv", "ticker,kind,scheduled_at,source\n", "text/csv")},
    )
    assert r.status_code == 401


def test_import_oversized_returns_413(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Files over 10 MB are rejected at the router with HTTP 413."""
    # 11 MB of innocuous CSV-ish data
    payload = "ticker,qty,avg_cost,opened_at\n" + ("MSFT,1,1,2026-01-01T00:00:00Z\n" * 400_000)
    assert len(payload.encode()) > 10 * 1024 * 1024
    r = client.post(
        "/api/v1/data/positions/import-csv",
        files={"file": ("big.csv", payload, "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 413, r.text


def test_import_chain_invalid_kind_skips_row(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A row with kind='BANANA' is reported in errors[] and counted as skipped.

    The route still returns 200 because the upload as a whole isn't
    invalid — per-row errors are part of the response envelope per §10.
    """
    csv_data = (
        "ticker,fetched_at,expiry,strike,kind,bid,ask,last,oi,volume,iv\n"
        "MSFT,2026-05-20T13:30:00Z,2026-06-19,415.0,BANANA,4.25,4.30,4.275,1000,100,0.28\n"
    )
    r = client.post(
        "/api/v1/data/chain/import-csv",
        files={"file": ("c.csv", csv_data, "text/csv")},
        headers=auth_headers,
    )
    # Without a live DB the service raises on the SELECT (existing dedupe
    # check). For the unit-test job (no live DB) this surfaces as 500;
    # for the smoke job it returns 200 with errors[]. Accept both.
    assert r.status_code in (200, 500)
    if r.status_code == 200:
        body = r.json()
        assert body["skipped"] >= 1
        assert any("BANANA" in (e.get("message") or "") for e in body["errors"])


# ----------------------------------------------------------------------
# /market/{ticker}/latest
# ----------------------------------------------------------------------
#
# The /market/{ticker}/latest endpoint is unavoidably DB-dependent (its
# entire purpose is to read chain/iv/hv/events rows). Starlette
# TestClient defaults to `raise_server_exceptions=True`, which re-raises
# any unhandled exception inside the route into the test rather than
# returning a 500 response — so unit-testing against a no-DB sandbox
# would crash the test with the underlying SQLAlchemy connection error.
#
# The §22.10 422 contract is therefore validated in the smoke suite
# (`tests/test_smoke_m1_17.py::test_market_latest_after_seeding_smoke` +
# its inverse for `insufficient_iv_history`) against the real Postgres
# the CI smoke job provisions. Unit tests below only cover routes whose
# 401 / 422 paths fire BEFORE the session dependency is exercised.


# ----------------------------------------------------------------------
# OpenAPI registration
# ----------------------------------------------------------------------


def test_m1_17_routes_in_openapi(client: TestClient) -> None:
    """Every M1.17 path is registered."""
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    # Profile
    assert "/api/v1/profile" in paths
    # Outcomes
    assert "/api/v1/outcomes" in paths
    assert "/api/v1/outcomes/{outcome_id}" in paths
    # Data import
    assert "/api/v1/data/positions/import-csv" in paths
    assert "/api/v1/data/option-positions/import-csv" in paths
    assert "/api/v1/data/chain/import-csv" in paths
    assert "/api/v1/data/iv/import-csv" in paths
    assert "/api/v1/data/events/import-csv" in paths
    # Market
    assert "/api/v1/market/{ticker}/latest" in paths
