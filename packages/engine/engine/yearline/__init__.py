"""Yearline statistical-context contract (OM-Y1).

The consumer-side `YearlineContext` value object + its pinned version range. See
`engine.yearline.types` and ADR-0009. The engine never imports yearline-universe;
this is the gated artifact it parses.
"""

from __future__ import annotations

from engine.yearline.types import (
    ACCEPTED_ADAPTER_VERSIONS,
    ACCEPTED_SCHEMA_VERSIONS,
    PRetryBasis,
    YearlineContext,
)

__all__ = [
    "ACCEPTED_ADAPTER_VERSIONS",
    "ACCEPTED_SCHEMA_VERSIONS",
    "PRetryBasis",
    "YearlineContext",
]
