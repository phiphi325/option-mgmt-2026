"""OM-Y2 unit tests for the pure parts of the yearline ingest job.

DB-backed idempotency + hydration are exercised by `test_smoke_yearline.py`
(live Postgres). These tests cover the validation + hashing logic that needs no
database: artifact parsing, the `adapter_version` pin, persistability guards,
and content-hash determinism.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from engine.yearline import YearlineContext
from pydantic import ValidationError

from app.jobs.ingest_yearline import (
    compute_payload_hash,
    parse_artifact,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "yearline"
GATED = _FIXTURES / "fixture_msft_gated.json"
STALE = _FIXTURES / "fixture_stale_empty.json"


def _gated() -> dict[str, Any]:
    return json.loads(GATED.read_text())


def test_parse_artifact_accepts_gated_fixture() -> None:
    ctx = parse_artifact(_gated())
    assert isinstance(ctx, YearlineContext)
    assert ctx.ticker == "MSFT"
    assert ctx.adapter_version == "v13_8_yearline_context_adapter_v1"


def test_parse_artifact_passes_through_model_instance() -> None:
    ctx = YearlineContext.model_validate(_gated())
    assert parse_artifact(ctx) is ctx


def test_parse_artifact_rejects_incompatible_adapter_version() -> None:
    raw = _gated()
    raw["adapter_version"] = "v99_future_adapter"
    with pytest.raises(ValueError, match="incompatible_adapter_version"):
        parse_artifact(raw)


def test_parse_artifact_rejects_missing_as_of() -> None:
    raw = _gated()
    raw["as_of"] = None
    with pytest.raises(ValueError, match="missing_as_of"):
        parse_artifact(raw)


def test_parse_artifact_rejects_missing_ticker() -> None:
    raw = _gated()
    raw["ticker"] = None
    with pytest.raises(ValueError, match="missing_ticker"):
        parse_artifact(raw)


def test_parse_artifact_rejects_unpinned_extra_field() -> None:
    raw = _gated()
    raw["gate_diagnostics"] = {"auc": 0.74}
    with pytest.raises(ValidationError):
        parse_artifact(raw)


def test_compute_payload_hash_is_deterministic_and_order_insensitive() -> None:
    ctx = parse_artifact(_gated())
    payload = ctx.model_dump(mode="json")
    h1 = compute_payload_hash(payload)
    # Re-serialize with shuffled key order — canonical (sorted) hash is stable.
    reordered = dict(reversed(list(payload.items())))
    h2 = compute_payload_hash(reordered)
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == len("sha256:") + 64


def test_compute_payload_hash_changes_on_content_change() -> None:
    ctx = parse_artifact(_gated())
    payload = ctx.model_dump(mode="json")
    before = compute_payload_hash(payload)
    payload["distance_to_ma250_pct"] = -9.999
    assert compute_payload_hash(payload) != before
