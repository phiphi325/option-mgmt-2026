"""Golden replay tests per plan v1.2 §19 Phase 1 Done bar (12/12 snapshots match).

Each fixture under `tests/fixtures/master_decisions/` is a directory with
`inputs.json` + `expected.json`. The harness parametrizes one test per
fixture; on failure the diff between actual and expected is rendered in
the failure message for easy human review.

Re-generate after intentional schema changes:

    cd packages/engine
    uv run python scripts/regenerate_decision_goldens.py --all

See the M1.24 dev spec
(`docs/phased-design/phase-1/m1.24-master-decision-goldens.md`) for the
12-scenario matrix + serialization conventions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.decision import produce_daily_decision, serialize_canonical
from tests._golden_helpers import (
    GOLDENS_DIR,
    PLACEHOLDER_MARKER,
    canonical_dumps,
    list_fixtures,
    load_inputs,
)


def _fixture_ids() -> list[str]:
    """Stable parametrize id list. Returns `[]` when no fixtures present so
    pytest skips cleanly during early development."""
    return list_fixtures()


@pytest.mark.parametrize("fixture", _fixture_ids())
def test_golden_decision_matches(fixture: str) -> None:
    """Replay `produce_daily_decision()` for the fixture, byte-compare output."""
    fixture_dir: Path = GOLDENS_DIR / fixture
    inputs_path = fixture_dir / "inputs.json"
    expected_path = fixture_dir / "expected.json"

    if not inputs_path.exists():
        pytest.skip(
            f"{fixture}: inputs.json not yet authored. "
            f"See {fixture_dir / 'README.md'} for the planned scenario."
        )

    if not expected_path.exists():
        # SOFT skip (not fail) so the suite is green during the draft-PR
        # phase when fixtures are landing in stages. The
        # `test_no_unpopulated_fixtures_at_ready_state` gate (see
        # `test_master_decision_goldens_meta.py`) flips this to a hard
        # failure once the PR moves out of draft.
        pytest.skip(
            f"{fixture}: expected.json missing. Run\n"
            f"    cd packages/engine && uv run python scripts/regenerate_decision_goldens.py --fixture {fixture}\n"
            f"to generate it, then review the result before committing."
        )

    expected_text = expected_path.read_text()
    if PLACEHOLDER_MARKER in expected_text:
        # Same rationale as the missing-expected case above — soft skip
        # while the PR is in draft, hard-fail via meta gate at ready state.
        pytest.skip(
            f"{fixture}: expected.json is a placeholder. Run\n"
            f"    cd packages/engine && uv run python scripts/regenerate_decision_goldens.py --fixture {fixture}\n"
            f"to replace the placeholder with the real engine output."
        )

    inputs = load_inputs(inputs_path)
    actual = serialize_canonical(produce_daily_decision(**inputs))
    expected = json.loads(expected_text)

    actual_str = canonical_dumps(actual)
    expected_str = canonical_dumps(expected)

    if actual_str != expected_str:
        # Provide an actionable diff snippet. The full diff is recoverable
        # by writing actual to a file and `diff`-ing against expected.
        pytest.fail(
            f"{fixture}: golden mismatch.\n\n"
            f"--- expected ({expected_path}) ---\n{expected_str[:2000]}"
            + ("...\n" if len(expected_str) > 2000 else "\n")
            + f"\n--- actual (recomputed) ---\n{actual_str[:2000]}"
            + ("...\n" if len(actual_str) > 2000 else "\n")
            + f"\nRegenerate with: "
            f"cd packages/engine && uv run python scripts/regenerate_decision_goldens.py --fixture {fixture}\n"
            f"Then review the git diff before committing."
        )


def test_fixture_directory_exists() -> None:
    """Sanity: the fixtures directory itself is present in the test tree."""
    assert GOLDENS_DIR.exists(), (
        f"Expected goldens directory at {GOLDENS_DIR}; create it (with at least "
        f"a README.md) when adding the first M1.24 fixture."
    )
