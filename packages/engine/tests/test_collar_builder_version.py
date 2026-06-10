"""Engine version + exports smoke tests for M1.11a."""

from __future__ import annotations

import engine
from engine.collar_builder import (
    CollarIntent,
    CollarLeg,
    CollarStructure,
    build,
)


def test_engine_version_is_1_7_0() -> None:
    """M1.24 bumped engine 1.6.0 → 1.7.0 per Open Question Q1 of the M1.24 dev
    spec (new public function `engine.decision.serialize_canonical` qualifies
    for a minor bump under strict ADR-0005 reading). Historical bumps preserved
    in CHANGELOG.md."""
    assert engine.__version__ == "1.7.0"


def test_collar_builder_types_exported_via_engine_namespace() -> None:
    """`CollarIntent`, `CollarLeg`, `CollarStructure` are reachable
    from the engine top level. `build()` itself stays namespaced
    under `engine.collar_builder` to avoid colliding with the
    generic verb at the top level."""
    assert engine.CollarIntent is CollarIntent
    assert engine.CollarLeg is CollarLeg
    assert engine.CollarStructure is CollarStructure


def test_build_is_importable_from_collar_builder_module() -> None:
    """The submodule entry point is `engine.collar_builder.build`."""
    from engine.collar_builder import build as build_from_module

    assert build_from_module is build


def test_collar_builder_types_in_engine_all() -> None:
    """The three collar_builder types are in `engine.__all__`."""
    expected = {"CollarIntent", "CollarLeg", "CollarStructure"}
    assert expected.issubset(set(engine.__all__))


def test_collar_intent_values_match_master_plan() -> None:
    """The three intents per master plan §7 + §9.10."""
    assert CollarIntent.ZERO_COST.value == "zero_cost"
    assert CollarIntent.INCOME.value == "income"
    assert CollarIntent.DEFENSIVE.value == "defensive"
    assert len(list(CollarIntent)) == 3
