"""M1.12 Execution downgrade callback tests.

Per plan v1.2 §9.8 (last paragraph) + §17 M1.12.

Test discipline:
  - `filter_chain_by_liquidity` is exercised across every gate (OI,
    volume, spread, missing quote, broken quote, default kwargs).
  - `downgrade_if_needed` covers: original passes, ladder rung 1
    succeeds, ladder rung 2 succeeds, ladder exhausted (escalated=True),
    empty original selection (NO_OP / REDUCE_COVERAGE / MONETIZE_PUT
    bypass), `len(rung.legs) != len(original.legs)` rejection,
    determinism, and the "no improvement on rung" path.
  - Integration: pipes the final execution's `liquidity_penalty` into
    `recommend(illiquidity_penalty=...)` and verifies confidence
    matches the post-downgrade fill — i.e. the downgrade actually
    influences the M1.10 composer.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.confidence import DEFAULT_WEIGHTS, compose, compute_confidence_inputs
from engine.execution import (
    DOWNGRADE_THRESHOLD,
    DowngradeResult,
    Execution,
    ExecutionLeg,
    OrderType,
    downgrade_if_needed,
    filter_chain_by_liquidity,
    liquidity_penalty,
)
from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import IncomeNeed, ProfileStyle, RiskTolerance, UserStrategyProfile
from engine.recommendation import PositionState, recommend
from engine.recommendation.types import Action, EmittedAction
from engine.recommendation.yaml_loader import load_default_rules
from engine.regimes import Regime
from engine.types import ChainSnapshot, OptionContract, OptionType

# ----------------------------------------------------------------------
# Fixture helpers
# ----------------------------------------------------------------------


_EXPIRY = date(2026, 6, 19)
_AS_OF = date(2026, 5, 20)


def _contract(
    *,
    strike: float,
    option_type: OptionType = OptionType.CALL,
    bid: float | None = 4.25,
    ask: float | None = 4.30,
    mid: float | None = 4.275,
    iv: float | None = 0.28,
    open_interest: int = 3000,
    volume: int = 200,
) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=_EXPIRY,
        strike=strike,
        option_type=option_type,
        bid=bid,
        ask=ask,
        mid=mid,
        iv=iv,
        open_interest=open_interest,
        volume=volume,
    )


def _chain(contracts: tuple[OptionContract, ...], spot: float = 415.0) -> ChainSnapshot:
    return ChainSnapshot(
        underlying="MSFT",
        spot=spot,
        as_of=_AS_OF,
        contracts=contracts,
    )


def _action(
    *,
    emit: EmittedAction = EmittedAction.SELL_COVERED_CALL_PARTIAL,
    target_dte: float = 30.0,
    target_delta: float = 0.25,
    size_pct: float = 0.30,
) -> Action:
    return Action(
        emit=emit,
        parameters={
            "target_dte": target_dte,
            "target_delta": target_delta,
            "size_pct": size_pct,
            "urgency_days": 5.0,
        },
    )


# ----------------------------------------------------------------------
# filter_chain_by_liquidity
# ----------------------------------------------------------------------


def test_filter_default_kwargs_keep_all() -> None:
    """No constraints = identity (modulo new ChainSnapshot wrapping)."""
    contracts = (
        _contract(strike=415.0),
        _contract(strike=420.0, open_interest=50, volume=2),
    )
    filtered = filter_chain_by_liquidity(_chain(contracts))
    assert len(filtered.contracts) == 2


def test_filter_min_oi_gate() -> None:
    contracts = (
        _contract(strike=410.0, open_interest=100),
        _contract(strike=415.0, open_interest=500),
        _contract(strike=420.0, open_interest=2500),
    )
    filtered = filter_chain_by_liquidity(_chain(contracts), min_oi=500)
    assert {c.strike for c in filtered.contracts} == {415.0, 420.0}


def test_filter_min_volume_gate() -> None:
    contracts = (
        _contract(strike=410.0, volume=20),
        _contract(strike=415.0, volume=50),
        _contract(strike=420.0, volume=200),
    )
    filtered = filter_chain_by_liquidity(_chain(contracts), min_volume=50)
    assert {c.strike for c in filtered.contracts} == {415.0, 420.0}


def test_filter_max_spread_bps_gate() -> None:
    """spread = 0.05 on mid 4.275 → 117 bps. spread = 1.0 on mid 4.5 → 2222 bps."""
    tight = _contract(strike=415.0, bid=4.25, ask=4.30, mid=4.275)
    wide = _contract(strike=420.0, bid=4.0, ask=5.0, mid=4.5)
    filtered = filter_chain_by_liquidity(
        _chain((tight, wide)), max_spread_bps=200
    )
    assert len(filtered.contracts) == 1
    assert filtered.contracts[0].strike == 415.0


def test_filter_max_spread_bps_excludes_broken_quote() -> None:
    """Missing bid/ask yields sentinel 9999 — excluded when cap is set."""
    healthy = _contract(strike=415.0)
    broken = _contract(strike=420.0, bid=None, ask=None, mid=None)
    filtered = filter_chain_by_liquidity(
        _chain((healthy, broken)), max_spread_bps=300
    )
    assert len(filtered.contracts) == 1
    assert filtered.contracts[0].strike == 415.0


def test_filter_max_spread_bps_none_keeps_broken_quote() -> None:
    """`max_spread_bps=None` (default) is permissive on broken quotes."""
    healthy = _contract(strike=415.0)
    broken = _contract(strike=420.0, bid=None, ask=None, mid=None)
    filtered = filter_chain_by_liquidity(_chain((healthy, broken)))
    assert len(filtered.contracts) == 2


def test_filter_combined_gates() -> None:
    contracts = (
        _contract(strike=410.0, open_interest=2000, volume=80, bid=4.20, ask=4.30, mid=4.25),
        _contract(strike=415.0, open_interest=3000, volume=200, bid=4.25, ask=4.30, mid=4.275),
        _contract(strike=420.0, open_interest=100, volume=200, bid=4.25, ask=4.30, mid=4.275),
    )
    filtered = filter_chain_by_liquidity(
        _chain(contracts), min_oi=500, min_volume=100, max_spread_bps=130
    )
    assert {c.strike for c in filtered.contracts} == {415.0}


def test_filter_preserves_chain_metadata() -> None:
    chain = _chain((_contract(strike=415.0),), spot=420.0)
    filtered = filter_chain_by_liquidity(chain, min_oi=100)
    assert filtered.underlying == chain.underlying
    assert filtered.spot == chain.spot
    assert filtered.as_of == chain.as_of


def test_filter_empty_chain() -> None:
    filtered = filter_chain_by_liquidity(_chain(()))
    assert filtered.contracts == ()


# ----------------------------------------------------------------------
# downgrade_if_needed — primary paths
# ----------------------------------------------------------------------


def _liquid_atm_call() -> OptionContract:
    """ATM call that clears rung 1 (oi 3000, vol 200, ~117 bps spread)."""
    return _contract(
        strike=415.0,
        bid=4.25, ask=4.30, mid=4.275,
        open_interest=3000, volume=200,
    )


def _illiquid_otm_call() -> OptionContract:
    """OTM call with poor liquidity — original selector prefers this for delta=0.25."""
    return _contract(
        strike=425.0,
        bid=1.50, ask=2.50, mid=2.00,
        open_interest=50, volume=3,
    )


def test_downgrade_original_passes_no_retry() -> None:
    """When original execution already passes the threshold, no ladder traversal."""
    healthy_only = _chain((_liquid_atm_call(),))
    # Target a strike that aligns with the healthy ATM (delta ~0.51 there)
    action = _action(target_delta=0.50)
    result = downgrade_if_needed(action=action, chain_snapshot=healthy_only)
    assert isinstance(result, DowngradeResult)
    assert result.iterations == 0
    assert result.escalated is False
    assert result.original_selection == result.final_selection
    assert result.downgrade_notes == ()


def test_downgrade_rung_one_succeeds_swaps_to_healthy_strike() -> None:
    """Ladder rung 1 filters out the illiquid OTM strike → selector picks the healthy ATM."""
    chain = _chain((_liquid_atm_call(), _illiquid_otm_call()))
    action = _action(target_delta=0.25)  # naturally points at OTM
    result = downgrade_if_needed(action=action, chain_snapshot=chain)
    # Original picked the illiquid OTM
    assert result.original_selection.legs[0].contract.strike == 425.0
    assert result.original_execution.legs[0].fill_confidence < DOWNGRADE_THRESHOLD
    # Final picked the healthy ATM
    assert result.final_selection.legs[0].contract.strike == 415.0
    assert result.final_execution.legs[0].fill_confidence >= DOWNGRADE_THRESHOLD
    assert result.iterations == 1
    assert result.escalated is False
    # Notes track the ladder traversal
    assert any("rung 1" in n and "SUCCESS" in n for n in result.downgrade_notes)


def test_downgrade_ladder_exhausted_escalated_true() -> None:
    """All strikes are too illiquid — no rung rescues the action."""
    # Two illiquid strikes — both fail every ladder rung.
    chain = _chain(
        (
            _contract(strike=415.0, bid=4.0, ask=5.0, mid=4.5, open_interest=20, volume=2),
            _contract(strike=420.0, bid=2.0, ask=3.0, mid=2.5, open_interest=10, volume=1),
        )
    )
    action = _action()
    result = downgrade_if_needed(action=action, chain_snapshot=chain)
    assert result.escalated is True
    assert result.iterations == 2  # all rungs tried
    assert result.original_execution.legs[0].fill_confidence < DOWNGRADE_THRESHOLD
    assert result.final_execution.legs[0].fill_confidence < DOWNGRADE_THRESHOLD
    assert any("escalated" in n for n in result.downgrade_notes)


def test_downgrade_no_contracts_clear_rung_skipped() -> None:
    """When a ladder rung's filter empties the chain, the rung is recorded as 'no contracts cleared'."""
    # All strikes have OI < 500, so rung 1 (min_oi=500) clears no contracts.
    chain = _chain(
        (
            _contract(strike=410.0, open_interest=100, volume=200, bid=4.0, ask=4.1, mid=4.05),
            _contract(strike=415.0, open_interest=200, volume=200, bid=4.0, ask=4.1, mid=4.05),
        )
    )
    action = _action(target_delta=0.50)
    result = downgrade_if_needed(action=action, chain_snapshot=chain)
    # Both rungs will report 'no contracts cleared the floor'.
    rung1_notes = [n for n in result.downgrade_notes if "rung 1" in n]
    assert any("no contracts cleared the floor" in n for n in rung1_notes)


