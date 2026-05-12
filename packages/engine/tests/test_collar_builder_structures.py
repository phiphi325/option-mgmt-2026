"""Per-intent solver tests for `engine.collar_builder.structures`."""

from __future__ import annotations

from engine.collar_builder import CollarIntent, build
from engine.collar_builder.structures import (
    DEFENSIVE_MAX_DEBIT_PCT,
    INCOME_MIN_CAPPED_UPSIDE_PCT,
    ZERO_COST_TOLERANCE,
    _candidate_expirations,
)
from engine.types import ChainSnapshot, OptionContract, OptionType

from ._collar_test_helpers import (
    SEED_AS_OF,
    SEED_EXPIRY,
    SEED_SPOT,
    seed_chain,
    seed_flow_score,
    seed_market_state,
    seed_profile,
)


def _kwargs() -> dict:
    return dict(
        spot=SEED_SPOT,
        underlying_qty=200,
        chain=seed_chain(),
        profile=seed_profile(),
        market_state=seed_market_state(),
        flow_score=seed_flow_score(),
    )


class TestZeroCostSolver:
    def test_finds_pair_within_tolerance(self) -> None:
        results = build(**_kwargs(), intents=[CollarIntent.ZERO_COST])
        assert len(results) == 1
        zc = results[0]
        assert abs(zc.net_debit_credit) <= ZERO_COST_TOLERANCE

    def test_no_solution_below_tolerance_returns_empty(self) -> None:
        """When `drawdown_tolerance` excludes EVERY put in the chain,
        the zero-cost solver has no protective leg to pair → returns
        an empty list (not an exception)."""
        kwargs = _kwargs()
        # Bump drawdown_tolerance above the deepest available put's
        # protection (360P → 10%). With min_protection = 0.11, no put
        # qualifies for the protective floor; the solver yields no
        # pairs at all.
        kwargs["profile"] = seed_profile(drawdown_tolerance=0.11)
        results = build(**kwargs, intents=[CollarIntent.ZERO_COST])
        assert results == []


class TestIncomeSolver:
    def test_finds_net_credit_pair(self) -> None:
        results = build(**_kwargs(), intents=[CollarIntent.INCOME])
        assert len(results) == 1
        inc = results[0]
        assert inc.net_debit_credit <= 0  # credit

    def test_respects_min_capped_upside(self) -> None:
        """Selected call must offer ≥ INCOME_MIN_CAPPED_UPSIDE_PCT
        room above spot."""
        results = build(**_kwargs(), intents=[CollarIntent.INCOME])
        assert results[0].capped_upside_pct >= INCOME_MIN_CAPPED_UPSIDE_PCT


class TestDefensiveSolver:
    def test_finds_max_protection_within_debit_cap(self) -> None:
        results = build(**_kwargs(), intents=[CollarIntent.DEFENSIVE])
        assert len(results) == 1
        df = results[0]
        # Maximum debit per share = DEFENSIVE_MAX_DEBIT_PCT * spot
        # (since position_notional = spot * 100 * contracts and the
        # cap is normalized to per-share).
        max_debit_per_share = DEFENSIVE_MAX_DEBIT_PCT * SEED_SPOT
        assert df.net_debit_credit <= max_debit_per_share + 1e-9

    def test_picks_deepest_protective_put(self) -> None:
        """On the seed chain, DEFENSIVE should pick 360P (deepest
        protection) paired with 430C (in-band call)."""
        results = build(**_kwargs(), intents=[CollarIntent.DEFENSIVE])
        df = results[0]
        # 360P is the lowest-strike put in the seed chain.
        assert df.long_put.strike == 360.0


class TestExpirationFiltering:
    def test_zero_horizon_returns_no_expirations(self) -> None:
        chain = seed_chain()
        assert _candidate_expirations(chain, 0) == []

    def test_horizon_30_includes_seed_expiry(self) -> None:
        chain = seed_chain()
        exps = _candidate_expirations(chain, 30)
        assert SEED_EXPIRY in exps

    def test_horizon_29_excludes_seed_expiry(self) -> None:
        """Seed DTE is exactly 30; horizon 29 should exclude it."""
        chain = seed_chain()
        assert _candidate_expirations(chain, 29) == []


class TestEmptyChainDegradesGracefully:
    def test_chain_with_no_in_band_calls_returns_empty(self) -> None:
        """Chain with only deep-ITM calls yields no in-band candidates."""
        contracts = (
            OptionContract(
                underlying="MSFT",
                expiry=SEED_EXPIRY,
                strike=200.0,  # deep ITM call → delta ≈ 0.99, out of band
                option_type=OptionType.CALL,
                bid=200.0,
                ask=205.0,
                iv=0.30,
                open_interest=10,
                volume=5,
            ),
            OptionContract(
                underlying="MSFT",
                expiry=SEED_EXPIRY,
                strike=350.0,
                option_type=OptionType.PUT,
                bid=0.05,
                ask=0.10,
                iv=0.30,
                open_interest=100,
                volume=10,
            ),
        )
        chain = ChainSnapshot(
            underlying="MSFT", spot=SEED_SPOT, as_of=SEED_AS_OF, contracts=contracts
        )
        result = build(
            spot=SEED_SPOT,
            underlying_qty=200,
            chain=chain,
            profile=seed_profile(),
            market_state=seed_market_state(),
            flow_score=seed_flow_score(),
            intents=[CollarIntent.ZERO_COST],
        )
        assert result == []

    def test_completely_empty_chain_returns_empty(self) -> None:
        chain = ChainSnapshot(
            underlying="MSFT",
            spot=SEED_SPOT,
            as_of=SEED_AS_OF,
            contracts=(),
        )
        result = build(
            spot=SEED_SPOT,
            underlying_qty=200,
            chain=chain,
            profile=seed_profile(),
            market_state=seed_market_state(),
            flow_score=seed_flow_score(),
        )
        assert result == []
