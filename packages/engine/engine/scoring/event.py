"""Event-uncertainty scoring primitive.

Per plan v1.2 §9.11 (Scoring Functions Module) and §17 M1.4a.

`event_score()` answers "how much event-driven uncertainty is sitting in
the chain?" It blends three signals tied to a single upcoming scheduled
event (earnings, FOMC, CPI, ex-dividend, ...):

  proximity      How soon is the event? 0d → 1.0; ≥ 30d → 0.0; linear.
                 None (no scheduled event) → 0.0; the score collapses to
                 zero regardless of the other components — there is no
                 event risk when no event is scheduled.
  kind_weight    How impactful is this kind of event historically for
                 the underlying? Earnings and FOMC are weighted highest;
                 ex-dividend lowest. Unknown kinds default to a mid weight.
  magnitude      How big do moves *of this kind* tend to be? Pulled from
                 `event_history.avg_abs_return_pct`. 5%+ avg → 1.0.

Composition:

    score = proximity · (0.5 · kind_weight + 0.5 · magnitude)

The `proximity` factor is multiplicative — distant events contribute
nothing to event_score even when their kind and magnitude are large,
which reflects the practical reality that 60-day-out earnings does not
"price" the same as 1-day-out earnings.

`event_history` is required even when `days_to_event is None` to keep
the signature stable; the caller may pass a default-constructed
`EventStats(0.0, 0.0, 0)` when no historical data exists. `event_score`
short-circuits to a zero score in that case via the proximity gate.

The `EventKind` enum and `EVENT_KIND_WEIGHTS` table are exposed so
callers can extend the recognized kinds without modifying this module
(though the canonical update path is to add a value here, in the API
event-calendar service, and in the UI event-icon mapping in lockstep).

Pure function (per ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from engine._utils import clip01

# Proximity normalization. 0d → 1.0; >= 30 trading days → 0.0; linear.
_PROXIMITY_FAR_DAYS = 30

# Magnitude normalization. avg_abs_return_pct of 0.05 (5%) → 1.0.
# Calibrated against typical mega-cap earnings moves; smaller-cap event
# moves saturate higher and the magnitude signal will simply hit 1.0
# more frequently rather than overshoot.
_MAGNITUDE_THRESHOLD = 0.05

# Inner-blend weights for kind vs magnitude. Sum to 1.0.
_W_KIND = 0.5
_W_MAGNITUDE = 0.5

# Default weight for an unknown / unspecified `event_kind`. Mid-tier:
# the engine assumes some impact rather than zero (an unknown event is
# not the same as no event) but doesn't escalate.
_DEFAULT_KIND_WEIGHT: Final[float] = 0.5


class EventKind(StrEnum):
    """The recognized event kinds that drive `event_score`.

    Adding a value requires updating `EVENT_KIND_WEIGHTS` below in the
    same change. The string values are the wire form used by the
    API event-calendar service and the Postgres `events` table.
    """

    EARNINGS = "earnings"
    FOMC = "fomc"
    CPI = "cpi"
    GUIDANCE = "guidance"
    EX_DIVIDEND = "ex_dividend"
    OTHER = "other"


# Event-kind impact weights, in [0, 1]. Calibrated via plan v1.2 §16
# (event-impact estimator, Phase 4 ML target) — the hand-coded weights
# below are the V1 prior, which the M4.5 model will replace.
EVENT_KIND_WEIGHTS: Final[dict[str, float]] = {
    EventKind.EARNINGS.value: 1.0,
    EventKind.FOMC.value: 0.7,
    EventKind.CPI.value: 0.6,
    EventKind.GUIDANCE.value: 0.5,
    EventKind.EX_DIVIDEND.value: 0.3,
    EventKind.OTHER.value: 0.5,
}


@dataclass(frozen=True)
class EventStats:
    """Historical event-day stats for the underlying.

    Calibrates `event_score` magnitude: an upcoming earnings event
    scores higher when MSFT typically moves ±5% on earnings vs ±1%.

    Fields:
        avg_abs_return_pct: Average absolute close-to-close return on
                            event day (decimal; 0.04 = 4%). Must be >= 0.
        iv_runup_pct: Average IV runup magnitude in the 5 sessions before
                      the event (decimal; 0.10 = 10 vol pts). Currently
                      surfaced for downstream consumers (Confidence
                      Composer breakdown, future M4.5 ML features); not
                      consumed by `event_score()` directly.
        sample_count: Number of prior events of this kind in the history.
                      Currently surfaced for downstream consumers; not
                      consumed by `event_score()` directly.
    """

    avg_abs_return_pct: float
    iv_runup_pct: float = 0.0
    sample_count: int = 0


@dataclass(frozen=True)
class EventScoreResult:
    """Result of `event_score()`. Score plus per-component breakdown.

    `breakdown` keys map 1:1 to the formula components.
    """

    score: float
    breakdown: dict[str, float]


def event_score(
    *,
    days_to_event: int | None,
    event_kind: str | None,
    event_history: EventStats,
) -> EventScoreResult:
    """Composite event-uncertainty score in [0, 1].

    Higher values indicate a larger event-driven risk premium sitting in
    the chain. Score is identically 0 when no event is scheduled or when
    the next event is more than `_PROXIMITY_FAR_DAYS` (30) trading days
    out — multiplicative proximity gate.

    Args:
        days_to_event: Trading days until the next scheduled event for
                       the underlying. `None` when no event is scheduled.
                       Negative values (event already past) are treated
                       as 0 days (score's proximity component clamps to
                       1.0 for the "right at / on" case; the engine
                       expects the event-calendar service to advance
                       past events promptly).
        event_kind: The kind of the upcoming event ("earnings", "fomc",
                    "cpi", ...). Unknown / unspecified kinds default to
                    `_DEFAULT_KIND_WEIGHT`. `None` when no event is
                    scheduled.
        event_history: Historical event-day stats. Must be present even
                       when `days_to_event is None`; pass
                       `EventStats(avg_abs_return_pct=0.0)` when no
                       history exists.

    Returns:
        `EventScoreResult` with `score` in [0, 1] and a `breakdown`
        dict carrying the proximity / kind / magnitude components.

    Raises:
        ValueError: `event_history.avg_abs_return_pct` is negative,
                    or `event_history.iv_runup_pct` is negative, or
                    `event_history.sample_count` is negative.
    """
    if event_history.avg_abs_return_pct < 0.0:
        raise ValueError(
            f"event_score: event_history.avg_abs_return_pct must be >= 0; "
            f"got {event_history.avg_abs_return_pct}"
        )
    if event_history.iv_runup_pct < 0.0:
        raise ValueError(
            f"event_score: event_history.iv_runup_pct must be >= 0; "
            f"got {event_history.iv_runup_pct}"
        )
    if event_history.sample_count < 0:
        raise ValueError(
            f"event_score: event_history.sample_count must be >= 0; "
            f"got {event_history.sample_count}"
        )

    if days_to_event is None:
        proximity = 0.0
    else:
        clamped_days = max(days_to_event, 0)
        proximity = clip01(
            1.0 - clamped_days / _PROXIMITY_FAR_DAYS
        )

    if event_kind is None:
        kind_weight = _DEFAULT_KIND_WEIGHT
    else:
        kind_weight = EVENT_KIND_WEIGHTS.get(event_kind, _DEFAULT_KIND_WEIGHT)

    magnitude = clip01(event_history.avg_abs_return_pct / _MAGNITUDE_THRESHOLD)

    inner = _W_KIND * kind_weight + _W_MAGNITUDE * magnitude
    score = clip01(proximity * inner)

    return EventScoreResult(
        score=score,
        breakdown={
            "proximity": proximity,
            "kind_weight": kind_weight,
            "magnitude": magnitude,
        },
    )
