"""yearline_trend_series: persisted presentation trend-series artifacts (OM-Y3)

Revision ID: 0005_yearline_trend_series
Revises: 0004_yearline_context
Create Date: 2026-06-10

NOTE: revision id is 26 chars — under the alembic_version.version_num
VARCHAR(32) ceiling.

Per ADR-0009 + docs/enhancements/yearline/producer-handoff/
ux_trend_plot_support_analysis.md (OM-Y3):

  The `YearlineTrendSeries` (`series_version = v13_8_1_yearline_trend_series_v1`)
  is the **presentation-only** time series powering the Today-screen trend plot.
  It is NOT an engine input and never enters the replay hash — kept in its own
  table, separate from `yearline_context` (the scalar engine contract), so the
  heavy chart payload never bloats the decision contract.

Same idempotency model as `yearline_context`: `UNIQUE (ticker, as_of)`,
re-ingest overwrites in place, `payload_hash` lets the upsert skip a no-op write.
Only `available: true` series (with a ticker + as_of) are persisted; the
`available: false` empty state is never stored (absence ⇒ the panel's empty
placeholder).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_yearline_trend_series"
down_revision: str | Sequence[str] | None = "0004_yearline_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE yearline_trend_series (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ticker              text NOT NULL,
            as_of               date NOT NULL,
            series_version      text NOT NULL,
            schema_version      text,
            model_stack_version text,
            payload             jsonb NOT NULL,
            payload_hash        text NOT NULL,
            ingested_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT yearline_trend_series_ticker_as_of_unique UNIQUE (ticker, as_of)
        );
        CREATE INDEX yearline_trend_series_ticker_asof_idx
            ON yearline_trend_series(ticker, as_of DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS yearline_trend_series;")
