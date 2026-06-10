"""Helpers shared by the M1.24 golden replay harness, meta tests, and regen script.

The fixture format and canonicalization conventions live in
`packages/engine/engine/decision/serialize.py` and in the M1.24 dev spec
(`docs/phased-design/phase-1/m1.24-master-decision-goldens.md`).

This module provides:

    canonical_dumps(value) -> str
        JSON-stringify with sorted keys, 2-space indent, trailing newline.
        The exact format used by both the harness comparison and the
        regeneration script's writes.

    load_inputs(path) -> dict[str, Any]
        Read an inputs.json file and reconstruct the engine-kwarg dict
        that produce_daily_decision() accepts. Handles deserialization
        of frozen dataclasses (DailyDecision input types) and Pydantic
        models from canonical-JSON form.

    list_fixtures() -> list[str]
        Enumerate the 12 named fixture directories under
        packages/engine/tests/fixtures/master_decisions/, sorted by
        directory name (numeric prefix yields stable ordering).

These helpers are imported by:
- test_master_decision_goldens.py (the parametrized harness)
- test_master_decision_goldens_meta.py (suite-level invariants)
- test_regenerate_decision_goldens_idempotent.py (byte-idempotency check)
- scripts/regenerate_decision_goldens.py (the regen utility)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Resolve the fixtures directory once. tests/ is one level below packages/engine
# so `Path(__file__).parent.parent` is the engine package root.
_THIS = Path(__file__).resolve()
TESTS_DIR = _THIS.parent
GOLDENS_DIR = TESTS_DIR / "fixtures" / "master_decisions"


def canonical_dumps(value: Any) -> str:
    """Stable JSON serialization for golden comparison.

    Conventions match `engine.decision.serialize.serialize_canonical`'s
    expectations: sorted keys, 2-space indent, trailing newline. UTF-8 is
    not enforced here because all our fixtures are ASCII-safe; if a future
    fixture has unicode, `ensure_ascii=False` is the right toggle.
    """
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def list_fixtures() -> list[str]:
    """Discover the named fixture directories.

    Returns the list of subdirectory names under
    packages/engine/tests/fixtures/master_decisions/, excluding hidden
    (`.`) and underscore-prefixed (`_`) entries.

    Sorted lexically — the directory names use a `NN-slug` prefix so this
    gives chronological order matching the dev spec's scenario matrix.
    """
    if not GOLDENS_DIR.exists():
        return []
    return sorted(
        p.name
        for p in GOLDENS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    )


def load_inputs(path: Path) -> dict[str, Any]:
    """Load an inputs.json and hydrate it into engine-kwarg form.

    The JSON file holds the canonical-JSON form of the engine kwargs.
    This function performs the inverse transformation:
      - ISO datetime strings -> aware `datetime` objects (UTC)
      - ISO date strings -> `date` objects
      - Nested dicts representing dataclasses -> reconstructed dataclass instances
      - The `rules` and `weights` fields are passed through as-is (None
        triggers the engine's default-load behavior, which is what every
        seed fixture uses).

    Args:
        path: Filesystem path to an `inputs.json` file (or any JSON file
              with the produce_daily_decision kwargs schema).

    Returns:
        A dict suitable for `produce_daily_decision(**load_inputs(...))`.

    The reconstruction uses lazy imports so the helper stays usable from
    tooling scripts that don't want the full engine import surface upfront.
    """
    raw = json.loads(path.read_text())

    # Lazy imports — keep this helper importable in contexts where the
    # engine modules might not be on sys.path yet (e.g. early tooling).
    from engine.flow_score.types import (  # noqa: PLC0415
        Bias,
        FlowScore,
        RecommendedAction,
    )
    from engine.market_state.classify import MarketStateResult  # noqa: PLC0415
    from engine.profiles import (  # noqa: PLC0415
        IncomeNeed,
        ProfileStyle,
        RiskTolerance,
        UserStrategyProfile,
    )
    from engine.recommendation import PositionState  # noqa: PLC0415
    from engine.regimes import Regime  # noqa: PLC0415
    from engine.types import ChainSnapshot, OptionContract, OptionType  # noqa: PLC0415

    out: dict[str, Any] = {}

    # Top-level scalars + strings ----------------------------------------
    out["as_of"] = _parse_datetime(raw["as_of"])
    out["ticker"] = raw["ticker"]
    out["risk_free_rate"] = raw.get("risk_free_rate", 0.05)
    out["dividend_yield"] = raw.get("dividend_yield", 0.0)

    # ChainSnapshot ------------------------------------------------------
    cs = raw["chain_snapshot"]
    out["chain_snapshot"] = ChainSnapshot(
        underlying=cs["underlying"],
        spot=cs["spot"],
        as_of=_parse_date(cs["as_of"]),
        contracts=tuple(
            OptionContract(
                underlying=c["underlying"],
                expiry=_parse_date(c["expiry"]),
                strike=c["strike"],
                option_type=OptionType(c["option_type"]),
                mid=c.get("mid"),
                bid=c.get("bid"),
                ask=c.get("ask"),
                iv=c.get("iv"),
                open_interest=c["open_interest"],
                volume=c["volume"],
            )
            for c in cs["contracts"]
        ),
    )

    # PositionState ------------------------------------------------------
    pos = raw["positions"]
    out["positions"] = PositionState(
        underlying_shares=pos["underlying_shares"],
        has_short_call=pos["has_short_call"],
        nearest_short_call_strike=pos.get("nearest_short_call_strike"),
        nearest_short_call_dte=pos.get("nearest_short_call_dte"),
        short_call_contracts=pos.get("short_call_contracts", 0),
        has_long_put=pos["has_long_put"],
        long_put_pnl_pct=pos.get("long_put_pnl_pct", 0.0),
        has_short_put=pos.get("has_short_put", False),
    )

    # UserStrategyProfile ------------------------------------------------
    pr = raw["profile"]
    out["profile"] = UserStrategyProfile(
        risk_tolerance=RiskTolerance(pr["risk_tolerance"]),
        income_need=IncomeNeed(pr["income_need"]),
        max_position_pct=pr["max_position_pct"],
        max_coverage_pct=pr["max_coverage_pct"],
        min_iv_rank_for_short_premium=pr["min_iv_rank_for_short_premium"],
        prefer_collars_over_covered_calls=pr["prefer_collars_over_covered_calls"],
        drawdown_tolerance=pr.get("drawdown_tolerance", 0.15),
        style=ProfileStyle(pr.get("style", "balanced")),
    )

    # MarketStateResult --------------------------------------------------
    ms = raw["market_state"]
    out["market_state"] = MarketStateResult(
        regime=Regime(ms["regime"]),
        regime_score=ms["regime_score"],
        all_scores={Regime(k): v for k, v in ms["all_scores"].items()},
        tags=tuple(ms["tags"]),
        spot=ms["spot"],
        iv_rank=ms["iv_rank"],
        iv_percentile=ms["iv_percentile"],
        hv_30=ms["hv_30"],
        expected_move_pct=ms["expected_move_pct"],
        max_pain=ms["max_pain"],
        max_pain_delta_pct=ms["max_pain_delta_pct"],
        pcr_volume=ms["pcr_volume"],
        pcr_oi=ms["pcr_oi"],
        trend_strength=ms["trend_strength"],
        realized_vs_implied=ms["realized_vs_implied"],
        breakout_signal=ms["breakout_signal"],
        oi_concentration_at_max_pain=ms["oi_concentration_at_max_pain"],
        days_to_next_event=ms.get("days_to_next_event"),
        next_event_kind=ms.get("next_event_kind"),
        days_since_event=ms.get("days_since_event"),
        days_to_nearest_opex=ms.get("days_to_nearest_opex"),
        iv_rank_change_1d=ms.get("iv_rank_change_1d"),
        gap_pct=ms.get("gap_pct"),
    )

    # FlowScore ----------------------------------------------------------
    fs = raw["flow_score"]
    out["flow_score"] = FlowScore(
        score=fs["score"],
        bullish_score=fs["bullish_score"],
        bearish_score=fs["bearish_score"],
        bias=Bias(fs["bias"]),
        recommended_action=RecommendedAction(fs["recommended_action"]),
        pin_probability=fs["pin_probability"],
        gamma_risk=fs["gamma_risk"],
        gamma_sign=fs.get("gamma_sign", 0),
        confidence=fs["confidence"],
        explanation=fs.get("explanation", ""),
        breakdown=fs.get("breakdown", {}),
    )

    # Optional pass-throughs ---------------------------------------------
    # rules + weights default to None (the engine uses its packaged defaults).
    out["rules"] = raw.get("rules")
    out["weights"] = raw.get("weights")

    if "data_freshness" in raw:
        out["data_freshness"] = tuple(tuple(x) for x in raw["data_freshness"])
    if "disclaimers" in raw:
        out["disclaimers"] = tuple(raw["disclaimers"])

    return out


def _parse_datetime(s: str) -> datetime:
    """Parse an ISO 8601 datetime string, accepting `Z` or `+HH:MM` forms."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _parse_date(s: str) -> date:
    """Parse an ISO 8601 date string (`YYYY-MM-DD`)."""
    return date.fromisoformat(s)


# Sentinel marker the regen script writes when expected.json is missing or
# is a placeholder. The harness recognizes this and emits a clear "run regen"
# error rather than a confusing JSON diff.
PLACEHOLDER_MARKER = "_M1_24_PLACEHOLDER_RUN_REGEN_FIRST_"