def test_downgrade_empty_selection_bypasses_ladder() -> None:
    """REDUCE_COVERAGE / MONETIZE_PUT / NO_OP have no legs — never downgraded."""
    chain = _chain((_liquid_atm_call(),))
    for emit in (
        EmittedAction.NO_OP,
        EmittedAction.REDUCE_COVERAGE,
        EmittedAction.MONETIZE_PUT,
    ):
        action = _action(emit=emit)
        result = downgrade_if_needed(action=action, chain_snapshot=chain)
        assert result.original_selection.legs == ()
        assert result.final_selection.legs == ()
        assert result.iterations == 0
        assert result.escalated is False
        assert result.downgrade_notes == ()


def test_downgrade_leg_count_mismatch_rung_rejected() -> None:
    """When a rung's stricter filter eliminates one of the required legs (e.g. the collar's call leg has no liquid candidate), the rung is skipped — it would lose a leg.

    Setup:
      - Call leg: low OI (200, fails rung 1 min_oi=500), wide spread → fill far below threshold.
      - Put leg: high OI (600, passes rung 1), tight spread → fill comfortably passes.

    Original collar gets both legs; the call's poor fill drags the
    aggregate below threshold → ladder entered. Rung 1 filters out the
    call (OI too low) → selector can't produce a 2-leg collar → leg
    count drops to 0 → rung is skipped with the leg-count note.
    """
    # Call with low OI (rung 1 will drop) AND wide spread (forces original below threshold).
    call_c = _contract(
        strike=420.0, option_type=OptionType.CALL,
        bid=3.5, ask=4.0, mid=3.75,
        iv=0.30, open_interest=200, volume=5,
    )
    # Put that comfortably passes rung 1 (OI=600, tight spread).
    put_c = _contract(
        strike=410.0, option_type=OptionType.PUT,
        bid=4.00, ask=4.05, mid=4.025,
        iv=0.30, open_interest=600, volume=80,
    )
    chain = _chain((call_c, put_c))
    action = _action(emit=EmittedAction.OPEN_COLLAR)
    result = downgrade_if_needed(action=action, chain_snapshot=chain)
    assert len(result.original_selection.legs) == 2
    # The "leg count != original" path must fire on at least one rung.
    assert any(
        "leg count" in n and "skip" in n for n in result.downgrade_notes
    ), f"expected leg-count-mismatch note in {result.downgrade_notes}"


