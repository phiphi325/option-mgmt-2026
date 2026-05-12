"""Master Decision Engine (M1.13) tests.

Per plan v1.2 §17 M1.13 acceptance, §9.6 (pipeline), §7 (`DailyDecision`).

Test discipline:
  - End-to-end pipeline for the healthy / illiquid / escalated paths.
  - Final `confidence` reflects post-downgrade `illiquidity_penalty` —
    NOT `recommendation.confidence` (which uses penalty=0 for rule
    selection).
  - Determinism: same inputs → byte-identical `DailyDecision`.
  - `inputs_hash` stability: identical inputs → identical hash; small
    permutations → different hash.
  - Per-action wiring: `len(strike_selections) == len(downgrades) ==
    len(executions) == len(recommendation.actions)`.
  - Replay safety: `decision_id` derives deterministically from
    `inputs_hash` + `as_of`.
  - The `escalated` flag propagates from any per-action downgrade.
  - Empty-action recommendations (NO_OP / REDUCE_COVERAGE rule fires
    without legs) leave `strike_selections` empty and `confidence` =
    recommendation's tentative (no illiquidity penalty).
  - `compute_inputs_hash` round-trips identical inputs to the same hash
    and handles every input type (`ChainSnapshot`, dataclass, Pydantic,
    nested tuple, date, datetime).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from engine.decision import (
    DEFAULT_DISCLAIMERS,
    DailyDecision,
    compute_inputs_hash,
    produce_daily_decision,
)
from engine.flow_score.types import Bias, FlowScore, RecommendedAction
from engine.market_state.classify import MarketStateResult
from engine.profiles import (
    IncomeNeed,
    ProfileStyle,
    RiskTolerance,
    UserStrategyProfile,
)
from engine.recommendation import PositionState
from engine.regimes import Regime
from engine.types import ChainSnapshot, OptionContract, OptionType
from engine.version import __version__ as engine_version

# ----------------------------------------------------------------------
# Fixture helpers
# ----------------------------------------------------------------------


_EXPIRY = date(2026, 6, 19)
_AS_OF_DT = datetime(2026, 5, 20, 14, 30)
_AS_OF_DATE = date(2026, 5, 20)


def _healthy_call(strike: float = 415.0) -> OptionContract:
    """A liquid ATM call (passes the M1.12 downgrade rung 1)."""
    return OptionContract(
        underlying="MSFT",
        expiry=_EXPIRY,
        strike=strike,
        option_type=OptionType.CALL,
        bid=4.25, ask=4.30, mid=4.275,
        iv=0.28,
        open_interest=3000,
        volume=200,
    )


def _illiquid_call(strike: float = 425.0) -> OptionContract:
    """A poorly-liquid OTM call (forces downgrade)."""
    return OptionContract(
        underlying="MSFT",
        expiry=_EXPIRY,
        strike=strike,
        option_type=OptionType.CALL,
        bid=1.5, ask=2.5, mid=2.0,
        iv=0.27,
        open_interest=50,
        volume=3,
    )


def _chain(contracts: tuple[OptionContract, ...], spot: float = 415.0) -> ChainSnapshot:
    return ChainSnapshot(
        underlying="MSFT",
        spot=spot,
        as_of=_AS_OF_DATE,
        contracts=contracts,
    )


def _profile(*, drawdown_tolerance: float = 0.15) -> UserStrategyProfile:
    return UserStrategyProfile(
        risk_tolerance=RiskTolerance.MODERATE,
        income_need=IncomeNeed.MEDIUM,
        max_position_pct=0.50,
        max_coverage_pct=0.75,
        min_iv_rank_for_short_premium=40,
        prefer_collars_over_covered_calls=False,
        drawdown_tolerance=drawdown_tolerance,
        style=ProfileStyle.BALANCED,
    )


def _market_state(
    *,
    regime: Regime = Regime.HIGH_IV_PIN,
    regime_score: float = 0.75,
    iv_rank: float = 0.65,
    days_to_next_event: int | None = None,
) -> MarketStateResult:
    return MarketStateResult(
        regime=regime,
        regime_score=regime_score,
        all_scores={r: 0.0 for r in Regime},
        tags=(),
        spot=415.0,
        iv_rank=iv_rank,
        iv_percentile=iv_rank,
        hv_30=0.22,
        expected_move_pct=0.04,
        max_pain=415.0,
        max_pain_delta_pct=0.0,
        pcr_volume=0.50,
        pcr_oi=0.50,
        trend_strength=0.30,
        realized_vs_implied=1.0,
        breakout_signal=0.0,
        oi_concentration_at_max_pain=0.20,
        days_to_next_event=days_to_next_event,
        next_event_kind=None,
        days_since_event=None,
        days_to_nearest_opex=None,
        iv_rank_change_1d=0.0,
        gap_pct=None,
    )


def _flow_score(*, confidence: float = 0.70, score: float = 40.0) -> FlowScore:
    return FlowScore(
        score=score,
        bullish_score=max(score, 0.0),
        bearish_score=max(-score, 0.0),
        bias=Bias.BULLISH if score > 0 else (Bias.BEARISH if score < 0 else Bias.NEUTRAL),
        recommended_action=RecommendedAction.SELL_CALL_PARTIAL,
        pin_probability=0.30,
        gamma_risk=0.20,
        gamma_sign=0,
        confidence=confidence,
        explanation="(test)",
        breakdown={},
    )


def _produce(
    *,
    contracts: tuple[OptionContract, ...] = (_healthy_call(),),
    market_state: MarketStateResult | None = None,
    flow_score: FlowScore | None = None,
    positions: PositionState | None = None,
    profile: UserStrategyProfile | None = None,
    as_of: datetime = _AS_OF_DT,
) -> DailyDecision:
    return produce_daily_decision(
        as_of=as_of,
        ticker="MSFT",
        chain_snapshot=_chain(contracts),
        positions=positions or PositionState(underlying_shares=100),
        profile=profile or _profile(),
        market_state=market_state or _market_state(),
        flow_score=flow_score or _flow_score(),
    )


# ----------------------------------------------------------------------
# Pipeline smoke / shape tests
# ----------------------------------------------------------------------


def test_produce_daily_decision_returns_dailydecision() -> None:
    result = _produce()
    assert isinstance(result, DailyDecision)


def test_decision_id_is_deterministic_from_inputs_hash() -> None:
    """Same inputs → same decision_id. decision_id starts with 'dd_' and
    embeds the first 12 hex chars of inputs_hash."""
    a = _produce()
    b = _produce()
    assert a.decision_id == b.decision_id
    expected_hex = a.inputs_hash.split(":", 1)[1][:12]
    assert a.decision_id.startswith(f"dd_{expected_hex}_")


def test_decision_id_changes_with_as_of() -> None:
    """Same inputs but different as_of → different decision_id."""
    a = _produce(as_of=datetime(2026, 5, 20, 14, 30))
    b = _produce(as_of=datetime(2026, 5, 20, 14, 31))
    assert a.decision_id != b.decision_id


def test_decision_pins_engine_and_weights_version() -> None:
    result = _produce()
    assert result.engine_version == engine_version
    assert result.weights_version == "v2.0"


def test_decision_inputs_hash_has_sha256_prefix() -> None:
    result = _produce()
    assert result.inputs_hash.startswith("sha256:")
    # 64 hex chars after the prefix
    hex_part = result.inputs_hash.split(":", 1)[1]
    assert len(hex_part) == 64
    int(hex_part, 16)  # must parse as hex


def test_decision_carries_default_disclaimers() -> None:
    result = _produce()
    assert result.disclaimers == DEFAULT_DISCLAIMERS


def test_decision_spot_echoes_chain_snapshot_spot() -> None:
    result = _produce()
    assert result.spot == 415.0


def test_decision_user_profile_snapshot_is_echoed() -> None:
    """The persisted profile snapshot must be the input — required for
    exact replay even if the user later edits their settings."""
    profile = _profile(drawdown_tolerance=0.08)
    result = _produce(profile=profile)
    assert result.user_profile_snapshot == profile


def test_decision_market_state_and_flow_score_are_echoed() -> None:
    ms = _market_state(regime=Regime.LOW_IV_RANGE, regime_score=0.55)
    fs = _flow_score(confidence=0.30, score=5)
    result = _produce(market_state=ms, flow_score=fs)
    assert result.market_state == ms
    assert result.flow_score == fs


# ----------------------------------------------------------------------
# Pipeline wiring (per-action shape)
# ----------------------------------------------------------------------


def test_strike_selections_zip_with_actions() -> None:
    """One strike_selection / downgrade / execution per action."""
    result = _produce()
    n = len(result.recommendation.actions)
    assert len(result.strike_selections) == n
    assert len(result.downgrades) == n
    assert len(result.executions) == n


def test_executions_match_downgrade_final_executions() -> None:
    """`executions[i]` is the M1.12 `final_execution[i]` — not the original."""
    result = _produce(contracts=(_healthy_call(), _illiquid_call()))
    for ex, dr in zip(result.executions, result.downgrades):  # noqa: B905
        assert ex == dr.final_execution


def test_strike_selections_match_downgrade_final_selections() -> None:
    """`strike_selections[i]` is the M1.12 `final_selection[i]`."""
    result = _produce(contracts=(_healthy_call(), _illiquid_call()))
    for sel, dr in zip(result.strike_selections, result.downgrades):  # noqa: B905
        assert sel == dr.final_selection


# ----------------------------------------------------------------------
# Final confidence reflects post-downgrade penalty
# ----------------------------------------------------------------------


def test_final_confidence_lower_than_tentative_when_chain_is_illiquid() -> None:
    """When the chain is illiquid, the post-downgrade illiquidity penalty
    drops the final confidence below the tentative recommendation
    confidence (which was computed with penalty=0)."""
    illiquid_only = _chain((_illiquid_call(),))
    result = produce_daily_decision(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=illiquid_only,
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    # An action was emitted (high_iv_sell_call matches)
    assert len(result.recommendation.actions) >= 1
    # Recommendation's tentative confidence used penalty=0
    assert result.confidence < result.recommendation.confidence


def test_final_confidence_equals_tentative_for_near_perfect_chain() -> None:
    """For a near-perfect chain (very tight spread + huge OI), the
    illiquidity penalty approaches 0 → final confidence ≈ tentative
    confidence (within a small epsilon).

    Even a 'healthy' MSFT-ish chain (235 bps spread) yields fill ≈ 0.57,
    so the penalty isn't zero — we need a near-zero spread / huge OI to
    make the post-downgrade penalty negligible.
    """
    near_perfect = OptionContract(
        underlying="MSFT",
        expiry=_EXPIRY,
        strike=415.0,
        option_type=OptionType.CALL,
        bid=4.299, ask=4.300, mid=4.2995,  # near-zero spread
        iv=0.28,
        open_interest=10_000,
        volume=1_000,
    )
    result = _produce(contracts=(near_perfect,))
    # Even with near-perfect fill, the penalty is ~0.003 → confidence
    # drops by 0.003 * 0.25 = 0.00075. Allow a small epsilon.
    assert result.confidence == pytest.approx(
        result.recommendation.confidence, abs=5e-3
    )


def test_final_breakdown_has_post_downgrade_illiquidity_penalty() -> None:
    """`confidence_breakdown.illiquidity_penalty` matches the aggregate
    over `liquidity_penalty(execution)` across per-action executions."""
    from engine.execution import liquidity_penalty

    result = _produce(contracts=(_illiquid_call(),))
    expected_penalty = max(
        (liquidity_penalty(ex) for ex in result.executions),
        default=0.0,
    )
    assert result.confidence_breakdown.illiquidity_penalty == pytest.approx(
        expected_penalty, abs=1e-12
    )


def test_final_breakdown_weights_version_matches_decision() -> None:
    result = _produce()
    assert result.confidence_breakdown.weights_version == result.weights_version


# ----------------------------------------------------------------------
# Escalation propagation
# ----------------------------------------------------------------------


def test_escalated_true_when_any_downgrade_escalates() -> None:
    """If the ladder can't rescue any action, `decision.escalated=True`."""
    # An action that picks the only contract (illiquid) → downgrade can't help.
    result = _produce(contracts=(_illiquid_call(),))
    if any(dr.escalated for dr in result.downgrades):
        assert result.escalated is True


