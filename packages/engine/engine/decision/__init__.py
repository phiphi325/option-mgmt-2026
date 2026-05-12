"""Master Decision Engine (M1.13) — `produce_daily_decision()`.

Per plan v1.2 §9.6 + §7 (`DailyDecision`) + §17 M1.13.

Public surface:

    types:
        DailyDecision
    orchestrator:
        produce_daily_decision(*, as_of, ticker, chain_snapshot,
                              positions, profile, market_state,
                              flow_score, rules=None, weights=None,
                              risk_free_rate=0.05, dividend_yield=0.0,
                              data_freshness=(), disclaimers=...)
                              -> DailyDecision
    hashing:
        compute_inputs_hash(*, as_of, ticker, chain_snapshot, positions,
                            profile, market_state, flow_score) -> str
    canonical disclaimer set:
        DEFAULT_DISCLAIMERS: tuple[str, ...]

`produce_daily_decision()` is the single entry point for the M1.14
`/engine/daily-plan` endpoint. The API layer hydrates inputs from
Postgres, calls this function, and persists the result. The engine
itself has no I/O per ADR-0005 — the filesystem boundary for rules
and weights stays in the M1.9 `recommendation/yaml_loader.py` and
M1.10 `confidence/yaml_loader.py` respectively.

`compute_inputs_hash()` is exposed for downstream callers that want
to check cache hits before invoking the full pipeline (e.g. an idempotency
filter on the daily-plan endpoint).

`DEFAULT_DISCLAIMERS` is the engine's contribution to the §15 disclaimer
text. The API layer may concatenate broker-specific or jurisdictional
addenda.
"""

from __future__ import annotations

from engine.decision.hashing import compute_inputs_hash
from engine.decision.produce import DEFAULT_DISCLAIMERS, produce_daily_decision
from engine.decision.types import DailyDecision

__all__ = [
    "DEFAULT_DISCLAIMERS",
    "DailyDecision",
    "compute_inputs_hash",
    "produce_daily_decision",
]
