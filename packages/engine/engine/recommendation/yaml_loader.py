"""YAML loader for the Recommendation Engine V1 rules.

Per plan v1.2 §9.5 and §22.8.

The engine itself is pure (per ADR-0005 — no I/O). This module is the
single file-system boundary: it opens `rules.yaml`, parses it, and
returns a frozen tuple of typed `RuleSpec`s. The recommend()
orchestrator takes the parsed `Sequence[RuleSpec]` (not a Path) so the
core decision logic remains pure.

The default V1 rules ship in `packages/engine/config/rules.yaml` —
the loader exposes a `load_default_rules()` helper that resolves the
packaged path so callers don't have to know it.

Schema validation:

  - Each YAML entry must have keys: `id`, `when`, `emit`, `rationale`.
    `risks` and `invalidation` default to empty tuples.
  - `emit` must match an `EmittedAction` enum value.
  - `when` clauses must be in `supported_clauses()` (per
    `engine.recommendation.rules`). Unknown clauses raise `ValueError`
    at LOAD time, not at evaluation time, so misconfigured YAML fails
    loudly during integration tests.

Errors are surfaced as `ValueError` with the failing rule id +
problem in the message — easy to find when CI is yelling at you.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from engine.recommendation.rules import supported_clauses
from engine.recommendation.types import EmittedAction, RuleSpec

# Path to the packaged V1 rules.yaml relative to the engine module.
#   packages/engine/engine/recommendation/yaml_loader.py  ← here
#   packages/engine/config/rules.yaml                     ← target
_DEFAULT_RULES_RELPATH = "../../config/rules.yaml"


def load_rules_yaml(path: Path | str) -> tuple[RuleSpec, ...]:
    """Read + parse + validate the rules YAML at `path`.

    Args:
        path: Filesystem path to a YAML file in the §22.8 schema.

    Returns:
        Tuple of validated `RuleSpec`s in YAML order. First-match-wins
        evaluation depends on this order.

    Raises:
        FileNotFoundError: `path` does not exist.
        ValueError: YAML is empty, the top level is not a list, a rule
            is missing required fields, an `emit` is not a valid
            `EmittedAction`, or a `when:` clause is not in
            `supported_clauses()`.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"rules.yaml not found: {p}")

    raw_text = p.read_text(encoding="utf-8")
    return _parse_rules_text(raw_text, source=str(p))


def load_default_rules() -> tuple[RuleSpec, ...]:
    """Load the packaged V1 rules from `packages/engine/config/rules.yaml`.

    Convenience for the M1.13 Master Decision Engine and tests — they
    don't have to know the packaged path layout.
    """
    here = Path(__file__).resolve().parent
    default = (here / _DEFAULT_RULES_RELPATH).resolve()
    return load_rules_yaml(default)


# ----------------------------------------------------------------------
# Internal: parse + validate
# ----------------------------------------------------------------------


_REQUIRED_FIELDS: frozenset[str] = frozenset({"id", "when", "emit", "rationale"})
_OPTIONAL_FIELDS: frozenset[str] = frozenset({"risks", "invalidation"})


def _parse_rules_text(text: str, *, source: str) -> tuple[RuleSpec, ...]:
    """Parse YAML text → validated `tuple[RuleSpec, ...]`.

    Split out from `load_rules_yaml` so tests can exercise the parser
    without writing a file.
    """
    parsed = yaml.safe_load(text)
    if parsed is None:
        raise ValueError(f"{source}: YAML is empty")
    if not isinstance(parsed, list):
        raise ValueError(
            f"{source}: top level must be a list of rules; got "
            f"{type(parsed).__name__}"
        )

    supported = supported_clauses()
    valid_emits = {e.value for e in EmittedAction}
    out: list[RuleSpec] = []

    for index, entry in enumerate(parsed):
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"{source}: rule at index {index} must be a mapping; "
                f"got {type(entry).__name__}"
            )

        missing = _REQUIRED_FIELDS - entry.keys()
        if missing:
            raise ValueError(
                f"{source}: rule at index {index} missing required "
                f"fields: {sorted(missing)}"
            )

        rule_id = str(entry["id"])
        emit_str = str(entry["emit"])
        if emit_str not in valid_emits:
            raise ValueError(
                f"{source}: rule '{rule_id}' has invalid emit "
                f"'{emit_str}'. Valid: {sorted(valid_emits)}"
            )
        emit = EmittedAction(emit_str)

        when_block = entry["when"]
        if not isinstance(when_block, Mapping):
            raise ValueError(
                f"{source}: rule '{rule_id}' has invalid 'when' block "
                f"(must be mapping); got {type(when_block).__name__}"
            )
        unknown_clauses = set(when_block.keys()) - supported
        if unknown_clauses:
            raise ValueError(
                f"{source}: rule '{rule_id}' uses unsupported clauses: "
                f"{sorted(unknown_clauses)}. Supported: {sorted(supported)}"
            )

        # risks / invalidation: tuple-ify if present, default to empty.
        risks = _tupleify(entry.get("risks", []), field="risks", rule_id=rule_id)
        invalidation = _tupleify(
            entry.get("invalidation", []), field="invalidation", rule_id=rule_id
        )

        # Forward-tolerant: accept unknown top-level keys (e.g. future
        # `score`) but ignore them in V1.
        out.append(
            RuleSpec(
                id=rule_id,
                when=dict(when_block),
                emit=emit,
                rationale=str(entry["rationale"]),
                risks=risks,
                invalidation=invalidation,
            )
        )

    return tuple(out)


def _tupleify(
    value: Any, *, field: str, rule_id: str
) -> tuple[str, ...]:
    """Validate `value` is a list[str] (or absent) and coerce to tuple."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(
            f"rule '{rule_id}': field '{field}' must be a list; "
            f"got {type(value).__name__}"
        )
    return tuple(str(x) for x in value)