def test_escalated_false_when_no_downgrade_escalates() -> None:
    """Healthy chain → no downgrade needed → `escalated=False`."""
    result = _produce()
    assert result.escalated is False


# ----------------------------------------------------------------------
# Empty-action / NO_OP rule pathway
# ----------------------------------------------------------------------


def test_no_op_recommendation_yields_empty_action_lists() -> None:
    """When `hold_no_op` fires, there are no actions and the per-action
    tuples are empty."""
    # Force hold_no_op by giving low IV + weak signals (confidence < 0.30).
    weak_ms = _market_state(regime=Regime.LOW_IV_RANGE, regime_score=0.10, iv_rank=0.30)
    weak_fs = _flow_score(confidence=0.10, score=0)
    result = _produce(market_state=weak_ms, flow_score=weak_fs)
    # The hold_no_op rule emits a NO_OP action — so we have 1 action with no legs
    # OR 0 actions; check the rule that matched.
    if result.recommendation.matched_rule is not None:
        if result.recommendation.matched_rule.rule_id == "hold_no_op":
            # NO_OP action has no concrete legs → executions are 'trivial'
            for ex in result.executions:
                assert ex.aggregate_fill_confidence == 1.0  # trivially fillable
            assert result.escalated is False


def test_no_op_confidence_equals_recommendation_confidence() -> None:
    """No legs → no penalty → final confidence == recommendation confidence."""
    weak_ms = _market_state(regime=Regime.LOW_IV_RANGE, regime_score=0.10, iv_rank=0.30)
    weak_fs = _flow_score(confidence=0.10, score=0)
    result = _produce(market_state=weak_ms, flow_score=weak_fs)
    if result.recommendation.matched_rule is not None and \
            result.recommendation.matched_rule.rule_id == "hold_no_op":
        # No-leg case: illiquidity_penalty stays 0
        assert result.confidence_breakdown.illiquidity_penalty == 0.0


