"""Unit tests for the M1.14 `/engine/*` endpoints.

These tests exercise the HTTP shape + validation + auth via TestClient
in-process. They use `persist=False` to avoid requiring a real
Postgres connection; the persistence path is exercised by the smoke
tests under `tests/test_smoke_engine.py`.

Scope:
  - 401 when no Authorization header
  - 422 on malformed request bodies (missing fields, wrong types)
  - 200 with `persist=False` returns a valid `DailyDecisionResponse`
  - 200 from `/engine/recommend` returns the rule pipeline output
  - The response carries the M1.13 three-pin replay metadata
    (engine_version, weights_version, inputs_hash)
  - The decision_id format matches `dd_<hex12>_<unix>`
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token

# Conftest provides the shared TestClient + sets JWT_SECRET.
pytestmark = []


# ----------------------------------------------------------------------
# Fixture helpers
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    """Issue a valid JWT for the test user."""
    token = create_access_token(subject="00000000-0000-0000-0000-000000000001")
    return {"Authorization": f"Bearer {token}"}


def _chain_payload() -> dict[str, Any]:
    """A liquid ATM call chain for SELL_COVERED_CALL_PARTIAL to fire."""
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


def _daily_plan_body(*, persist: bool = False) -> dict[str, Any]:
    return {
        "ticker": "MSFT",
        "as_of": datetime(2026, 5, 20, 14, 30, tzinfo=timezone.utc).isoformat(),  # noqa: UP017
        "inputs": _inputs_payload(),
        "persist": persist,
    }


def _recommend_body() -> dict[str, Any]:
    return {
        "ticker": "MSFT",
        "market_state": _market_state_payload(),
        "flow_score": _flow_score_payload(),
        "positions": {"underlying_shares": 100},
        "profile": _profile_payload(),
    }


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------


def test_daily_plan_requires_auth(client: TestClient) -> None:
    """No Authorization header → 401."""
    r = client.post("/api/v1/engine/daily-plan", json=_daily_plan_body())
    assert r.status_code == 401, r.text


def test_recommend_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/engine/recommend", json=_recommend_body())
    assert r.status_code == 401, r.text


def test_daily_plan_invalid_jwt_returns_401(client: TestClient) -> None:
    r = client.post(
        "/api/v1/engine/daily-plan",
        json=_daily_plan_body(),
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401, r.text


# ----------------------------------------------------------------------
# /engine/daily-plan — success path (persist=False to skip DB)
# ----------------------------------------------------------------------


def test_daily_plan_returns_200_no_persist(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """End-to-end pipeline runs with `persist=False`."""
    r = client.post(
        "/api/v1/engine/daily-plan",
        json=_daily_plan_body(persist=False),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_row"] is False  # nothing was persisted
    decision = body["decision"]
    assert decision["ticker"] == "MSFT"
    assert decision["engine_version"]  # stamped
    assert decision["weights_version"] == "v2.0"
    assert decision["inputs_hash"].startswith("sha256:")
    assert len(decision["inputs_hash"]) == 71
    # decision_id format: dd_<12hex>_<unix>
    assert decision["decision_id"].startswith("dd_")
    assert decision["decision_id"].count("_") == 2


def test_daily_plan_response_has_full_pipeline_output(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify every M1.13 DailyDecision field is in the JSON response."""
    r = client.post(
        "/api/v1/engine/daily-plan",
        json=_daily_plan_body(persist=False),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    decision = r.json()["decision"]
    for required_field in (
        "decision_id", "as_of", "ticker", "spot",
        "user_profile_snapshot", "market_state", "flow_score",
        "recommendation",
        "strike_selections", "downgrades", "executions",
        "confidence", "confidence_breakdown",
        "inputs_hash", "engine_version", "weights_version",
        "data_freshness", "disclaimers", "escalated",
    ):
        assert required_field in decision, f"missing field: {required_field}"


def test_daily_plan_determinism(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Two calls with identical inputs → identical inputs_hash + decision_id."""
    body = _daily_plan_body(persist=False)
    r1 = client.post("/api/v1/engine/daily-plan", json=body, headers=auth_headers)
    r2 = client.post("/api/v1/engine/daily-plan", json=body, headers=auth_headers)
    assert r1.status_code == r2.status_code == 200
    d1 = r1.json()["decision"]
    d2 = r2.json()["decision"]
    assert d1["inputs_hash"] == d2["inputs_hash"]
    assert d1["decision_id"] == d2["decision_id"]
    assert d1["confidence"] == d2["confidence"]


def test_daily_plan_high_iv_pin_emits_sell_call_action(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """HIGH_IV_PIN + iv_rank=0.65 + no short call → high_iv_sell_call fires."""
    r = client.post(
        "/api/v1/engine/daily-plan",
        json=_daily_plan_body(persist=False),
        headers=auth_headers,
    )
    decision = r.json()["decision"]
    actions = decision["recommendation"]["actions"]
    assert len(actions) >= 1
    assert actions[0]["emit"] == "SELL_COVERED_CALL_PARTIAL"


# ----------------------------------------------------------------------
# /engine/daily-plan — validation errors
# ----------------------------------------------------------------------


# NOTE: M1.17.5 made `DailyPlanRequest.inputs` optional — submitting a
# body without `inputs` no longer triggers a Pydantic 422 because the
# service hydrates from DB instead. The previous
# `test_daily_plan_missing_inputs_returns_422` test was therefore
# semantically invalidated and is removed. The new happy path (omitted
# inputs → DB hydration → 200) and the new failure cases (missing
# positions / chain / iv_history → 422 from hydration) are smoke-tested
# in `tests/test_smoke_m1_17_5.py` against the real Postgres in the CI
# smoke job — same rationale as M1.17's market_service unit-test gap.


def test_daily_plan_invalid_iv_rank_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """iv_rank > 1.0 violates the Pydantic Field(le=1.0) constraint."""
    body = _daily_plan_body(persist=False)
    body["inputs"]["market_state"]["iv_rank"] = 1.5
    r = client.post("/api/v1/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_daily_plan_invalid_regime_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Regime must match one of the 6 enum values."""
    body = _daily_plan_body(persist=False)
    body["inputs"]["market_state"]["regime"] = "NOT_A_REAL_REGIME"
    r = client.post("/api/v1/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 422


def test_daily_plan_extra_field_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Pydantic extra="forbid" rejects unknown fields."""
    body = _daily_plan_body(persist=False)
    body["unexpected_field"] = "should be rejected"
    r = client.post("/api/v1/engine/daily-plan", json=body, headers=auth_headers)
    assert r.status_code == 422


# ----------------------------------------------------------------------
# /engine/recommend
# ----------------------------------------------------------------------


def test_recommend_returns_200(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Recommend pipeline runs without persistence."""
    r = client.post(
        "/api/v1/engine/recommend",
        json=_recommend_body(),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    rec = body["recommendation"]
    assert "matched_rule" in rec
    assert "actions" in rec
    assert "confidence" in rec
    assert "regime" in rec
    assert rec["regime"] == "HIGH_IV_PIN"


def test_recommend_emits_sell_call_action(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/v1/engine/recommend",
        json=_recommend_body(),
        headers=auth_headers,
    )
    rec = r.json()["recommendation"]
    assert len(rec["actions"]) >= 1
    assert rec["actions"][0]["emit"] == "SELL_COVERED_CALL_PARTIAL"


def test_recommend_response_does_not_carry_inputs_hash(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The recommend response is a RecommendationResult, not a DailyDecision —
    no inputs_hash / engine_version / weights_version on this surface."""
    r = client.post(
        "/api/v1/engine/recommend",
        json=_recommend_body(),
        headers=auth_headers,
    )
    body = r.json()
    assert "inputs_hash" not in body["recommendation"]


def test_recommend_missing_market_state_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = _recommend_body()
    del body["market_state"]
    r = client.post("/api/v1/engine/recommend", json=body, headers=auth_headers)
    assert r.status_code == 422


# ----------------------------------------------------------------------
# OpenAPI registration
# ----------------------------------------------------------------------


def test_engine_routes_in_openapi(client: TestClient) -> None:
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/engine/daily-plan" in paths
    assert "/api/v1/engine/recommend" in paths