def test_downgrade_partial_improvement_kept_as_best_so_far() -> None:
    """When rung 1 dramatically improves fill but the threshold is set above what rung 1 can clear, the rung is recorded as 'partial improvement; keeping as best-so-far'; rung 2 then reports 'no improvement; skip'."""
    # Three call strikes:
    #   - worst_otm (delta ~0.25): wide spread; original picks this; fill ≈ 0.22
    #   - liquid_atm (delta ~0.50): tight spread; clears both rungs; fill ≈ 0.96
    # With threshold=0.99, even the liquid_atm strike (fill 0.96) doesn't pass.
    # Rung 1 keeps the liquid_atm → 'partial improvement'.
    # Rung 2 picks the same strike → 'no improvement'.
    worst_otm = _contract(
        strike=425.0,
        bid=1.5, ask=2.5, mid=2.0,
        iv=0.27, open_interest=600, volume=60,
    )
    liquid_atm = _contract(
        strike=415.0,
        bid=4.275, ask=4.285, mid=4.28,
        iv=0.28, open_interest=3000, volume=200,
    )
    chain = _chain((liquid_atm, worst_otm))
    action = _action(target_delta=0.25)
    result = downgrade_if_needed(
        action=action, chain_snapshot=chain, threshold=0.99
    )
    assert any("partial improvement" in n for n in result.downgrade_notes)
    assert any("no improvement" in n for n in result.downgrade_notes)
    # The ladder was exhausted (still < 0.99); final selection is the better strike.
    assert result.escalated is True
    assert result.final_selection.legs[0].contract.strike == 415.0


