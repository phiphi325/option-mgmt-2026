"""OM-Y1 cross-repo contract test for `YearlineContext`.

Parses the two vendored V13.8 fixtures into the frozen Pydantic model and pins
the accepted `adapter_version` / `schema_version` range. No behaviour change ships
in OM-Y1 — this guards the producer↔consumer contract (ADR-0009 +
`docs/enhancements/0002-yearline-context-assessment.md`) so a yearline-side
adapter bump, or any un-pinned field-shape change, fails in CI.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.yearline.types import (
    ACCEPTED_ADAPTER_VERSIONS,
    ACCEPTED_SCHEMA_VERSIONS,
    PRetryBasis,
    YearlineContext,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "yearline"
GATED = _FIXTURES / "fixture_msft_gated.json"
STALE = _FIXTURES / "fixture_stale_empty.json"


def _load(path: Path) -> YearlineContext:
    return YearlineContext.model_validate_json(path.read_text())


def test_gated_fixture_parses() -> None:
    ctx = _load(GATED)
    assert ctx.ticker == "MSFT"
    assert ctx.as_of == date(2026, 5, 29)
    assert ctx.repair_active is True
    assert ctx.p_retry_basis is PRetryBasis.BLEND
    # int horizon keys (coerced from JSON string keys), gated all-true.
    assert ctx.p_retry == {10: 0.54, 20: 0.6477, 40: 0.8941, 60: 0.936}
    assert ctx.gate_passed == {10: True, 20: True, 40: True, 60: True}
    assert ctx.success_gate_passed is True
    assert ctx.must_not_auto_execute is True


def test_stale_fixture_is_abstention_shape() -> None:
    ctx = _load(STALE)
    assert ctx.is_stale is True
    assert ctx.repair_active is False
    assert ctx.p_retry == {}  # dormant above the yearline → no horizons
    assert ctx.gate_passed == {}
    assert ctx.p_retry_basis is None
    assert ctx.success_gate_passed is False
    assert ctx.must_not_auto_execute is True


@pytest.mark.parametrize("path", [GATED, STALE], ids=["gated", "stale"])
def test_adapter_and_schema_versions_pinned(path: Path) -> None:
    ctx = _load(path)
    assert ctx.adapter_version in ACCEPTED_ADAPTER_VERSIONS
    assert ctx.schema_version in ACCEPTED_SCHEMA_VERSIONS


@pytest.mark.parametrize("path", [GATED, STALE], ids=["gated", "stale"])
def test_roundtrip_json_matches_fixture(path: Path) -> None:
    """`model_dump(mode="json")` reproduces the fixture bytes' parsed form.

    int horizon keys serialize back to strings, so compare against the raw
    JSON object (dict equality is order-insensitive).
    """
    raw = json.loads(path.read_text())
    dumped = _load(path).model_dump(mode="json")
    assert dumped == raw


def test_extra_producer_field_is_rejected() -> None:
    """`extra="forbid"`: an un-pinned producer field (e.g. a future
    `gate_diagnostics` block) fails loudly — the cross-repo drift guard."""
    raw = json.loads(GATED.read_text())
    raw["gate_diagnostics"] = {"auc": 0.74, "mace": 0.08, "n": 120}
    with pytest.raises(ValidationError):
        YearlineContext.model_validate(raw)


def test_must_not_auto_execute_cannot_be_false() -> None:
    raw = json.loads(GATED.read_text())
    raw["must_not_auto_execute"] = False
    with pytest.raises(ValidationError):
        YearlineContext.model_validate(raw)


def test_model_is_frozen() -> None:
    ctx = _load(GATED)
    with pytest.raises(ValidationError):
        ctx.repair_active = False  # type: ignore[misc]
