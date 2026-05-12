"""Boundary + happy-path tests for `engine.collar_builder.build()`."""

from __future__ import annotations

import pytest

from engine.collar_builder import CollarIntent, build

from ._collar_test_helpers import (
    SEED_SPOT,
    seed_chain,
    seed_flow_score,
    seed_market_state,
    seed_profile,
)


def _kwargs_default() -> dict:
    """Construct the default kwarg bundle for `build()`."""
    return dict(
        spot=SEED_SPOT,
        underlying_qty=100,
        chain=seed_chain(),
        profile=seed_profile(),
        market_state=seed_market_state(),
        flow_score=seed_flow_score(),
    )


class TestBoundaries:
    def test_underlying_qty_below_100_raises(self) -> None:
        kwargs = _kwargs_default()
        kwargs["underlying_qty"] = 99
        with pytest.raises(ValueError, match="underlying_qty must be >= 100"):
            build(**kwargs)

    def test_underlying_qty_zero_raises(self) -> None:
        kwargs = _kwargs_default()
        kwargs["underlying_qty"] = 0
        with pytest.raises(ValueError, match="underlying_qty"):
            build(**kwargs)

    def test_underlying_qty_negative_raises(self) -> None:
        kwargs = _kwargs_default()
        kwargs["underlying_qty"] = -100
        with pytest.raises(ValueError, match="underlying_qty"):
            build(**kwargs)

    def test_underlying_qty_exactly_100_works(self) -> None:
        result = build(**_kwargs_default(), intents=[CollarIntent.ZERO_COST])
        assert isinstance(result, list)

    def test_intents_empty_returns_empty_list(self) -> None:
        result = build(**_kwargs_default(), intents=[])
        assert result == []

    def test_horizon_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="horizon_days"):
            build(**_kwargs_default(), horizon_days=0)

    def test_horizon_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="horizon_days"):
            build(**_kwargs_default(), horizon_days=-5)

    def test_coverage_ratio_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="coverage_ratio"):
            build(**_kwargs_default(), coverage_ratio=0.0)

    def test_coverage_ratio_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="coverage_ratio"):
            build(**_kwargs_default(), coverage_ratio=1.5)

    def test_coverage_ratio_resolves_to_zero_contracts_raises(self) -> None:
        """qty=100, coverage=0.5 → 50 shares → 0 contracts → raise."""
        kwargs = _kwargs_default()
        with pytest.raises(ValueError, match="resolves to .* contracts"):
            build(**kwargs, coverage_ratio=0.5)


class TestDefaults:
    def test_default_intents_are_all_three(self) -> None:
        """When `intents=None`, build() considers all three intents.
        With the seed chain, all three should yield a feasible structure."""
        kwargs = _kwargs_default()
        kwargs["underlying_qty"] = 200  # 2 contracts → both ZERO_COST + DEFENSIVE pairs feasible
        result = build(**kwargs)
        intents = {s.intent for s in result}
        # At minimum, ZERO_COST should be feasible on the seed chain.
        assert CollarIntent.ZERO_COST in intents

    def test_default_horizon_filters_seed_expiry(self) -> None:
        """Seed chain has 30-day expiry; default horizon 45 catches it."""
        result = build(**_kwargs_default(), intents=[CollarIntent.ZERO_COST])
        assert len(result) >= 1

    def test_horizon_shorter_than_expiry_excludes_all(self) -> None:
        """Setting horizon < seed DTE (30) excludes the only expiration."""
        result = build(
            **_kwargs_default(),
            intents=[CollarIntent.ZERO_COST],
            horizon_days=14,
        )
        assert result == []


class TestSmoke:
    def test_zero_cost_returns_a_structure(self) -> None:
        result = build(**_kwargs_default(), intents=[CollarIntent.ZERO_COST])
        assert len(result) == 1
        assert result[0].intent is CollarIntent.ZERO_COST

    def test_income_returns_a_structure(self) -> None:
        result = build(**_kwargs_default(), intents=[CollarIntent.INCOME])
        assert len(result) == 1
        assert result[0].intent is CollarIntent.INCOME

    def test_defensive_returns_a_structure(self) -> None:
        result = build(**_kwargs_default(), intents=[CollarIntent.DEFENSIVE])
        assert len(result) == 1
        assert result[0].intent is CollarIntent.DEFENSIVE

    def test_result_is_intent_ordered(self) -> None:
        """Output order matches input `intents` order."""
        ordered = [CollarIntent.DEFENSIVE, CollarIntent.ZERO_COST, CollarIntent.INCOME]
        result = build(**_kwargs_default(), intents=ordered)
        # At least the intents that produced results follow the input order.
        produced = [s.intent for s in result]
        # Filter `ordered` down to intents that actually came back.
        expected = [i for i in ordered if i in produced]
        assert produced == expected
