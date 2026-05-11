"""Confidence Composer V1 contract types.

Per plan v1.2 §9.7 (Confidence Composer) and §22.13 (multiplicative
penalty redesign — the canonical formula). The §22.13 form supersedes
§9.7's v1.0 additive formula. ADR-0003 is the architectural anchor.

The six components partition into:

  Positive (sum-to-1.0 weighted average; pre-penalty score):
    - flow_alignment        signal alignment from FlowScore
    - structure_alignment   signal alignment from market structure
    - regime_match          regime classifier confidence
    - signal_alignment      composite reliability blend

  Penalty (multiplicative; each can shrink confidence by `cap × p`):
    - event_risk_penalty    proximity to a scheduled event
    - illiquidity_penalty   execution feasibility (M1.11 plumbing)

All component values live in `[0, 1]`. `Weights` enforces:

  - `positive_weights.{flow, struct, regime, signal}` sum to 1.0
  - `penalty_caps.{event, liquidity}` are each in `[0, 1]`

Tolerance for the sum-to-1 check is `1e-6` — tight enough to catch
typos in weights.yaml, loose enough to admit floating-point fuzz from
hand-authored values.

Frozen dataclasses per ADR-0005. The values flow into Postgres +
TypeScript via `confidence_breakdown` on DailyDecision (M1.13+).
"""

from __future__ import annotations

from dataclasses import dataclass

# Tolerance for the positive-weight sum-to-1.0 check. Hand-authored YAML
# values like 0.30 + 0.25 + 0.25 + 0.20 sum exactly to 1.0 under IEEE 754,
# but a reasonable epsilon guards against intermediate edits (e.g.
# 1/3 + 1/3 + 1/3 != 1.0 exactly).
_SUM_TOLERANCE: float = 1e-6


@dataclass(frozen=True)
class ConfidenceInputs:
    """The six raw component values fed into the composer.

    Each value is in `[0, 1]`. Construction validates this; downstream
    consumers can assume bounded inputs without re-checking.

    Fields:
        flow_alignment:       Reliability + magnitude of the FlowScore
                              signal. Higher = more decisive flow.
        structure_alignment:  Decisiveness of market structure
                              (trend / breakout / pin / OI concentration).
        regime_match:         Confidence of the winning regime
                              (= `MarketStateResult.regime_score`).
        signal_alignment:     Composite reliability blend
                              (regime confidence × flow confidence).
        event_risk_penalty:   Penalty applied multiplicatively for
                              proximity to a scheduled event. `1.0`
                              corresponds to "event today"; the cap
                              `penalty_caps.event` controls how much
                              of a multiplier this becomes.
        illiquidity_penalty:  Penalty applied multiplicatively for
                              poor execution feasibility. Plumbed
                              from the M1.11 Execution module; V1
                              callers pass `0.0` until M1.11 ships.

    Raises:
        ValueError: Any field is outside `[0, 1]`.
    """

    flow_alignment: float
    structure_alignment: float
    regime_match: float
    signal_alignment: float
    event_risk_penalty: float
    illiquidity_penalty: float

    def __post_init__(self) -> None:
        for name, value in (
            ("flow_alignment", self.flow_alignment),
            ("structure_alignment", self.structure_alignment),
            ("regime_match", self.regime_match),
            ("signal_alignment", self.signal_alignment),
            ("event_risk_penalty", self.event_risk_penalty),
            ("illiquidity_penalty", self.illiquidity_penalty),
        ):
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError(
                    f"ConfidenceInputs.{name} must be in [0, 1]; got {value!r}"
                )


@dataclass(frozen=True)
class PositiveWeights:
    """Weights for the four positive components.

    Constraint: `flow + struct + regime + signal == 1.0` (enforced by
    `Weights.__post_init__`).

    Naming mirrors `packages/engine/config/weights.yaml` exactly to
    keep the on-disk YAML and the in-code representation 1-to-1.
    """

    flow: float
    struct: float
    regime: float
    signal: float


@dataclass(frozen=True)
class PenaltyCaps:
    """Maximum reduction each penalty can apply (multiplicatively).

    A `penalty_caps.event = 0.30` means: `event_risk_penalty = 1.0`
    reduces confidence by up to 30% (multiplier `1 - 0.30 * 1.0 = 0.70`).
    Both caps must be in `[0, 1]`.
    """

    event: float
    liquidity: float


@dataclass(frozen=True)
class Weights:
    """Weights bundle for the multiplicative composer.

    `version` is the `weights_version` string persisted on every
    DailyDecision (alongside `engine_version` + `inputs_hash`) for
    exact replay. Bump it whenever the values change so historical
    decisions remain attributable to the weights that produced them.

    Construction validates:
      - `positive_weights` sum to 1.0 (within `_SUM_TOLERANCE`)
      - `penalty_caps.event` in `[0, 1]`
      - `penalty_caps.liquidity` in `[0, 1]`

    Raises:
        ValueError: Constraints violated.
    """

    version: str
    positive_weights: PositiveWeights
    penalty_caps: PenaltyCaps

    def __post_init__(self) -> None:
        s = (
            self.positive_weights.flow
            + self.positive_weights.struct
            + self.positive_weights.regime
            + self.positive_weights.signal
        )
        if abs(s - 1.0) > _SUM_TOLERANCE:
            raise ValueError(
                f"Weights.positive_weights must sum to 1.0 "
                f"(within {_SUM_TOLERANCE}); got {s!r}"
            )
        for name, value in (
            ("flow", self.positive_weights.flow),
            ("struct", self.positive_weights.struct),
            ("regime", self.positive_weights.regime),
            ("signal", self.positive_weights.signal),
        ):
            if value < 0.0:
                raise ValueError(
                    f"Weights.positive_weights.{name} must be non-negative; "
                    f"got {value!r}"
                )
        for name, value in (
            ("event", self.penalty_caps.event),
            ("liquidity", self.penalty_caps.liquidity),
        ):
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"Weights.penalty_caps.{name} must be in [0, 1]; got {value!r}"
                )


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """The composer's explainable output.

    Carries every input back out (for traceability) plus two derived
    intermediates added by §22.13: `positive_score` (the pre-penalty
    weighted average, in `[0, 1]`) and `penalty_multiplier` (the
    aggregate multiplier applied, in `[0, 1]`). Their product
    (post-clip) equals the final `confidence`.

    `weights_version` is the `Weights.version` used — pinned for
    historical-replay correctness alongside `engine_version` on the
    DailyDecision.

    The UI (per §22.13 final paragraph) renders the four positive
    components as a stacked bar with the penalty multiplier as a
    darker overlay reducing the final width.
    """

    flow_alignment: float
    structure_alignment: float
    regime_match: float
    signal_alignment: float
    event_risk_penalty: float
    illiquidity_penalty: float
    positive_score: float
    penalty_multiplier: float
    weights_version: str
