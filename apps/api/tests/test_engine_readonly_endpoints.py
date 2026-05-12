"""Unit tests for the M1.15 `/engine/{what-if,market-state,flow-score}` endpoints.

These tests exercise the HTTP shape + validation + auth via TestClient
in-process. None of them require Postgres — what-if is non-persisting
by design (§22.14), and the other two endpoints have nothing to persist.

Scope (per plan §17 M1.15 + the M1.15 dev spec):
  - 401 when no Authorization header (3 tests, one per endpoint)
  - /what-if: happy path → 200, no override → matches a daily-plan
    persist=False run on the same body (deterministic)
  - /what-if: with overrides → distinct inputs_hash vs no-override run
  - /what-if: invalid override key → 422 with the key list
  - /what-if: invalid override value (e.g. iv_rank=1.5) → 422 (Pydantic)
  - /market-state: happy path HIGH_IV_PIN → regime matches
  - /market-state: happy path BREAKOUT (high breakout_signal) → regime matches
  - /market-state: missing required field (breakout_signal) → 422
  - /market-state: invalid iv_rank range → 422
  - /flow-score: happy path → 200 + V1 contract fields present
  - /flow-score: missing expiry_focus → 422
  - /flow-score: empty expiry_focus list → 422 (Pydantic min_length=1)
  - OpenAPI: all three new paths registered

Conftest provides the shared TestClient + sets JWT_SECRET.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token

pytestmark = []


# ----------------------------------------------------------------------
# Fixture helpers — mirror the M1.14 test fixture style for consistency
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    token = create_access_token(subject="00000000-0000-0000-0000-000000000001")
    return {"Authorization": f"Bearer {token}"}


def _chain_payload() -> dict[str, Any]:
    """A liquid ATM call chain shared across all three M1.15 endpoints."""
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


def _profile_payload() -> dict[str, Any]:
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


def _market_state_payload(regime: str = "HIGH_IV_PIN") -> dict[str, Any]:
    return {
        "regime": regime,
        "regime_score": 0.75,
        "all_scores": {
            "HIGH_IV_EVENT": 0.30,
            "HIGH_IV_PIN": 0.75,
            "LOW_IV_TREND": 0.10,
            "LOW_IV_RANGE": 0.15,
            "BREAKOUT": 0.05,
            "POST_EVENT_REPRICE": 0.10,
        },
        "tags": [],
        "spot": 415.0,
        "iv_rank": 0.65,
        "iv_percentile": 0.60,
        "hv_30": 0.22,
        "expected_move_pct": 0.04,
        "max_pain": 415.0,
        "max_pain_delta_pct": 0.0,
        "pcr_volume": 0.50,
        "pcr_oi": 0.50,
        "trend_strength": 0.30,
        "realized_vs_implied": 1.0,
        "breakout_signal": 0.0,
        "oi_concentration_at_max_pain": 0.20,
        "days_to_next_event": 14,
        "next_event_kind": "earnings",
        "days_since_event": None,
        "days_to_nearest_opex": None,
        "iv_rank_change_1d": 0.0,
        "gap_pct": None,
    }


def _flow_score_payload() -> dict[str, Any]:
    return {
        "score": 40.0,
        "bullish_score": 55.0,
        "bearish_score": 15.0,
        "bias": "BULLISH",
        "recommended_action": "SELL_CALL_PARTIAL",
        "pin_probability": 0.30,
        "gamma_risk": 0.20,
        "gamma_sign": 0,
        "confidence": 0.70,
        "explanation": "(test)",
        "breakdown": {},
    }


def _inputs_payload() -> dict[str, Any]:
    return {
        "chain_snapshot": _chain_payload(),
        "positions": {"underlying_shares": 100},
        "profile": _profile_payload(),
        "market_state": _market_state_payload(),
        "flow_score": _flow_score_payload(),
    }


def _what_if_body(*, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ticker": "MSFT",
        "as_of": datetime(2026, 5, 20, 14, 30, tzinfo=timezone.utc).isoformat(),  # noqa: UP017
        "inputs": _inputs_payload(),
        "overrides": overrides or {},
    }
    return body


def _market_state_body(
    *, regime_signal: str = "pin", **overrides: Any
) -> dict[str, Any]:
    """Build a classify() request body that selects a known regime."""
    if regime_signal == "pin":
        body: dict[str, Any] = {
            "ticker": "MSFT",
            "spot": 415.0,
            "iv_rank": 0.65,
            "iv_percentile": 0.60,
            "hv_30": 0.22,
            "expected_move_pct": 0.04,
            "max_pain": 415.0,
            "pcr_volume": 0.50,
            "pcr_oi": 0.50,
            "trend_strength": 0.30,
            "realized_vs_implied": 1.0,
            "breakout_signal": 0.0,
            "oi_concentration_at_max_pain": 0.30,
            "days_to_next_event": 14,
            "next_event_kind": "earnings",
            "days_since_event": None,
            "days_to_nearest_opex": 2,
            "iv_rank_change_1d": 0.0,
            "gap_pct": None,
        }
    elif regime_signal == "breakout":
        body = {
            "ticker": "MSFT",
            "spot": 415.0,
            "iv_rank": 0.40,
            "iv_percentile": 0.45,
            "hv_30": 0.22,
            "expected_move_pct": 0.04,
            "max_pain": 400.0,
            "pcr_volume": 0.50,
            "pcr_oi": 0.50,
            "trend_strength": 0.40,
            "realized_vs_implied": 1.0,
            "breakout_signal": 0.95,
            "oi_concentration_at_max_pain": 0.10,
            "days_to_next_event": 30,
            "next_event_kind": None,
            "days_since_event": None,
            "days_to_nearest_opex": None,
            "iv_rank_change_1d": 0.0,
            "gap_pct": None,
        }
    else:
        raise ValueError(f"unknown regime_signal: {regime_signal}")
    body.update(overrides)
    return body


def _flow_score_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ticker": "MSFT",
        "chain_snapshot": _chain_payload(),
        "spot": 415.0,
        "expiry_focus": [date(2026, 6, 19).isoformat()],
        "dte_to_nearest_opex": 30,
        "risk_free_rate": 0.05,
        "dividend_yield": 0.0,
    }
    body.update(overrides)
    return body


# ----------------------------------------------------------------------
# Auth — 401 across all three new endpoints
# ----------------------------------------------------------------------


def test_what_if_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/engine/what-if", json=_what_if_body())
    assert r.status_code == 401, r.text


def test_market_state_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/engine/market-state", json=_market_state_body())
    assert r.status_code == 401, r.text


def test_flow_score_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/engine/flow-score", json=_flow_score_body())
    assert r.status_code == 401, r.text


# ----------------------------------------------------------------------
# /engine/what-if
# ----------------------------------------------------------------------


def test_what_if_returns_200_no_overrides(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Happy path: what-if without overrides runs the engine and returns 200."""
    r = client.post(
        "/api/v1/engine/what-if",
        json=_what_if_body(),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_row"] is False  # discriminant; never persists
    decision = body["decision"]
    assert decision["ticker"] == "MSFT"
    assert decision["inputs_hash"].startswith("sha256:")
    assert decision["weights_version"] == "v2.0"


def test_what_if_matches_daily_plan_no_persist(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Without overrides, what-if and daily-plan persist=False produce the SAME decision."""
    what_if_body = _what_if_body()
    daily_plan_body = {
        **{k: v for k, v in what_if_body.items() if k != "overrides"},
        "persist": False,
    }
    r_what = client.post(
        "/api/v1/engine/what-if",
        json=what_if_body,
        headers=auth_headers,
    )
    r_daily = client.post(
        "/api/v1/engine/daily-plan",
        json=daily_plan_body,
        headers=auth_headers,
    )
    assert r_what.status_code == 200, r_what.text
    assert r_daily.status_code == 200, r_daily.text
    assert (
        r_what.json()["decision"]["inputs_hash"]
        == r_daily.json()["decision"]["inputs_hash"]
    )


def test_what_if_overrides_change_inputs_hash(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Applying a `spot` override changes inputs_hash vs the no-override run."""
    r_no_override = client.post(
        "/api/v1/engine/what-if",
        json=_what_if_body(),
        headers=auth_headers,
    )
    r_with_override = client.post(
        "/api/v1/engine/what-if",
        json=_what_if_body(overrides={"spot": 425.0}),
        headers=auth_headers,
    )
    assert r_no_override.status_code == r_with_override.status_code == 200
    h0 = r_no_override.json()["decision"]["inputs_hash"]
    h1 = r_with_override.json()["decision"]["inputs_hash"]
    assert h0 != h1, "overrides must change the inputs_hash"


def test_what_if_unknown_override_key_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Override keys must match MarketStateResultModel fields; otherwise 422."""
    r = client.post(
        "/api/v1/engine/what-if",
        json=_what_if_body(overrides={"not_a_real_field": 1.0}),
        headers=auth_headers,
    )
    assert r.status_code == 422, r.text
    assert "not_a_real_field" in r.text


def test_what_if_invalid_override_value_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """iv_rank > 1.0 violates Field(le=1.0); service raises ValueError → 422."""
    r = client.post(
        "/api/v1/engine/what-if",
        json=_what_if_body(overrides={"iv_rank": 1.5}),
        headers=auth_headers,
    )
    assert r.status_code == 422, r.text


# ----------------------------------------------------------------------
# /engine/market-state
# ----------------------------------------------------------------------


def test_market_state_high_iv_pin(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Pin-flavored inputs → HIGH_IV_PIN regime."""
    r = client.post(
        "/api/v1/engine/market-state",
        json=_market_state_body(regime_signal="pin"),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["market_state"]["regime"] == "HIGH_IV_PIN"
    assert 0.0 <= body["market_state"]["regime_score"] <= 1.0


def test_market_state_breakout(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """High breakout_signal (0.95) + low IV → BREAKOUT regime."""
    r = client.post(
        "/api/v1/engine/market-state",
        json=_market_state_body(regime_signal="breakout"),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["market_state"]["regime"] == "BREAKOUT"


def test_market_state_response_carries_all_scores(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Response includes the all_scores map for explainability."""
    r = client.post(
        "/api/v1/engine/market-state",
        json=_market_state_body(),
        headers=auth_headers,
    )
    ms = r.json()["market_state"]
    assert "all_scores" in ms
    assert set(ms["all_scores"].keys()) == {
        "HIGH_IV_EVENT", "HIGH_IV_PIN", "LOW_IV_TREND",
        "LOW_IV_RANGE", "BREAKOUT", "POST_EVENT_REPRICE",
    }


def test_market_state_missing_breakout_signal_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = _market_state_body()
    del body["breakout_signal"]
    r = client.post("/api/v1/engine/market-state", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_market_state_invalid_iv_rank_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = _market_state_body(iv_rank=1.5)
    r = client.post("/api/v1/engine/market-state", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


# ----------------------------------------------------------------------
# /engine/flow-score
# ----------------------------------------------------------------------


def test_flow_score_returns_200(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Happy path: liquid ATM chain → 200 + V1 contract fields."""
    r = client.post(
        "/api/v1/engine/flow-score",
        json=_flow_score_body(),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    fs = r.json()["flow_score"]
    # V1 LOCKED contract (§22.2 / §9.3a) — all 11 fields present
    for field in (
        "score", "bullish_score", "bearish_score", "bias",
        "recommended_action", "pin_probability", "gamma_risk",
        "gamma_sign", "confidence", "explanation", "breakdown",
    ):
        assert field in fs, f"missing V1 contract field: {field}"
    # Score is signed
    assert -100.0 <= fs["score"] <= 100.0
    # Bullish/bearish are non-negative
    assert fs["bullish_score"] >= 0.0
    assert fs["bearish_score"] >= 0.0


def test_flow_score_missing_expiry_focus_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = _flow_score_body()
    del body["expiry_focus"]
    r = client.post("/api/v1/engine/flow-score", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_flow_score_empty_expiry_focus_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Pydantic Field(min_length=1) rejects an empty expiry_focus list."""
    r = client.post(
        "/api/v1/engine/flow-score",
        json=_flow_score_body(expiry_focus=[]),
        headers=auth_headers,
    )
    assert r.status_code == 422, r.text


# ----------------------------------------------------------------------
# OpenAPI registration
# ----------------------------------------------------------------------


def test_m1_15_routes_in_openapi(client: TestClient) -> None:
    """All three new paths appear in the generated OpenAPI document."""
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/engine/what-if" in paths
    assert "/api/v1/engine/market-state" in paths
    assert "/api/v1/engine/flow-score" in paths
