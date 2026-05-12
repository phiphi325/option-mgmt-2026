"""daily_decisions: UNIQUE(user_id, inputs_hash) for idempotent persistence

Revision ID: 0002_dd_unique_user_hash
Revises: 0001_init
Create Date: 2026-05-12

NOTE: The revision id is intentionally short (24 chars). Alembic's
`alembic_version.version_num` column is VARCHAR(32) by default; longer
ids fail with StringDataRightTruncation on the
`UPDATE alembic_version SET version_num=...` step.

Per plan v1.2 §7 (Idempotency & replay):

> "POST /engine/daily-plan is read-only with respect to the engine; it
>  always persists the resulting DailyDecision row. Concurrent calls
>  with identical inputs_hash collapse via
>  INSERT ... ON CONFLICT (user_id, inputs_hash) DO RETURNING."

The 0001_init migration created `daily_decisions` with the right
columns but did not add the UNIQUE constraint. M1.14 wires
`produce_daily_decision()` into `POST /engine/daily-plan` and uses
the `ON CONFLICT` upsert pattern in `app.services.decision_service`,
which requires the constraint to exist.

Idempotency semantics:
  - Same `(user_id, inputs_hash)` → the same `daily_decisions` row
    (no duplicate inserts).
  - The service's `is_new_row` flag distinguishes fresh inserts
    (returns the inserted id) from idempotent retries (ON CONFLICT
    DO NOTHING returns no id).

Pre-existing rows: this migration assumes `daily_decisions` is empty
at upgrade time (which is true in V1 — M1.14 is the first endpoint
that writes to it). If you're applying this against a populated DB,
add a pre-check / dedupe step.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_dd_unique_user_hash"
down_revision: str | Sequence[str] | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE daily_decisions
        ADD CONSTRAINT daily_decisions_user_inputs_hash_unique
        UNIQUE (user_id, inputs_hash);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE daily_decisions
        DROP CONSTRAINT IF EXISTS daily_decisions_user_inputs_hash_unique;
        """
    )
