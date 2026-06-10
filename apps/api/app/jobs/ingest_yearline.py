"""Ingest a yearline-universe `YearlineContext` artifact into Postgres (OM-Y2).

Per ADR-0009 + docs/enhancements/0002-yearline-context-assessment.md.

The nightly yearline-universe batch publishes a per-ticker `YearlineContext`
artifact (a JSON blob). This job validates it against the engine's frozen
contract (`engine.yearline.YearlineContext`), pins the accepted
`adapter_version` range, and upserts a `yearline_context` row keyed by
`(ticker, as_of)`.

The pure engine never imports yearline-universe (ADR-0005); this job is the
jobs-layer producer side of the persisted-artifact boundary — exactly the slot
`inputs_hydration_service` fills for MarketState / FlowScore.

Idempotency: `ON CONFLICT (ticker, as_of) DO UPDATE ... WHERE payload_hash
changed`. Re-ingesting identical bytes is a true no-op (no write); a changed
artifact for the same `(ticker, as_of)` overwrites in place. The returned
`IngestResult.status` distinguishes `inserted` / `updated` / `unchanged`.

## Public API

  parse_artifact(artifact)            -> YearlineContext   (pure; validates + pins)
  compute_payload_hash(payload)       -> str               (pure; canonical sha256)
  ingest_yearline_context(session, …) -> IngestResult      (DB upsert)
  ingest_yearline_file(session, path) -> IngestResult      (read file, then upsert)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from engine.yearline import ACCEPTED_ADAPTER_VERSIONS, YearlineContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.yearline import ACCEPTED_SERIES_VERSIONS, YearlineTrendSeriesModel

IngestStatus = Literal["inserted", "updated", "unchanged"]


@dataclass(frozen=True)
class IngestResult:
    """Outcome of an ingest call.

    `status`:
      - `inserted`  — a new `(ticker, as_of)` row was created
      - `updated`   — an existing row's payload changed and was overwritten
      - `unchanged` — the row already held identical bytes (true no-op)
    """

    status: IngestStatus
    ticker: str
    as_of: str  # ISO date
    payload_hash: str


def parse_artifact(artifact: dict[str, Any] | YearlineContext) -> YearlineContext:
    """Validate a raw artifact into the frozen contract + pin its version.

    Raises:
        pydantic.ValidationError: artifact violates the `YearlineContext` shape
            (incl. an un-pinned producer field, via `extra="forbid"`).
        ValueError("incompatible_adapter_version" | "missing_as_of" |
            "missing_ticker"): the artifact parses but cannot be persisted.
    """
    ctx = (
        artifact
        if isinstance(artifact, YearlineContext)
        else YearlineContext.model_validate(artifact)
    )
    if ctx.adapter_version not in ACCEPTED_ADAPTER_VERSIONS:
        raise ValueError(
            f"incompatible_adapter_version: {ctx.adapter_version!r} not in "
            f"{sorted(ACCEPTED_ADAPTER_VERSIONS)} — a coordinated OM-Y1 pin bump "
            f"is required before this artifact can be ingested."
        )
    # A persisted row is keyed by (ticker, as_of); both must be present even
    # though the wire contract allows them null for the degenerate empty case.
    if ctx.as_of is None:
        raise ValueError("missing_as_of: artifact has no as_of; cannot persist.")
    if ctx.ticker is None:
        raise ValueError("missing_ticker: artifact has no ticker; cannot persist.")
    return ctx


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Deterministic content hash of a JSON-able payload (sorted keys)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_UPSERT_SQL = text(
    """
    INSERT INTO yearline_context (
        ticker, as_of, schema_version, model_stack_version,
        adapter_version, payload, payload_hash
    )
    VALUES (
        :ticker, CAST(:as_of AS date), :schema_version, :model_stack_version,
        :adapter_version, CAST(:payload AS jsonb), :payload_hash
    )
    ON CONFLICT (ticker, as_of) DO UPDATE SET
        schema_version      = EXCLUDED.schema_version,
        model_stack_version = EXCLUDED.model_stack_version,
        adapter_version     = EXCLUDED.adapter_version,
        payload             = EXCLUDED.payload,
        payload_hash        = EXCLUDED.payload_hash,
        ingested_at         = now()
    WHERE yearline_context.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
    RETURNING (xmax = 0) AS inserted;
    """
)


async def ingest_yearline_context(
    *,
    session: AsyncSession,
    artifact: dict[str, Any] | YearlineContext,
) -> IngestResult:
    """Validate + idempotently upsert one artifact. Commits on success."""
    ctx = parse_artifact(artifact)
    payload = ctx.model_dump(mode="json")
    payload_hash = compute_payload_hash(payload)
    assert ctx.as_of is not None and ctx.ticker is not None  # narrowed by parse_artifact
    as_of_iso = ctx.as_of.isoformat()

    result = await session.execute(
        _UPSERT_SQL,
        {
            "ticker": ctx.ticker,
            "as_of": as_of_iso,
            "schema_version": ctx.schema_version,
            "model_stack_version": ctx.model_stack_version,
            "adapter_version": ctx.adapter_version,
            "payload": json.dumps(payload),
            "payload_hash": payload_hash,
        },
    )
    row = result.first()
    await session.commit()

    if row is None:
        # ON CONFLICT WHERE-clause excluded the update → bytes unchanged.
        status: IngestStatus = "unchanged"
    else:
        status = "inserted" if bool(row[0]) else "updated"

    return IngestResult(
        status=status,
        ticker=ctx.ticker,
        as_of=as_of_iso,
        payload_hash=payload_hash,
    )


async def ingest_yearline_file(
    *,
    session: AsyncSession,
    path: str | Path,
) -> IngestResult:
    """Read a `YearlineContext` JSON artifact from disk and ingest it."""
    raw = json.loads(Path(path).read_text())
    return await ingest_yearline_context(session=session, artifact=raw)


# ----------------------------------------------------------------------
# Trend series (presentation-only artifact, OM-Y3)
# ----------------------------------------------------------------------


def parse_trend_series(
    artifact: dict[str, Any] | YearlineTrendSeriesModel,
) -> YearlineTrendSeriesModel:
    """Validate a raw trend-series artifact + pin its version + persistability.

    Raises:
        pydantic.ValidationError: artifact violates the schema (incl. extra fields).
        ValueError("incompatible_series_version" | "unavailable_series" |
            "missing_as_of" | "missing_ticker"): parses but cannot be persisted.
    """
    model = (
        artifact
        if isinstance(artifact, YearlineTrendSeriesModel)
        else YearlineTrendSeriesModel.model_validate(artifact)
    )
    if model.series_version not in ACCEPTED_SERIES_VERSIONS:
        raise ValueError(
            f"incompatible_series_version: {model.series_version!r} not in "
            f"{sorted(ACCEPTED_SERIES_VERSIONS)}."
        )
    # Only `available` series with a (ticker, as_of) are persistable; the
    # `available: false` empty state is never stored — its absence drives the
    # panel's empty placeholder.
    if not model.available:
        raise ValueError("unavailable_series: available=false; nothing to persist.")
    if model.as_of is None:
        raise ValueError("missing_as_of: series has no as_of; cannot persist.")
    if model.ticker is None:
        raise ValueError("missing_ticker: series has no ticker; cannot persist.")
    return model


_TREND_UPSERT_SQL = text(
    """
    INSERT INTO yearline_trend_series (
        ticker, as_of, series_version, schema_version, model_stack_version,
        payload, payload_hash
    )
    VALUES (
        :ticker, CAST(:as_of AS date), :series_version, :schema_version,
        :model_stack_version, CAST(:payload AS jsonb), :payload_hash
    )
    ON CONFLICT (ticker, as_of) DO UPDATE SET
        series_version      = EXCLUDED.series_version,
        schema_version      = EXCLUDED.schema_version,
        model_stack_version = EXCLUDED.model_stack_version,
        payload             = EXCLUDED.payload,
        payload_hash        = EXCLUDED.payload_hash,
        ingested_at         = now()
    WHERE yearline_trend_series.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
    RETURNING (xmax = 0) AS inserted;
    """
)


async def ingest_yearline_trend_series(
    *,
    session: AsyncSession,
    artifact: dict[str, Any] | YearlineTrendSeriesModel,
) -> IngestResult:
    """Validate + idempotently upsert one trend-series artifact. Commits."""
    model = parse_trend_series(artifact)
    payload = model.model_dump(mode="json")
    payload_hash = compute_payload_hash(payload)
    assert model.as_of is not None and model.ticker is not None  # narrowed by parse
    as_of_iso = model.as_of.isoformat()

    result = await session.execute(
        _TREND_UPSERT_SQL,
        {
            "ticker": model.ticker,
            "as_of": as_of_iso,
            "series_version": model.series_version,
            "schema_version": model.schema_version,
            "model_stack_version": model.model_stack_version,
            "payload": json.dumps(payload),
            "payload_hash": payload_hash,
        },
    )
    row = result.first()
    await session.commit()

    if row is None:
        status: IngestStatus = "unchanged"
    else:
        status = "inserted" if bool(row[0]) else "updated"

    return IngestResult(
        status=status,
        ticker=model.ticker,
        as_of=as_of_iso,
        payload_hash=payload_hash,
    )


__all__ = [
    "IngestResult",
    "IngestStatus",
    "compute_payload_hash",
    "ingest_yearline_context",
    "ingest_yearline_file",
    "ingest_yearline_trend_series",
    "parse_artifact",
    "parse_trend_series",
]
