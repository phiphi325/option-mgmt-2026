r"""positions + option_positions: composite UNIQUE for CSV upsert idempotency

Revision ID: 0003_imp_unique_constraints
Revises: 0002_dd_unique_user_hash
Create Date: 2026-05-12

NOTE: revision id is 28 chars — under the alembic_version.version_num
VARCHAR(32) ceiling. See M1.14 lesson and 0002_dd_unique_user_hash.py.

Per master plan v1.2 §10 (Data Ingestion) + §17 M1.17 + the M1.17 dev
spec at `docs/phased-design/phase-1/m1.17-profile-outcomes-csv-import.md`:

  CSV uploads (`POST /data/positions/import-csv` + `/data/option-positions/
  import-csv`) need composite UNIQUE constraints to power the
  `INSERT ... ON CONFLICT ... DO UPDATE` upsert pattern. Without these,
  the same CSV uploaded twice would create duplicate rows rather than
  no-op on the second upload.

Idempotency keys:
  - `positions`: (user_id, ticker, opened_at) — same user + same ticker
    + same opening time means the same lot opening event.
  - `option_positions`: (user_id, ticker, side, kind, strike, expiry,
    opened_at) — composite identifies a specific option leg opening.

Other tables (option_chain_snapshots, iv_history, events) are NOT
touched by this migration:
  - `option_chain_snapshots` is append-only by design (§6 schema);
    duplicate rows are deduplicated at the upload layer by exact match.
  - `iv_history.(ticker, ts)` already has PRIMARY KEY semantics from
    0001_init — natural ON CONFLICT key.
  - `events` has no natural primary key beyond `id`; CSV upload
    dedupes at the application layer on `(ticker, kind, scheduled_at,
    source)`.

The constraint names follow Postgres's default `<table>_<cols>_key`
convention without abbreviating — readable in `\d` output and in error
messages.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_imp_unique_constraints"
down_revision: str | Sequence[str] | None = "0002_dd_unique_user_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # positions: (user_id, ticker, opened_at)
    op.execute(
        """
        ALTER TABLE positions
        ADD CONSTRAINT positions_user_ticker_opened_unique
        UNIQUE (user_id, ticker, opened_at);
        """
    )

    # option_positions: (user_id, ticker, side, kind, strike, expiry, opened_at)
    op.execute(
        """
        ALTER TABLE option_positions
        ADD CONSTRAINT option_positions_user_leg_unique
        UNIQUE (user_id, ticker, side, kind, strike, expiry, opened_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE option_positions
        DROP CONSTRAINT IF EXISTS option_positions_user_leg_unique;
        """
    )
    op.execute(
        """
        ALTER TABLE positions
        DROP CONSTRAINT IF EXISTS positions_user_ticker_opened_unique;
        """
    )
