"""UserStrategyProfile validation + immutability tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.profiles import IncomeNeed, RiskTolerance, UserStrategyProfile


def _build(**overrides: object) -> UserStrategyProfile:
    """Helper: construct a default profile, allowing per-test overrides."""
    base: dict[str, object] = {
        "risk_tolerance": RiskTolerance.MODERATE,
        "income_need": IncomeNeed.MEDIUM,
        "max_position_pct": 0.25,
        "max_coverage_pct": 0.5,
        "min_iv_rank_for_short_premium": 30,
        "prefer_collars_over_covered_calls": False,
    }
    base.update(overrides)
    return UserStrategyProfile(**base)  # type: ignore[arg-type]


def test_default_profile_constructs() -> None:
    profile = _build()
    assert profile.risk_tolerance is RiskTolerance.MODERATE
    assert profile.income_need is IncomeNeed.MEDIUM


def test_profile_is_frozen() -> None:
    """Mutating a field after construction raises (replay correctness)."""
    profile = _build()
    with pytest.raises(ValidationError):
        profile.max_coverage_pct = 0.9  # type: ignore[misc]


@pytest.mark.parametrize("field", ["max_position_pct", "max_coverage_pct"])
def test_pct_bounds_enforced(field: str) -> None:
    """Pct fields are constrained to [0.0, 1.0] — out-of-range fails."""
    with pytest.raises(ValidationError):
        _build(**{field: -0.01})
    with pytest.raises(ValidationError):
        _build(**{field: 1.01})


@pytest.mark.parametrize("bad", [-1, 101, 500])
def test_iv_rank_bounds_enforced(bad: int) -> None:
    """IV rank is 0..100 (percentile by definition)."""
    with pytest.raises(ValidationError):
        _build(min_iv_rank_for_short_premium=bad)


def test_enum_string_values() -> None:
    """Enum members serialize as their string values (matches TS / DB)."""
    assert RiskTolerance.CONSERVATIVE.value == "conservative"
    assert RiskTolerance.MODERATE.value == "moderate"
    assert RiskTolerance.AGGRESSIVE.value == "aggressive"
    assert IncomeNeed.LOW.value == "low"
    assert IncomeNeed.MEDIUM.value == "medium"
    assert IncomeNeed.HIGH.value == "high"
