"""Master Decision Engine V1 contract types.

Per plan v1.2 §7 (`DailyDecision`) + §9.6 (Master Decision Engine).

`DailyDecision` is the single source of truth for "what the engine
recommended at this point in time" — it bundles every upstream engine's
output into one frozen dataclass that the API layer persists to the
`daily_decisions` Postgres table for exact replay.

Three pins are stamped on every decision and persisted as their own
columns alongside the JSONB payload:
  - `engine_version`   the `packages/engine/engine/version.py` semver
  - `weights_version`  the v2.0 string from `weights.yaml` (M1.10)
  - `inputs_hash`      SHA-256 of the canonical JSON of all engine inputs

Same `(engine_version, weights_version, inputs_hash)` triple → same
output, byte-identical. The M1.16 `/engine/what-if` endpoint relies on
this for instant cache hits.

The engine ships frozen dataclasses; the API layer projects them into
the §7 Pydantic schemas for JSON serialization to clients. The two
representations carry the same field names — projection is a 1:1
mapping, not a transformation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from engine.confidence.types import ConfidenceBreakdown
from engine.execution.downgrade import DowngradeResult
from engine.execution.types import Execution
from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile
from engine.recommendation.types import RecommendationResult
from engine.strike_selector.types import StrikeSelection


@dataclass(frozen=True)
class DailyDecision:
    """The unified output of the Master Decision Engine per plan §7 + §9.6.

    Fields (in groups by purpose):

      Identification:
        decision_id:           Locally-generated UUID4 string (str — no
                               UUID type to keep the dataclass JSON-safe).
        as_of:                 The decision's logical timestamp (the
                               "as of" the inputs were observed).
        ticker:                Underlying symbol; MSFT-only in V1.
        spot:                  Underlying spot at `as_of` (float; the API
                               layer projects to Decimal for the
                               `daily_decisions.payload` JSONB).

      Upstream engine outputs (echoed for traceability + UI drill-down):
        user_profile_snapshot: Frozen snapshot of the profile at decision
                               time. Required for replay even if the user
                               later edits their settings.
        market_state:          M1.4 `MarketStateResult`.
        flow_score:            M1.5b `FlowScore`.
        recommendation:        M1.9 `RecommendationResult` — carries the
                               matched rule + actions + rationale.

      Per-action concrete legs and execution:
        strike_selections:     One `StrikeSelection` per `Action` in
                               `recommendation.actions`. Equal-length
                               tuples zip cleanly with `executions`.
        downgrades:            Per-action `DowngradeResult` (the M1.12
                               callback wrapper). The `final_selection`
                               + `final_execution` here override the
                               original selection when the ladder
                               rescued the action.
        executions:            Per-action `Execution` taken from the
                               matching `DowngradeResult.final_execution`.
                               Persisted as a flat list in the API JSONB
                               payload.

      Decision-level scoring (final, post-downgrade):
        confidence:            The final M1.10 composite confidence, in
                               `[0, 1]`. Differs from
                               `recommendation.confidence` when the
                               downgrade rescue improved (or didn't
                               rescue) the per-action illiquidity penalty.
        confidence_breakdown:  Final `ConfidenceBreakdown` with the
                               post-downgrade `illiquidity_penalty`.

      Replay pins (the three "version" axes):
        inputs_hash:           `"sha256:" + hex` over canonical JSON of
                               all engine inputs at decision time.
        engine_version:        Echoed `engine.__version__`.
        weights_version:       Echoed `confidence_breakdown.weights_version`.

      Operational metadata:
        data_freshness:        Optional payload describing input staleness
                               ({"spot_age_seconds":..., "chain_age_seconds":...,
                                "any_stale":bool}). The engine doesn't
                               compute these — the API layer hydrates
                               them. Empty tuple = "not tracked".
        disclaimers:           Tuple of disclaimer strings. The engine
                               echoes a canonical set; the API layer
                               may augment per the §15 policy.
        escalated:             True iff any per-action `DowngradeResult`
                               escalated (M1.12 callback exhausted ladder).
                               UI uses this to surface a "low liquidity"
                               warning on the Today screen.

    Frozen dataclass per ADR-0005.
    """

    decision_id: str
    as_of: datetime
    ticker: str
    spot: float
    user_profile_snapshot: UserStrategyProfile
    market_state: MarketStateResult
    flow_score: FlowScore
    recommendation: RecommendationResult
    strike_selections: tuple[StrikeSelection, ...]
    downgrades: tuple[DowngradeResult, ...]
    executions: tuple[Execution, ...]
    confidence: float
    confidence_breakdown: ConfidenceBreakdown
    inputs_hash: str
    engine_version: str
    weights_version: str
    data_freshness: tuple[tuple[str, int | float | bool], ...] = ()
    disclaimers: tuple[str, ...] = ()
    escalated: bool = False
