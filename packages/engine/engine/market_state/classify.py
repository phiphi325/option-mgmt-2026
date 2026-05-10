"""Market State Engine — `classify()` and `MarketStateResult`.

Per plan v1.2 §22.3 (extended `classify()` signature, 18 inputs) and §9.2
(per-regime predicate sketches) and §17 M1.4 (size L, 24 regime fixtures).

`classify()` is the central regime selector for the Phase 1 engine. It
takes a flat record of pre-computed market-state inputs (IV, HV, max
pain, PCR, event proximity, trend strength, breakout signal, etc.) and
emits one of the six locked `Regime` values plus a confidence score in
`[0, 1]`, the score map across all regimes, a tag list for downstream
consumers, and the echoed inputs for explainability.

The function is pure (per ADR-0005). All inputs flow in via kwargs;
there is no DB / network / clock access. The result is hashable-shaped
(frozen dataclass) so `inputs_hash` semantics hold for replay.

## Algorithm

For each of the six regimes we compute a predicate score in `[0, 1]`
(see `_score_*` helpers below — these implement the §9.2 sketches with
audit-noted corrections). The regime with the highest score wins.

**Tie resolution (delta < `_TIE_DELTA`)**: when the runner-up's score
is within `_TIE_DELTA` of the leader, we resolve toward the more
conservative (event-aware) regime per `_TIE_BREAK_PRIORITY`. The
priority is:

    HIGH_IV_EVENT > HIGH_IV_PIN > POST_EVENT_REPRICE > BREAKOUT >
    LOW_IV_TREND > LOW_IV_RANGE

This matches plan §9.2: "Ties (delta < 0.10) resolve toward the more
conservative (event-aware) regime."

## Scale conventions

`iv_rank`, `iv_percentile`, `trend_strength`, `breakout_signal`, and
`oi_concentration_at_max_pain` are all in `[0, 1]` (engine-canonical
scale, matching `engine.market_state.iv.iv_rank()` and
`engine.market_state.trend_strength.compute_trend_strength()`).

`iv_rank_change_1d` is the **delta** of `iv_rank` over one day, so it
lives in `[-1, 1]`. A 20-percentage-point IV crush corresponds to
`iv_rank_change_1d = -0.20`.

`gap_pct` is the post-event price gap as a fraction of spot (e.g.
`0.025 = 2.5%`). It can be positive or negative.

`expected_move_pct` is a fraction of spot (e.g. `0.04 = 4%`).

`spot` and `max_pain` are floats in dollars. Plan v1.2 §22.3 lists
these as `Decimal` aspirationally; the engine currently uses `float`
to match `engine.market_state.compute_max_pain` and `OptionContract`.

## §9.2 sketch corrections

Plan §9.2 has a sign error in `score_post_event_reprice`: the sketch
writes `iv_crushed = max(0, 1 - x.iv_rank_change_1d / -20)`, which
evaluates to 0 (rather than 1) when IV crushes by 20+ points. Per the
adjacent comment "IV dropped >= 20pts" the intended formula is
`iv_crushed = clip01(-iv_rank_change_1d / 0.20)` (in `[0, 1]` scale).
We implement the corrected formula and document the deviation here.

The §9.2 sketch also writes thresholds as raw numbers (e.g. 70, 60, 30,
20) which assume `iv_rank` in `[0, 100]`. Our engine uses `[0, 1]`, so
these are scaled by `1/100` (e.g. 70 → 0.70, slope 10 → 0.10). The
sigmoid arguments are unchanged — both numerator and denominator scale
identically.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine._utils import clip01, sigmoid
from engine.regimes import Regime

# ----------------------------------------------------------------------
# Constants — calibration tunables. Each is documented at point of use
# in the score helpers below; centralized here so they are easy to find.
# ----------------------------------------------------------------------

# Sigmoid threshold and slope for IV "high" / "mid" / "low" components.
# All values are on the engine-canonical [0, 1] iv_rank scale.
_IV_HIGH_THRESHOLD = 0.70  # plan §9.2: 70 in 0..100
_IV_MID_THRESHOLD = 0.60  # plan §9.2: 60 in 0..100
_IV_LOW_THRESHOLD = 0.30  # plan §9.2: 30 in 0..100
_IV_SIGMOID_SLOPE = 0.10  # plan §9.2: 10 in 0..100

# HIGH_IV_EVENT: how close must the next event be to count as "near"?
_HIGH_IV_EVENT_NEAR_DAYS = 7
_HIGH_IV_EVENT_FAR_DEFAULT = 99  # sentinel when days_to_next_event is None

# HIGH_IV_PIN: pin tolerance and opex sensitivity.
# pin_close = max(0, 1 - |spot - max_pain| / spot / _PIN_TOLERANCE_PCT)
_PIN_TOLERANCE_PCT = 0.01  # 1% deviation → pin_close = 0
_OPEX_HORIZON_DAYS = 5  # near_expiry = max(0, 1 - dte/_OPEX_HORIZON_DAYS)
_OPEX_FAR_DEFAULT = 30  # sentinel when days_to_nearest_opex is None

# POST_EVENT_REPRICE: IV-crush and gap thresholds.
_POST_EVENT_WINDOW_DAYS = 1  # only score post-event when within 1 day
_IV_CRUSH_FULL_DROP = 0.20  # 20 pp drop → iv_crushed = 1.0
_POST_EVENT_GAP_THRESHOLD = 0.02  # |gap_pct| > 2% → big_gap = 1.0

# Tie-break: when the leader's margin is below this, prefer the
# higher-priority regime in `_TIE_BREAK_PRIORITY` rather than the raw max.
_TIE_DELTA = 0.10  # plan §9.2: "Ties (delta < 0.10)"

# Tie-break priority. Order is "more conservative / event-aware first".
_TIE_BREAK_PRIORITY: tuple[Regime, ...] = (
    Regime.HIGH_IV_EVENT,
    Regime.HIGH_IV_PIN,
    Regime.POST_EVENT_REPRICE,
    Regime.BREAKOUT,
    Regime.LOW_IV_TREND,
    Regime.LOW_IV_RANGE,
)

# Tag thresholds — all on the canonical [0, 1] scale where applicable.
_TAG_SELL_VOL_FAVORABLE_IV = 0.70
_TAG_SELL_VOL_UNFAVORABLE_IV = 0.30
_TAG_EVENT_HORIZON_DAYS = 14
_TAG_POST_EVENT_HORIZON_DAYS = 2
_TAG_PIN_RISK_DIST = 0.005  # 0.5% of spot
_TAG_PIN_RISK_DTE = 5
_TAG_BREAKOUT_ACTIVE = 0.70
_TAG_TRENDING = 0.70
_TAG_RANGING = 0.30
_TAG_CONCENTRATED_OI = 0.60


# ----------------------------------------------------------------------
# Result type
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class MarketStateResult:
    """Output of `classify()`. Carries the chosen regime, all scores,
    advisory tags, and the echoed inputs for downstream consumers
    (Strike Selector, Recommendation Engine, Confidence Composer, UI).

    `tags` is a `tuple` (not `list`) so the dataclass remains hashable
    when tests want to compare results structurally.

    `all_scores` is a regular `dict` keyed by `Regime` — the dataclass
    itself is `frozen=True` so the field can't be reassigned, though
    the dict's contents are not deep-frozen. Engine code MUST treat it
    as read-only; downstream consumers should `.copy()` if they need
    to mutate.
    """

    # Engine output
    regime: Regime
    regime_score: float
    all_scores: dict[Regime, float]
    tags: tuple[str, ...]

    # Echoed inputs — full input vector for explainability + replay.
    spot: float
    iv_rank: float
    iv_percentile: float
    hv_30: float
    expected_move_pct: float
    max_pain: float
    max_pain_delta_pct: float
    pcr_volume: float
    pcr_oi: float
    trend_strength: float
    realized_vs_implied: float
    breakout_signal: float
    oi_concentration_at_max_pain: float
    days_to_next_event: int | None
    next_event_kind: str | None
    days_since_event: int | None
    days_to_nearest_opex: int | None
    iv_rank_change_1d: float | None
    gap_pct: float | None


# ----------------------------------------------------------------------
# Per-regime score predicates (plan §9.2, scaled to [0, 1] iv_rank)
# ----------------------------------------------------------------------


def _score_high_iv_event(
    *, iv_rank: float, days_to_next_event: int | None
) -> float:
    """HIGH_IV_EVENT: rich premium + scheduled near-term event.

    `iv_high = sigmoid((iv_rank − 0.70) / 0.10)` rises through 0.5 around
    iv_rank = 0.70 and saturates above ~0.85.

    `near_event = 1.0` when an event is within `_HIGH_IV_EVENT_NEAR_DAYS`
    (7) days, else 0. The function never raises — `None` collapses to a
    far-future sentinel so the regime simply scores low rather than
    blocking the whole pipeline.
    """
    iv_high = sigmoid((iv_rank - _IV_HIGH_THRESHOLD) / _IV_SIGMOID_SLOPE)
    days = days_to_next_event if days_to_next_event is not None else _HIGH_IV_EVENT_FAR_DEFAULT
    near_event = 1.0 if days <= _HIGH_IV_EVENT_NEAR_DAYS else 0.0
    return clip01(0.5 * iv_high + 0.5 * near_event)


def _score_high_iv_pin(
    *,
    iv_rank: float,
    spot: float,
    max_pain: float,
    days_to_nearest_opex: int | None,
) -> float:
    """HIGH_IV_PIN: mid-high IV + tight max-pain alignment + near opex."""
    iv_mid = sigmoid((iv_rank - _IV_MID_THRESHOLD) / _IV_SIGMOID_SLOPE)
    pin_close = max(0.0, 1.0 - abs(spot - max_pain) / spot / _PIN_TOLERANCE_PCT)
    dte = days_to_nearest_opex if days_to_nearest_opex is not None else _OPEX_FAR_DEFAULT
    near_expiry = max(0.0, 1.0 - dte / _OPEX_HORIZON_DAYS)
    return clip01(0.4 * iv_mid + 0.4 * pin_close + 0.2 * near_expiry)


def _score_low_iv_trend(*, iv_rank: float, trend_strength: float) -> float:
    """LOW_IV_TREND: low IV + sustained directional movement (high ADX)."""
    iv_low = sigmoid((_IV_LOW_THRESHOLD - iv_rank) / _IV_SIGMOID_SLOPE)
    return clip01(0.5 * iv_low + 0.5 * trend_strength)


def _score_low_iv_range(
    *,
    iv_rank: float,
    trend_strength: float,
    realized_vs_implied: float,
) -> float:
    """LOW_IV_RANGE: low IV + flat ADX + realized matching implied."""
    iv_low = sigmoid((_IV_LOW_THRESHOLD - iv_rank) / _IV_SIGMOID_SLOPE)
    not_trending = 1.0 - clip01(trend_strength)
    realized_matches = max(0.0, 1.0 - abs(realized_vs_implied - 1.0))
    return clip01(0.4 * iv_low + 0.3 * not_trending + 0.3 * realized_matches)


def _score_breakout(*, breakout_signal: float) -> float:
    """BREAKOUT: defer entirely to the breakout_signal composite (§22.5).

    `breakout_signal` is itself a 4-component composite: price-move,
    vol-change, OI-shift, distance-above-resistance (see
    `engine.market_state.breakout`). The Market State Engine simply
    forwards it as the BREAKOUT regime's likelihood.
    """
    return clip01(breakout_signal)


def _score_post_event_reprice(
    *,
    days_since_event: int | None,
    iv_rank_change_1d: float | None,
    gap_pct: float | None,
) -> float:
    """POST_EVENT_REPRICE: just past an event with IV crush + price gap.

    Active only within `_POST_EVENT_WINDOW_DAYS` (1) of the event. Plan
    §9.2 has a sign-flipped iv_crushed formula; we implement the
    intended `clip01(-iv_rank_change_1d / 0.20)` so a 20pp drop → 1.0.
    """
    if days_since_event is None or days_since_event > _POST_EVENT_WINDOW_DAYS:
        return 0.0
    if iv_rank_change_1d is None:
        # No IV-change signal → can't say whether the event repriced
        # anything; the regime is silent rather than guessing.
        return 0.0
    iv_crushed = clip01(-iv_rank_change_1d / _IV_CRUSH_FULL_DROP)
    big_gap = (
        1.0
        if (gap_pct is not None and abs(gap_pct) > _POST_EVENT_GAP_THRESHOLD)
        else 0.0
    )
    return clip01(0.6 * iv_crushed + 0.4 * big_gap)


# ----------------------------------------------------------------------
# Tag generation
# ----------------------------------------------------------------------


def _generate_tags(
    *,
    iv_rank: float,
    days_to_next_event: int | None,
    days_since_event: int | None,
    spot: float,
    max_pain: float,
    days_to_nearest_opex: int | None,
    breakout_signal: float,
    trend_strength: float,
    oi_concentration_at_max_pain: float,
) -> tuple[str, ...]:
    """Advisory tag list. Consumed by Strike Selector / Recommendation /
    Confidence Composer to nudge strategy + rationale strings.

    Tags are best-effort — they're not part of the regime selection
    decision (the regime score map is). Adding a new tag is non-
    breaking; removing or renaming one IS breaking.
    """
    tags: list[str] = []
    if iv_rank >= _TAG_SELL_VOL_FAVORABLE_IV:
        tags.append("sell_vol_favorable")
    if iv_rank <= _TAG_SELL_VOL_UNFAVORABLE_IV:
        tags.append("sell_vol_unfavorable")
    if days_to_next_event is not None and days_to_next_event <= _TAG_EVENT_HORIZON_DAYS:
        tags.append(f"event_in_{days_to_next_event}d")
    if days_since_event is not None and days_since_event <= _TAG_POST_EVENT_HORIZON_DAYS:
        tags.append("post_event_window")
    pin_dist_pct = abs(spot - max_pain) / spot
    if (
        pin_dist_pct <= _TAG_PIN_RISK_DIST
        and days_to_nearest_opex is not None
        and days_to_nearest_opex <= _TAG_PIN_RISK_DTE
    ):
        tags.append("pin_risk")
    if breakout_signal >= _TAG_BREAKOUT_ACTIVE:
        tags.append("breakout_active")
    if trend_strength >= _TAG_TRENDING:
        tags.append("trending")
    elif trend_strength <= _TAG_RANGING:
        tags.append("ranging")
    if oi_concentration_at_max_pain >= _TAG_CONCENTRATED_OI:
        tags.append("concentrated_oi_at_pin")
    return tuple(tags)


# ----------------------------------------------------------------------
# Tie resolution
# ----------------------------------------------------------------------


def _select_regime(scores: dict[Regime, float]) -> tuple[Regime, float]:
    """Select the winning regime from the score map.

    Picks the max-scoring regime. When the runner-up's score is within
    `_TIE_DELTA` of the leader, resolves toward the higher-priority
    regime per `_TIE_BREAK_PRIORITY`.

    Returns the chosen `(regime, score)` pair. The returned score is
    always the score that regime received — not the leader's score —
    so callers can trust `regime_score == all_scores[regime]`.
    """
    max_score = max(scores.values())
    # Candidates within _TIE_DELTA of the leader, in priority order.
    for candidate in _TIE_BREAK_PRIORITY:
        if max_score - scores[candidate] < _TIE_DELTA:
            return candidate, scores[candidate]
    # Fallback (unreachable when _TIE_BREAK_PRIORITY covers all six
    # regimes) — return the literal max if priority list is somehow
    # incomplete. Defensive.
    leader = max(scores, key=lambda r: scores[r])
    return leader, scores[leader]


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def classify(
    *,
    spot: float,
    iv_rank: float,
    iv_percentile: float,
    hv_30: float,
    expected_move_pct: float,
    max_pain: float,
    pcr_volume: float,
    pcr_oi: float,
    days_to_next_event: int | None,
    next_event_kind: str | None,
    trend_strength: float,
    realized_vs_implied: float,
    days_since_event: int | None,
    days_to_nearest_opex: int | None,
    iv_rank_change_1d: float | None,
    gap_pct: float | None,
    breakout_signal: float,
    oi_concentration_at_max_pain: float,
) -> MarketStateResult:
    """Full Market State Engine: score all six regimes, pick the winner,
    emit tags, and echo inputs.

    Per plan v1.2 §22.3 (extended 18-input signature) and §9.2 (predicates).

    Args:
        spot: Current underlying spot. Must be > 0.
        iv_rank: Range-based IV rank in [0, 1].
        iv_percentile: Count-based IV percentile in [0, 1].
        hv_30: 30-day annualized historical volatility (decimal). Must be >= 0.
        expected_move_pct: One-σ expected move as fraction of spot. Must be >= 0.
        max_pain: Max-pain strike for the focus expiry. Must be > 0.
        pcr_volume: Σ put volume / Σ call volume. Must be >= 0.
        pcr_oi: Σ put OI / Σ call OI. Must be >= 0.
        days_to_next_event: Days until next scheduled event, or None.
                            Must be >= 0 when not None.
        next_event_kind: Kind of the next event, e.g. "earnings", or None.
        trend_strength: Wilder-ADX-derived trend score in [0, 1].
        realized_vs_implied: HV / IV ratio. Must be >= 0.
        days_since_event: Days since the most recent event, or None.
                          Must be >= 0 when not None.
        days_to_nearest_opex: Trading days to nearest monthly opex, or None.
                              Must be >= 0 when not None.
        iv_rank_change_1d: One-day delta of `iv_rank` in [-1, 1], or None.
                           Used by POST_EVENT_REPRICE.
        gap_pct: Post-event price gap as a fraction of spot, signed, or None.
        breakout_signal: Composite breakout score in [0, 1] (per §22.5).
        oi_concentration_at_max_pain: Fraction of OI sitting at the max-pain
                                      strike, in [0, 1].

    Returns:
        `MarketStateResult` with the chosen `regime`, the `regime_score`,
        the full `all_scores` map, an advisory `tags` tuple, and the
        echoed input vector.

    Raises:
        ValueError: any input violates its documented bounds. The engine
                    refuses to silently coerce — callers must hydrate
                    valid inputs (the API service layer is responsible
                    for staleness handling per plan §22.12).
    """
    _validate_inputs(
        spot=spot,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        hv_30=hv_30,
        expected_move_pct=expected_move_pct,
        max_pain=max_pain,
        pcr_volume=pcr_volume,
        pcr_oi=pcr_oi,
        days_to_next_event=days_to_next_event,
        trend_strength=trend_strength,
        realized_vs_implied=realized_vs_implied,
        days_since_event=days_since_event,
        days_to_nearest_opex=days_to_nearest_opex,
        iv_rank_change_1d=iv_rank_change_1d,
        breakout_signal=breakout_signal,
        oi_concentration_at_max_pain=oi_concentration_at_max_pain,
    )

    scores: dict[Regime, float] = {
        Regime.HIGH_IV_EVENT: _score_high_iv_event(
            iv_rank=iv_rank, days_to_next_event=days_to_next_event
        ),
        Regime.HIGH_IV_PIN: _score_high_iv_pin(
            iv_rank=iv_rank,
            spot=spot,
            max_pain=max_pain,
            days_to_nearest_opex=days_to_nearest_opex,
        ),
        Regime.LOW_IV_TREND: _score_low_iv_trend(
            iv_rank=iv_rank, trend_strength=trend_strength
        ),
        Regime.LOW_IV_RANGE: _score_low_iv_range(
            iv_rank=iv_rank,
            trend_strength=trend_strength,
            realized_vs_implied=realized_vs_implied,
        ),
        Regime.BREAKOUT: _score_breakout(breakout_signal=breakout_signal),
        Regime.POST_EVENT_REPRICE: _score_post_event_reprice(
            days_since_event=days_since_event,
            iv_rank_change_1d=iv_rank_change_1d,
            gap_pct=gap_pct,
        ),
    }

    regime, regime_score = _select_regime(scores)

    tags = _generate_tags(
        iv_rank=iv_rank,
        days_to_next_event=days_to_next_event,
        days_since_event=days_since_event,
        spot=spot,
        max_pain=max_pain,
        days_to_nearest_opex=days_to_nearest_opex,
        breakout_signal=breakout_signal,
        trend_strength=trend_strength,
        oi_concentration_at_max_pain=oi_concentration_at_max_pain,
    )

    return MarketStateResult(
        regime=regime,
        regime_score=regime_score,
        all_scores=scores,
        tags=tags,
        spot=spot,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        hv_30=hv_30,
        expected_move_pct=expected_move_pct,
        max_pain=max_pain,
        max_pain_delta_pct=(max_pain - spot) / spot,
        pcr_volume=pcr_volume,
        pcr_oi=pcr_oi,
        trend_strength=trend_strength,
        realized_vs_implied=realized_vs_implied,
        breakout_signal=breakout_signal,
        oi_concentration_at_max_pain=oi_concentration_at_max_pain,
        days_to_next_event=days_to_next_event,
        next_event_kind=next_event_kind,
        days_since_event=days_since_event,
        days_to_nearest_opex=days_to_nearest_opex,
        iv_rank_change_1d=iv_rank_change_1d,
        gap_pct=gap_pct,
    )


# ----------------------------------------------------------------------
# Input validation
# ----------------------------------------------------------------------


def _validate_inputs(
    *,
    spot: float,
    iv_rank: float,
    iv_percentile: float,
    hv_30: float,
    expected_move_pct: float,
    max_pain: float,
    pcr_volume: float,
    pcr_oi: float,
    days_to_next_event: int | None,
    trend_strength: float,
    realized_vs_implied: float,
    days_since_event: int | None,
    days_to_nearest_opex: int | None,
    iv_rank_change_1d: float | None,
    breakout_signal: float,
    oi_concentration_at_max_pain: float,
) -> None:
    """Validate every input bound documented on `classify()`.

    Centralised so the public entry point reads cleanly. Each check
    raises `ValueError` with a descriptive message naming the offending
    field and value — the API service layer surfaces these as HTTP 422
    per plan §22.12.
    """
    if spot <= 0.0:
        raise ValueError(f"classify: spot must be > 0; got {spot}")
    if max_pain <= 0.0:
        raise ValueError(f"classify: max_pain must be > 0; got {max_pain}")
    if not 0.0 <= iv_rank <= 1.0:
        raise ValueError(f"classify: iv_rank must be in [0, 1]; got {iv_rank}")
    if not 0.0 <= iv_percentile <= 1.0:
        raise ValueError(
            f"classify: iv_percentile must be in [0, 1]; got {iv_percentile}"
        )
    if hv_30 < 0.0:
        raise ValueError(f"classify: hv_30 must be >= 0; got {hv_30}")
    if expected_move_pct < 0.0:
        raise ValueError(
            f"classify: expected_move_pct must be >= 0; got {expected_move_pct}"
        )
    if pcr_volume < 0.0:
        raise ValueError(f"classify: pcr_volume must be >= 0; got {pcr_volume}")
    if pcr_oi < 0.0:
        raise ValueError(f"classify: pcr_oi must be >= 0; got {pcr_oi}")
    if not 0.0 <= trend_strength <= 1.0:
        raise ValueError(
            f"classify: trend_strength must be in [0, 1]; got {trend_strength}"
        )
    if realized_vs_implied < 0.0:
        raise ValueError(
            f"classify: realized_vs_implied must be >= 0; got {realized_vs_implied}"
        )
    if not 0.0 <= breakout_signal <= 1.0:
        raise ValueError(
            f"classify: breakout_signal must be in [0, 1]; got {breakout_signal}"
        )
    if not 0.0 <= oi_concentration_at_max_pain <= 1.0:
        raise ValueError(
            f"classify: oi_concentration_at_max_pain must be in [0, 1]; "
            f"got {oi_concentration_at_max_pain}"
        )
    if days_to_next_event is not None and days_to_next_event < 0:
        raise ValueError(
            f"classify: days_to_next_event must be >= 0 when not None; "
            f"got {days_to_next_event}"
        )
    if days_since_event is not None and days_since_event < 0:
        raise ValueError(
            f"classify: days_since_event must be >= 0 when not None; "
            f"got {days_since_event}"
        )
    if days_to_nearest_opex is not None and days_to_nearest_opex < 0:
        raise ValueError(
            f"classify: days_to_nearest_opex must be >= 0 when not None; "
            f"got {days_to_nearest_opex}"
        )
    if iv_rank_change_1d is not None and not -1.0 <= iv_rank_change_1d <= 1.0:
        raise ValueError(
            f"classify: iv_rank_change_1d must be in [-1, 1] when not None; "
            f"got {iv_rank_change_1d}"
        )
