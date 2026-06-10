"""OM-Y3 unit tests — trend-series validation + panel-endpoint auth gate.

DB-backed ingest/read + the full HTTP round-trip are in `test_smoke_yearline.py`
(live Postgres). These cover the DB-free logic: trend-series parsing/pinning and
the endpoint's auth gate (which runs before any DB access).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.jobs.ingest_yearline import parse_trend_series
from app.schemas.yearline import YearlineTrendSeriesModel

_FIXTURES = Path(__file__).parent / "fixtures" / "yearline"
TREND = _FIXTURES / "fixture_msft_trend_series.json"
UNAVAILABLE = _FIXTURES / "fixture_unavailable_trend_series.json"


def _trend() -> dict[str, Any]:
    return json.loads(TREND.read_text())


def test_parse_trend_series_accepts_available_fixture() -> None:
    model = parse_trend_series(_trend())
    assert isinstance(model, YearlineTrendSeriesModel)
    assert model.available is True
    assert model.ticker == "MSFT"
    assert model.series_version == "v13_8_1_yearline_trend_series_v1"
    assert model.dates is not None and model.n == len(model.dates)


def test_parse_trend_series_rejects_unavailable() -> None:
    raw = json.loads(UNAVAILABLE.read_text())
    with pytest.raises(ValueError, match="unavailable_series"):
        parse_trend_series(raw)


def test_parse_trend_series_rejects_incompatible_version() -> None:
    raw = _trend()
    raw["series_version"] = "v99_future_series"
    with pytest.raises(ValueError, match="incompatible_series_version"):
        parse_trend_series(raw)


def test_parse_trend_series_rejects_unpinned_extra_field() -> None:
    raw = _trend()
    raw["surprise_panel"] = [1, 2, 3]
    with pytest.raises(ValidationError):
        parse_trend_series(raw)


def test_trend_series_gated_arrays_gap_with_nulls() -> None:
    """Gated series carry `null` off-regime (UX §6.3) — the model preserves
    them as None (not zero), so the UI can gap the line."""
    model = parse_trend_series(_trend())
    assert model.p_retry_40d is not None
    assert None in model.p_retry_40d  # at least one off-regime gap


def test_yearline_endpoint_requires_auth(client: TestClient) -> None:
    """The panel endpoint is auth-gated; the 401 fires before any DB access."""
    r = client.get("/api/v1/engine/yearline-context", params={"ticker": "MSFT"})
    assert r.status_code == 401