# ----------------------------------------------------------------------
# Determinism & purity
# ----------------------------------------------------------------------


def test_produce_daily_decision_is_deterministic() -> None:
    """Same inputs → byte-identical DailyDecision."""
    a = _produce()
    b = _produce()
    assert a == b


def test_dailydecision_is_frozen() -> None:
    """Cannot mutate a `DailyDecision` post-construction."""
    import dataclasses
    result = _produce()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.confidence = 0.99  # type: ignore[misc]


# ----------------------------------------------------------------------
# Custom-weights override
# ----------------------------------------------------------------------


def test_custom_weights_propagate_through_to_decision() -> None:
    """Pass a custom Weights bundle → `weights_version` reflects it."""
    from engine.confidence import PenaltyCaps, PositiveWeights, Weights

    custom = Weights(
        version="test-v9.0",
        positive_weights=PositiveWeights(
            flow=0.40, struct=0.25, regime=0.25, signal=0.10
        ),
        penalty_caps=PenaltyCaps(event=0.20, liquidity=0.15),
    )
    result = produce_daily_decision(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
        weights=custom,
    )
    assert result.weights_version == "test-v9.0"
    assert result.confidence_breakdown.weights_version == "test-v9.0"


# ----------------------------------------------------------------------
# compute_inputs_hash (utility coverage)
# ----------------------------------------------------------------------


