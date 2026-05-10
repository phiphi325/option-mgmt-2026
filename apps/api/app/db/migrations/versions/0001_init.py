"""initial schema

Revision ID: 0001_init
Revises:
Create Date: 2026-05-10

Applies the full Phase 0 schema for the MSFT Option Risk Management Engine
per plan v1.2 §6, with the v1.2 §22 corrections folded in:

  - §22.6 / C5: users.disclaimer_accepted_at column.
  - §22.2 / C2: flow_scores schema = V1 contract (bullish_score, bearish_score,
    signed score in [-100, 100], pin_probability, gamma_risk, recommended_action,
    explanation; no legacy dealer_gamma_proxy column).
  - §22.14 / M4: outcomes.actual_regime_realized typed as the regime enum.
  - §22.15 / L5: lots.ltcg_eligible_at = opened_at + interval '1 year' + interval '1 day'
    (handles leap years correctly per IRS "more than one year" rule).
  - §22.5: iv_history extended with high/low/close columns required by the
    Wilder ADX trend_strength computation.

market_states.regime is intentionally kept as text (per plan §6 and v1.2 §22 not
specifying a tightening). A follow-up migration can constrain it to the regime
enum once the engine populates it consistently.

The migration is hand-written SQL via op.execute() rather than autogenerate
because it uses Postgres-specific features (uuid, jsonb, generated columns,
custom enums, partial indexes, contract multipliers) that autogenerate handles
poorly. M0.6+ adds SQLAlchemy models and switches future migrations to
autogenerate.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() lives in pgcrypto on Postgres < 13, in core on >= 13.
    # Postgres 16 (docker image) has it in core, but pgcrypto is also fine.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # ---- enum types -------------------------------------------------------
    op.execute(
        """
        CREATE TYPE option_side AS ENUM ('BUY','SELL');
        CREATE TYPE option_kind AS ENUM ('PUT','CALL');
        CREATE TYPE option_status AS ENUM (
            'OPEN','CLOSED','EXPIRED','ASSIGNED','EXERCISED'
        );

        CREATE TYPE event_kind AS ENUM (
            'earnings','fomc','build','launch',
            'opex_monthly','opex_weekly','custom'
        );

        CREATE TYPE outcome_quality AS ENUM ('good','neutral','bad');
        CREATE TYPE outcome_error AS ENUM (
            'early_roll','late_roll','missed_breakout','over_coverage',
            'under_coverage','wrong_strike','ignored_event','none'
        );
        CREATE TYPE outcome_source AS ENUM ('manual','auto');

        -- v1.2 §22.14 M4: regime is a typed enum, used by
        -- outcomes.actual_regime_realized. The 6 named regimes match
        -- packages/engine/engine/regimes.py (M0.6+).
        CREATE TYPE regime AS ENUM (
            'HIGH_IV_EVENT','HIGH_IV_PIN','LOW_IV_TREND','LOW_IV_RANGE',
            'BREAKOUT','POST_EVENT_REPRICE'
        );
        """
    )

    # ---- users & settings (v1.2 §22.6 / C5) -------------------------------
    op.execute(
        """
        CREATE TABLE users (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email         text UNIQUE NOT NULL,
            password_hash text NOT NULL,
            strategy_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
            -- v1.2 §22.6 / C5: gates the first-run disclaimer modal.
            disclaimer_accepted_at timestamptz,
            created_at    timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE settings (
            user_id uuid REFERENCES users(id) ON DELETE CASCADE,
            key     text NOT NULL,
            value   jsonb NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        """
    )

    # ---- positions & lots (v1.2 §22.15 / L5) ------------------------------
    op.execute(
        """
        CREATE TABLE positions (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker     text NOT NULL,
            qty        numeric(18,4) NOT NULL,
            avg_cost   numeric(18,4) NOT NULL,
            opened_at  timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX positions_user_ticker_idx ON positions(user_id, ticker);

        CREATE TABLE lots (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            position_id   uuid NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
            qty           numeric(18,4) NOT NULL,
            cost_basis    numeric(18,4) NOT NULL,
            opened_at     timestamptz NOT NULL,
            -- IRS "more than one year" rule. v1.2 §22.15 L5: handles leap years
            -- correctly; '+ 366 days' would be wrong on leap-year acquisitions.
            ltcg_eligible_at timestamptz GENERATED ALWAYS AS
                (opened_at + interval '1 year' + interval '1 day') STORED
        );
        """
    )

    # ---- option positions -------------------------------------------------
    op.execute(
        """
        CREATE TABLE option_positions (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker        text NOT NULL,
            side          option_side NOT NULL,
            kind          option_kind NOT NULL,
            strike        numeric(18,4) NOT NULL,
            expiry        date NOT NULL,
            qty           integer NOT NULL,
            opened_at     timestamptz NOT NULL,
            opened_price  numeric(18,4) NOT NULL,
            closed_at     timestamptz,
            closed_price  numeric(18,4),
            status        option_status NOT NULL DEFAULT 'OPEN'
        );
        CREATE INDEX option_positions_user_open_idx
            ON option_positions(user_id, status) WHERE status='OPEN';
        """
    )

    # ---- option chain snapshots ------------------------------------------
    op.execute(
        """
        CREATE TABLE option_chain_snapshots (
            id         bigserial PRIMARY KEY,
            ticker     text NOT NULL,
            fetched_at timestamptz NOT NULL,
            expiry     date NOT NULL,
            strike     numeric(18,4) NOT NULL,
            kind       option_kind NOT NULL,
            bid        numeric(18,4),
            ask        numeric(18,4),
            last       numeric(18,4),
            mark       numeric(18,4),
            oi         integer,
            volume     integer,
            iv         numeric(10,6),
            delta      numeric(10,6),
            gamma      numeric(10,6),
            theta      numeric(10,6),
            vega       numeric(10,6),
            source     text NOT NULL
        );
        CREATE INDEX chain_lookup_idx
            ON option_chain_snapshots(ticker, expiry, strike, kind, fetched_at DESC);
        """
    )

    # ---- iv & hv history (v1.2 §22.5: iv_history extended with OHLC) -----
    op.execute(
        """
        CREATE TABLE iv_history (
            ticker         text NOT NULL,
            ts             timestamptz NOT NULL,
            atm_iv_30d     numeric(10,6),
            atm_iv_60d     numeric(10,6),
            iv_rank        numeric(6,3),
            iv_percentile  numeric(6,3),
            -- v1.2 §22.5: OHLC required for Wilder ADX trend_strength
            -- (compute_trend_strength expects high/low/close lists).
            high           numeric(18,4),
            low            numeric(18,4),
            close          numeric(18,4),
            PRIMARY KEY (ticker, ts)
        );

        CREATE TABLE hv_history (
            ticker text NOT NULL,
            ts     timestamptz NOT NULL,
            hv_10  numeric(10,6),
            hv_30  numeric(10,6),
            hv_60  numeric(10,6),
            hv_252 numeric(10,6),
            PRIMARY KEY (ticker, ts)
        );
        """
    )

    # ---- events ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE events (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ticker       text,
            kind         event_kind NOT NULL,
            scheduled_at timestamptz NOT NULL,
            source       text NOT NULL,
            notes        text
        );
        CREATE INDEX events_ticker_when_idx ON events(ticker, scheduled_at);
        """
    )

    # ---- engine outputs --------------------------------------------------
    op.execute(
        """
        CREATE TABLE market_states (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ticker         text NOT NULL,
            computed_at    timestamptz NOT NULL DEFAULT now(),
            -- regime kept as text per plan §6 (v1.2 did not tighten it).
            -- Application layer validates against the 6 enum values.
            regime         text NOT NULL,
            regime_score   numeric(6,3) NOT NULL,
            tags           jsonb NOT NULL DEFAULT '[]'::jsonb,
            inputs         jsonb NOT NULL,
            inputs_hash    text NOT NULL,
            engine_version text NOT NULL
        );
        CREATE INDEX market_states_lookup_idx
            ON market_states(ticker, computed_at DESC);
        """
    )

    # v1.2 §22.2 / C2: flow_scores = V1 contract.
    op.execute(
        """
        CREATE TABLE flow_scores (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ticker          text NOT NULL,
            computed_at     timestamptz NOT NULL DEFAULT now(),
            bullish_score   numeric(6,3) NOT NULL,
            bearish_score   numeric(6,3) NOT NULL,
            score           numeric(8,3) NOT NULL,           -- signed: -100..100
            bias            text NOT NULL,
            pin_probability numeric(6,4) NOT NULL,
            gamma_risk      numeric(6,4) NOT NULL,
            support_oi_wall    numeric(18,4),
            resistance_oi_wall numeric(18,4),
            recommended_action text NOT NULL,
            explanation     text NOT NULL,
            confidence      numeric(6,3) NOT NULL,
            inputs_hash     text NOT NULL,
            engine_version  text NOT NULL
        );
        CREATE INDEX flow_scores_ticker_at_idx
            ON flow_scores(ticker, computed_at DESC);
        """
    )

    op.execute(
        """
        CREATE TABLE strike_candidates (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ticker         text NOT NULL,
            computed_at    timestamptz NOT NULL DEFAULT now(),
            intent         text NOT NULL,
            candidates     jsonb NOT NULL,
            inputs_hash    text NOT NULL,
            engine_version text NOT NULL
        );

        CREATE TABLE recommendations (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker         text NOT NULL,
            computed_at    timestamptz NOT NULL DEFAULT now(),
            strategy       text NOT NULL,
            actions        jsonb NOT NULL,
            coverage_after numeric(6,3),
            rationale      jsonb NOT NULL DEFAULT '[]'::jsonb,
            risks          jsonb NOT NULL DEFAULT '[]'::jsonb,
            inputs_hash    text NOT NULL,
            engine_version text NOT NULL
        );
        """
    )

    # ---- daily_decisions (the audit record) ------------------------------
    op.execute(
        """
        CREATE TABLE daily_decisions (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker        text NOT NULL,
            as_of         timestamptz NOT NULL,
            market_state_id      uuid REFERENCES market_states(id),
            flow_score_id        uuid REFERENCES flow_scores(id),
            strike_candidates_id uuid REFERENCES strike_candidates(id),
            recommendation_id    uuid REFERENCES recommendations(id),
            payload              jsonb NOT NULL,
            confidence           numeric(6,3) NOT NULL,
            confidence_breakdown jsonb NOT NULL,
            execution            jsonb NOT NULL,
            weights_version      text NOT NULL,
            engine_version       text NOT NULL,
            inputs_hash          text NOT NULL
        );
        CREATE INDEX daily_decisions_user_asof_idx
            ON daily_decisions(user_id, ticker, as_of DESC);
        """
    )

    # ---- outcomes (v1.2 §22.14 / M4: actual_regime_realized typed) -------
    op.execute(
        """
        CREATE TABLE outcomes (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            daily_decision_id  uuid NOT NULL UNIQUE
                REFERENCES daily_decisions(id) ON DELETE CASCADE,
            evaluated_at       timestamptz NOT NULL DEFAULT now(),
            horizon_days       integer NOT NULL,
            pnl_realized       numeric(18,4),
            pnl_unrealized     numeric(18,4),
            decision_quality   outcome_quality,
            error_type         outcome_error NOT NULL DEFAULT 'none',
            -- v1.2 §22.14 M4: typed regime enum (was: text in v1.0).
            actual_regime_realized regime,
            regime_match       boolean,
            notes              text,
            source             outcome_source NOT NULL DEFAULT 'manual'
        );
        """
    )

    # ---- scenarios & playbooks (Phase 3) ---------------------------------
    op.execute(
        """
        CREATE TABLE scenarios (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker         text NOT NULL,
            computed_at    timestamptz NOT NULL DEFAULT now(),
            scenario_set   text NOT NULL,
            results        jsonb NOT NULL,
            inputs_hash    text NOT NULL,
            engine_version text NOT NULL
        );

        CREATE TABLE playbooks (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker       text NOT NULL,
            period_start date NOT NULL,
            period_end   date NOT NULL,
            payload      jsonb NOT NULL
        );
        """
    )

    # ---- audit log -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE audit_log (
            id      bigserial PRIMARY KEY,
            user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            action  text NOT NULL,
            payload jsonb,
            ts      timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    # Drop tables in reverse foreign-key dependency order, then enum types.
    op.execute(
        """
        DROP TABLE IF EXISTS audit_log;
        DROP TABLE IF EXISTS playbooks;
        DROP TABLE IF EXISTS scenarios;
        DROP TABLE IF EXISTS outcomes;
        DROP TABLE IF EXISTS daily_decisions;
        DROP TABLE IF EXISTS recommendations;
        DROP TABLE IF EXISTS strike_candidates;
        DROP TABLE IF EXISTS flow_scores;
        DROP TABLE IF EXISTS market_states;
        DROP TABLE IF EXISTS events;
        DROP TABLE IF EXISTS hv_history;
        DROP TABLE IF EXISTS iv_history;
        DROP TABLE IF EXISTS option_chain_snapshots;
        DROP TABLE IF EXISTS option_positions;
        DROP TABLE IF EXISTS lots;
        DROP TABLE IF EXISTS positions;
        DROP TABLE IF EXISTS settings;
        DROP TABLE IF EXISTS users;

        DROP TYPE IF EXISTS regime;
        DROP TYPE IF EXISTS outcome_source;
        DROP TYPE IF EXISTS outcome_error;
        DROP TYPE IF EXISTS outcome_quality;
        DROP TYPE IF EXISTS event_kind;
        DROP TYPE IF EXISTS option_status;
        DROP TYPE IF EXISTS option_kind;
        DROP TYPE IF EXISTS option_side;
        """
    )
