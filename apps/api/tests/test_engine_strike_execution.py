"""Unit tests for the M1.16 `/engine/{strike-candidates,execution-check}` endpoints.

These tests exercise the HTTP shape + validation + auth via TestClient
in-process. No DB writes — both endpoints are read-only by design.

Scope (per plan §17 M1.16 + the M1.16 dev spec):
  - 401 when no Authorization header (2 tests, one per endpoint)
  - /strike-candidates: happy path with SELL_COVERED_CALL_PARTIAL action → 1 SHORT call leg
  - /strike-candidates: NO_OP action → empty legs + skipped_reason
  - /strike-candidates: invalid action emit value → 422
  - /strike-candidates: spot <= 0 in chain → 422 (engine ValueError)
  - /execution-check: happy path with one SHORT call leg → aggregate fields populated
  - /execution-check: empty legs → 200 with aggregate-only Execution
  - /execution-check: mismatched quantities length → 422 (engine ValueError)
  - OpenAPI: both new paths registered

Conftest provides the shared TestClient + sets JWT_SECRET.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token

pytestmark = []


# ----------------------------------------------------------------------
# Fixture helpers — mirror the M1.14/M1.15 fixture style
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    token = create_access_token(subject="00000000-0000-0000-0000-000000000001")
    return {"Authorization": f"Bearer {token}"}


def _chain_payload() -> dict[str, Any]:
    """A liquid ATM chain with both put + call contracts at expiry 2026-06-19."""
    return {
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
            {
                "underlying": "MSFT",
                "expiry": date(2026, 6, 19).isoformat(),
                "strike": 420.0,
                "option_type": "CALL",
                "bid": 2.40,
                "ask": 2.50,
                "mid": 2.45,
                "iv": 0.27,
                "open_interest": 2500,
                "volume": 180,
            },
            {
                "underlying": "MSFT",
                "expiry": date(2026, 6, 19).isoformat(),
                "strike": 425.0,
                "option_type": "CALL",
                "bid": 1.20,
                "ask": 1.30,
                "mid": 1.25,
                "iv": 0.26,
                "open_interest": 2000,
                "volume": 150,
            },
            {
                "underlying": "MSFT",
                "expiry": date(2026, 6, 19).isoformat(),
                "strike": 415.0,
                "option_type": "PUT",
                "bid": 4.10,
                "ask": 4.20,
                "mid": 4.15,
                "iv": 0.29,
                "open_interest": 2000,
                "volume": 150,
            },
        ],
    }


def _strike_candidates_body(
    emit: str = "SELL_COVERED_CALL_PARTIAL",
    *,
    target_delta: float = 0.25,
    target_dte: float = 30.0,
) -> dict[str, Any]:
    """Build a strike-candidates request body for the given emit."""
    return {
        "ticker": "MSFT",
        "action": {
            "emit": emit,
            "parameters": {
                "target_delta": target_delta,
                "target_dte": target_dte,
                "size_pct": 0.5,
            },
        },
        "chain_snapshot": _chain_payload(),
        "risk_free_rate": 0.05,
        "dividend_yield": 0.0,
    }


def _strike_leg_payload(
    *,
    strike: float = 420.0,
    option_type: str = "CALL",
    side: str = "SHORT",
    delta_target: float = 0.25,
    delta_actual: float = 0.27,
    dte_actual: int = 30,
    mid_price: float | None = 2.45,
) -> dict[str, Any]:
    """A minimal StrikeLegPayload matching one of the chain rows."""
    return {
        "contract": {
            "underlying": "MSFT",
            "expiry": date(2026, 6, 19).isoformat(),
            "strike": strike,
            "option_type": option_type,
            "bid": 2.40,
            "ask": 2.50,
            "mid": mid_price,
            "iv": 0.27,
            "open_interest": 2500,
            "volume": 180,
        },
        "side": side,
        "delta_target": delta_target,
        "delta_actual": delta_actual,
        "delta_distance": abs(delta_actual - delta_target),
        "dte_actual": dte_actual,
        "mid_price": mid_price,
    }


# ----------------------------------------------------------------------
# Auth — 401 across both new endpoints
# ----------------------------------------------------------------------


def test_strike_candidates_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/engine/strike-candidates", json=_strike_candidates_body())
    assert r.status_code == 401, r.text


def test_execution_check_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/engine/execution-check",
        json={"legs": [_strike_leg_payload()]},
    )
    assert r.status_code == 401, r.text


# ----------------------------------------------------------------------
# /engine/strike-candidates
# ----------------------------------------------------------------------


def test_strike_candidates_sell_covered_call_returns_one_short_call(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """SELL_COVERED_CALL_PARTIAL emit → 1 SHORT call leg per §9.4 leg structure."""
    r = client.post(
        "/api/v1/engine/strike-candidates",
        json=_strike_candidates_body(emit="SELL_COVERED_CALL_PARTIAL"),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    sel = r.json()["strike_selection"]
    assert sel["emit"] == "SELL_COVERED_CALL_PARTIAL"
    assert len(sel["legs"]) == 1
    leg = sel["legs"][0]
    assert leg["side"] == "SHORT"
    assert leg["contract"]["option_type"] == "CALL"
    # delta_target stays positive for calls per side convention
    assert leg["delta_target"] > 0


def test_strike_candidates_no_op_returns_empty_legs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """NO_OP emit → empty legs + skipped_reason per §9.4 leg structure."""
    r = client.post(
        "/api/v1/engine/strike-candidates",
        json=_strike_candidates_body(emit="NO_OP"),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    sel = r.json()["strike_selection"]
    assert sel["emit"] == "NO_OP"
    assert sel["legs"] == []
    assert sel["skipped_reason"] is not None


def test_strike_candidates_invalid_emit_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """emit must be a valid EmittedAction value."""
    body = _strike_candidates_body()
    body["action"]["emit"] = "NOT_A_REAL_EMIT"
    r = client.post(
        "/api/v1/engine/strike-candidates",
        json=body,
        headers=auth_headers,
    )
    assert r.status_code == 422, r.text


def test_strike_candidates_response_carries_emit_echo(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The strike_selection echoes the input emit code."""
    r = client.post(
        "/api/v1/engine/strike-candidates",
        json=_strike_candidates_body(emit="ROLL_UP_AND_OUT"),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["strike_selection"]["emit"] == "ROLL_UP_AND_OUT"


# ----------------------------------------------------------------------
# /engine/execution-check
# ----------------------------------------------------------------------


def test_execution_check_returns_200_with_one_leg(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Happy path: one liquid SHORT call leg → aggregate fields populated."""
    r = client.post(
        "/api/v1/engine/execution-check",
        json={"legs": [_strike_leg_payload()]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    execution = r.json()["execution"]
    # Aggregate fields (canonical Execution shape per §9.8)
    assert "aggregate_liquidity_score" in execution
    assert "aggregate_fill_confidence" in execution
    assert "legs" in execution
    assert len(execution["legs"]) == 1
    leg = execution["legs"][0]
    assert "liquidity_score" in leg
    assert "fill_confidence" in leg
    assert "spread_bps" in leg


def test_execution_check_empty_legs_returns_200(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Empty legs is valid (NO_OP shape) — aggregate-only Execution returned."""
    r = client.post(
        "/api/v1/engine/execution-check",
        json={"legs": []},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    execution = r.json()["execution"]
    assert execution["legs"] == []


def test_execution_check_mismatched_quantities_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """quantities length != legs length → engine ValueError → 422."""
    r = client.post(
        "/api/v1/engine/execution-check",
        json={
            "legs": [_strike_leg_payload()],
            "quantities": [1, 2],  # 2 quantities for 1 leg
        },
        headers=auth_headers,
    )
    assert r.status_code == 422, r.text


def test_execution_check_explicit_quantities(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Explicit per-leg quantities are accepted when lengths match."""
    r = client.post(
        "/api/v1/engine/execution-check",
        json={
            "legs": [_strike_leg_payload()],
            "quantities": [5],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text


# ----------------------------------------------------------------------
# OpenAPI registration
# ----------------------------------------------------------------------


def test_m1_16_routes_in_openapi(client: TestClient) -> None:
    """Both new paths appear in the generated OpenAPI document."""
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/engine/strike-candidates" in paths
    assert "/api/v1/engine/execution-check" in paths