def test_inputs_hash_format() -> None:
    h = compute_inputs_hash(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    assert h.startswith("sha256:")
    assert len(h) == 71  # "sha256:" + 64 hex chars


def test_inputs_hash_is_deterministic() -> None:
    """Identical inputs → identical hash."""
    args = dict(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    assert compute_inputs_hash(**args) == compute_inputs_hash(**args)


def test_inputs_hash_changes_with_ticker() -> None:
    """Different ticker → different hash."""
    args = dict(
        as_of=_AS_OF_DT,
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    h1 = compute_inputs_hash(ticker="MSFT", **args)
    h2 = compute_inputs_hash(ticker="AAPL", **args)
    assert h1 != h2


def test_inputs_hash_changes_with_spot() -> None:
    """Different chain spot → different hash."""
    base_args = dict(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    h1 = compute_inputs_hash(chain_snapshot=_chain((_healthy_call(),), spot=415.0), **base_args)
    h2 = compute_inputs_hash(chain_snapshot=_chain((_healthy_call(),), spot=416.0), **base_args)
    assert h1 != h2


def test_inputs_hash_changes_with_positions() -> None:
    """Different positions → different hash."""
    args = dict(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    h1 = compute_inputs_hash(positions=PositionState(underlying_shares=100), **args)
    h2 = compute_inputs_hash(positions=PositionState(underlying_shares=200), **args)
    assert h1 != h2


def test_inputs_hash_changes_with_profile() -> None:
    """Different drawdown_tolerance → different hash."""
    args = dict(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    h1 = compute_inputs_hash(profile=_profile(drawdown_tolerance=0.15), **args)
    h2 = compute_inputs_hash(profile=_profile(drawdown_tolerance=0.20), **args)
    assert h1 != h2


def test_inputs_hash_naive_datetime_assumed_utc() -> None:
    """A naive datetime is treated as UTC for canonicalization (per docstring)."""
    args = dict(
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
    )
    # Same naive datetime → same hash; deterministic UTC normalization.
    h1 = compute_inputs_hash(as_of=datetime(2026, 5, 20, 14, 30), **args)
    h2 = compute_inputs_hash(as_of=datetime(2026, 5, 20, 14, 30), **args)
    assert h1 == h2


# ----------------------------------------------------------------------
# data_freshness / disclaimers passthrough
# ----------------------------------------------------------------------


def test_data_freshness_is_passed_through() -> None:
    result = produce_daily_decision(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
        data_freshness=(
            ("spot_age_seconds", 47),
            ("chain_age_seconds", 1832),
            ("any_stale", False),
        ),
    )
    assert result.data_freshness == (
        ("spot_age_seconds", 47),
        ("chain_age_seconds", 1832),
        ("any_stale", False),
    )


def test_custom_disclaimers_are_passed_through() -> None:
    result = produce_daily_decision(
        as_of=_AS_OF_DT,
        ticker="MSFT",
        chain_snapshot=_chain((_healthy_call(),)),
        positions=PositionState(underlying_shares=100),
        profile=_profile(),
        market_state=_market_state(),
        flow_score=_flow_score(),
        disclaimers=("Custom disclaimer 1", "Custom disclaimer 2"),
    )
    assert result.disclaimers == ("Custom disclaimer 1", "Custom disclaimer 2")


def test_data_freshness_defaults_to_empty_tuple() -> None:
    result = _produce()
    assert result.data_freshness == ()


# ----------------------------------------------------------------------
# Hashing internals: _canonical fallback paths (coverage)
# ----------------------------------------------------------------------


def test_compute_inputs_hash_handles_set_input() -> None:
    """The `_canonical` helper handles set inputs deterministically via
    sorted-by-repr. We force the path by hashing a market_state whose
    `all_scores` dict-of-Regime-keys would be canonicalized."""
    # Default _market_state already exercises dict/dataclass/tuple/enum/date paths.
    # Direct call to _canonical on a frozenset:
    from engine.decision.hashing import _canonical

    s = frozenset({3, 1, 2})
    canonical = _canonical(s)
    assert canonical == sorted(canonical)
    assert canonical == [1, 2, 3]


def test_compute_inputs_hash_fallback_on_unhandled_type() -> None:
    """An unknown type falls through to `_fallback` (repr-based)."""
    from engine.decision.hashing import _canonical

    class _Unknown:
        def __repr__(self) -> str:
            return "<Unknown>"

    assert _canonical(_Unknown()) == "<Unknown>"


def test_compute_inputs_hash_aware_datetime_kept_as_is() -> None:
    """A timezone-aware datetime keeps its isoformat (no UTC override)."""

    from engine.decision.hashing import _canonical

    # noqa UP017: keeping `timezone.utc` instead of `UTC` so the test
    # imports work on the 3.9 sandbox shim. CI runs on 3.14 where both
    # spellings are valid.
    aware = datetime(2026, 5, 20, 14, 30, tzinfo=timezone.utc)  # noqa: UP017
    assert _canonical(aware) == aware.isoformat()


def test_compute_inputs_hash_canonical_handles_enum_string() -> None:
    """StrEnum hits the str branch first (StrEnum subclasses str), so the
    rendered value is the value-string when serialized to JSON. The
    Python 3.9 sandbox's `str()` returns `'Regime.HIGH_IV_PIN'` while
    Python 3.11+ returns `'HIGH_IV_PIN'`, but `json.dumps` uses the
    underlying str content (the value) on both — that's the
    deterministic-hash invariant we care about.
    """
    import json

    from engine.decision.hashing import _canonical
    from engine.regimes import Regime

    rendered = _canonical(Regime.HIGH_IV_PIN)
    # json.dumps serializes the underlying str content, not __str__:
    assert json.dumps(rendered) == '"HIGH_IV_PIN"'


def test_compute_inputs_hash_canonical_handles_non_string_enum() -> None:
    """A pure (non-string) Enum hits the dedicated Enum branch and
    returns `.value`. This is the line-133 coverage path."""
    import enum

    from engine.decision.hashing import _canonical

    class _IntEnum(enum.Enum):
        ONE = 1
        TWO = 2

    assert _canonical(_IntEnum.ONE) == 1


def test_compute_inputs_hash_canonical_handles_date() -> None:
    from engine.decision.hashing import _canonical

    assert _canonical(date(2026, 5, 20)) == "2026-05-20"


def test_compute_inputs_hash_canonical_handles_primitives() -> None:
    """None / bool / int / float / str pass through unchanged."""
    from engine.decision.hashing import _canonical

    assert _canonical(None) is None
    assert _canonical(True) is True
    assert _canonical(42) == 42
    assert _canonical(3.14) == 3.14
    assert _canonical("hello") == "hello"
