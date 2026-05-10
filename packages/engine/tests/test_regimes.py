"""Regime taxonomy tests — guards the locked decision in ADR-0002.

Adding a new regime here without updating Postgres + TS will fail this test
(or upstream test_codegen.py for the TS side), reminding contributors of the
coupling spelled out in ADR-0002.
"""

from __future__ import annotations

from engine.regimes import REGIME_COLORS, Regime

# The exact six locked regimes — frozen against ADR-0002.
EXPECTED_REGIMES: frozenset[str] = frozenset(
    {
        "HIGH_IV_EVENT",
        "HIGH_IV_PIN",
        "LOW_IV_TREND",
        "LOW_IV_RANGE",
        "BREAKOUT",
        "POST_EVENT_REPRICE",
    }
)


def test_six_regimes_exactly() -> None:
    """The taxonomy is locked at six. Any drift breaks downstream coupling."""
    actual = {r.value for r in Regime}
    assert actual == EXPECTED_REGIMES


def test_regime_value_equals_name() -> None:
    """Each regime's value must match its name (Postgres enum literal)."""
    for r in Regime:
        assert r.value == r.name


def test_every_regime_has_a_color() -> None:
    """Every locked regime has a UI color token; no orphans, no extras."""
    assert set(REGIME_COLORS.keys()) == set(Regime)
    # Tokens are short lowercase strings (Tailwind palette names).
    for color in REGIME_COLORS.values():
        assert color.islower()
        assert " " not in color


def test_regime_colors_are_distinct() -> None:
    """No two regimes share a color (visual ambiguity is a UI bug)."""
    assert len(set(REGIME_COLORS.values())) == len(REGIME_COLORS)
