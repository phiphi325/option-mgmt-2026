"""Response shapes for the 5 CSV import endpoints (M1.17).

Per plan v1.2 §7 + §10 (canonical CSV formats) + §17 M1.17.

All five endpoints (`POST /data/{positions, option-positions, chain,
iv, events}/import-csv`) accept `multipart/form-data` with a single
`file` field and return the same shape:

  {
    "inserted":            int,   // rows newly created
    "updated":             int,   // rows upsert-updated (positions + option_positions only)
    "skipped":             int,   // duplicate-exact rows or rows with errors
    "errors":              [...], // per-row failures with line + column + message
    "validation_warnings": [...]  // soft warnings (e.g. §22.12 IV-history < 60 days)
  }

The endpoints differ in their idempotency strategy (see
`app/services/csv_import_service.py`):

  - `positions`         — upsert on (user_id, ticker, opened_at)
  - `option-positions`  — upsert on (user_id, ticker, side, kind, strike, expiry, opened_at)
  - `chain`             — append-only; dedupe exact (ticker, fetched_at, expiry, strike, kind) at upload
  - `iv`                — upsert on (ticker, ts) [existing PK]
  - `events`            — dedupe on (ticker, kind, scheduled_at, source) at upload

Per §22.12, IV history uploads validate post-insert row count and
return HTTP 422 when `count(*) < 30` for the ticker.

V1 CSV uploads accept up to 10 MB per file (enforced at the router
layer via FastAPI's `UploadFile` size check). Above that returns 413.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CsvImportError(BaseModel):
    """A single row's parse / validation error."""

    model_config = ConfigDict(extra="forbid")

    line: int = Field(ge=1, description="1-indexed line number in the source CSV (header is line 1)")
    column: str | None = None
    message: str


class CsvImportResponse(BaseModel):
    """Uniform response across all 5 CSV import endpoints."""

    model_config = ConfigDict(extra="forbid")

    inserted: int = Field(ge=0)
    updated: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: list[CsvImportError] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


__all__ = ["CsvImportError", "CsvImportResponse"]
