"""YAML loader for the Confidence Composer weights.

Per plan v1.2 §9.7 + §22.13.

The engine itself is pure (per ADR-0005). This module is the single
filesystem boundary for confidence weights: it reads
`packages/engine/config/weights.yaml`, parses + validates it, and
returns a `Weights` instance. `engine.recommendation.recommend` takes
the parsed `Weights` (not a path), keeping the core decision logic
pure.

The default V1 weights ship in `packages/engine/config/weights.yaml`.
`load_default_weights()` resolves that path so callers don't have to.

The YAML schema (per §22.13):

    version: "v2.0"
    positive_weights:
      flow:    0.30
      struct:  0.25
      regime:  0.25
      signal:  0.20
    penalty_caps:
      event:    0.30
      liquidity: 0.25

Schema validation:
  - Top level is a mapping with exactly `version`, `positive_weights`,
    `penalty_caps` (extra top-level keys are forward-tolerant).
  - `version` is non-empty string.
  - `positive_weights` is a mapping with float values for
    `flow`, `struct`, `regime`, `signal` (sum-to-1.0 enforced by
    `Weights.__post_init__`).
  - `penalty_caps` is a mapping with float values for
    `event`, `liquidity` (each in `[0, 1]` enforced by
    `Weights.__post_init__`).

Errors surface as `ValueError` with the YAML source + problem in the
message — easy to find when CI fails on a malformed weights file.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from engine.confidence.types import PenaltyCaps, PositiveWeights, Weights

# Path to the packaged V1 weights.yaml relative to the engine module.
#   packages/engine/engine/confidence/yaml_loader.py   ← here
#   packages/engine/config/weights.yaml                ← target
_DEFAULT_WEIGHTS_RELPATH = "../../config/weights.yaml"


def load_weights_yaml(path: Path | str) -> Weights:
    """Read + parse + validate the weights YAML at `path`.

    Args:
        path: Filesystem path to a YAML file in the §22.13 schema.

    Returns:
        A validated `Weights` instance.

    Raises:
        FileNotFoundError: `path` does not exist.
        ValueError: YAML is empty / wrong shape / missing required
            keys / fails `Weights` invariants (sum-to-1, cap range).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"weights.yaml not found: {p}")
    raw_text = p.read_text(encoding="utf-8")
    return _parse_weights_text(raw_text, source=str(p))


def load_default_weights() -> Weights:
    """Load the packaged V1 weights from `packages/engine/config/weights.yaml`.

    Convenience for `engine.recommendation.recommend` and tests — they
    don't have to know the packaged path layout.
    """
    here = Path(__file__).resolve().parent
    default = (here / _DEFAULT_WEIGHTS_RELPATH).resolve()
    return load_weights_yaml(default)


# ----------------------------------------------------------------------
# Internal: parse + validate
# ----------------------------------------------------------------------


_REQUIRED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {"version", "positive_weights", "penalty_caps"}
)
_REQUIRED_POSITIVE_KEYS: frozenset[str] = frozenset(
    {"flow", "struct", "regime", "signal"}
)
_REQUIRED_PENALTY_KEYS: frozenset[str] = frozenset({"event", "liquidity"})


def _parse_weights_text(text: str, *, source: str) -> Weights:
    """Parse YAML text → validated `Weights`.

    Split out from `load_weights_yaml` so tests can exercise the parser
    without writing a file.
    """
    parsed = yaml.safe_load(text)
    if parsed is None:
        raise ValueError(f"{source}: YAML is empty")
    if not isinstance(parsed, Mapping):
        raise ValueError(
            f"{source}: top level must be a mapping; got {type(parsed).__name__}"
        )

    missing = _REQUIRED_TOP_LEVEL_KEYS - parsed.keys()
    if missing:
        raise ValueError(
            f"{source}: missing required top-level keys: {sorted(missing)}"
        )

    version = parsed["version"]
    if not isinstance(version, str) or not version:
        raise ValueError(
            f"{source}: 'version' must be a non-empty string; got {version!r}"
        )

    positive = _parse_positive_weights(parsed["positive_weights"], source=source)
    caps = _parse_penalty_caps(parsed["penalty_caps"], source=source)

    # Forward-tolerant: unknown top-level keys are ignored (e.g.
    # future `metadata:` block).
    return Weights(version=version, positive_weights=positive, penalty_caps=caps)


def _parse_positive_weights(value: Any, *, source: str) -> PositiveWeights:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{source}: 'positive_weights' must be a mapping; "
            f"got {type(value).__name__}"
        )
    missing = _REQUIRED_POSITIVE_KEYS - value.keys()
    if missing:
        raise ValueError(
            f"{source}: 'positive_weights' missing required keys: {sorted(missing)}"
        )
    return PositiveWeights(
        flow=_as_float(value["flow"], field="positive_weights.flow", source=source),
        struct=_as_float(
            value["struct"], field="positive_weights.struct", source=source
        ),
        regime=_as_float(
            value["regime"], field="positive_weights.regime", source=source
        ),
        signal=_as_float(
            value["signal"], field="positive_weights.signal", source=source
        ),
    )


def _parse_penalty_caps(value: Any, *, source: str) -> PenaltyCaps:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{source}: 'penalty_caps' must be a mapping; got {type(value).__name__}"
        )
    missing = _REQUIRED_PENALTY_KEYS - value.keys()
    if missing:
        raise ValueError(
            f"{source}: 'penalty_caps' missing required keys: {sorted(missing)}"
        )
    return PenaltyCaps(
        event=_as_float(value["event"], field="penalty_caps.event", source=source),
        liquidity=_as_float(
            value["liquidity"], field="penalty_caps.liquidity", source=source
        ),
    )


def _as_float(value: Any, *, field: str, source: str) -> float:
    """Coerce a YAML scalar to float; raise with field name on failure."""
    if isinstance(value, bool):
        # bool subclasses int in Python; reject explicitly so True/False
        # don't silently become 1.0/0.0.
        raise ValueError(
            f"{source}: '{field}' must be a number; got bool ({value!r})"
        )
    if not isinstance(value, (int, float)):
        raise ValueError(
            f"{source}: '{field}' must be a number; got {type(value).__name__}"
        )
    return float(value)