def test_min_fill_empty_legs_returns_one() -> None:
    """`_min_fill` on an empty Execution returns 1.0 (trivially fillable)."""
    # Direct internal-helper coverage. The empty-Execution path is reachable in
    # principle (a rung's `assess([])` if leg-count check ever returned 0),
    # but coverage tooling needs a direct call to mark it covered.
    from engine.execution.downgrade import _min_fill
    empty_exec = Execution(
        aggregate_liquidity_score=1.0,
        aggregate_fill_confidence=1.0,
        suggested_order_type=OrderType.LIMIT,
        legs=(),
        notes=(),
    )
    assert _min_fill(empty_exec) == 1.0


def test_downgrade_determinism() -> None:
    """Same inputs → byte-identical DowngradeResult."""
    chain = _chain((_liquid_atm_call(), _illiquid_otm_call()))
    action = _action(target_delta=0.25)
    a = downgrade_if_needed(action=action, chain_snapshot=chain)
    b = downgrade_if_needed(action=action, chain_snapshot=chain)
    assert a == b


def test_downgrade_custom_threshold() -> None:
    """A relaxed threshold should let the original pass that would otherwise downgrade."""
    chain = _chain((_liquid_atm_call(), _illiquid_otm_call()))
    action = _action(target_delta=0.25)
    # Default 0.50 threshold → original fails, ladder rescues
    default_result = downgrade_if_needed(action=action, chain_snapshot=chain)
    assert default_result.iterations == 1

    # Aggressive (lower) threshold — original passes
    relaxed_result = downgrade_if_needed(
        action=action, chain_snapshot=chain, threshold=0.01
    )
    assert relaxed_result.iterations == 0
    assert relaxed_result.escalated is False


def test_downgrade_threshold_default_is_downgrade_threshold() -> None:
    """The default threshold kwarg equals `DOWNGRADE_THRESHOLD = 0.50`."""
    assert DOWNGRADE_THRESHOLD == 0.50


# ----------------------------------------------------------------------
# Integration: downgrade → liquidity_penalty → recommend / compose
# ----------------------------------------------------------------------


def _profile() -> UserStrategyProfile:
    return UserStrategyProfile(
        risk_tolerance=RiskTolerance.MODERATE,
        income_need=IncomeNeed.MEDIUM,
        max_position_pct=0.50,
        max_coverage_pct=0.75,
        min_iv_rank_for_short_premium=40,
        prefer_collars_over_covered_calls=False,
        drawdown_tolerance=0.15,
        style=ProfileStyle.BALANCED,
    )


def _market_state() -> MarketStateResult:
    return MarketStateResult(
        regime=Regime.LOW_IV_RANGE,
        regime_score=0.60,
        all_scores={r: 0.0 for r in Regime},
        tags=(),
        spot=415.0,
        iv_rank=0.50,
        iv_percentile=0.50,
        hv_30=0.20,
        expected_move_pct=0.04,
        max_pain=415.0,
        max_pain_delta_pct=0.0,
        pcr_volume=0.50,
        pcr_oi=0.50,
        trend_strength=0.30,
        realized_vs_implied=1.0,
        breakout_signal=0.0,
        oi_concentration_at_max_pain=0.20,
        days_to_next_event=None,
        next_event_kind=None,
        days_since_event=None,
        days_to_nearest_opex=None,
        iv_rank_change_1d=0.0,
        gap_pct=None,
    )


def _flow_score(confidence: float = 0.60, score: float = 20.0) -> FlowScore:
    return FlowScore(
        score=score, bullish_score=max(score, 0.0), bearish_score=max(-score, 0.0),
        bias=Bias.NEUTRAL, recommended_action=RecommendedAction.MONITOR,
        pin_probability=0.0, gamma_risk=0.20, gamma_sign=0,
        confidence=confidence, explanation="(test)", breakdown={},
    )


