"""Regenerate one or all M1.24 golden `expected.json` files.

CI never runs this. Humans run it locally after:
  - An intentional schema change to `DailyDecision`
  - A new fixture's `inputs.json` has just landed
  - The canonical serializer's rounding policy changes

Usage:

    cd packages/engine
    uv run python scripts/regenerate_decision_goldens.py --all
    uv run python scripts/regenerate_decision_goldens.py --fixture 01-high-iv-event-collar-feasible

The script:
  1. Locates each fixture directory under tests/fixtures/master_decisions/
  2. Loads inputs.json (via tests._golden_helpers.load_inputs)
  3. Runs produce_daily_decision(**inputs)
  4. Canonicalizes via engine.decision.serialize_canonical
  5. Writes expected.json with sorted keys + 2-space indent + trailing newline

Review the resulting `git diff` carefully before committing. The
`test_regenerate_decision_goldens_idempotent` test will catch
nondeterminism, and the meta tests (`test_master_decision_goldens_meta`)
will catch coverage regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `tests._golden_helpers` importable when this script is run from any
# working directory.
_THIS = Path(__file__).resolve()
_REPO_ENGINE = _THIS.parent.parent  # packages/engine/
if str(_REPO_ENGINE) not in sys.path:
    sys.path.insert(0, str(_REPO_ENGINE))

from engine.decision import produce_daily_decision, serialize_canonical  # noqa: E402
from tests._golden_helpers import (  # noqa: E402
    GOLDENS_DIR,
    canonical_dumps,
    list_fixtures,
    load_inputs,
)


def regenerate(name: str, out_dir: Path | None = None) -> str:
    """Regenerate the `expected.json` for `name` and return its bytes.

    Args:
        name: Fixture directory name (e.g. `"01-high-iv-event-collar-feasible"`).
        out_dir: If provided, write to `out_dir/<name>/expected.json`.
                 If None (default), overwrite the fixture's existing
                 expected.json in place. The test-idempotency harness uses
                 out_dir to avoid mutating the committed fixtures.

    Returns:
        The canonical JSON string that was written (with trailing newline).

    Raises:
        FileNotFoundError: if the fixture directory or its inputs.json doesn't exist.
    """
    fixture_dir = GOLDENS_DIR / name
    inputs_path = fixture_dir / "inputs.json"
    if not inputs_path.exists():
        raise FileNotFoundError(
            f"{name}: inputs.json not found at {inputs_path}. "
            f"Author the fixture inputs before regenerating."
        )

    inputs = load_inputs(inputs_path)
    decision = produce_daily_decision(**inputs)
    canonical = serialize_canonical(decision)
    text = canonical_dumps(canonical)

    if out_dir is None:
        write_path = fixture_dir / "expected.json"
    else:
        target = out_dir / name
        target.mkdir(parents=True, exist_ok=True)
        write_path = target / "expected.json"

    write_path.write_text(text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Regenerate expected.json for every fixture with an inputs.json.",
    )
    group.add_argument(
        "--fixture",
        metavar="NAME",
        help="Regenerate expected.json for a single fixture (directory name).",
    )
    args = parser.parse_args()

    if args.all:
        names = [
            name for name in list_fixtures()
            if (GOLDENS_DIR / name / "inputs.json").exists()
        ]
        if not names:
            print("No fixtures with inputs.json found; nothing to do.", file=sys.stderr)
            return 1
    else:
        names = [args.fixture]

    print(f"Regenerating {len(names)} fixture(s)...")
    for name in names:
        try:
            text = regenerate(name)
        except FileNotFoundError as exc:
            print(f"  SKIP: {exc}", file=sys.stderr)
            continue
        size = len(text)
        decision = json.loads(text)
        emit = (
            (decision.get("recommendation") or {}).get("matched_rule") or {}
        ).get("emit", "?")
        regime = (decision.get("market_state") or {}).get("regime", "?")
        confidence = decision.get("confidence", "?")
        print(
            f"  ok: {name:50}  {size:6}b  regime={regime:<22}  emit={emit:<28}  "
            f"confidence={confidence}"
        )
    print("\nReview the git diff before committing. The meta tests will catch ")
    print("coverage regressions; the idempotency test will catch nondeterminism.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
