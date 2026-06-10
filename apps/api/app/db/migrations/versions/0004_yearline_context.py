"""yearline_context: persisted YearlineContext artifacts (OM-Y2)

Revision ID: 0004_yearline_context
Revises: 0003_imp_unique_constraints
Create Date: 2026-06-10

NOTE: revision id is 21 chars — under the alembic_version.version_num
VARCHAR(32) ceiling. See 0002/0003 for the lesson.

Per ADR-0009 + docs/enhancements/0002-yearline-context-assessment.md (OM-Y2):

  yearline-universe emits a nightly per-ticker `YearlineContext` artifact.
  The jobs layer (`app.jobs.ingest_yearline`) persists it here; the hydration
  service (`app.services.yearline_hydration_service`) reads the latest row back
  into the engine's `engine.yearline.YearlineContext` value object. The pure
  engine never imports yearline-universe — coupling is this persisted,
  versioned artifact (mirrors `inputs_hydration_service` for MarketState/Flow).

Idempotency key: `UNIQUE (ticker, as_of)` — one context per ticker per data
date. Re-ingesting the same `(ticker, as_of)` overwrites in place (the nightly
job is idempotent per the handoff "key the artifact by {ticker}_{as_of}"); the
`payload_hash` column lets the upsert skip a write when bytes are unchanged.

Columns mirror the plan's shape (`as_of, ticker, schema_version,
model_stack_version, payload JSONB, payload_hash`) plus `adapter_version` (the
contract pin) and `ingested_at` (ops/freshness).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_yearline_context"
down_revision: str | Sequence[str] | None = "0003_imp_unique_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE yearline_context (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ticker              text NOT NULL,
            as_of               date NOT NULL,
            schema_version      text,
            model_stack_version text,
            adapter_version     text NOT NULL,
            payload             jsonb NOT NULL,
            payload_hash        text NOT NULL,
            ingested_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT yearline_context_ticker_as_of_unique UNIQUE (ticker, as_of)
        );
        CREATE INDEX yearline_context_ticker_asof_idx
            ON yearline_context(ticker, as_of DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS yearline_context;")
