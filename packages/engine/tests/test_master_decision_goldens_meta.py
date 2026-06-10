"""Suite-level invariants for the M1.24 golden fixtures.

These tests don't exercise `produce_daily_decision()` — they assert
*coverage properties* across the 12 fixtures, so a Phase 2+ refactor
that silently drops a regime / emit code from the suite fails CI
immediately.

Per the M1.24 dev spec acceptance criteria.

When fewer than 12 fixtures have their `expected.json` populated, the
asserts soft-skip rather than fail (so this module remains green during
the staged fixture authoring in PR cycle).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.confidence import DEFAULT_WEIGHTS
from engine.recommendation.types import EmittedAction
from engine.regimes import Regime
from engine.version import __version__ as engine_version
from tests._golden_helpers import GOLDENS_DIR, PLACEHOLDER_MARKER, list_fixtures

# Minimum fixture count to enforce strict coverage. Below this we soft-skip
# because the fixture suite is still being authored.
_MIN_FIXTURES_FOR_STRICT_COVERAGE = 12


def _populated_fixtures() -> list[Path]:
    """Fixture dirs whose expected.json exists AND is not a placeholder."""
    out: list[Path] = []
    for name in list_fixtures():
        expected = GOLDENS_DIR / name / "expected.json"
        if not expected.exists():
            continue
        text = expected.read_text()
        if PLACEHOLDER_MARKER in text:
            continue
        out.append(GOLDENS_DIR / name)
    return out


def _maybe_skip_strict_coverage(populated: list[Path]) -> None:
    """Soft-skip when the suite is incomplete; assert when fully populated."""
    if len(populated) < _MIN_FIXTURES_FOR_STRICT_COVERAGE:
        pytest.skip(
            f"Only {len(populated)}/{_MIN_FIXTURES_FOR_STRICT_COVERAGE} fixtures "
            f"populated; strict-coverage meta-tests soft-skipped. "
            f"Author remaining inputs.json + run "
            f"scripts/regenerate_decision_goldens.py to enable."
        )


def test_all_v1_emit_codes_covered() -> None:
    """Each EmittedAction value (except NO_OP, which has its own fixture)
    appears as `recommendation.matched_rule.emit` in at least one fixture.
    """
    populated = _populated_fixtures()
    _maybe_skip_strict_coverage(populated)

    emits_seen: set[str] = set()
    for f in populated:
        decision = json.loads((f / "expected.json").read_text())
        rec = decision.get("recommendation") or {}
        matched = rec.get("matched_rule") or {}
        emit = matched.get("emit")
        if emit:
            emits_seen.add(emit)
        for action in rec.get("actions") or []:
            if action.get("emit"):
                emits_seen.add(action["emit"])

    expected = {member.value for member in EmittedAction}
    missing = expected - emits_seen
    assert not missing, (
        f"V1 emit codes not covered by any fixture: {sorted(missing)}. "
        f"Add a fixture that triggers each missing emit, then regen expected.json."
    )


def test_both_collar_paths_covered() -> None:
    """At least one fixture has collar_structures[i] populated (M1.11b feasible
    path); at least one has collar_structures[i] = None for an OPEN_COLLAR
    emit (M1.11b degraded path)."""
    populated = _populated_fixtures()
    _maybe_skip_strict_coverage(populated)

    has_feasible = False
    has_degraded = False
    for f in populated:
        decision = json.loads((f / "expected.json").read_text())
        structures = decision.get("collar_structures") or []
        actions = (decision.get("recommendation") or {}).get("actions") or []
        for i, struct in enumerate(structures):
            if i >= len(actions):
                continue
            emit = actions[i].get("emit")
            if emit == "OPEN_COLLAR":
                if struct is not None:
                    has_feasible = True
                else:
                    has_degraded = True

    assert has_feasible, "No fixture exercises the M1.11b feasible-collar path."
    assert has_degraded, "No fixture exercises the M1.11b empty-collar (degrade) path."


def test_escalation_path_covered() -> None:
    """At least one fixture has escalated=True (M1.12 ladder exhausted)."""
    populated = _populated_fixtures()
    _maybe_skip_strict_coverage(populated)

    has_escalated = any(
        json.loads((f / "expected.json").read_text()).get("escalated", False)
        for f in populated
    )
    assert has_escalated, "No fixture exercises the M1.12 ladder-exhausted path."


def test_all_six_regimes_covered() -> None:
    """Each Regime value appears as market_state.regime in at least one fixture."""
    populated = _populated_fixtures()
    _maybe_skip_strict_coverage(populated)

    seen: set[str] = set()
    for f in populated:
        decision = json.loads((f / "expected.json").read_text())
        regime = (decision.get("market_state") or {}).get("regime")
        if regime:
            seen.add(regime)

    expected = {r.value for r in Regime}
    missing = expected - seen
    assert not missing, f"Regimes not covered: {sorted(missing)}"


def test_version_stamps_consistent() -> None:
    """Every populated fixture stamps the current engine_version + weights_version."""
    populated = _populated_fixtures()
    if not populated:
        pytest.skip("No populated fixtures yet.")

    weights_version = DEFAULT_WEIGHTS.version
    for f in populated:
        decision = json.loads((f / "expected.json").read_text())
        assert decision.get("engine_version") == engine_version, (
            f"{f.name}: engine_version={decision.get('engine_version')!r}, "
            f"expected {engine_version!r}. Regenerate the fixture."
        )
        assert decision.get("weights_version") == weights_version, (
            f"{f.name}: weights_version={decision.get('weights_version')!r}, "
            f"expected {weights_version!r}. Regenerate the fixture."
        )


def test_inputs_hash_stability() -> None:
    """Recomputing compute_inputs_hash() on each fixture's inputs yields
    the expected.json's inputs_hash exactly. Catches canonicalization
    regressions in engine.decision.hashing without re-running the full
    produce_daily_decision pipeline."""
    populated = _populated_fixtures()
    if not populated:
        pytest.skip("No populated fixtures yet.")

    from engine.decision import compute_inputs_hash  # noqa: PLC0415
    from tests._golden_helpers import load_inputs  # noqa: PLC0415

    for f in populated:
        expected = json.loads((f / "expected.json").read_text())
        inputs = load_inputs(f / "inputs.json")
        # compute_inputs_hash takes a subset of produce_daily_decision's kwargs.
        hash_kwargs = {
            k: inputs[k]
            for k in (
                "as_of",
                "ticker",
                "chain_snapshot",
                "positions",
                "profile",
                "market_state",
                "flow_score",
            )
        }
        actual_hash = compute_inputs_hash(**hash_kwargs)
        assert actual_hash == expected.get("inputs_hash"), (
            f"{f.name}: inputs_hash drifted.\n"
            f"  expected: {expected.get('inputs_hash')}\n"
            f"  actual:   {actual_hash}\n"
            f"  Likely a canonicalization change in engine.decision.hashing — "
            f"investigate before regenerating fixtures."
        )
