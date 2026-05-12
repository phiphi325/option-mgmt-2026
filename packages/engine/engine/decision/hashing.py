"""`inputs_hash` utility — SHA-256 over canonical JSON of engine inputs.

Per plan v1.2 §5 (replay) + §6 (every `daily_decisions` row carries
`inputs_hash`) + Day 14 of §17 (`utils/hashing.py`).

The hash collapses every input to the Master Decision Engine into one
deterministic string. Two calls with byte-identical inputs produce the
same hash; the engine version stamp + the weights version stamp + this
hash together identify a replayable decision exactly.

What goes into the hash (the canonical input set, per §5.4):
  - `as_of` (ISO-8601 string)
  - `ticker`
  - `chain_snapshot` (underlying, spot, as_of, contracts tuple)
  - `positions` (PositionState — frozen dataclass)
  - `profile` (UserStrategyProfile — frozen Pydantic)
  - `market_state` (M1.4 result with regime + 17 echo fields)
  - `flow_score` (M1.5b result with score + breakdown)

What we deliberately exclude:
  - `weights_version` — already a separate pin on `DailyDecision`
  - `engine_version` — already a separate pin
  - `data_freshness` — operational metadata, not a logical input
  - `disclaimers` — text echoed, not a logical input

Canonical JSON conventions (matches §22.x — required for cross-language
hash agreement):
  - keys sorted alphabetically (Python `json.dumps(..., sort_keys=True)`)
  - no whitespace (`separators=(",", ":")`)
  - UTF-8 encoding (Python default)
  - dates → ISO-8601 (`YYYY-MM-DD` for `date`, RFC 3339 with Z suffix
    for `datetime`)
  - floats with full precision (no rounding; `repr` semantics)
  - tuples → lists (JSON has no tuple)
  - frozen dataclasses → dict of fields, recursively
  - Pydantic models → `model_dump()` with `mode="json"`

The hash output format is `"sha256:" + hexdigest`. This 71-character
string is human-distinguishable from a bare SHA-256 (which could be
confused for git SHAs) and survives JSON round-trips.

Pure function (per ADR-0005). No I/O, no clock.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


def compute_inputs_hash(
    *,
    as_of: datetime,
    ticker: str,
    chain_snapshot: Any,
    positions: Any,
    profile: Any,
    market_state: Any,
    flow_score: Any,
) -> str:
    """Compute the canonical `"sha256:<hex>"` hash over engine inputs.

    Args:
        as_of:           Decision-time timestamp.
        ticker:          Underlying symbol.
        chain_snapshot:  `ChainSnapshot` (Pydantic BaseModel).
        positions:       `PositionState` (frozen dataclass).
        profile:         `UserStrategyProfile` (Pydantic BaseModel).
        market_state:    `MarketStateResult` (frozen dataclass).
        flow_score:      `FlowScore` (frozen dataclass).

    Returns:
        `"sha256:" + 64-char-lowercase-hex` — 71 characters total.
    """
    payload = {
        "as_of": _canonical(as_of),
        "ticker": ticker,
        "chain_snapshot": _canonical(chain_snapshot),
        "positions": _canonical(positions),
        "profile": _canonical(profile),
        "market_state": _canonical(market_state),
        "flow_score": _canonical(flow_score),
    }
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_fallback,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _canonical(value: Any) -> Any:
    """Recursive normalization of any value to a JSON-friendly shape.

    Handles:
      - None, bool, int, float, str → passthrough
      - date / datetime → ISO-8601 string
      - Enum → its `.value`
      - Pydantic BaseModel → `model_dump(mode="json")` (already JSON-clean)
      - dataclass (frozen or not) → dict of `_canonical(field)`
      - mapping → dict of `_canonical(value)` (keys coerced to str)
      - sequence (tuple, list) → list of `_canonical(item)`
      - frozenset / set → sorted list (stable order)
      - other → falls through to `_fallback`

    Returns:
        A value composed only of `None`, bool, int, float, str, list, dict.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        # RFC 3339 with explicit UTC suffix when naive (assume UTC for replay).
        if value.tzinfo is None:
            return value.isoformat() + "Z"
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _canonical(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        # Sort by canonical-string for stability across runs.
        return sorted((_canonical(item) for item in value), key=repr)
    return _fallback(value)


def _fallback(value: Any) -> str:
    """Last-resort coercion to string.

    Reached when `_canonical` encounters a type it doesn't know
    (e.g. a future scoring primitive). The string fallback is
    deterministic for a given input; CI catches unhandled types via
    explicit unit tests on the engine surface.
    """
    return repr(value)
