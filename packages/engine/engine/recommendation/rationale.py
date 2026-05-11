"""Rationale rendering for the Recommendation Engine.

Per plan v1.2 §9.5 and §22.8.

Each rule's `rationale` template carries `{{var}}` placeholders that
get substituted with values from the upstream engines + user profile.
The renderer is intentionally minimal — Mustache-style placeholders
only, no conditionals or loops. Phase 4 ML may upgrade to a richer
templater; V1 stays simple and fast.

Supported placeholders:

  {{iv_rank}}                       → int 0-100 (from MarketStateResult)
  {{iv_rank_change_1d}}             → int (pp, signed)
  {{days_to_next_event}}            → int (days)
  {{event_kind}}                    → str (e.g. "earnings")
  {{dte}}                           → int (nearest_short_call_dte)
  {{put_pnl_pct}}                   → str percentage ("30%")
  {{confidence}}                    → str percentage ("28%")
  {{profile.iv_rank_sell_threshold}} → int (from profile.min_iv_rank_for_short_premium)
  {{profile.drawdown_tolerance}}    → str percentage

Unknown placeholders are LEFT IN the rendered string (with their
braces) — Phase 1 prefers loud-fail over silent-fill: a missing var
shows up to QA, not buried in a deployed string.

Pure function (per ADR-0005).
"""

from __future__ import annotations

import re

from engine.flow_score.types import FlowScore
from engine.market_state.classify import MarketStateResult
from engine.profiles import UserStrategyProfile
from engine.recommendation.types import PositionState

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def render_rationale(
    *,
    template: str,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    positions: PositionState,
    profile: UserStrategyProfile,
    confidence: float,
) -> str:
    """Substitute `{{var}}` placeholders against the supplied context."""
    values = _build_substitution_map(
        market_state=market_state,
        flow_score=flow_score,
        positions=positions,
        profile=profile,
        confidence=confidence,
    )

    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in values:
            return values[key]
        # Unknown placeholder: leave the {{var}} in-line so QA sees it.
        return m.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)


def _build_substitution_map(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    positions: PositionState,
    profile: UserStrategyProfile,
    confidence: float,
) -> dict[str, str]:
    """Build the placeholder → string map for one rationale rendering."""
    iv_rank_pct = int(round(market_state.iv_rank * 100.0))
    iv_rank_change = getattr(market_state, "iv_rank_change_1d", None)
    iv_rank_change_str = (
        f"{int(round(iv_rank_change * 100.0)):+d}"
        if iv_rank_change is not None
        else "—"
    )

    dte_str = (
        str(positions.nearest_short_call_dte)
        if positions.nearest_short_call_dte is not None
        else "—"
    )

    days_to_event_str = (
        str(market_state.days_to_next_event)
        if market_state.days_to_next_event is not None
        else "—"
    )
    event_kind_str = market_state.next_event_kind or "event"

    put_pnl_str = f"{int(round(positions.long_put_pnl_pct * 100))}%"
    confidence_str = f"{int(round(confidence * 100))}%"

    drawdown_str = f"{int(round(profile.drawdown_tolerance * 100))}%"

    return {
        "iv_rank": str(iv_rank_pct),
        "iv_rank_change_1d": iv_rank_change_str,
        "days_to_next_event": days_to_event_str,
        "event_kind": event_kind_str,
        "dte": dte_str,
        "put_pnl_pct": put_pnl_str,
        "confidence": confidence_str,
        "profile.iv_rank_sell_threshold": str(profile.min_iv_rank_for_short_premium),
        "profile.drawdown_tolerance": drawdown_str,
    }


__all__ = ["render_rationale"]
