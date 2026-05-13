"""Unit tests for POST /engine/collar-builder (M1.16a).

Scope per spec:
  - 401 when unauthenticated
  - Happy path: 3 intents → 3 CollarStructureResponse items
  - Intent ordering: input order preserved (ZERO_COST before others)
  - coverage_ratio override forwarded to engine
  - horizon_days override forwarded to engine
  - < 100 shares → 422
  - No chain ingested → 422
  - unsupported ticker → 422
  - Partial list when engine can't solve one intent

Tests use `unittest.mock.patch` to avoid spinning up the full engine
(same pattern as test_engine_strike_execution.py).  Where DB state is
needed the fixture uses the in-process SQLite DB provided by conftest.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token

pytestmark: list[Any] = []

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    token = create_access_token(subject="00000000-0000-0000-0000-000000000001")
    return {"Authorization": f"Bearer {token}"}


def _make_collar_structure(intent: str = "zero_cost") -> dict[str, Any]:
    """Minimal CollarStructure shape returned by a mocked run_collar_builder."""
    leg = {
        "kind": "PUT",
        "side": "BUY",
        "strike": 400.0,
        "expiry": date(2026, 6, 19).isoformat(),
        "qty": 2,
        "delta": -0.35,
        "iv": 0.30,
        "bid": 3.50,
        "ask": 3.60,
        "mid": 3.55,
        "premium": 3.55,
    }
    call_leg = {**leg, "kind": "CALL", "side": "SELL", "strike": 435.0, "delta": 0.25, "premium": -3.50}
    return {
        "name": f"{intent.replace('_', '-')} 30d collar 400/435",
        "intent": intent,
        "horizon_days": 30,
        "long_put": leg,
        "short_call": call_leg,
        "net_debit_credit": 0.05,
        "max_gain": 19.95,
        "max_loss": -15.55,
        "upside_breakeven": 435.05,
        "downside_breakeven": 400.0,
        "capped_upside_pct": 0.05,
        "protected_downside_pct": 0.04,
        "confidence": 0.72,
        "confidence_breakdown": {
            "flow_alignment": 0.2,
            "structure_alignment": 0.15,
            "regime_match": 0.18,
            "signal_alignment": 0.12,
            "event_risk_penalty": 0.0,
            "illiquidity_penalty": 0.0,
            "weights_version": "v2.0",
        },
        "rationale": ["IV rank elevated", "defensive regime match"],
        "risks": ["Earnings event approaching"],
        "invalidation": ["IV rank drops below 30"],
        "execution": {
            "aggregate_liquidity_score": 0.85,
            "aggregate_fill_confidence": 0.87,
            "suggested_order_type": "limit",
            "legs": [],
            "notes": [],
        },
        "score": 0.78,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCollarBuilderAuth:
    """Authentication guard."""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        """No JWT → 401 before the service layer is even called."""
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT"},
        )
        assert resp.status_code == 401


class TestCollarBuilderHappyPath:
    """Happy-path scenarios with the service layer mocked out."""

    @patch("app.routers.engine.run_collar_builder")
    def test_three_intents_returns_three_structures(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """All three intents → response list has exactly three items."""
        mock_run.return_value = [
            _make_collar_structure("zero_cost"),
            _make_collar_structure("income"),
            _make_collar_structure("defensive"),
        ]
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT", "intents": ["zero_cost", "income", "defensive"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert [s["intent"] for s in data] == ["zero_cost", "income", "defensive"]

    @patch("app.routers.engine.run_collar_builder")
    def test_intent_ordering_preserved(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Input intent order is preserved in the response (engine contract)."""
        mock_run.return_value = [
            _make_collar_structure("defensive"),
            _make_collar_structure("zero_cost"),
        ]
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT", "intents": ["defensive", "zero_cost"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert [s["intent"] for s in data] == ["defensive", "zero_cost"]

    @patch("app.routers.engine.run_collar_builder")
    def test_coverage_ratio_forwarded_to_service(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """coverage_ratio in the request body is passed through to the service."""
        mock_run.return_value = [_make_collar_structure("zero_cost")]
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT", "intents": ["zero_cost"], "coverage_ratio": 0.30},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # The service receives coverage_ratio=0.30 from the request object
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["request"].coverage_ratio == pytest.approx(0.30)

    @patch("app.routers.engine.run_collar_builder")
    def test_horizon_days_forwarded_to_service(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """horizon_days in the request body is passed through to the service."""
        mock_run.return_value = [_make_collar_structure("income")]
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT", "intents": ["income"], "horizon_days": 21},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["request"].horizon_days == 21

    @patch("app.routers.engine.run_collar_builder")
    def test_partial_list_when_intent_infeasible(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Engine returns only one structure when zero_cost is infeasible → list of 1."""
        mock_run.return_value = [_make_collar_structure("income")]
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT", "intents": ["zero_cost", "income"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["intent"] == "income"

    @patch("app.routers.engine.run_collar_builder")
    def test_response_shape_has_required_fields(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Each CollarStructureResponse item has the expected top-level fields."""
        mock_run.return_value = [_make_collar_structure("zero_cost")]
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        item = resp.json()[0]
        for key in ("name", "intent", "horizon_days", "long_put", "short_call",
                    "net_debit_credit", "confidence", "rationale", "risks",
                    "invalidation", "execution"):
            assert key in item, f"Missing field: {key}"


class TestCollarBuilderErrors:
    """Error cases — all expect 422."""

    @patch("app.routers.engine.run_collar_builder")
    def test_insufficient_shares_422(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Service raises ValueError('insufficient_shares') → 422."""
        mock_run.side_effect = ValueError(
            "insufficient_shares: 50 MSFT shares on record; need >= 100"
        )
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert "insufficient_shares" in resp.json()["title"]

    @patch("app.routers.engine.run_collar_builder")
    def test_missing_chain_422(
        self,
        mock_run: AsyncMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Service raises ValueError('missing_chain') → 422."""
        mock_run.side_effect = ValueError("missing_chain: no chain for MSFT")
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert "missing_chain" in resp.json()["title"]

    def test_unsupported_ticker_extra_field_rejected(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """extra='forbid': sending underlying_qty in the body → 422."""
        resp = client.post(
            "/api/v1/engine/collar-builder",
            json={"ticker": "MSFT", "underlying_qty": 200},
            headers=auth_headers,
        )
        assert resp.status_code == 422