def test_downgrade_improves_recommend_confidence() -> None:
    """End-to-end: ladder rescue → smaller illiquidity_penalty → higher recommend() confidence."""
    rules = load_default_rules()
    chain = _chain((_liquid_atm_call(), _illiquid_otm_call()))
    action = _action(target_delta=0.25)
    result = downgrade_if_needed(action=action, chain_snapshot=chain)

    # Sanity: the rescue happened.
    assert result.iterations == 1
    assert result.escalated is False

    original_penalty = liquidity_penalty(result.original_execution)
    final_penalty = liquidity_penalty(result.final_execution)
    assert final_penalty < original_penalty

    common = dict(
        market_state=_market_state(),
        flow_score=_flow_score(),
        positions=PositionState(),
        profile=_profile(),
        rules=rules,
    )
    no_downgrade_rec = recommend(**common, illiquidity_penalty=original_penalty)
    with_downgrade_rec = recommend(**common, illiquidity_penalty=final_penalty)
    assert with_downgrade_rec.confidence > no_downgrade_rec.confidence


def test_downgrade_escalated_flow_keeps_high_penalty() -> None:
    """When every rung escalates, liquidity_penalty stays close to 1.0 → confidence drops by the full cap."""
    chain = _chain(
        (
            _contract(strike=415.0, bid=4.0, ask=5.0, mid=4.5, open_interest=20, volume=2),
        )
    )
    result = downgrade_if_needed(action=_action(), chain_snapshot=chain)
    assert result.escalated is True
    final_penalty = liquidity_penalty(result.final_execution)
    assert final_penalty > 0.5  # the chain is genuinely awful

    inputs = compute_confidence_inputs(
        market_state=_market_state(),
        flow_score=_flow_score(),
        profile=_profile(),
        illiquidity_penalty=final_penalty,
    )
    _, breakdown = compose(inputs, DEFAULT_WEIGHTS)
    # The composer should reflect a substantial illiquidity penalty.
    assert breakdown.illiquidity_penalty == final_penalty
    assert breakdown.penalty_multiplier < 1.0


# ----------------------------------------------------------------------
# Shape + invariants
# ----------------------------------------------------------------------


def test_downgrade_result_is_frozen() -> None:
    """`DowngradeResult` is a frozen dataclass; can't be mutated post-construction."""
    chain = _chain((_liquid_atm_call(),))
    result = downgrade_if_needed(action=_action(target_delta=0.50), chain_snapshot=chain)
    # FrozenInstanceError is raised by dataclasses on mutation attempts.
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.iterations = 99  # type: ignore[misc]


def test_downgrade_notes_are_tuple_of_strings() -> None:
    chain = _chain((_liquid_atm_call(), _illiquid_otm_call()))
    result = downgrade_if_needed(action=_action(target_delta=0.25), chain_snapshot=chain)
    assert isinstance(result.downgrade_notes, tuple)
    for note in result.downgrade_notes:
        assert isinstance(note, str)


def test_downgrade_original_execution_always_populated() -> None:
    """Even when the original passes, `original_execution.legs` is populated."""
    chain = _chain((_liquid_atm_call(),))
    result = downgrade_if_needed(
        action=_action(target_delta=0.50), chain_snapshot=chain
    )
    assert len(result.original_execution.legs) == 1
    assert result.original_execution.legs[0].liquidity_score > 0.0


# ----------------------------------------------------------------------
# Edge: post-downgrade Execution still flows through assess() correctly
# ----------------------------------------------------------------------


def test_downgrade_final_execution_consistent_with_assess() -> None:
    """final_execution should be exactly what assess() would produce on final_selection."""
    from engine.execution import assess

    chain = _chain((_liquid_atm_call(), _illiquid_otm_call()))
    result = downgrade_if_needed(action=_action(target_delta=0.25), chain_snapshot=chain)
    re_executed = assess(legs=result.final_selection.legs)
    # Both Executions should be equal (same StrikeLeg → same assess() output).
    assert re_executed == result.final_execution


# ----------------------------------------------------------------------
# Inline ExecutionLeg/Execution use isn't ambiguous: we still import these symbols
# (suppress unused-warning by referencing them in a smoke test).
# ----------------------------------------------------------------------


def test_smoke_executionleg_orderype_imports_resolve() -> None:
    """Smoke-import test: the public surface still re-exports the underlying types."""
    assert ExecutionLeg.__name__ == "ExecutionLeg"
    assert Execution.__name__ == "Execution"
    assert OrderType.LIMIT.value == "limit"
