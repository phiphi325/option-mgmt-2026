"""Canonical-JSON serializer for `DailyDecision` per plan v1.2 §19 (Phase 1 Done bar).

Produces a deterministic dict representation suitable for byte-equal golden
comparison. Used by:

  - `packages/engine/tests/test_master_decision_goldens.py` — the replay harness.
  - `packages/engine/scripts/regenerate_decision_goldens.py` — fixture regeneration.

The output is a plain `dict` with stable types; callers `json.dumps` with
`sort_keys=True` to get the byte-stable wire representation.

## Conventions

- **Floats** are rounded to `_FLOAT_PRECISION` (6) decimal places at serialization
  time. This absorbs cross-platform float ULP differences (Apple Silicon vs.
  Linux x86_64) while preserving more precision than the UI displays (2 places).
  See plan v1.2 §19 + M1.24 dev spec Open Question Q2.
- **Decimals** are converted via `float(d)` then rounded — same precision policy
  as floats. (The engine itself uses floats per ADR-0005 + M1.6 Greeks
  convention; `Decimal` appears only at the API → DB boundary.)
- **`datetime`** is serialized as ISO 8601. Naive datetimes are assumed UTC
  (matching `engine.decision.hashing.compute_inputs_hash` conventions). Aware
  datetimes preserve their offset, but `+00:00` is normalized to `Z` for
  consistency.
- **`date`** is serialized as ISO 8601 date string (`YYYY-MM-DD`).
- **Enums** (`StrEnum`, `IntEnum`, plain `Enum`) are serialized as `.value`.
- **Tuples** are converted to lists (JSON has no tuple type).
- **`frozenset`** is converted to a sorted list (sorted by `repr(item)` for
  cross-platform stability — same convention as `compute_inputs_hash`).
- **`dataclass` instances** are converted via `dataclasses.asdict` then walked
  recursively.
- **Pydantic `BaseModel` instances** are converted via `model_dump(mode="json")`
  then walked recursively (preserves the canonicalization for nested types).
- **`None`** stays as `None` (JSON `null`).
- **`bool`** stays as `bool` (NOT converted to int — JSON has booleans).
- **`int`** stays as `int`.
- **`str`** stays as `str`.

This module ships in engine 1.7.0 (M1.24). It is **test-infrastructure only** —
no production code path imports it. The function is in
`engine.decision` rather than `engine.decision.tests` because the regeneration
script (which lives outside the test tree) needs to import it too.

Public API:

  serialize_canonical(decision) -> dict
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from engine.decision.types import DailyDecision

# 6 decimal places: max precision loss is 5e-7, well below the UI display
# precision (2 places) and the M1.10 composer's clip01 sensitivity.
_FLOAT_PRECISION = 6


def serialize_canonical(decision: DailyDecision) -> dict[str, Any]:
    """Return a canonical-JSON-ready dict for the given `DailyDecision`.

    The output is suitable for byte-equal comparison via
    `json.dumps(result, sort_keys=True, indent=2)`. Floats are rounded to 6
    decimal places to absorb cross-platform ULP differences.

    Args:
        decision: The `DailyDecision` to serialize. Frozen dataclass per
                  ADR-0005; this function does not mutate it.

    Returns:
        A plain `dict[str, Any]` with only JSON-native types
        (`dict`, `list`, `str`, `int`, `float`, `bool`, `None`) plus
        no datetimes, dates, enums, tuples, frozensets, or dataclasses.

    Pure function. Same input → byte-identical output (per the
    M1.24 acceptance criteria).
    """
    return _canonicalize(decision)  # type: ignore[no-any-return]


def _canonicalize(value: Any) -> Any:
    """Recursive walker. Each branch handles one type class."""
    # Order matters: bool before int (bool is a subclass of int), Enum before
    # str (StrEnum is a subclass of str).
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        # StrEnum / IntEnum / plain Enum all expose `.value`.
        return _canonicalize(value.value)
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Round to absorb cross-platform ULP differences. NaN and Inf are
        # preserved (JSON serializers will raise; that's the right behavior).
        if math.isnan(value) or math.isinf(value):
            return value
        return round(value, _FLOAT_PRECISION)
    if isinstance(value, datetime):
        # Naive datetimes assumed UTC, matching engine.decision.hashing
        # canonicalization conventions.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        # Normalize +00:00 to Z for cross-environment stability.
        iso = value.isoformat()
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        return iso
    if isinstance(value, date):
        # date (not datetime) → ISO 8601 date string.
        return value.isoformat()
    if isinstance(value, dict):
        # Recursively canonicalize keys + values. Keys must be JSON-string-able
        # post-canonicalization. We coerce non-string keys to str (matches
        # json.dumps default behavior).
        return {str(_canonicalize(k)): _canonicalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, frozenset):
        # Sort by repr for cross-platform stability (same convention as
        # engine.decision.hashing.compute_inputs_hash for frozensets).
        return [_canonicalize(item) for item in sorted(value, key=repr)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # Walk dataclass instances field-by-field. We avoid dataclasses.asdict
        # because it doesn't handle non-dataclass nested types (e.g. Pydantic
        # models) the way we want.
        return {
            f.name: _canonicalize(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    # Pydantic v2 BaseModel detection without importing pydantic at the
    # top level (keeps this module engine-pure if pydantic vanishes).
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            # `mode` kwarg unsupported (very old pydantic); fall back.
            dumped = model_dump()
        return _canonicalize(dumped)
    # Fallback: string-coerce. Hit for types like Decimal (which has __str__
    # returning a string-of-the-number suitable for replay). We then attempt
    # to parse back to float to preserve numeric semantics; if that fails
    # (rare for engine types), the string survives.
    try:
        return round(float(value), _FLOAT_PRECISION)
    except (TypeError, ValueError):
        return str(value)
