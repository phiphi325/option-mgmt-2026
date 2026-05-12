# MSFT Option Risk Management Engine — Phased Development Plan

Implementation-ready engine-first development plan for the MSFT long-equity + options-overlay decision system. 20 sections; Claude Code-ready.

## 0. Document Metadata

**Version**: 1.2 (audit corrections, 2026-05-09)
**Date**: 2026-04-29 (v1.0/v1.1) · 2026-05-09 (v1.2)
**Status**: **Approved for implementation. All blockers resolved.**
**Locked decisions**: Next.js **`16.2.6`** (verified directly against npm registry 2026-05-09; auditor's "16.2.4 doesn't exist" claim was wrong — see §22.1) · engine-first product framing · 6-regime taxonomy · formal Confidence Composer (multiplicative penalties, v2.0) · Execution Feasibility Module · User Strategy Profile · Outcome learning loop · Collar Builder as first-class engine · 5 standalone scoring functions (iv/structure/gamma/event/flow) · Phase 1 hard contract
**Phase 1 duration**: 5 weeks (engine MVP + Today screen + Collar Builder + scoring module). Day count: 35.
**Audience**: Claude Code or a senior full-stack engineer implementing the MVP step-by-step. **Read §22 before §1.**

The plan does NOT predict price direction. It manages payoff structure for a long-term MSFT holder using a deterministic decision engine, with explicit ML upgrade paths in Phase 4.

### Reading order

1. §22 (Patch v1.2 — Audit Corrections) — read first; supersedes earlier sections where they conflict.
2. §0 → §21 — original spec.
3. Implementers must reconcile mentally: §22 wins on every conflict.

### Version history

- **v1.0** (2026-04-29) — initial 20-section plan.
- **v1.1** (2026-04-29) — sanity-check patch: Collar Builder as first-class engine, 5 standalone scoring functions, system endpoints (`/health`, `/engine/collar-builder`, `/market/{ticker}/latest`), legacy API mapping, Flow Score V1 contract, Phase 1 hard contract, monorepo simplification.
- **v1.2** (2026-05-09) — external audit corrections: 25 of 25 issues resolved. Critical fixes: FlowScore DB schema reconciled, classify() signature extended, ChainSnapshot/infer_intent/trend_strength/breakout_signal/expected_slippage/size_warnings specified, disclaimer_accepted_at column added. High fixes: docker-compose simplified, all 8 rules.yaml entries written, max pain formula spelled out, MarketLatestSnapshot data source specified, underlying_qty resolved at service layer, IV history validation policy. Confidence Composer redesigned with multiplicative penalties (true [0,1] range). Next.js version verified: **16.2.6** (the auditor's C1 claim that 16.2.4 doesn't exist was incorrect — registry confirms 16.x is the stable line since 2025-10-22).

## 1. Product Brief

## Vision

A decision engine that answers a single question every day for a long-term MSFT holder: **"What should I do today?"** The user has ~5,000 shares around a $400 cost basis, a 12-month minimum hold, and wants to be a friend of time without losing sleep over volatility.

## Core concept

Given current spot, position, option positions, IV/HV, max pain, expected move, events, and a User Strategy Profile, produce a single unified `DailyDecision`:

- a regime label from a controlled set
- a recommended strategy from a regime-specific whitelist
- ranked actions with per-leg execution feasibility
- a confidence score that is **formally composed and decomposable**
- watch levels, rationale, risks, and invalidation criteria
- an outcome slot the user (later: an auto-fill heuristic, later still: ML) closes the loop on

Everything else in the app is drill-down for *why*, not the answer to *what*.

## Value proposition

- Reduces fear of volatility for long-term holders by giving structured, auditable guidance.
- Encodes the philosophy: **long equity + short volatility + tail hedge**.
- Makes options-overlay decisions explainable, version-stamped, and improvable over time.
- Cleanly separates the core long-term position from the tactical option overlay.
- Supports partial coverage, gamma-aware execution, event-driven risk, and dynamic collars.
- Optimizes for risk-adjusted return, not maximum upside.

## Non-goals

- No automated order execution (ever, in this codebase).
- No personalized financial advice — everything is educational, with disclaimers gating first run and persistent in the footer.
- No price-direction prediction. The product manages payoff structure.
- No Bloomberg-clone analytics dashboard. Drill-downs exist to explain decisions, not to be the product.
- No dark-pattern "buy now" or "sell now" CTAs.

## Design principles

1. **One screen, one question, one answer.** The Today screen renders one `DailyDecision`.
2. **Every recommendation is auditable and decomposable.** `confidence_breakdown`, `inputs_hash`, `weights_version`, `engine_version` on every row.
3. **Engines first, dashboards second.** API namespaces (`/engine/*` primary, `/data/*` secondary) and Phase 1 scope reflect this.
4. **Deterministic V1; ML upgrades replace specific nodes** without changing engine interfaces. The V1 deterministic node serves as the baseline for backtesting ML upgrades.
5. **Educational disclaimers always visible.** First-run gate + persistent footer + injection into the `DailyDecision` payload.
6. **No dark patterns.** No urgency cues, no countdown timers, no FOMO.

## 2. User Personas

## Primary — Helen, 47, senior engineer

5,000 MSFT shares, cost basis ~$400, 12-month+ horizon. Has sold covered calls casually, gets nervous around earnings and FOMC. Works full-time; checks the app once a day, twice on event days. Wants **structured guidance**, not a charting tool.

```jsonc
"strategy_profile": {
  "style": "balanced",
  "max_coverage": 0.60,
  "roll_aggressiveness": "medium",
  "drawdown_tolerance": 0.15,
  "tax_sensitivity": "ltcg_aware",
  "iv_rank_sell_threshold": 50,
  "delta_target_band": [0.15, 0.30],
  "dte_band_days": [21, 60]
}
```

## Secondary — Ravi, 31, early-career investor

200 MSFT shares. Wants to learn options without endangering the position. Reads Tastytrade. Wants the app to *teach the philosophy* alongside the actions — rationale and risks panels matter to him as much as the action.

```jsonc
"strategy_profile": {
  "style": "growth",
  "max_coverage": 0.30,
  "roll_aggressiveness": "low",
  "drawdown_tolerance": 0.20,
  "tax_sensitivity": "none",
  "iv_rank_sell_threshold": 60,
  "delta_target_band": [0.10, 0.20],
  "dte_band_days": [30, 60]
}
```

## Tertiary — Diana, 52, RIA

Manages client portfolios. Treats the app as a **sounding board**, not a source of truth. Cares deeply about audit trail, decomposability, and the ability to share `confidence_breakdown` and `rationale` with clients.

```jsonc
"strategy_profile": {
  "style": "income",
  "max_coverage": 0.80,
  "roll_aggressiveness": "high",
  "drawdown_tolerance": 0.10,
  "tax_sensitivity": "wash_sale_aware",
  "iv_rank_sell_threshold": 40,
  "delta_target_band": [0.20, 0.35],
  "dte_band_days": [14, 45]
}
```

## Persona implications

- **Helen drives MVP.** Today screen, regime guidance, execution feasibility annotations.
- **Ravi drives the rationale UI.** Drawer for rationale, risks, invalidation; teach-as-you-decide microcopy.
- **Diana drives audit and sharing.** Every decision exportable as JSON; Phase 3 playbook as PDF.

## 3. MVP Scope

## In scope (Phase 1 MVP)

**Engines**
- Market State Engine
- Flow Score Engine
- Strike Selector
- Recommendation Engine
- Master Decision Engine

**Cross-cutting**
- Confidence Composer (formal weighted composition)
- Execution Feasibility Module
- User Strategy Profile (full schema, settings UI)
- Outcome Tracker (schema + manual entry; auto-fill is Phase 3)

**Locked taxonomy**
- 6 regimes: `HIGH_IV_EVENT`, `HIGH_IV_PIN`, `LOW_IV_TREND`, `LOW_IV_RANGE`, `BREAKOUT`, `POST_EVENT_REPRICE`

**API (`/engine/*` primary)**
- `POST /engine/daily-plan`
- `POST /engine/recommend`
- `POST /engine/what-if`
- `POST /engine/market-state`
- `POST /engine/flow-score`
- `POST /engine/strike-candidates`
- `POST /engine/execution-check`
- `GET/PUT /profile`
- `GET/POST/PATCH /outcomes`
- `POST /data/positions/import-csv`, `POST /data/chain/import-csv`, `POST /data/iv/import-csv`, `POST /data/events/import-csv`
- `POST /auth/login`, `POST /auth/register`

**UI**
- Today screen (single `DailyDecision` card with all sub-components)
- Settings screen (User Strategy Profile form)
- Outcomes screen (manual entry + history)
- Disclaimer gate (first-run modal + persistent footer)

**Data**
- Manual CSV ingestion for positions, option chain, IV history, events
- Local-first deployment via `docker compose up`
- Single-user with auth-ready architecture (NextAuth + JWT)

## Out of scope (Phase 2+)

- Live data integration (yfinance, Tradier, Polygon)
- Drill-down dashboards (Chain, IV Profile, Max Pain, Expected Move, Payoff)
- 12-month playbook generator
- Decision-based scenario simulator UI (the engine module exists; the screen is Phase 3)
- Brokerage integration
- ML/AI engine nodes
- Multi-ticker UI
- Mobile app
- Auto-fill outcome heuristics
- Tax-aware roll *enforcement* (`tax_sensitivity` field is in the profile, but engine logic is Phase 3+)
- Watch-level alerting (email / push)

## Success criteria

1. User uploads a CSV of positions, chain, and events → receives a full `DailyDecision` in **< 5 seconds**.
2. Every `confidence` value is decomposable into named components in `confidence_breakdown`.
3. Every recommended action carries an execution feasibility annotation (`liquidity_score`, `fill_confidence`, `spread_bps`, `suggested_order_type`).
4. `DailyDecision` changes coherently when User Strategy Profile changes (e.g. switching `style: income → growth` shifts strategy whitelist and delta target band).
5. Regime classification matches the expected regime on a fixed set of **24 historical fixtures** (≥ 80% accuracy required for CI green).
6. `engine_version`, `weights_version`, and `inputs_hash` are recorded on every `daily_decisions` row for audit and replay.
7. Disclaimer is shown on first run and gates the Today screen until acknowledged.
8. Manual outcome entry works; `outcomes` rows accumulate 1:1 with `daily_decisions`.

---

## Phase 1 Hard Contract (locked, anti-creep guard)

The list below is the **complete** Phase 1 scope. Anything not on this list is out-of-MVP, period. Build creep guard: every PR opened during Phase 1 must answer **"does this advance the Today screen rendering a coherent DailyDecision?"** If the answer is no, the PR is rejected.

**Engines (5)**: Market State, Flow Score, Strike Selector, Recommendation, Master Decision
**Specialty engine (1, added v1.1)**: Collar Builder
**Cross-cutting (4)**: Confidence Composer, Execution Feasibility, User Strategy Profile, Outcome Tracker
**Scoring functions (5, individually testable, added v1.1)**: `iv_score`, `structure_score`, `gamma_score`, `event_score`, `flow_score`

**APIs (Phase 1, complete list)**:
- `/engine/daily-plan`, `/engine/recommend`, `/engine/what-if`
- `/engine/market-state`, `/engine/flow-score`, `/engine/strike-candidates`
- `/engine/execution-check`, `/engine/collar-builder`
- `/profile` (GET, PUT)
- `/outcomes` (GET, POST, PATCH)
- `/data/{positions,option-positions,chain,iv,events}/import-csv`
- `/market/msft/latest`
- `/auth/{login,register}`
- `/health`, `/healthz` (alias), `/version`

**UI (Phase 1, complete list)**:
- Today screen (single DailyDecision card)
- Settings screen (UserStrategyProfileForm + persona presets)
- Outcomes screen (manual entry + history)
- Disclaimer gate (first-run modal + persistent footer)
- Auth pages (login, register)

**Data (Phase 1)**: manual CSV ingestion only.

### Explicitly OUT of Phase 1

- Chain table screen
- IV Profile / Term Structure screen
- Max Pain screen
- Expected Move screen
- Payoff Diagram screen
- Event Calendar screen
- Scenario Simulator UI (engine module exists; UI is Phase 3)
- Playbook screen
- Live data providers (yfinance, Tradier, Polygon)
- Cron-scheduled ingestion jobs (manual CSV only)
- Watch-level alerting
- ML/AI engine nodes
- LLM narration
- Brokerage integration
- Multi-ticker UI
- Mobile app
- Auto-fill outcome heuristics
- Tax-aware roll *enforcement* (schema field present; engine logic Phase 3+)

## 4. Phase 0 → Phase 4 Roadmap

## Phase 0 — Foundation (1 week)

**Goal**: Repo, infra, schema, design primitives. No engines yet.

**Deliverables**
- pnpm + uv monorepo bootstrapped
- `docker-compose.yml` with `web`, `api`, `jobs`, `postgres`, `redis`
- Alembic migrations for the **full** schema (every table from §6, even if unused in P0)
- GitHub Actions CI: lint (ruff, eslint), typecheck (mypy, tsc), unit tests, integration tests
- Next.js `16.2.4` app shell with shadcn/ui + Tailwind; `/today` route placeholder
- FastAPI app shell with `/healthz`, `/version`, JWT auth scaffolding
- Disclaimer gate component (first-run modal, persistent footer)
- `packages/engine/regimes.py` enum (the 6 regimes), `packages/engine/profiles.py` types
- TS types generated from Pydantic via `datamodel-code-generator`

**Exit criteria**
- `docker compose up` works end-to-end
- CI green
- `/healthz` and `/version` respond
- `pnpm typecheck` and `uv run pytest` pass with placeholder content

## Phase 1 — Engine MVP (4 weeks)

**Goal**: All 5 engines + 4 cross-cutting modules + Today screen rendering a full `DailyDecision`.

**Weekly cadence**
- **Week 1** — Market State Engine: IV rank/percentile, max pain, expected move, PCR, regime classification, 24 fixtures
- **Week 2** — Flow Score Engine + Strike Selector + payoff math (BS, Greeks, IV solver)
- **Week 3** — Recommendation Engine + Master Decision Engine + Confidence Composer + Execution Feasibility Module
- **Week 4** — Today screen + DailyDecision rendering + Profile UI + Outcome manual entry + golden tests + E2E

**API delivered**: all `/engine/*` + `/profile` + `/outcomes` + CSV upload endpoints.

**UI delivered**: Today, Settings, Outcomes, Disclaimer gate.

**Exit criteria**
- End-to-end DailyDecision generation from a CSV upload, in **< 5s**
- All engines unit-tested; ≥ 80% line coverage on `packages/engine`
- 24 regime fixtures pass with ≥ 80% accuracy
- Today screen renders confidence breakdown bar, execution badges, watch levels, rationale, risks, invalidation
- Profile change re-renders Today screen with coherent shifts
- Manual outcome entry persists and round-trips
- Playwright E2E green on the disclaimer-gate → CSV-upload → Today flow

## Phase 2 — Data & Drill-downs (2–3 weeks)

**Goal**: Replace manual CSV with live data; add drill-down screens for explainability.

**Deliverables**
- `MarketDataProvider` interface
- `YfinanceProvider` (spot, HV, basic chain)
- `TradierProvider` (chain with bid/ask/OI/volume/IV/Greeks)
- IV history backfill job (252 trading days)
- Cron-scheduled ingestion: chain every 30 min during market hours, IV/HV daily 16:30 ET, events daily 17:00 ET
- Drill-down screens: Chain table, IV Profile / Term Structure, Max Pain, Expected Move, Payoff Diagram, Event Calendar
- Settings UI for User Strategy Profile (full editor)
- Staleness flags: `data_freshness` JSONB on every `DailyDecision`, surfaced as UI badges

**Exit criteria**
- App runs without manual CSV upload (CSV remains as fallback)
- Drill-downs accessible from Today via in-card links
- Data freshness shown on every decision
- Provider abstraction passes integration tests against recorded responses

## Phase 3 — Decision Simulator + Playbook + Outcome Auto-fill (3 weeks)

**Goal**: What-if planning, structured 12-month plan, self-improving feedback loop.

**Deliverables**
- Decision-based scenario simulator (6 named scenarios; each emits action + reason + execution)
- `/sim` screen rendering scenario table + per-scenario action card
- 12-month playbook generator with monthly + quarterly review cadence; `/playbook` screen
- Outcome auto-fill heuristics: PnL from positions, error_type from spot/IV trajectory, regime_match from realized regime classifier replay
- Watch-level alerting (email + in-app)
- Partial coverage modeling refinement
- Gamma-aware execution hints (proximity-to-short-strike risk in `risks[]`)
- Tax-aware roll logic enforcement (LTCG holding period, wash-sale buffer)

**Exit criteria**
- Scenario sim live; every scenario carries an action
- Playbook live; user can export to PDF
- Outcomes auto-fill within 30 days of decision
- Alerts firing on watch-level breaches

## Phase 4 — ML/AI + Brokerage (open-ended)

**Goal**: Replace deterministic engine nodes with learned nodes; integrate brokerage read-only.

**Deliverables**
- HMM or transformer regime classifier trained on stored `(state, decision, outcome)` triples
- Confidence weight recalibration via outcome quality (CMA-ES or similar)
- LLM-narrated `DailyDecision` (rationale paragraphs, friendly explanations, persona-tuned)
- Anomaly detection on chain skew (isolation forest)
- Vol-surface fitting (SVI parameterization)
- IBKR read-only integration (positions sync, market data)
- Multi-ticker UI
- Mobile-responsive Today screen

**Exit criteria**
- ML regime classifier outperforms deterministic V1 on backtest (held-out fixtures)
- LLM narration A/B tested against template rationale; user prefers ≥ 60%
- IBKR positions sync without manual CSV
- All ML nodes shippable with feature flag (deterministic fallback always available)

## 5. System Architecture

## Layer cake (top = primary surface; bottom = supporting)

```
+-----------------------------------------------------------+
|  TODAY SCREEN  (single DailyDecision card)                |
|  primary UI surface                                        |
+-----------------------------------------------------------+
|  /engine/* Decision API   |   /data/* Data API (drill-down)|
+-----------------------------------------------------------+
|  CORE ENGINES  (the product)                              |
|   1. Market State Engine    -> regime + scoring vector    |
|   2. Flow Score Engine      -> directional bias           |
|   3. Strike Selector        -> ranked candidates          |
|   4. Recommendation Engine  -> structured action          |
|   5. Master Decision Engine -> unified DailyDecision      |
+-----------------------------------------------------------+
|  CROSS-CUTTING MODULES                                    |
|   A. User Strategy Profile  <- settings                   |
|   B. Confidence Composer    -> formal scoring             |
|   C. Execution Feasibility  -> liquidity / slippage       |
|   D. Outcome Tracker        -> learning loop (P3+)        |
+-----------------------------------------------------------+
|  Data ingestion + provider abstraction                    |
|  Postgres  |  Redis (cache, optional in MVP)              |
+-----------------------------------------------------------+
```

## Component map

| Component | Tech | Role |
|---|---|---|
| `apps/web` | Next.js 16.2.4, TypeScript, Tailwind, shadcn/ui, Recharts/visx | Today + drill-down screens, settings, outcomes |
| `apps/api` | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | REST API; calls into `packages/engine` |
| `apps/jobs` | Python (Arq or APScheduler) | Scheduled ingestion + outcome auto-fill (P3+) |
| `packages/engine` | Pure Python (numpy, scipy, pandas, py_vollib) | The product. Pure functions. No I/O. |
| `packages/shared-types` | TypeScript types generated from Pydantic | Wire-format type safety end-to-end |
| Postgres | Neon (managed) or local Docker | Source of truth |
| Redis | Optional in MVP | Cache engine outputs (5-min TTL on `daily-plan`) |

## Data flow (request lifecycle)

1. **Ingestion** — cron job (`apps/jobs`) calls `MarketDataProvider.get_chain()` etc. and writes snapshots to Postgres. In MVP this is replaced by user CSV upload.
2. **User opens `/today`** — Next.js server component calls `POST /engine/daily-plan { ticker: "MSFT" }`.
3. **API loads inputs** — most-recent rows from `positions`, `option_positions`, `option_chain_snapshots`, `iv_history`, `events`, `users.strategy_profile`.
4. **API calls `engine.decision.produce_daily_decision(...)`**, which orchestrates:
   - `engine.market_state.classify(...)` -> `MarketState`
   - `engine.flow_score.compute(...)` -> `FlowScore`
   - `engine.strike_selector.select(...)` -> `StrikeCandidates`
   - `engine.recommendation.recommend(...)` -> `Recommendation`
   - `engine.confidence.compose(...)` -> `ConfidenceBreakdown`
   - `engine.execution.assess(...)` -> `Execution`
5. **API persists** the full `DailyDecision` payload to `daily_decisions` with `inputs_hash`, `engine_version`, `weights_version`. Returns the payload.
6. **Today screen renders** the `DailyDecision`. Drill-down links route to `/chain`, `/iv`, etc. (Phase 2).
7. **Later**, the user (Phase 1) or an auto-fill heuristic (Phase 3) writes a row to `outcomes` linked to `daily_decision_id`. Phase 4 ML consumes `(state, decision, outcome)` triples.

## Versioning rules

- **`engine_version`** (semver, e.g. `0.1.0`) is bumped on any change to engine module logic.
- **`weights_version`** (e.g. `v1.0`) is bumped on any change to `packages/engine/config/weights.yaml`.
- **`inputs_hash`** is a SHA-256 over the canonical JSON of all inputs (positions, chain, IV, events, profile snapshot at decision time). Enables exact replay.

## Caching

- MVP: no cache; recompute on every request (sub-5s on a single user).
- Phase 2: Redis cache keyed on `(user_id, ticker, inputs_hash)` with 5-min TTL.
- All caches are invalidated on profile mutation, position mutation, weights change, or engine version bump.

## 6. Database Schema

All money columns are `numeric(18,4)`. All timestamps are `timestamptz`. JSONB used for flexible payloads. Every engine output table carries `inputs_hash` for replay and `engine_version` for audit.

```sql
-- Users & profile
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  strategy_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE settings (
  user_id uuid REFERENCES users(id) ON DELETE CASCADE,
  key     text NOT NULL,
  value   jsonb NOT NULL,
  PRIMARY KEY (user_id, key)
);

-- Equity positions & lots
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
  ltcg_eligible_at timestamptz GENERATED ALWAYS AS (opened_at + interval '366 days') STORED
);

-- Option positions
CREATE TYPE option_side AS ENUM ('BUY','SELL');
CREATE TYPE option_kind AS ENUM ('PUT','CALL');
CREATE TYPE option_status AS ENUM ('OPEN','CLOSED','EXPIRED','ASSIGNED','EXERCISED');

CREATE TABLE option_positions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ticker        text NOT NULL,
  side          option_side NOT NULL,
  kind          option_kind NOT NULL,
  strike        numeric(18,4) NOT NULL,
  expiry        date NOT NULL,
  qty           integer NOT NULL,                     -- contracts (1 = 100 shares)
  opened_at     timestamptz NOT NULL,
  opened_price  numeric(18,4) NOT NULL,
  closed_at     timestamptz,
  closed_price  numeric(18,4),
  status        option_status NOT NULL DEFAULT 'OPEN'
);
CREATE INDEX option_positions_user_open_idx ON option_positions(user_id, status) WHERE status='OPEN';

-- Option chain snapshots
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
  source     text NOT NULL                            -- 'csv','yfinance','tradier',...
);
CREATE INDEX chain_lookup_idx
  ON option_chain_snapshots(ticker, expiry, strike, kind, fetched_at DESC);

-- IV / HV history
CREATE TABLE iv_history (
  ticker      text NOT NULL,
  ts          timestamptz NOT NULL,
  atm_iv_30d  numeric(10,6),
  atm_iv_60d  numeric(10,6),
  iv_rank     numeric(6,3),                           -- 0..100
  iv_percentile numeric(6,3),                         -- 0..100
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

-- Events
CREATE TYPE event_kind AS ENUM ('earnings','fomc','build','launch','opex_monthly','opex_weekly','custom');
CREATE TABLE events (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker       text,                                  -- nullable for macro events
  kind         event_kind NOT NULL,
  scheduled_at timestamptz NOT NULL,
  source       text NOT NULL,                         -- 'manual','yahoo','fred',...
  notes        text
);
CREATE INDEX events_ticker_when_idx ON events(ticker, scheduled_at);

-- Engine outputs
CREATE TABLE market_states (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker        text NOT NULL,
  computed_at   timestamptz NOT NULL DEFAULT now(),
  regime        text NOT NULL,                        -- one of the 6 regime enum values
  regime_score  numeric(6,3) NOT NULL,
  tags          jsonb NOT NULL DEFAULT '[]'::jsonb,
  inputs        jsonb NOT NULL,                       -- full input snapshot
  inputs_hash   text NOT NULL,
  engine_version text NOT NULL
);
CREATE INDEX market_states_lookup_idx ON market_states(ticker, computed_at DESC);

CREATE TABLE flow_scores (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker        text NOT NULL,
  computed_at   timestamptz NOT NULL DEFAULT now(),
  score         numeric(6,3) NOT NULL,                -- 0..100
  bias          text NOT NULL,                        -- 'bearish','neutral_bearish','neutral','neutral_bullish','bullish'
  confidence    numeric(6,3) NOT NULL,
  support_oi_wall    numeric(18,4),
  resistance_oi_wall numeric(18,4),
  dealer_gamma_proxy text,
  inputs_hash   text NOT NULL,
  engine_version text NOT NULL
);

CREATE TABLE strike_candidates (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker        text NOT NULL,
  computed_at   timestamptz NOT NULL DEFAULT now(),
  intent        text NOT NULL,                        -- 'sell_call','buy_put','collar','sell_put'
  candidates    jsonb NOT NULL,                       -- ordered ranked list
  inputs_hash   text NOT NULL,
  engine_version text NOT NULL
);

CREATE TABLE recommendations (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ticker        text NOT NULL,
  computed_at   timestamptz NOT NULL DEFAULT now(),
  strategy      text NOT NULL,
  actions       jsonb NOT NULL,
  coverage_after numeric(6,3),
  rationale     jsonb NOT NULL DEFAULT '[]'::jsonb,
  risks         jsonb NOT NULL DEFAULT '[]'::jsonb,
  inputs_hash   text NOT NULL,
  engine_version text NOT NULL
);

-- The unified output (the audit record)
CREATE TABLE daily_decisions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ticker        text NOT NULL,
  as_of         timestamptz NOT NULL,
  market_state_id      uuid REFERENCES market_states(id),
  flow_score_id        uuid REFERENCES flow_scores(id),
  strike_candidates_id uuid REFERENCES strike_candidates(id),
  recommendation_id    uuid REFERENCES recommendations(id),
  payload             jsonb NOT NULL,                 -- the full DailyDecision JSON
  confidence          numeric(6,3) NOT NULL,
  confidence_breakdown jsonb NOT NULL,
  execution           jsonb NOT NULL,
  weights_version     text NOT NULL,
  engine_version      text NOT NULL,
  inputs_hash         text NOT NULL
);
CREATE INDEX daily_decisions_user_asof_idx ON daily_decisions(user_id, ticker, as_of DESC);

-- Outcomes (learning loop)
CREATE TYPE outcome_quality AS ENUM ('good','neutral','bad');
CREATE TYPE outcome_error AS ENUM (
  'early_roll','late_roll','missed_breakout','over_coverage',
  'under_coverage','wrong_strike','ignored_event','none'
);
CREATE TYPE outcome_source AS ENUM ('manual','auto');

CREATE TABLE outcomes (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  daily_decision_id  uuid NOT NULL UNIQUE REFERENCES daily_decisions(id) ON DELETE CASCADE,
  evaluated_at       timestamptz NOT NULL DEFAULT now(),
  horizon_days       integer NOT NULL,
  pnl_realized       numeric(18,4),
  pnl_unrealized     numeric(18,4),
  decision_quality   outcome_quality,
  error_type         outcome_error NOT NULL DEFAULT 'none',
  actual_regime_realized text,
  regime_match       boolean,
  notes              text,
  source             outcome_source NOT NULL DEFAULT 'manual'
);

-- Scenarios & playbooks (P3)
CREATE TABLE scenarios (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ticker       text NOT NULL,
  computed_at  timestamptz NOT NULL DEFAULT now(),
  scenario_set text NOT NULL,
  results      jsonb NOT NULL,
  inputs_hash  text NOT NULL,
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

-- Audit
CREATE TABLE audit_log (
  id      bigserial PRIMARY KEY,
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  action  text NOT NULL,
  payload jsonb,
  ts      timestamptz NOT NULL DEFAULT now()
);
```

## Schema notes

- **Why store full `inputs` snapshot on `market_states`**: enables full replay even if upstream chain rows are pruned later.
- **Why `daily_decisions.payload` is JSONB**: the wire format evolves more frequently than the column shape, and we want to render directly from the row without joins.
- **Why `outcomes` is 1:1 with `daily_decisions` via UNIQUE**: prevents duplicate outcomes per decision; auto-fill in P3 uses `INSERT ... ON CONFLICT DO UPDATE`.
- **`option_chain_snapshots` is wide and frequently inserted**: partition by month in P2 if row count exceeds 100M.

## 7. API Endpoint Design

All endpoints under `/api/v1/*`. JSON only. JWT auth via `Authorization: Bearer ...`. Errors follow RFC 7807.

## `/engine/*` — primary

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/engine/daily-plan` | `DailyPlanRequest` | `DailyDecision` |
| POST | `/engine/recommend` | `RecommendRequest` | `Recommendation` |
| POST | `/engine/what-if` | `WhatIfRequest` | `DailyDecision` |
| POST | `/engine/market-state` | `MarketStateRequest` | `MarketState` |
| POST | `/engine/flow-score` | `FlowScoreRequest` | `FlowScore` |
| POST | `/engine/strike-candidates` | `StrikeCandidatesRequest` | `StrikeCandidates` |
| POST | `/engine/execution-check` | `ExecutionCheckRequest` | `Execution` |

## `/profile`, `/outcomes`, `/data/*`, `/auth/*`

| Method | Path | Description |
|---|---|---|
| GET | `/profile` | Get current user's `UserStrategyProfile` |
| PUT | `/profile` | Replace `UserStrategyProfile` |
| GET | `/outcomes?since=` | List outcomes (paginated) |
| POST | `/outcomes` | Create outcome (manual entry) |
| PATCH | `/outcomes/:id` | Update outcome |
| GET | `/data/positions` | List positions |
| POST | `/data/positions/import-csv` | multipart CSV upload |
| POST | `/data/option-positions/import-csv` | multipart CSV upload |
| POST | `/data/chain/import-csv` | multipart CSV upload |
| POST | `/data/iv/import-csv` | multipart CSV upload |
| POST | `/data/events/import-csv` | multipart CSV upload |
| GET | `/data/chain?ticker=&expiry=` | (P2) latest chain snapshot |
| GET | `/data/iv?ticker=&from=&to=` | (P2) IV history range |
| GET | `/data/events?ticker=&from=&to=` | events list |
| POST | `/data/events` | manual event |
| POST | `/auth/register` | new user |
| POST | `/auth/login` | returns JWT |

## Pydantic schemas (canonical)

```python
# packages/shared-types -> generated TS mirror
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

class Regime(str, Enum):
    HIGH_IV_EVENT       = "HIGH_IV_EVENT"
    HIGH_IV_PIN         = "HIGH_IV_PIN"
    LOW_IV_TREND        = "LOW_IV_TREND"
    LOW_IV_RANGE        = "LOW_IV_RANGE"
    BREAKOUT            = "BREAKOUT"
    POST_EVENT_REPRICE  = "POST_EVENT_REPRICE"

class Style(str, Enum):
    INCOME = "income"
    GROWTH = "growth"
    BALANCED = "balanced"

class UserStrategyProfile(BaseModel):
    style: Style = Style.BALANCED
    max_coverage: float = Field(0.6, ge=0, le=1)
    roll_aggressiveness: Literal["low","medium","high"] = "medium"
    drawdown_tolerance: float = Field(0.15, ge=0, le=1)
    tax_sensitivity: Literal["none","ltcg_aware","wash_sale_aware"] = "none"
    iv_rank_sell_threshold: float = Field(50, ge=0, le=100)
    delta_target_band: tuple[float, float] = (0.15, 0.30)
    dte_band_days: tuple[int, int] = (21, 60)

class MarketState(BaseModel):
    regime: Regime
    regime_score: float
    tags: list[str] = []
    iv_rank: float
    iv_percentile: float
    hv_30: float
    expected_move_pct: float
    max_pain: Decimal
    max_pain_delta_pct: float
    pcr_volume: float
    pcr_oi: float
    next_event: dict | None
    inputs_hash: str
    engine_version: str

class FlowScore(BaseModel):
    score: float = Field(..., ge=0, le=100)
    bias: Literal["bearish","neutral_bearish","neutral","neutral_bullish","bullish"]
    confidence: float = Field(..., ge=0, le=1)
    support_oi_wall: Decimal | None
    resistance_oi_wall: Decimal | None
    dealer_gamma_proxy: str | None

class StrikeCandidate(BaseModel):
    expiry: date
    strike: Decimal
    kind: Literal["PUT","CALL"]
    delta: float
    iv: float
    bid: Decimal
    ask: Decimal
    mid: Decimal
    oi: int
    volume: int
    distance_from_spot_pct: float
    rationale: str
    rank: int

class StrikeCandidates(BaseModel):
    intent: Literal["sell_call","buy_put","collar","sell_put"]
    candidates: list[StrikeCandidate]

class ExecutionLeg(BaseModel):
    leg_id: str
    liquidity_score: float
    spread_bps: int
    fill_confidence: float
    expected_slippage: Decimal
    suggested_order_type: Literal["limit","marketable_limit"]
    limit_price_band: tuple[Decimal, Decimal]
    size_warnings: list[str] = []

class Execution(BaseModel):
    aggregate_liquidity_score: float
    aggregate_fill_confidence: float
    suggested_order_type: Literal["limit","marketable_limit"]
    legs: list[ExecutionLeg]
    notes: list[str] = []

class ConfidenceBreakdown(BaseModel):
    flow_alignment: float
    structure_alignment: float
    regime_match: float
    signal_alignment: float
    event_risk_penalty: float
    illiquidity_penalty: float
    weights_version: str

class Action(BaseModel):
    step: int
    verb: Literal["BUY_TO_OPEN","SELL_TO_OPEN","BUY_TO_CLOSE","SELL_TO_CLOSE","NO_OP"]
    leg: str            # e.g. "short_call_415_2026-05-16"
    qty: int
    delta_target: float | None = None
    limit_price_band: tuple[Decimal, Decimal] | None = None

class DailyDecision(BaseModel):
    decision_id: str
    as_of: datetime
    ticker: str
    spot: Decimal
    user_profile_snapshot: UserStrategyProfile
    market_state: MarketState
    flow_score: FlowScore
    recommended_strategy: str
    actions: list[Action]
    coverage_after: float
    confidence: float
    confidence_breakdown: ConfidenceBreakdown
    execution: Execution
    rationale: list[str]
    risks: list[str]
    watch_levels: dict
    next_trigger: str
    invalidation: list[str]
    weights_version: str
    engine_version: str
    inputs_hash: str
    data_freshness: dict           # {"spot_age_seconds":..., "chain_age_seconds":..., ...}
    outcome: dict | None = None    # filled later
    disclaimers: list[str]

# Requests
class DailyPlanRequest(BaseModel):
    ticker: str = "MSFT"
    as_of: datetime | None = None    # default: now
    use_cache: bool = True

class WhatIfRequest(BaseModel):
    ticker: str
    overrides: dict                  # e.g. {"spot": 425.00, "iv_rank": 35}
class RecommendRequest(BaseModel):
    ticker: str
    market_state: MarketState | None = None
    flow_score: FlowScore | None = None
class StrikeCandidatesRequest(BaseModel):
    ticker: str
    intent: Literal["sell_call","buy_put","collar","sell_put"]
    delta_band: tuple[float, float] | None = None    # defaults to profile
    dte_band_days: tuple[int, int] | None = None
class ExecutionCheckRequest(BaseModel):
    actions: list[Action]
    as_of: datetime | None = None
```

## Error envelope

```json
{
  "type": "https://errors.msft-engine.local/insufficient-data",
  "title": "Insufficient data to compute regime",
  "status": 422,
  "detail": "IV history requires \u2265 60 trading days; only 12 found",
  "instance": "/api/v1/engine/daily-plan",
  "missing": ["iv_history.atm_iv_30d (52 days)"]
}
```

## Idempotency & replay

- `POST /engine/daily-plan` is read-only with respect to the engine; it always **persists** the resulting `DailyDecision` row. Concurrent calls with identical `inputs_hash` collapse via `INSERT ... ON CONFLICT (user_id, inputs_hash) DO RETURNING`.
- `POST /engine/what-if` does NOT persist (flagged via `__transient: true` in payload).

---

## Patch v1.1 — Additional Endpoints, Expanded Schemas, Legacy Mapping

### New endpoints (Phase 1)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{ status, uptime_seconds, db, version, engine_version, weights_version }` |
| GET | `/healthz` | — | alias of `/health` |
| GET | `/version` | — | `{ version, engine_version, weights_version, git_sha }` |
| POST | `/engine/collar-builder` | `CollarBuilderRequest` | `CollarStructure[]` (typically 1–3) |
| GET | `/market/msft/latest` | — | `MarketLatestSnapshot` |

### Legacy → canonical mapping (`/docs/api/legacy.md`)

| Legacy / external name | Canonical endpoint | Notes |
|---|---|---|
| `/engine/recommendation` | `/engine/daily-plan` | `DailyDecision` is the full canonical output. `/engine/recommend` (singular) returns the `Recommendation` sub-object only. |
| `/engine/score` | `/engine/market-state` + `/engine/flow-score` | Or call `/engine/daily-plan` to get the composite result in one round-trip. |
| `/options/collar` | `/engine/collar-builder` | Renamed for engine-namespace consistency. |
| `/api/health` | `/api/v1/health` | API version is mandatory. |

In Phase 2, `/engine/recommendation` will return HTTP 308 redirect to `/engine/daily-plan` for backward compatibility with any external integrations.

### Replaced: `FlowScore` schema (V1 contract — locked)

The `FlowScore` model defined earlier in this section is superseded by the V1-contract version below. All consumers use these fields.

```python
class FlowScoreAction(str, Enum):
    SELL_CALL_AGGRESSIVE = "sell_call_aggressive"
    SELL_CALL_PARTIAL    = "sell_call_partial"
    REDUCE_COVERAGE      = "reduce_coverage"
    WAIT                 = "wait"
    BUY_PROTECTION       = "buy_protection"
    MONITOR              = "monitor"

class FlowScore(BaseModel):
    # Dual-direction scores (both populated; never just one)
    bullish_score: float = Field(..., ge=0, le=100)
    bearish_score: float = Field(..., ge=0, le=100)
    # Signed composite
    score: float = Field(..., ge=-100, le=100)              # = bullish - bearish
    bias: Literal["bearish","neutral_bearish","neutral","neutral_bullish","bullish"]
    # Pin & gamma
    pin_probability: float = Field(..., ge=0, le=1)         # P(spot ends within ±1% of max_pain at next expiry)
    gamma_risk: float = Field(..., ge=0, le=1)              # normalized magnitude of dealer-gamma exposure
    # Walls
    support_oi_wall: Decimal | None
    resistance_oi_wall: Decimal | None
    # Decision-ready
    recommended_action: FlowScoreAction
    confidence: float = Field(..., ge=0, le=1)
    explanation: str                                        # 1–3 sentence human-readable
```

Adding fields to `FlowScore` is permitted; renaming or removing a field is a breaking change requiring an `engine_version` major bump.

### New: `CollarBuilderRequest`, `CollarLeg`, `CollarStructure`

```python
class CollarIntent(str, Enum):
    ZERO_COST = "zero_cost"
    INCOME    = "income"
    DEFENSIVE = "defensive"

class CollarBuilderRequest(BaseModel):
    ticker: str = "MSFT"
    intents: list[CollarIntent] = [CollarIntent.ZERO_COST, CollarIntent.INCOME, CollarIntent.DEFENSIVE]
    coverage_ratio: float | None = None       # default: profile.max_coverage
    horizon_days: int | None = None           # default: profile.dte_band_days[1]
    underlying_qty: int | None = None         # default: current MSFT shares

class CollarLeg(BaseModel):
    kind: Literal["PUT","CALL"]
    side: Literal["BUY","SELL"]
    strike: Decimal
    expiry: date
    qty: int
    delta: float
    iv: float
    bid: Decimal
    ask: Decimal
    mid: Decimal
    premium: Decimal                          # signed: + paid, - received

class CollarStructure(BaseModel):
    name: str                                 # "Zero-cost 30d collar 405/430"
    intent: CollarIntent
    horizon_days: int
    long_put: CollarLeg
    short_call: CollarLeg
    net_debit_credit: Decimal                 # negative = credit
    max_gain: Decimal
    max_loss: Decimal
    upside_breakeven: Decimal
    downside_breakeven: Decimal
    capped_upside_pct: float
    protected_downside_pct: float
    confidence: float
    confidence_breakdown: ConfidenceBreakdown
    rationale: list[str]
    risks: list[str]
    invalidation: list[str]
    execution: Execution
```

### New: `MarketLatestSnapshot`

```python
class MarketLatestSnapshot(BaseModel):
    as_of: datetime
    ticker: str
    spot: Decimal
    iv_rank: float
    iv_percentile: float
    hv_30: float
    expected_move_pct: float
    max_pain: Decimal
    pcr_volume: float
    pcr_oi: float
    next_event: dict | None
    data_freshness: dict
```

A convenience read-through that bundles the most-recent state without invoking the engines. Used by the Today screen header and by external integrations (Slack bot in Phase 4) that want raw context without a full `DailyDecision`.

## 8. Frontend Component Structure

## Routing tree (Next.js 16.2.4 App Router)

```
apps/web/app/
  layout.tsx                       # root: Disclaimer gate, theme, auth context
  page.tsx                         # redirect -> /today
  (auth)/
    login/page.tsx
    register/page.tsx
  today/
    page.tsx                       # SERVER component: fetches DailyDecision
    loading.tsx
    error.tsx
  settings/
    page.tsx                       # User Strategy Profile editor
  outcomes/
    page.tsx                       # Manual entry + history table
  # --- Phase 2 ---
  chain/page.tsx
  iv/page.tsx
  max-pain/page.tsx
  payoff/page.tsx
  events/page.tsx
  # --- Phase 3 ---
  sim/page.tsx
  playbook/page.tsx
```

## Today screen component tree (Phase 1 primary)

```
<TodayPage>                              -- server component
  <DailyDecisionCard decision={...}>     -- client (interactive)
    <DecisionHeader>
      <TickerSpotBlock />
      <AsOfBadge />
      <DataFreshnessBadge />            -- spot/chain/iv staleness
    </DecisionHeader>

    <MarketStateBadge regime tags />     -- color-coded by regime

    <StrategyTitle name="ROLL_UP_AND_OUT_PARTIAL" />

    <ActionList>
      <ActionRow                          -- one per leg
        verb leg qty delta_target
        limit_price_band
        executionLeg={...}
      >
        <ExecutionBadge fillConfidence liquidityScore spreadBps />
      </ActionRow>
    </ActionList>

    <CoverageRing before after />

    <ConfidenceBreakdownChart            -- horizontal stacked bar
      flow_alignment structure_alignment regime_match signal_alignment
      event_risk_penalty illiquidity_penalty
      total weights_version
    />

    <ExecutionFeasibilityPanel
      aggregate_liquidity_score aggregate_fill_confidence notes />

    <WatchLevels above below iv_rank_drop_below />
    <NextTriggerNote text />

    <Drawer label="Why">
      <RationaleList items />
    </Drawer>
    <Drawer label="Risks">
      <RisksList items />
    </Drawer>
    <Drawer label="What invalidates this?">
      <InvalidationList items />
    </Drawer>

    <DrillDownLinks />                    -- Phase 2: deep-link to /chain, /iv, ...
    <DisclaimerFooter />
  </DailyDecisionCard>

  <OutcomeQuickEntry decisionId />        -- Phase 1 manual; Phase 3 auto-suggested
</TodayPage>
```

## Settings screen (Phase 1)

```
<SettingsPage>
  <UserStrategyProfileForm
    style max_coverage roll_aggressiveness drawdown_tolerance
    tax_sensitivity iv_rank_sell_threshold
    delta_target_band dte_band_days
  />
  <PersonaPresetButtons />               -- "Helen / Ravi / Diana" presets
  <AccountSection />                     -- email, password, logout
</SettingsPage>
```

## Outcomes screen (Phase 1)

```
<OutcomesPage>
  <OutcomeFilters />
  <OutcomeTable>
    <OutcomeRow                          -- decision summary + outcome editor inline
      decision_id as_of regime confidence
      outcome={...}
      onSave={...}
    />
  </OutcomeTable>
  <OutcomeStats />                       -- counts by quality, error_type histogram
</OutcomesPage>
```

## Shared primitives

`apps/web/components/ui/` — shadcn (Card, Badge, Button, Slider, Tooltip, Drawer, Dialog, Tabs, Form, Input, Select, Sheet, Toast, Skeleton, Separator).

`apps/web/components/today/` — domain components listed above.

`apps/web/components/charts/` — Recharts wrappers: `StackedConfidenceBar`, `PayoffDiagram` (P2), `IvTermStructure` (P2), `MaxPainBar` (P2).

## State management

- **Server components** for read-heavy pages (Today, Outcomes, Chain).
- **React Query** for client-side mutations and re-fetching after profile/outcome edits.
- **React Hook Form + zod** for forms; zod schemas mirror Pydantic via generated TS types.
- No Redux. No Zustand. Server state lives on the server; UI state stays local.

## Theming & accessibility

- Tailwind + shadcn theme with semantic color tokens for regimes:
  `regime-high-iv-event` (amber), `regime-high-iv-pin` (slate), `regime-low-iv-trend` (emerald), `regime-low-iv-range` (sky), `regime-breakout` (violet), `regime-post-event-reprice` (rose).
- Dark mode default (Helen reviews late evening).
- All charts have text-equivalent fallback for screen readers.
- Confidence components shown both as bar AND as labeled numeric values (no color-only encoding).

## 9. Engine Design (Core)

All engines are pure-function Python under `packages/engine/`. **No I/O, no DB, no network.** They take typed inputs and return typed outputs. Side effects (persistence, caching) belong to the API layer.

## 9.1 Regime Taxonomy (locked)

`packages/engine/regimes.py`:

```python
from enum import Enum
from typing import TypedDict

class Regime(str, Enum):
    HIGH_IV_EVENT       = "HIGH_IV_EVENT"
    HIGH_IV_PIN         = "HIGH_IV_PIN"
    LOW_IV_TREND        = "LOW_IV_TREND"
    LOW_IV_RANGE        = "LOW_IV_RANGE"
    BREAKOUT            = "BREAKOUT"
    POST_EVENT_REPRICE  = "POST_EVENT_REPRICE"

class RegimeSpec(TypedDict):
    allowed_strategies: list[str]
    risk_profile: str
    expected_behavior: str

REGIME_SPEC: dict[Regime, RegimeSpec] = {
    Regime.HIGH_IV_EVENT: {
        "allowed_strategies": [
            "OPEN_COLLAR", "SELL_COVERED_CALL_PARTIAL",
            "ROLL_OUT", "TRIM_COVERAGE_POST_EVENT",
        ],
        "risk_profile": "event_gap",
        "expected_behavior": "sell vol favorable; brace for IV crush",
    },
    Regime.HIGH_IV_PIN: {
        "allowed_strategies": [
            "SELL_COVERED_CALL_TIGHT", "ROLL_PIN_AWARE", "IRON_FLY_BIAS",
        ],
        "risk_profile": "pin_until_catalyst",
        "expected_behavior": "pinning dominates absent catalyst",
    },
    Regime.LOW_IV_TREND: {
        "allowed_strategies": [
            "BUY_LONG_DATED_PUT", "REDUCE_COVERAGE", "RATIO_CALL_SPREAD",
        ],
        "risk_profile": "premium_poor_trend_cap",
        "expected_behavior": "ride trend; hedge cheap; avoid capping",
    },
    Regime.LOW_IV_RANGE: {
        "allowed_strategies": [
            "SELL_COVERED_CALL_PARTIAL", "WHEEL", "SHORT_STRANGLE_SIZED",
        ],
        "risk_profile": "chop_decay",
        "expected_behavior": "harvest theta; avoid over-coverage",
    },
    Regime.BREAKOUT: {
        "allowed_strategies": [
            "ROLL_UP_AND_OUT", "REDUCE_COVERAGE", "MONETIZE_PUT",
        ],
        "risk_profile": "left_tail_of_upside",
        "expected_behavior": "trend continuation; un-cap upside",
    },
    Regime.POST_EVENT_REPRICE: {
        "allowed_strategies": [
            "RE_STRIKE_COLLAR", "SELL_RICHER_SKEW_PREMIUM", "ROLL_INTO_NEW_VOL",
        ],
        "risk_profile": "wrong_way_gap",
        "expected_behavior": "re-anchor at new spot",
    },
}
```

## 9.2 Market State Engine

`packages/engine/market_state/`

```python
def classify(
    *,
    spot: Decimal,
    iv_rank: float,
    iv_percentile: float,
    hv_30: float,
    expected_move_pct: float,
    max_pain: Decimal,
    pcr_volume: float,
    pcr_oi: float,
    days_to_next_event: int | None,
    next_event_kind: str | None,
    trend_strength: float,        # ADX-like proxy 0..1
    realized_vs_implied: float,   # hv_30 / atm_iv_30d
    days_since_event: int | None,
) -> MarketStateResult:
    ...
```

**Scoring approach**: each regime has a predicate function `score_<regime>(inputs) -> float in [0,1]`. The engine evaluates all six and selects the max. Ties (delta < 0.10) resolve toward the more conservative (event-aware) regime.

**Predicate sketches**:

```python
def score_high_iv_event(x):
    iv_high = sigmoid((x.iv_rank - 70) / 10)        # rises above IVR 70
    near_event = 1.0 if (x.days_to_next_event or 99) <= 7 else 0.0
    return clip01(0.5 * iv_high + 0.5 * near_event)

def score_high_iv_pin(x):
    iv_mid = sigmoid((x.iv_rank - 60) / 10)
    pin_close = max(0, 1 - abs(x.spot - x.max_pain) / x.spot / 0.01)
    near_expiry = max(0, 1 - (x.days_to_nearest_opex or 30) / 5)
    return clip01(0.4 * iv_mid + 0.4 * pin_close + 0.2 * near_expiry)

def score_low_iv_trend(x):
    iv_low = sigmoid((30 - x.iv_rank) / 10)
    trending = x.trend_strength
    return clip01(0.5 * iv_low + 0.5 * trending)

def score_low_iv_range(x):
    iv_low = sigmoid((30 - x.iv_rank) / 10)
    not_trending = 1 - x.trend_strength
    realized_matches = max(0, 1 - abs(x.realized_vs_implied - 1.0))
    return clip01(0.4 * iv_low + 0.3 * not_trending + 0.3 * realized_matches)

def score_breakout(x):
    return clip01(x.breakout_signal)        # composite: price+vol+OI shift

def score_post_event_reprice(x):
    if (x.days_since_event or 99) > 1: return 0.0
    iv_crushed = max(0, 1 - x.iv_rank_change_1d / -20)   # IV dropped >=20pts
    return clip01(0.6 * iv_crushed + 0.4 * (1 if abs(x.gap_pct) > 2 else 0))
```

**Output**:

```python
@dataclass(frozen=True)
class MarketStateResult:
    regime: Regime
    regime_score: float
    all_scores: dict[Regime, float]
    tags: list[str]                        # e.g. ["sell_vol_favorable","event_in_5d"]
    iv_rank: float
    iv_percentile: float
    hv_30: float
    expected_move_pct: float
    max_pain: Decimal
    max_pain_delta_pct: float
    pcr_volume: float
    pcr_oi: float
    next_event: dict | None
```

## 9.3 Flow Score Engine

`packages/engine/flow_score/`

```python
def compute(
    *,
    chain_snapshot: ChainSnapshot,
    spot: Decimal,
    expiry_focus: list[date],          # the 1-3 expirations to weigh
) -> FlowScoreResult:
    ...
```

**Logic**:
1. **OI walls**: per `expiry_focus`, find strikes with OI > 90th percentile; the highest below spot is `support_oi_wall`, the lowest above is `resistance_oi_wall`.
2. **PCR**: `pcr_volume = sum(put_volume) / sum(call_volume)`; same for OI.
3. **Skew tilt**: 25-delta put IV minus 25-delta call IV; positive = fear premium.
4. **Dealer-gamma proxy**: signed sum of `gamma * oi * (strike - spot)` across the focus expiries; negative = "short gamma above spot" (volatility amplifier).
5. **Bias mapping**: combine PCR, skew, OI shift over last 5 sessions, distance-from-walls.
6. **Score 0-100**: weighted composite.
7. **Confidence**: function of total OI in focus (low OI -> low confidence).

## 9.4 Strike Selector

`packages/engine/strike_selector/`

```python
def select(
    *,
    intent: Literal["sell_call","buy_put","collar","sell_put"],
    spot: Decimal,
    chain_snapshot: ChainSnapshot,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScoreResult,
    delta_band: tuple[float, float] | None = None,
    dte_band: tuple[int, int] | None = None,
    top_k: int = 5,
) -> StrikeCandidatesResult:
    ...
```

Filters chain by:
- Within `delta_band` (defaults from `profile.delta_target_band`)
- Within `dte_band_days`
- `oi >= 100`, `volume >= 10` (configurable)
- `spread_bps <= 300` (illiquid filter)

Scores candidates by:
- Premium per day per delta unit (yield)
- Distance from OI walls (closer to wall = better S/R alignment)
- Tag-based bonuses from `market_state.tags` (e.g. `sell_vol_favorable` -> boost short calls with high IV)

Returns top-K with rationale string per candidate.

## 9.5 Recommendation Engine

`packages/engine/recommendation/`

```python
def recommend(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScoreResult,
    positions: PositionState,
    profile: UserStrategyProfile,
    chain_snapshot: ChainSnapshot,
    rules_yaml: Path,
) -> RecommendationResult:
    ...
```

**Rule pipeline**:
1. Look up `REGIME_SPEC[regime].allowed_strategies` -> strategy whitelist.
2. Score each whitelisted strategy via predicates from `rules_yaml`. Each rule has `predicate`, `score`, `rationale`, `risks`, `invalidation` fields.
3. Top-scoring strategy wins. If two within 0.05, pick the one with lower drawdown impact (compatible with `profile.drawdown_tolerance`).
4. Generate `actions[]` by parameterizing the strategy template with strike/expiry from `Strike Selector`.
5. Compute `coverage_after` based on resulting short-call contracts vs underlying shares.

**Encoded V1 rules** (the 8 from the brief):

```yaml
# packages/engine/config/rules.yaml
- id: high_iv_sell_call
  when: { regime: ["HIGH_IV_EVENT","HIGH_IV_PIN","LOW_IV_RANGE"], iv_rank_gte: 50 }
  emit: SELL_COVERED_CALL_PARTIAL
  rationale: "IV rank {{iv_rank}} above sell threshold {{profile.iv_rank_sell_threshold}}"
  risks: ["Capped upside if breakout","Assignment risk near expiry"]
  invalidation: ["IV rank drops below 40", "Spot breaks above resistance with volume"]

- id: roll_up_and_out_when_short_call_threatened
  when: { has_short_call_within_pct: 1.0, days_to_expiry_lte: 14 }
  emit: ROLL_UP_AND_OUT
  rationale: "Short call within 1% of spot with {{dte}} DTE; roll captures more upside while harvesting premium"
  risks: ["Net debit if rolled at midpoint","New strike still ITM on continued rally"]

- id: reduce_coverage_on_breakout_post_event
  when: { regime: BREAKOUT, days_since_event_lte: 2, iv_rank_change_lte: -15 }
  emit: REDUCE_COVERAGE
  rationale: "Post-event IV crush + breakout pattern; reducing coverage preserves upside"
  risks: ["Trend may stall and we forgo premium"]

# ... 5 more rules
```

## 9.6 Master Decision Engine

`packages/engine/decision/`

```python
def produce_daily_decision(
    *,
    user_id: UUID,
    ticker: str,
    as_of: datetime,
    inputs: EngineInputs,                   # hydrated by API layer
    weights_path: Path,
    engine_version: str,
) -> DailyDecision:
    ms   = market_state.classify(...)
    fs   = flow_score.compute(...)
    sc   = strike_selector.select(intent=infer_intent(ms, inputs.positions), ...)
    rec  = recommendation.recommend(...)
    exe  = execution.assess(actions=rec.actions, chain=inputs.chain_snapshot)
    conf = confidence.compose(
        components=ConfidenceInputs(
            flow_alignment       = align_score(fs, rec),
            structure_alignment  = align_score(ms, rec),
            regime_match         = ms.regime_score,
            signal_alignment     = signal_align(ms, fs, rec),
            event_risk_penalty   = event_penalty(ms),
            illiquidity_penalty  = liquidity_penalty(exe),
        ),
        weights=load_weights(weights_path),
    )
    return assemble_payload(ms, fs, sc, rec, exe, conf, ...)
```

`infer_intent()`: looks at current positions and regime allowed strategies; e.g. `BREAKOUT` + existing short call \u2192 `intent="sell_call"` for the *new* (rolled-up) strike.

## 9.7 Confidence Composer

`packages/engine/confidence/`

```python
@dataclass(frozen=True)
class ConfidenceInputs:
    flow_alignment: float        # in [0,1]
    structure_alignment: float
    regime_match: float
    signal_alignment: float
    event_risk_penalty: float    # in [0,1] (subtracted)
    illiquidity_penalty: float   # in [0,1] (subtracted)

def compose(components: ConfidenceInputs, weights: Weights) -> tuple[float, ConfidenceBreakdown]:
    raw = (
        weights.w_flow      * components.flow_alignment +
        weights.w_struct    * components.structure_alignment +
        weights.w_regime    * components.regime_match +
        weights.w_signal    * components.signal_alignment -
        weights.w_event     * components.event_risk_penalty -
        weights.w_liquidity * components.illiquidity_penalty
    )
    confidence = clip01(raw)
    breakdown = ConfidenceBreakdown(
        flow_alignment=components.flow_alignment,
        structure_alignment=components.structure_alignment,
        regime_match=components.regime_match,
        signal_alignment=components.signal_alignment,
        event_risk_penalty=components.event_risk_penalty,
        illiquidity_penalty=components.illiquidity_penalty,
        weights_version=weights.version,
    )
    return confidence, breakdown
```

`packages/engine/config/weights.yaml`:

```yaml
version: "v1.0"
w_flow:      0.25
w_struct:    0.20
w_regime:    0.20
w_signal:    0.15
w_event:     0.10
w_liquidity: 0.10
```

Constraint: `|w_flow| + |w_struct| + |w_regime| + |w_signal| + |w_event| + |w_liquidity| == 1.0`. Validated on load.

## 9.8 Execution Feasibility Module

`packages/engine/execution/`

```python
def assess(*, actions: list[Action], chain: ChainSnapshot) -> Execution:
    legs = []
    for a in actions:
        q = chain.lookup(a.leg_descriptor)
        spread = q.ask - q.bid
        spread_bps = int(spread / max(q.mid, Decimal("0.01")) * 10000)
        liq = clip01(
            0.4 * norm_oi(q.oi) +
            0.4 * norm_volume(q.volume) +
            0.2 * (1 - min(spread_bps, 300) / 300)
        )
        slip = expected_slippage(q, a.qty)
        fill_conf = clip01(0.6 * liq + 0.4 * (1 - spread_bps / 300))
        legs.append(ExecutionLeg(
            leg_id=a.leg,
            liquidity_score=liq,
            spread_bps=spread_bps,
            fill_confidence=fill_conf,
            expected_slippage=slip,
            suggested_order_type="limit",
            limit_price_band=(q.mid - tick(q), q.mid + tick(q)),
            size_warnings=size_warnings(q, a.qty),
        ))
    return aggregate(legs)
```

**Downgrade rule**: if any leg has `fill_confidence < 0.5`, the Recommendation Engine receives a callback to propose nearby strikes with better liquidity (re-runs Strike Selector with adjusted filters).

## 9.9 User Strategy Profile

`packages/engine/profiles.py` — schema in \u00a77 (Pydantic). Stored in `users.strategy_profile` JSONB.

Validation rules:
- `delta_target_band[0] < delta_target_band[1]`
- `dte_band_days[0] < dte_band_days[1]`
- `max_coverage` in [0,1]
- `iv_rank_sell_threshold` in [0,100]

Propagation:
- **Strike Selector** uses `delta_target_band` and `dte_band_days` as defaults.
- **Recommendation Engine** uses `style` to filter strategy whitelist (e.g. `style="growth"` excludes `SHORT_STRANGLE_SIZED`).
- **Confidence Composer** does not directly read profile; but `event_risk_penalty` is up-weighted when `drawdown_tolerance < 0.10`.
- **Coverage logic** uses `max_coverage` as the upper bound for resulting short-call contracts.

## 9.10 Outcome Tracker / Learning Loop

`packages/engine/outcomes/`

**Phase 1**: schema + manual entry. `outcomes` rows linked 1:1 to `daily_decisions`.

**Phase 3 auto-fill heuristics**:

```python
def auto_fill_outcome(decision: DailyDecision, history: PriceIvHistory) -> Outcome:
    horizon = 7        # default; configurable
    pnl = compute_pnl(decision.actions, history)
    realized_regime = classify_realized_regime(history.window(horizon))
    error = infer_error_type(decision, history)
    quality = quality_from_pnl_and_regime_match(pnl, decision.market_state.regime, realized_regime)
    return Outcome(...)
```

**Phase 4** uses the accumulated `(state, decision, outcome)` triples for ML retraining (see \u00a716).

---

## 9.3a — Flow Score V1 Contract (LOCKED in v1.1)

The expanded `FlowScore` schema in §7 Patch v1.1 is the V1 contract. Subsequent ML upgrades MUST preserve these field names and semantics. Adding fields is permitted; renaming or removing is breaking.

The deterministic V1 baseline (`packages/engine/engine/flow_score/__init__.py:compute()`) computes:

```python
def compute(*, chain_snapshot, spot, expiry_focus, profile) -> FlowScore:
    walls = oi_walls.compute(chain_snapshot, spot, expiry_focus)
    skew  = skew_25d(chain_snapshot, expiry_focus)
    basis = futures_basis(spot)                         # 0 if futures unavailable
    pcrv  = pcr_volume(chain_snapshot, expiry_focus)
    pcroi = pcr_oi(chain_snapshot, expiry_focus)
    gamma = scoring.gamma_score(...)                    # see §9.11

    bullish_score = clip01_to_100(
        0.30 * dist_to_resistance_norm(spot, walls) +
        0.25 * call_volume_norm(chain_snapshot) +
        0.20 * max(0.0, -skew) +                        # negative skew = bullish flow
        0.15 * max(0.0,  basis) +
        0.10 * (1.0 - pcrv)
    ) * 100

    bearish_score = clip01_to_100(
        0.30 * dist_to_support_norm(spot, walls) +
        0.25 * put_volume_norm(chain_snapshot) +
        0.20 * max(0.0,  skew) +
        0.15 * max(0.0, -basis) +
        0.10 * pcrv
    ) * 100

    score = bullish_score - bearish_score
    bias  = bias_from_score(score)                      # bins
    pin_probability = sigmoid_pin(spot, max_pain, dte_to_nearest_opex,
                                  oi_concentration_at_max_pain)
    gamma_risk = gamma.score                            # 0..1
    recommended_action = decision_tree(
        score, gamma_risk, pin_probability, profile.style)
    confidence = confidence_from_oi_total(chain_snapshot, expiry_focus)
    explanation = render_explanation(walls, skew, score, gamma, pin_probability)
    return FlowScore(...)
```

`recommended_action` decision tree (V1):
- `score \u2265 +40` and `gamma_risk \u2264 0.5` -> `sell_call_aggressive`
- `score \u2265 +10` -> `sell_call_partial`
- `score in (-10, +10)` and `pin_probability \u2265 0.6` -> `wait`
- `score \u2264 -20` and `gamma_risk \u2265 0.6` -> `buy_protection`
- `score \u2264 -10` -> `reduce_coverage`
- otherwise -> `monitor`

This decision tree is itself unit-tested with named fixtures.

---

## 9.10 — Collar Builder (added v1.1)

**First-class engine module** (not embedded in Recommendation). Justification: collars are the primary structural strategy for the long-equity holder; users will invoke them directly ("show me 3 collar candidates") independent of the Master Decision flow.

Module: `packages/engine/engine/collar_builder/`

```python
def build(
    *,
    spot: Decimal,
    underlying_qty: int,
    chain: ChainSnapshot,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    intents: list[CollarIntent] = list(CollarIntent),
    horizon_days: int | None = None,
    coverage_ratio: float | None = None,
) -> list[CollarStructure]:
    """Returns ranked candidate collars (typically 1 per requested intent)."""
```

### Algorithm per intent

**`zero_cost`**: solve for `(K_put, K_call)` such that `net_debit_credit \u2248 0` (\u00b15 cents per share), subject to:
- `protected_downside_pct \u2265 profile.drawdown_tolerance`
- short call delta in `profile.delta_target_band`
- both legs pass Execution Feasibility floors (`liquidity_score \u2265 0.5`, `fill_confidence \u2265 0.5`)
- expiry from `dte_band_days` (default `profile.dte_band_days[1]`)

**`income`**: solve for max `net_credit` subject to:
- `capped_upside_pct \u2265 X` (config; default 4%)
- `protected_downside_pct \u2265 Y` (config; default `profile.drawdown_tolerance / 2`)

**`defensive`**: solve for max `protected_downside_pct` subject to:
- `net_debit \u2264 Z` (config; default 0.5% of position notional)

### Solver

Grid search over (K_put \u00d7 K_call) using the chain. Filter by liquidity. Sort candidates by intent objective. Tie-break by `score = scoring.iv_score - scoring.event_score - illiquidity_penalty`.

### Output

For each intent, the top candidate becomes a `CollarStructure` (\u00a77 schema). Include full `ConfidenceBreakdown`, `Execution`, rationale, risks, invalidation. The list returned is intent-ordered.

### Integration with Master Decision Engine

- When `market_state.regime in {HIGH_IV_EVENT, POST_EVENT_REPRICE}` AND `existing collar legs are absent`, the Master Decision Engine calls `collar_builder.build(intents=[ZERO_COST])` and may include the result as the recommended action.
- When called via `POST /engine/collar-builder`, the user gets ALL requested intents ranked side-by-side (typically 3).

### Tests

`packages/engine/tests/test_collar_builder.py`:
- 3 named fixtures (one per intent) with expected strikes (\u00b1 1 strike tolerance).
- Property: `zero_cost.net_debit_credit \u2208 [-0.10, +0.10]`.
- Property: `income.net_debit_credit < 0` (always credit) or function returns empty list with reason.
- Property: `defensive.protected_downside_pct \u2265 income.protected_downside_pct`.
- Liquidity downgrade test: when chosen strikes fail Execution, builder must fall back to nearby strikes or return empty with reason.

---

## 9.11 — Scoring Functions Module (added v1.1)

Module: `packages/engine/engine/scoring/`

Five named scoring primitives. Four new in v1.1; `flow_score` remains in its existing package and is the orchestrator that consumes the others.

```python
# packages/engine/engine/scoring/iv.py
def iv_score(*, iv_rank: float, iv_percentile: float, hv_30: float, atm_iv_30d: float) -> IvScoreResult:
    """0..1; higher = more favorable for selling premium."""

# packages/engine/engine/scoring/structure.py
def structure_score(*, oi_walls, max_pain: Decimal, spot: Decimal,
                    expected_move_pct: float, dte_to_nearest_opex: int) -> StructureScoreResult:
    """0..1; higher = stronger options-structure signal (walls, pin, EM containment)."""

# packages/engine/engine/scoring/gamma.py
def gamma_score(*, dealer_gamma_proxy: Decimal, spot: Decimal,
                gamma_walls: list[GammaWall]) -> GammaScoreResult:
    """0..1 magnitude + sign in result; positive=stabilizing, negative=amplifying."""

# packages/engine/engine/scoring/event.py
def event_score(*, days_to_event: int | None, event_kind: str | None,
                event_history: EventStats) -> EventScoreResult:
    """0..1; higher = greater event-driven uncertainty / risk."""

# packages/engine/engine/flow_score/__init__.py  (existing, orchestrates)
def compute(*, chain_snapshot, spot, expiry_focus, profile) -> FlowScore:
    """V1 FlowScore (\u00a79.3a). Composes scoring/iv, scoring/gamma, scoring/structure under the hood."""
```

Each `*Result` dataclass carries `score` in `[0,1]` and a `breakdown` dict naming the contributing factors and their values (used by Confidence Composer for explainability).

### Wiring matrix (which engine consumes which scoring fn)

| Consumer | iv | structure | gamma | event | flow |
|---|---|---|---|---|---|
| Market State Engine | x | x |   | x |   |
| Flow Score Engine (orchestrator) | x |   | x |   | (self) |
| Recommendation Engine |   | x |   |   | x |
| Confidence Composer | x | x |   | x | x |
| Collar Builder | x |   |   | x |   |
| Strike Selector | x |   |   |   |   |

### Tests

`packages/engine/tests/test_scoring_{iv,structure,gamma,event}.py`:
- 5+ named fixtures per scoring fn, including extremes (zero, max, edge cases).
- Property: each `score \u2208 [0,1]`.
- Property: monotonicity where applicable (e.g., `iv_score` non-decreasing in `iv_rank` holding others fixed).
- CI requires **100% line coverage** on `packages/engine/engine/scoring/`.

## 10. Data Ingestion Plan

## Provider abstraction

`packages/engine/providers/base.py`:

```python
from abc import ABC, abstractmethod

class MarketDataProvider(ABC):
    name: str
    capabilities: set[Literal["spot","chain","iv_history","events","greeks","oi_volume"]]

    @abstractmethod
    def get_spot(self, ticker: str) -> Decimal: ...
    @abstractmethod
    def get_chain(self, ticker: str, expiries: list[date] | None) -> ChainSnapshot: ...
    @abstractmethod
    def get_iv_history(self, ticker: str, lookback_days: int) -> IvHistory: ...
    @abstractmethod
    def get_events(self, ticker: str, window_days: int) -> list[Event]: ...
```

| Provider | Phase | Capabilities | Notes |
|---|---|---|---|
| `CsvProvider` | P1 | all (manual) | reads from user uploads; canonical format below |
| `YfinanceProvider` | P2 | spot, basic chain (delayed), HV | free, rate-limited, no real-time |
| `TradierProvider` | P2 | chain, OI/volume, IV, Greeks, events | free dev sandbox; real-time with key |
| `PolygonProvider` | P2 paid | full chain, historical IV, surface | best quality; subscription |
| `FredProvider` | P2 | FOMC schedule | free |
| `IBKRProvider` | P4 | positions sync, market data | read-only first |

## Cron schedule (`apps/jobs`, P2+)

| Time (ET) | Job | Job script |
|---|---|---|
| 06:30 daily | Refresh events for next 60 days | `jobs/refresh_events.py` |
| 09:30, 10:00, ..., 16:00 every 30min | Snapshot chain | `jobs/ingest_chain.py` |
| 16:30 daily | Compute IV rank/percentile, HV | `jobs/compute_iv.py` |
| 17:00 daily | Recompute regimes, persist `daily_decisions` for next morning preview | `jobs/precompute_decisions.py` |
| 17:00 daily (P3+) | Auto-fill outcomes for decisions older than horizon | `jobs/auto_outcome.py` |

Scheduler: **Arq** on Redis (lightweight, async, fits FastAPI ecosystem). Alternative: APScheduler for in-process.

## Canonical CSV formats (Phase 1)

`positions.csv`:
```
ticker,qty,avg_cost,opened_at
MSFT,5000,400.12,2025-08-15T00:00:00Z
```

`option_positions.csv`:
```
ticker,side,kind,strike,expiry,qty,opened_at,opened_price,status
MSFT,SELL,CALL,415.00,2026-05-16,5,2026-04-15T15:30:00Z,2.85,OPEN
```

`chain.csv`:
```
ticker,fetched_at,expiry,strike,kind,bid,ask,last,oi,volume,iv,delta,gamma,theta,vega
MSFT,2026-04-29T13:30:00Z,2026-05-16,415.00,CALL,3.10,3.40,3.25,12450,3210,0.2812,0.4521,0.0123,-0.0876,0.6234
```

`iv_history.csv`:
```
ticker,ts,atm_iv_30d,iv_rank,iv_percentile,hv_30
MSFT,2026-04-28T20:00:00Z,0.2814,78.4,84.1,0.2231
```

`events.csv`:
```
ticker,kind,scheduled_at,source,notes
MSFT,earnings,2026-05-04T20:30:00Z,manual,Q3 FY26 print AMC
,fomc,2026-05-07T18:00:00Z,fred,
```

CSV upload endpoint: `POST /data/<resource>/import-csv` (multipart). Response: `{ inserted, updated, errors[] }`.

## Backfill strategy

CLI:

```
$ uv run engine backfill --provider tradier --resource iv_history --days 365 --ticker MSFT
$ uv run engine backfill --provider polygon --resource chain --from 2025-01-01
```

Idempotent inserts via `(ticker, ts)` UNIQUE keys; conflict updates value if differing.

## Rate-limit handling

Token bucket per provider (`tokenbucket` PyPI). Exponential backoff on HTTP 429 (1s, 2s, 4s, 8s, capped 60s). Failed jobs surface in `audit_log` with `kind="ingestion_failure"` and trigger an in-app banner if affecting today's decision.

## Staleness flags

Every `DailyDecision.data_freshness`:

```json
{
  "spot_age_seconds": 47,
  "chain_age_seconds": 1832,
  "iv_age_seconds": 87400,
  "events_last_refreshed": "2026-04-29T06:30:00Z",
  "any_stale": false,
  "stale_threshold_seconds": { "spot": 300, "chain": 3600, "iv": 90000 }
}
```

UI renders an amber `DataFreshnessBadge` when `any_stale=true` and a tooltip listing which inputs.

## 11. Option Payoff Calculation Module

`packages/engine/payoff/` — pure-function pricing module. No I/O.

## Public API

```python
def bs_price(
    spot: float, strike: float, dte_years: float,
    iv: float, r: float, q: float,
    kind: Literal["call","put"],
) -> float: ...

def bs_greeks(
    spot, strike, dte_years, iv, r, q, kind,
) -> dict[str, float]:
    # returns {delta, gamma, theta_per_day, vega_per_volpt, rho_per_pct}
    ...

def iv_solve(
    market_price: float, spot: float, strike: float,
    dte_years: float, r: float, q: float, kind: str,
    *, tol: float = 1e-6, max_iter: int = 64,
) -> float:
    # Brent's method on [1e-4, 5.0]
    ...

@dataclass(frozen=True)
class Leg:
    side: Literal["LONG","SHORT"]
    kind: Literal["CALL","PUT","STOCK"]
    strike: float | None         # None for stock
    qty: int                      # contracts (100 multiplier) or shares for stock
    cost_basis: float             # premium paid/received per contract, or share cost
    expiry: date | None

def terminal_pl(
    legs: list[Leg], spot_grid: np.ndarray, at: date,
) -> np.ndarray:
    # returns shape (len(spot_grid),) of terminal P/L in dollars at `at`
    ...

def breakevens(legs: list[Leg]) -> list[float]:
    # finds zero crossings of terminal_pl()
    ...

def combined_greeks(
    legs: list[Leg], spot: float, dte_years: float,
    iv: float, r: float, q: float,
) -> dict[str, float]:
    # aggregate sensitivities across all legs at current spot
    ...
```

## Conventions

- `dte_years` is calendar days / 365.0 (we use trading-day variant only in the regime engine, not BS).
- `iv` is decimal volatility (0.28 = 28%).
- `r` from FRED 3-month T-bill (manual config in MVP).
- `q` (dividend yield) configured per ticker; MSFT default 0.0075.
- All Greeks scaled per sensible unit: `theta_per_day`, `vega_per_volpt`, `rho_per_pct`.

## Numerical robustness

- Reject `iv < 1e-4` or `iv > 5.0` from solver; surface as `MarketPriceImpliedVolError`.
- Clamp `dte_years \u2265 1/365`.
- Use `scipy.special.ndtr` for CDF (faster + more accurate than `math.erf`).

## Reference values & golden tests

Golden vectors derived from `py_vollib` published reference (BS-Merton model). Tolerance:
- price: 1e-4
- delta, gamma: 1e-5
- theta_per_day, vega_per_volpt: 1e-4
- IV solver round-trip: solve(price(iv)) -> iv within 1e-5

## Used by

- **Strike Selector** (\u00a79.4): IV solve where chain `iv` is missing; delta filter; ranking.
- **What-If endpoint** (\u00a77): terminal P/L grid for the user-overridden state.
- **Scenario Simulator** (\u00a712): re-prices legs under `(spot_after, iv_after)` perturbations.
- **Recommendation Engine**: estimates net debit/credit of proposed multi-leg actions.

## 12. Scenario Simulation Module

`packages/engine/scenarios/` — decision-based, not just PnL.

## Six locked scenarios

```python
class ScenarioId(str, Enum):
    EARNINGS_BEAT_GAP_UP_6PCT       = "EARNINGS_BEAT_GAP_UP_6PCT"
    EARNINGS_MISS_GAP_DOWN_6PCT     = "EARNINGS_MISS_GAP_DOWN_6PCT"
    IV_CRUSH_30PCT_NO_PRICE_MOVE    = "IV_CRUSH_30PCT_NO_PRICE_MOVE"
    PIN_AT_MAX_PAIN_3D_TO_EXPIRY    = "PIN_AT_MAX_PAIN_3D_TO_EXPIRY"
    BREAKOUT_ABOVE_RES_5PCT_HIVOL   = "BREAKOUT_ABOVE_RES_5PCT_HIVOL"
    RANGE_BOUND_DRIFT_2PCT_30D      = "RANGE_BOUND_DRIFT_2PCT_30D"

SCENARIO_PARAMS = {
    ScenarioId.EARNINGS_BEAT_GAP_UP_6PCT: dict(
        spot_pct=+0.06, iv_change_pct=-0.30, days_forward=1, regime_after="POST_EVENT_REPRICE"),
    ScenarioId.EARNINGS_MISS_GAP_DOWN_6PCT: dict(
        spot_pct=-0.06, iv_change_pct=-0.25, days_forward=1, regime_after="POST_EVENT_REPRICE"),
    ScenarioId.IV_CRUSH_30PCT_NO_PRICE_MOVE: dict(
        spot_pct=0.0, iv_change_pct=-0.30, days_forward=1, regime_after="LOW_IV_RANGE"),
    ScenarioId.PIN_AT_MAX_PAIN_3D_TO_EXPIRY: dict(
        spot_to="max_pain", iv_change_pct=-0.05, days_forward=3, regime_after="HIGH_IV_PIN"),
    ScenarioId.BREAKOUT_ABOVE_RES_5PCT_HIVOL: dict(
        spot_pct=+0.05, iv_change_pct=+0.05, days_forward=2, regime_after="BREAKOUT"),
    ScenarioId.RANGE_BOUND_DRIFT_2PCT_30D: dict(
        spot_pct=+0.02, iv_change_pct=0.0, days_forward=30, regime_after="LOW_IV_RANGE"),
}
```

## Output schema

```python
class ScenarioOutcome(BaseModel):
    scenario: ScenarioId
    spot_after: Decimal
    iv_change: float                        # decimal (e.g. -0.30 = IV down 30 pts relative)
    iv_after: float
    position_pnl: Decimal
    position_pnl_pct: float
    action: str                             # e.g. "ROLL_UP_AND_OUT"
    suggested_strike: Decimal | None
    suggested_expiry: date | None
    reason: str
    confidence: float
    execution: Execution                    # under post-scenario chain
    risks: list[str]
```

## Engine

```python
def simulate_scenarios(
    *, current_state: EngineInputs, scenarios: list[ScenarioId] | None = None,
) -> list[ScenarioOutcome]:
    ...
```

For each scenario:
1. Apply parameters to derive `(spot_after, iv_after, regime_after)`.
2. Synthesize a hypothetical `ChainSnapshot` by re-pricing chain via `bs_price` with `iv_after`.
3. Re-compute `position_pnl` from existing legs at the new state.
4. Run the full Master Decision Engine against the hypothetical state with `regime_after` forced.
5. Extract recommended action + strike + expiry + reason + confidence from the resulting `DailyDecision`.
6. Run Execution Feasibility on the hypothetical chain.

## Phase 3 enhancement: Monte Carlo

Add `simulate_monte_carlo(n_paths, horizon_days)` that samples from a fitted GBM with regime-conditional drift/vol. Output: distribution over `position_pnl` plus probability-weighted recommended action. Out of MVP.

## UI surface

- **Phase 1**: drawer on Today screen showing all 6 scenarios as a table with action column.
- **Phase 3**: dedicated `/sim` screen with full per-scenario cards, what-if sliders for `spot_pct`, `iv_change_pct`, `days_forward`.

## 13. Testing Strategy

## Test pyramid

```
         /\
        /E2\         Playwright (1-2 critical flows)
       /----\
      / Inte \       FastAPI TestClient (per route)
     /--------\
    / Property  \    hypothesis (math invariants)
   /------------\
  /  Unit + Gold \   pytest, vitest, golden fixtures
 /----------------\
```

## Unit tests (`packages/engine/tests/`)

**Pricing math** (`test_payoff.py`):
- `bs_price` matches `py_vollib` reference within 1e-4 across an 80-point grid (S, K, T, IV, type).
- `bs_greeks` matches finite-difference values within 1e-3.
- `iv_solve` round-trip: `iv_solve(bs_price(iv0)) == iv0` within 1e-5 across [0.05, 2.0].

**Confidence** (`test_confidence.py`):
- `compose()` output in [0,1] for any inputs in [0,1].
- Weights summing to anything other than 1.0 raise on load.
- Each component pure-function tested in isolation with 5 fixtures.

**Liquidity / execution** (`test_execution.py`):
- `liquidity_score` in [0,1] for synthetic chain with extremes (oi=0, oi=1e6).
- `fill_confidence < 0.5` triggers downgrade callback in Recommendation Engine integration test.
- `size_warnings` populated when `qty > 30%` of strike volume.

**Regime classification** (`test_market_state.py`):
- 24 historical fixtures: pre-earnings, post-earnings, FOMC week, OpEx week, breakout day, low-vol summer drift, etc.
- Each fixture has expected regime; engine must match \u2265 80% (CI threshold).

**Strike selector** (`test_strike_selector.py`):
- Filters respect `delta_band`, `dte_band`, OI/volume floors.
- Ranking deterministic given same inputs (golden snapshot).

**Recommendation** (`test_recommendation.py`):
- Each of the 8 encoded YAML rules has a positive fixture (rule fires) and a negative fixture (rule does not fire).

**Master Decision** (`test_decision.py`):
- Golden DailyDecision snapshots: 12 fixtures spanning regime + position combinations.
- Snapshots use `syrupy` for diff-friendly review.
- `inputs_hash` deterministic across runs.

## Property-based (`hypothesis`)

```python
@given(spot=st.floats(50,500), strike=st.floats(50,500), iv=st.floats(0.05,2.0), t=st.floats(1/365, 2.0))
def test_bs_call_monotone_in_spot(spot, strike, iv, t):
    p1 = bs_price(spot,     strike, t, iv, 0.05, 0.0, "call")
    p2 = bs_price(spot+1.0, strike, t, iv, 0.05, 0.0, "call")
    assert p2 >= p1 - 1e-9
```

Properties tested:
- BS call price monotone non-decreasing in spot, IV, T.
- BS put price monotone non-increasing in spot.
- Liquidity score \u2208 [0,1].
- Confidence \u2208 [0,1].
- Long-call payoff = \u2212 short-call payoff (mirror).
- `terminal_pl(legs, grid)` is piecewise linear with kinks at strikes.

## Integration (`apps/api/tests/`)

Using FastAPI `TestClient` + a transactional Postgres fixture (`pytest-postgresql`):

- `POST /engine/daily-plan` happy path with seeded fixtures \u2192 returns coherent payload, persists row.
- CSV upload \u2192 daily-plan flow generates a DailyDecision.
- `PUT /profile` then `POST /engine/daily-plan` produces a different output (regression).
- `POST /engine/what-if` does NOT persist a row.
- Auth: unauthenticated \u2192 401; cross-tenant access \u2192 403.

## E2E (`apps/web/tests/`, Playwright)

Critical flows:
1. **Disclaimer gate**: visit `/`, see modal, accept, land on `/today`.
2. **CSV \u2192 Today**: upload positions + chain CSV, navigate to `/today`, see DailyDecision card with all sub-components rendered.
3. **Profile change**: edit profile in settings, return to today, see card change.
4. **Outcome entry**: from Today, click "log outcome", fill form, see row in Outcomes.

## Calibration tests (P3, but scaffolded in P1)

- Run engine across 12 months of historical fixtures; bin by `confidence`; assert empirical success rate is monotonic across bins.
- Regime classification accuracy \u2265 80% on the 24 fixtures (already covered).
- Soft assert: any new fixture added to the suite must not drop accuracy below 75% (CI warning, not failure).

## CI gates

GitHub Actions matrix:

| Job | Tool | Blocking? |
|---|---|---|
| Lint | `ruff`, `eslint` | Yes |
| Typecheck | `mypy --strict` (engine), `tsc --noEmit` (web) | Yes |
| Engine unit | `pytest packages/engine -q` | Yes |
| Engine property | `pytest packages/engine -k property` | Yes |
| API integration | `pytest apps/api -q` | Yes |
| Web unit | `vitest` | Yes |
| Playwright E2E | headless Chrome | Yes (P1+) |
| Coverage | engine \u2265 80% | Yes |
| Calibration soft | regime accuracy logged | Warn |

## Test data

- `packages/engine/tests/fixtures/regimes/` \u2014 24 JSON files with `inputs.json` + `expected.json`.
- `packages/engine/tests/fixtures/decisions/` \u2014 12 JSON files mapping inputs \u2192 expected DailyDecision.
- `packages/engine/tests/fixtures/chain/` \u2014 sample chain snapshots (Apr 2026 MSFT real-looking).
- Fixtures are versioned in git; large ones (>50KB) compressed.

## 14. Deployment Plan

## Environments

| Env | Web | API | DB | Branch |
|---|---|---|---|---|
| Local | `next dev` (Turbopack) | `uvicorn --reload` | Postgres in Docker | any |
| Staging | Vercel preview | Fly.io app `msft-engine-api-stg` | Neon (staging branch) | `staging` |
| Production | Vercel | Fly.io app `msft-engine-api` | Neon (main branch) | `main` |

## Local: docker-compose.yml

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: msft_engine
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: ./apps/api
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:dev@postgres:5432/msft_engine
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET: dev-secret
    depends_on: [postgres, redis]
    ports: ["8000:8000"]
    volumes: [./packages/engine:/code/packages/engine]

  jobs:
    build: ./apps/jobs
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:dev@postgres:5432/msft_engine
      REDIS_URL: redis://redis:6379/0
    depends_on: [postgres, redis]

  web:
    build: ./apps/web
    environment:
      NEXT_PUBLIC_API_BASE: http://api:8000/api/v1
    depends_on: [api]
    ports: ["3000:3000"]

volumes:
  pgdata:
```

## Secrets management

- **Local**: `.env.local` (gitignored). Loaded via `pydantic-settings` (api), `dotenv` (web).
- **Vercel**: env vars per environment; preview-scoped vs production-scoped.
- **Fly.io**: `fly secrets set KEY=...` per app.
- **Neon**: connection strings rotated quarterly; stored in Vercel + Fly secret stores.
- Required secrets: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `TRADIER_API_KEY` (P2), `POLYGON_API_KEY` (P2 paid).

## Migrations

Alembic. Migrations live in `apps/api/app/db/migrations/`. Workflow:

```
$ uv run alembic revision --autogenerate -m "add outcomes table"
$ uv run alembic upgrade head
```

- **Dev**: API container runs `alembic upgrade head` on startup.
- **Staging**: GitHub Actions runs migrations as a pre-deploy step.
- **Prod**: same, gated on manual approval.

## CI/CD pipeline (`.github/workflows/`)

`ci.yml` — runs on every PR:
- `lint` (ruff, eslint)
- `typecheck` (mypy strict on engine, tsc on web)
- `test-engine` (pytest unit + property + golden)
- `test-api` (pytest integration + Postgres service)
- `test-web` (vitest)
- `e2e` (Playwright, headless)

`deploy-staging.yml` — on push to `staging`:
- Build Docker images for `api` and `jobs`; push to Fly registry.
- Run `alembic upgrade head` against Neon staging.
- `flyctl deploy` for both apps.
- Vercel auto-deploys web on push.

`deploy-prod.yml` — on push to `main`, requires manual approval:
- Same as staging, against prod targets.
- Tag the release.

## Observability

- **Logs**: structured JSON via `loguru` (api, jobs); Vercel logs (web). Aggregated to Better Stack or Datadog (P3+).
- **Metrics**: Prometheus client in FastAPI; key metrics: `engine_decision_seconds`, `regime_classification_total{regime=...}`, `daily_decisions_persisted_total`, `cache_hit_total`.
- **Tracing**: OpenTelemetry, exporting to Honeycomb (P3+).
- **Errors**: Sentry on web + api.
- **Uptime**: Better Stack or Pingdom against `/healthz` and `/today` (HEAD).

## Rollback

- Docker tags pinned by SHA; previous image held for 7 days.
- Alembic downgrade migrations required for any breaking schema change (one revision back, always).
- Feature flags via `unleash` or simple env-var toggles for ML nodes (P4).

## Cost ceiling (informational)

- Vercel hobby/free for MVP.
- Fly.io shared-cpu-1x (api) + shared-cpu-1x (jobs): ~$5/mo each.
- Neon free tier (compute auto-suspend): $0 for MVP; ~$19/mo at scale.
- Total MVP infra: < $15/mo.

## 15. Security & Privacy

## Authentication & authorization

- **Web auth**: NextAuth (credentials provider + optional OAuth in P3). Sessions are JWT (HS256) with 30-day refresh tokens.
- **API auth**: FastAPI dependency `Depends(get_current_user)` validates `Authorization: Bearer <jwt>`. JWT contains `sub` (user_id), `iat`, `exp`. Verifies against `JWT_SECRET`.
- **Cross-tenant isolation**: every query is scoped by `user_id`; Postgres row-level security policies enforced as defense-in-depth (P3).
- **Password hashing**: `argon2-cffi` (preferred) or `bcrypt` (cost factor 12).
- **Rate limiting**: `slowapi` per-IP and per-user; `/auth/login` capped at 5/min.

## Secrets

- Never in repo. `.env.local` gitignored.
- Vercel + Fly secret stores in deployed envs.
- `JWT_SECRET` rotated annually or on suspected compromise; rotation invalidates active sessions.
- Provider API keys (Tradier, Polygon) per-environment; rotated quarterly.

## PII minimization

- Stored: email, password hash, optional display name.
- NOT stored: full legal name, address, brokerage credentials, SSN, account numbers.
- Position data is sensitive financial data \u2014 column-level encryption via `pgcrypto` on `lots.cost_basis` and `positions.qty` in P3+.

## Audit trail

- Every `daily_decisions` row persisted with `inputs_hash`, `weights_version`, `engine_version` for full replay.
- `audit_log` captures profile mutations, login, CSV uploads, weight changes (with diff).
- Outcomes captured 1:1 with decisions for accountability.

## Disclaimer enforcement

- First-run modal blocks navigation until `disclaimer_accepted_at` is recorded in `users`.
- Persistent footer on every page: "Educational only \u00b7 Not financial advice \u00b7 Verify with broker".
- Every `DailyDecision.disclaimers` array carries the disclaimer text \u2014 frontend cannot render the card without it.
- API response envelope includes `disclaimers` to prevent header-stripping.

## No-execution guard rails

- **Codebase invariant**: no module imports any broker SDK in MVP. CI script `scripts/check_no_broker_imports.sh` greps for forbidden imports and fails the build if found.
- Phase 4 brokerage integration is **read-only**: positions sync only, no order endpoints. A separate codeowner approval is required to add any write-capable broker call.

## Dependency hygiene

- GitHub Dependabot weekly PRs.
- `pip-audit` in CI for Python; `npm audit --omit=dev` for web.
- Lockfiles committed: `uv.lock`, `pnpm-lock.yaml`. CI fails on lockfile drift.
- Subresource integrity for any CDN-loaded assets (none in MVP).

## Data retention

- `option_chain_snapshots`: keep 90 days hot, archive to object storage older than 90 days (P2+).
- `daily_decisions`: retained indefinitely (audit + ML training).
- `audit_log`: retained 1 year minimum.
- User-deletion: cascade deletes all rows tied to `user_id` except aggregated `audit_log` entries (which anonymize the user_id).

## Compliance posture

- The product is a **decision-support tool** for the user's own decisions; it is not a broker, advisor, or RIA platform.
- Disclaimers are explicit and persistent.
- No personalized advice language ("buy", "sell" \u2014 use "consider", "evaluate").
- Before any paid offering: legal review of disclaimers; SOC 2 Type 1 starting point; consider state securities counsel re: RIA status.

## Threat model (high-level)

| Threat | Mitigation |
|---|---|
| Credential theft | Argon2; rate limit; 30-day session expiry; refresh rotation |
| SQL injection | SQLAlchemy ORM only; raw SQL banned via lint rule |
| XSS | React + DOMPurify on user notes; CSP header (strict) |
| CSRF | SameSite=Strict cookies + double-submit token on mutating endpoints |
| Broker abuse | No broker write paths exist (CI invariant) |
| Data exfiltration | Cross-tenant queries blocked; per-user row scoping; RLS in P3 |
| Dependency CVE | Dependabot; pip-audit; npm audit |
| Misuse / overreliance | Disclaimers; confidence breakdown forces explainability |

## 16. Future ML/AI Enhancements

All ML upgrades replace specific deterministic engine nodes **without changing engine interfaces**. The V1 deterministic node always remains as a feature-flagged fallback and the baseline for backtesting.

## 16.1 Regime Classifier (P4 priority 1)

**Replace**: `engine.market_state.classify()` deterministic predicates.
**With**: Hidden Markov Model (states = 6 regimes, observations = `(iv_rank, iv_percentile, expected_move, max_pain_delta, pcr_volume, pcr_oi, trend_strength, days_to_event, gap_pct)`).

- Training data: `(state, decision, outcome)` triples + `actual_regime_realized` from outcomes table.
- Cross-validation: walk-forward by month.
- Success metric: classification accuracy on held-out fixtures \u2265 deterministic V1 + 5pp.
- Alternative: small transformer encoder over a 60-day window of features; same labels.

## 16.2 Flow Score Model (P4 priority 2)

**Replace**: `engine.flow_score.compute()` weighted composite.
**With**: Gradient-boosted regressor (LightGBM) trained on `(chain_features, T+5_directional_move)`.

- Features: OI walls, PCR breakdown, OI delta over 5 sessions, skew, dealer-gamma proxy, basis (futures vs spot if available).
- Output: bias probability vector + confidence (entropy-derived).
- Calibration: Platt scaling or isotonic regression on confidence.

## 16.3 Confidence Weight Recalibration (P4 priority 3)

**Replace**: hard-coded `weights.yaml`.
**With**: Gradient-free optimization (CMA-ES) over the 6 weights, maximizing realized outcome quality across `daily_decisions` history.

- Objective: weighted sum of `outcomes.decision_quality` (good=+1, neutral=0, bad=-1) for decisions where `outcome IS NOT NULL`.
- Constraint: `\u03a3|w| = 1`.
- Re-fit monthly; `weights_version` bumps.
- Backtest: replay last 6 months of decisions with new weights; ensure no regime regression.

## 16.4 Event-Impact Estimator (P4)

**New module**: predicts post-event spot move and IV change.

- Training: every `events` row joined with subsequent realized return + IV crush over T+1.
- Inputs: event kind, days-to-event, pre-event IV setup, surprise priors (analyst dispersion if available), historical event-day distribution for ticker.
- Output: distribution `(spot_change, iv_change)` 90% CI.
- Used in: Confidence Composer (sharpens `event_risk_penalty`); Scenario Simulator (replaces fixed-parameter scenarios with sampled realistic ones).

## 16.5 LLM-Narrated DailyDecision (P4)

**Augment**: `rationale[]` and `risks[]` are template-generated in V1.
**With**: small LLM (e.g. Claude Haiku-class) generates fluent prose conditioned on the structured `DailyDecision` payload + persona.

- Persona-tuned: Helen sees "balanced", Ravi sees "teach me", Diana sees "compliance-clean".
- Strict prompt: model must not invent numbers; only narrate what's in the payload.
- A/B test: users prefer LLM narration \u2265 60%; never replace structured output.
- Fallback: deterministic templates remain in shipped code.

## 16.6 Anomaly Detection on Chain Skew (P4)

**New module**: flags unusual chain configurations.

- Isolation Forest on `(skew_25d, term_structure_slope, oi_concentration_gini, pcr_volume, pcr_oi)`.
- Threshold tuned for 1-in-30 sessions.
- Adds `anomaly` tag to `market_state.tags` and an explicit warning on Today screen.

## 16.7 Vol-Surface Fitting (P4)

**Replace**: per-strike `iv` reads from chain.
**With**: SVI (Stochastic Volatility Inspired) parameterization fit per expiry.

- Smooths sparse/illiquid IVs.
- Produces consistent IV interpolation for hypothetical strikes (Scenario Simulator + What-If).
- Falls back to raw chain IV when fit residual exceeds threshold.

## 16.8 Monte Carlo Scenario Engine (P4)

Sample N paths from a regime-conditional GBM (or a more sophisticated stochastic-vol process) over horizon. Outputs a distribution over `position_pnl` and a probability-weighted recommended action. Surfaces percentiles in the scenario UI.

## ML governance

- Every shipped ML node has:
  - A feature flag with deterministic fallback.
  - A monitored drift metric (PSI on input features, Brier score on confidence calibration).
  - A versioned model artifact stored in object storage; `model_version` field added to `daily_decisions`.
- Model cards documented in `docs/models/`.
- Periodic backtest review (monthly) before any auto-deploy of recalibrated weights.

## 17. Development Milestones with Complexity

T-shirt sizes: **S** = 1 day, **M** = 2-3 days, **L** = 4-5 days, **XL** = > 5 days. All estimates assume one focused engineer.

## Phase 0 — Foundation (1 week)

| ID | Milestone | Size |
|---|---|---|
| M0.1 | pnpm + uv monorepo bootstrap; Docker Compose | S |
| M0.2 | Postgres schema + Alembic + seed | M |
| M0.3 | FastAPI shell + `/healthz` + `/version` + JWT scaffolding | S |
| M0.4 | Next.js 16.2.4 shell + shadcn/ui + Tailwind + Disclaimer gate | S |
| M0.5 | CI pipelines (lint, typecheck, unit, integration) | S |
| M0.6 | `regimes.py` + `profiles.py` + Pydantic schemas + TS type generation | S |
| M0.7 | End-to-end smoke test (`docker compose up` → `/healthz`) | S |

## Phase 1 — Engine MVP (4 weeks)

| ID | Milestone | Size |
|---|---|---|
| M1.1 | IV rank/percentile + HV computations | S |
| M1.2 | Max pain + expected move + PCR | S |
| M1.3 | Trend strength proxy + technical context | S |
| M1.4 | Market State Engine + 24 regime fixtures | L |
| M1.5 | Flow Score Engine + OI walls + dealer-gamma proxy | M |
| M1.6 | Black-Scholes + Greeks + IV solver + golden vectors | M |
| M1.7 | Strike Selector core + intents + tests | L |
| M1.8 | Recommendation Engine + regime-strategy whitelist | M |
| M1.9 | Recommendation Engine: 8 YAML rules + tests | M |
| M1.10 | Confidence Composer + weights.yaml + component fns | M |
| M1.11 | Execution Feasibility Module (liquidity, spread, slippage, fill) | M |
| M1.12 | Execution downgrade callback into Strike Selector | S |
| M1.13 | Master Decision Engine orchestration + DailyDecision schema | M |
| M1.14 | `/engine/daily-plan` + `/engine/recommend` endpoints | S |
| M1.15 | `/engine/what-if` + `/engine/market-state` + `/engine/flow-score` | S |
| M1.16 | `/engine/strike-candidates` + `/engine/execution-check` | S |
| M1.17 | `/profile` + `/outcomes` + CSV upload endpoints | M |
| M1.18 | Today screen scaffolding + DecisionCard + StrategyTitle | M |
| M1.19 | ActionList + ActionRow + ExecutionBadge | S |
| M1.20 | ConfidenceBreakdownChart + ExecutionFeasibilityPanel | S |
| M1.21 | WatchLevels + Drawer (Rationale, Risks, Invalidation) | S |
| M1.22 | User Strategy Profile UI + persona presets | M |
| M1.23 | Outcome manual entry + history view | M |
| M1.24 | Golden tests (12 DailyDecision snapshots) | M |
| M1.25 | Calibration tests + Playwright E2E + polish | M |

**Phase 1 size**: ~XL aggregate (4 weeks).


## Phase 1.5 — Enhancement E1: GEX Module (~2 weeks, post-M1.25)

Per [ADR-0008](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/decisions/0008-enhancement-adoption-roadmap.md), Phase 1.5 ships the GEX (Gamma Exposure) module as the first adopted enhancement. It replaces the `dealer_gamma_proxy` heuristic from M1.5 with a real `GexResult` (gamma flip, call/put walls, `gex_em_ratio`).

| ID | Milestone | Size |
|---|---|---|
| ME1.0 | ADR amending FlowScore V1 contract (`dealer_gamma_proxy` → `gex_context`) | S |
| ME1.1 | `packages/engine/engine/gex/` module: `compute_gex()` + `GexResult` + tests | M |
| ME1.2 | Flow Score Engine integration (replace dealer_gamma_proxy) | S |
| ME1.3 | Strike Selector + Collar Builder GEX-aware ranking | S |
| ME1.4 | Recommendation rules: 2 GEX-aware rules in `rules.yaml` | S |
| ME1.5 | `POST /engine/gex` endpoint | S |
| ME1.6 | `DailyDecision.gex_context` + Today screen `GexContextStrip` | M |
| ME1.7 | `/gex` drill-down: `GEXByStrikeChart` + `CumulativeGexChart` | M |

Bumps `engine.__version__` to `0.3.0` (per ADR-0005).

## Phase 2 — Data & Drill-downs (2-3 weeks)

| ID | Milestone | Size |
|---|---|---|
| M2.1 | Provider abstraction interface | S |
| M2.2 | YfinanceProvider + tests | S |
| M2.3 | TradierProvider + integration tests against recorded responses | M |
| M2.4 | Cron jobs (Arq) + IV backfill | M |
| M2.5 | FRED FOMC ingestion | S |
| M2.6 | Chain drill-down screen | M |
| M2.7 | IV Profile / Term Structure screen | M |
| M2.8 | Max Pain & Expected Move screen | S |
| M2.9 | Payoff diagram component + screen | M |
| M2.10 | Event Calendar screen | S |
| M2.11 | Settings UI for User Strategy Profile (full editor) | S |
| M2.12 | Staleness flags + UI badges | S |


> **Enhancement work in Phase 2** (per [ADR-0008](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/decisions/0008-enhancement-adoption-roadmap.md)): adopted modules **E2** (Vol Surface & Skew), **E3 partial** (`pnl_by_price` + `scenario_table` + 2D drill-down), **E4 display-only** (Earnings Gap Score, surfaced when event_in_14d, NOT folded into Confidence Composer math), **E5** (Vol Premium Tracker, bundled with E2), and **E8** (Dividend-Aware Pricing) ship inside this phase. Sequencing inside Phase 2 is left to that phase's planning round; data dependencies (Tradier/Polygon) gate E2 and E5.

## Phase 3 — Decision Simulator + Playbook + Outcome Auto-fill (3 weeks)

| ID | Milestone | Size |
|---|---|---|
| M3.1 | Decision-based scenario simulator (6 scenarios) | L |
| M3.2 | `/sim` screen with per-scenario action cards | M |
| M3.3 | 12-month playbook generator | L |
| M3.4 | `/playbook` screen + PDF export | M |
| M3.5 | Outcome auto-fill heuristics | M |
| M3.6 | Watch-level alerting (email + in-app) | M |
| M3.7 | Partial coverage refinement | S |
| M3.8 | Gamma-aware execution hints | S |
| M3.9 | Tax-aware roll enforcement (LTCG, wash-sale buffer) | M |
| M3.10 | Calibration test suite (rubric + CI integration) | M |


> **Enhancement work in Phase 3** (per [ADR-0008](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/decisions/0008-enhancement-adoption-roadmap.md)): adopted module **E9** (Assignment Risk Module — depends on E8 from Phase 2) ships in this phase. **E3's 3D Plotly surface** ships here only if Phase 2's 2D drill-down click-through justifies the UI investment. **E6 (Multi-Expiry)** and **E7 (Backtest)** are deferred and re-evaluated post-Phase-3.

## Phase 4 — ML/AI + Brokerage (open-ended)

| ID | Milestone | Size |
|---|---|---|
| M4.1 | HMM regime classifier (training + serving) | XL |
| M4.2 | Transformer regime classifier (alternative) | XL |
| M4.3 | Flow Score gradient-boosted model | L |
| M4.4 | Confidence weight recalibration via CMA-ES | L |
| M4.5 | Event-impact estimator | L |
| M4.6 | LLM-narrated rationale (persona-tuned) | M |
| M4.7 | Anomaly detection (Isolation Forest) | M |
| M4.8 | SVI vol-surface fitting | L |
| M4.9 | Monte Carlo scenario engine | L |
| M4.10 | IBKR read-only integration | XL |
| M4.11 | Multi-ticker UI | L |
| M4.12 | Mobile-responsive Today screen | M |

---

## Patch v1.1 — Additional Phase 1 milestones

| ID | Milestone | Size |
|---|---|---|
| M1.4a | `iv_score()` + `structure_score()` + `event_score()` pure fns + tests (100% line coverage) | M |
| M1.5a | `gamma_score()` pure fn + tests | S |
| M1.5b | Flow Score V1 contract refit: bullish/bearish/pin/gamma_risk/recommended_action/explanation | M |
| M1.11a | Collar Builder engine: `build()` with 3 intents (zero_cost, income, defensive) | L |
| M1.11b | Collar Builder integration with Master Decision Engine (event-regime auto-call) | M |
| M1.16a | `POST /engine/collar-builder` route + tests | S |
| M1.16b | `GET /health` + `/healthz` alias + `/version` + `GET /market/msft/latest` | S |

**Phase 1 revised total**: ~5 weeks (was 4) to absorb Collar Builder + scoring module + new endpoints.

### Day-by-day insertions into §19

| Day | Insertion |
|---|---|
| 12.5 | M1.4a (iv/structure/event scoring pure fns + 100% coverage tests) |
| 14.5 | M1.5a (gamma_score pure fn + tests) |
| 17.5 | M1.5b (Flow Score V1 contract refit using scoring module) |
| 26.5 | M1.11a (Collar Builder engine) |
| 27.0 | M1.11b (Collar Builder integration with Master Decision Engine) |
| 27.5 | M1.16a + M1.16b (collar + health + market/latest endpoints) |

The Phase 1 ship date moves from Day 35 to **Day 40**. The Definition of Phase 1 Done in §19 expands:
- 24/24 regime fixtures pass with ≥ 80% accuracy
- 12/12 golden DailyDecision snapshots match
- 5/5 scoring functions at 100% line coverage
- 3/3 Collar Builder intents return valid structures on the seed fixture
- 4/4 Playwright E2E flows green
- `pytest --cov=packages/engine` ≥ 85% (raised from 80% due to scoring requirement)
- One real CSV upload (Helen-shaped position) generates a coherent `DailyDecision` and a coherent collar set in < 5s

## 18. Recommended Repo Structure

```
msft-options-engine/
├── apps/
│   ├── web/                              # Next.js 16.2.4
│   │   ├── app/
│   │   │   ├── layout.tsx                # root: Disclaimer gate, theme, auth ctx
│   │   │   ├── page.tsx                  # redirect -> /today
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx
│   │   │   │   └── register/page.tsx
│   │   │   ├── today/
│   │   │   │   ├── page.tsx              # SERVER component
│   │   │   │   ├── loading.tsx
│   │   │   │   └── error.tsx
│   │   │   ├── settings/page.tsx
│   │   │   ├── outcomes/page.tsx
│   │   │   ├── chain/page.tsx            # P2
│   │   │   ├── iv/page.tsx               # P2
│   │   │   ├── max-pain/page.tsx         # P2
│   │   │   ├── payoff/page.tsx           # P2
│   │   │   ├── events/page.tsx           # P2
│   │   │   ├── sim/page.tsx              # P3
│   │   │   └── playbook/page.tsx         # P3
│   │   ├── components/
│   │   │   ├── ui/                       # shadcn primitives
│   │   │   ├── today/
│   │   │   │   ├── DailyDecisionCard.tsx
│   │   │   │   ├── MarketStateBadge.tsx
│   │   │   │   ├── ActionList.tsx
│   │   │   │   ├── ActionRow.tsx
│   │   │   │   ├── ExecutionBadge.tsx
│   │   │   │   ├── ConfidenceBreakdownChart.tsx
│   │   │   │   ├── ExecutionFeasibilityPanel.tsx
│   │   │   │   ├── WatchLevels.tsx
│   │   │   │   ├── RationaleDrawer.tsx
│   │   │   │   ├── RisksDrawer.tsx
│   │   │   │   ├── InvalidationList.tsx
│   │   │   │   ├── DataFreshnessBadge.tsx
│   │   │   │   └── DisclaimerFooter.tsx
│   │   │   ├── settings/
│   │   │   │   └── UserStrategyProfileForm.tsx
│   │   │   └── charts/
│   │   │       ├── StackedConfidenceBar.tsx
│   │   │       ├── PayoffDiagram.tsx     # P2
│   │   │       ├── IvTermStructure.tsx   # P2
│   │   │       └── MaxPainBar.tsx        # P2
│   │   ├── lib/
│   │   │   ├── api.ts                    # fetch wrappers + JWT
│   │   │   ├── auth.ts                   # NextAuth config
│   │   │   └── format.ts                 # money/percent/date formatters
│   │   ├── tests/
│   │   │   ├── e2e/
│   │   │   │   ├── disclaimer.spec.ts
│   │   │   │   ├── csv-to-today.spec.ts
│   │   │   │   ├── profile-change.spec.ts
│   │   │   │   └── outcome-entry.spec.ts
│   │   │   └── unit/
│   │   ├── package.json                  # "next": "16.2.4" exact
│   │   ├── tsconfig.json
│   │   ├── tailwind.config.ts
│   │   ├── next.config.ts
│   │   └── playwright.config.ts
│   ├── api/                              # FastAPI
│   │   ├── app/
│   │   │   ├── main.py                   # FastAPI app
│   │   │   ├── deps.py                   # auth, db session deps
│   │   │   ├── core/
│   │   │   │   ├── config.py             # pydantic-settings
│   │   │   │   ├── security.py           # JWT, hashing
│   │   │   │   └── logging.py
│   │   │   ├── routers/
│   │   │   │   ├── engine.py             # /engine/* primary
│   │   │   │   ├── outcomes.py
│   │   │   │   ├── profile.py
│   │   │   │   ├── data.py               # /data/* + CSV upload
│   │   │   │   └── auth.py
│   │   │   ├── schemas/                  # Pydantic (mirrors packages/engine types)
│   │   │   ├── models/                   # SQLAlchemy ORM
│   │   │   ├── services/                 # orchestration helpers
│   │   │   │   ├── decision_service.py   # hydrates EngineInputs, persists DailyDecision
│   │   │   │   └── csv_import.py
│   │   │   ├── db/
│   │   │   │   ├── session.py
│   │   │   │   ├── base.py
│   │   │   │   └── migrations/           # alembic
│   │   │   └── tests/
│   │   │       ├── conftest.py
│   │   │       ├── test_engine_routes.py
│   │   │       ├── test_outcomes.py
│   │   │       ├── test_profile.py
│   │   │       └── test_csv_import.py
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   └── Dockerfile
│   └── jobs/                             # Scheduled ingestion (P2+)
│       ├── jobs/
│       │   ├── __init__.py
│       │   ├── runner.py                 # Arq worker bootstrap
│       │   ├── ingest_chain.py
│       │   ├── compute_iv.py
│       │   ├── refresh_events.py
│       │   ├── precompute_decisions.py
│       │   └── auto_outcome.py           # P3
│       ├── pyproject.toml
│       └── Dockerfile
├── packages/
│   ├── engine/                           # PYTHON — the product
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── version.py                # __version__ (semver)
│   │   │   ├── regimes.py
│   │   │   ├── profiles.py
│   │   │   ├── types.py                  # shared dataclasses
│   │   │   ├── market_state/
│   │   │   │   ├── __init__.py           # classify()
│   │   │   │   ├── predicates.py
│   │   │   │   ├── iv_metrics.py         # IV rank/percentile
│   │   │   │   ├── max_pain.py
│   │   │   │   ├── expected_move.py
│   │   │   │   ├── pcr.py
│   │   │   │   └── trend.py
│   │   │   ├── flow_score/
│   │   │   │   ├── __init__.py           # compute()
│   │   │   │   ├── oi_walls.py
│   │   │   │   └── dealer_gamma.py
│   │   │   ├── strike_selector/
│   │   │   │   ├── __init__.py           # select()
│   │   │   │   ├── filters.py
│   │   │   │   └── ranking.py
│   │   │   ├── recommendation/
│   │   │   │   ├── __init__.py           # recommend()
│   │   │   │   ├── rules_loader.py
│   │   │   │   └── strategy_templates.py
│   │   │   ├── decision/
│   │   │   │   ├── __init__.py           # produce_daily_decision()
│   │   │   │   ├── orchestrator.py
│   │   │   │   └── intent_inference.py
│   │   │   ├── confidence/
│   │   │   │   ├── __init__.py           # compose()
│   │   │   │   ├── components.py
│   │   │   │   └── weights.py
│   │   │   ├── execution/
│   │   │   │   ├── __init__.py           # assess()
│   │   │   │   ├── liquidity.py
│   │   │   │   └── slippage.py
│   │   │   ├── outcomes/
│   │   │   │   ├── __init__.py
│   │   │   │   └── auto_fill.py          # P3
│   │   │   ├── payoff/
│   │   │   │   ├── __init__.py           # bs_price, bs_greeks, iv_solve
│   │   │   │   ├── black_scholes.py
│   │   │   │   ├── greeks.py
│   │   │   │   ├── iv_solver.py
│   │   │   │   └── pl.py                 # terminal_pl, breakevens
│   │   │   ├── scenarios/
│   │   │   │   ├── __init__.py           # simulate_scenarios()
│   │   │   │   └── scenarios.py
│   │   │   ├── providers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── csv_provider.py
│   │   │   │   ├── yfinance_provider.py  # P2
│   │   │   │   ├── tradier_provider.py   # P2
│   │   │   │   ├── polygon_provider.py   # P2 paid
│   │   │   │   └── ibkr_provider.py      # P4
│   │   │   ├── config/
│   │   │   │   ├── weights.yaml
│   │   │   │   └── rules.yaml
│   │   │   └── utils/
│   │   │       ├── hashing.py            # inputs_hash
│   │   │       └── math_utils.py         # clip01, sigmoid, norm
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   ├── fixtures/
│   │   │   │   ├── regimes/              # 24 fixtures
│   │   │   │   ├── decisions/            # 12 golden DailyDecision snapshots
│   │   │   │   └── chain/
│   │   │   ├── test_market_state.py
│   │   │   ├── test_flow_score.py
│   │   │   ├── test_strike_selector.py
│   │   │   ├── test_recommendation.py
│   │   │   ├── test_decision.py
│   │   │   ├── test_confidence.py
│   │   │   ├── test_execution.py
│   │   │   ├── test_payoff.py
│   │   │   ├── test_scenarios.py
│   │   │   └── test_property.py          # hypothesis
│   │   └── pyproject.toml
│   └── shared-types/                     # TS types from Pydantic
│       ├── package.json
│       ├── src/
│       │   ├── index.ts                  # generated
│       │   └── manual.ts                 # hand-curated extras
│       └── scripts/
│           └── generate.sh               # datamodel-code-generator
├── docs/
│   ├── architecture.md
│   ├── engine.md
│   ├── operations.md
│   ├── data-formats.md
│   └── models/                           # P4 model cards
├── scripts/
│   ├── check_no_broker_imports.sh
│   └── seed_local.py
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── deploy-staging.yml
│       └── deploy-prod.yml
├── docker-compose.yml
├── pnpm-workspace.yaml
├── pyproject.toml                        # uv workspace root
├── uv.lock
├── pnpm-lock.yaml
├── README.md
├── LICENSE
└── .gitignore
```

## Workspace conventions

- Python: `uv` workspaces; each `apps/*` and `packages/engine` has its own `pyproject.toml` with `tool.uv.workspace`.
- TypeScript: `pnpm` workspaces; `packages/shared-types` referenced from `apps/web` via `workspace:*`.
- Common scripts at root: `make dev`, `make test`, `make lint`, `make migrate`, `make e2e`.

---

## Patch v1.1 — Repo additions

New subdirectories under `packages/engine/engine/`:

```
packages/engine/engine/
  collar_builder/
    __init__.py
    build.py                    # build() entry
    structures.py               # zero_cost / income / defensive solvers
    leg_factory.py              # CollarLeg from chain quotes
  scoring/
    __init__.py
    iv.py                       # iv_score()
    structure.py                # structure_score()
    gamma.py                    # gamma_score()
    event.py                    # event_score()
    types.py                    # IvScoreResult, StructureScoreResult, ...
  flow_score/                   # existing, refactored to consume scoring/
    __init__.py                 # compute() (V1 contract orchestrator)
    decision_tree.py            # recommended_action decision tree
    explanations.py             # render_explanation()
```

New tests under `packages/engine/tests/`:

```
packages/engine/tests/
  test_collar_builder.py        # 3 intents + property tests
  test_scoring_iv.py
  test_scoring_structure.py
  test_scoring_gamma.py
  test_scoring_event.py
  test_flow_score_v1.py         # V1 contract conformance tests
  fixtures/
    collars/                    # 3 named fixtures (one per intent)
    scoring/                    # per-fn fixture sets
```

---

## Phase 1 monorepo simplification (locked)

To keep MVP scope manageable, **Phase 1 consolidates `apps/jobs` into `apps/api`**. There is no separate jobs process in P1; cron is not needed because P1 ingests via manual CSV upload only.

```
apps/api/app/
  jobs/                         # P1: stub package; relocates to apps/jobs/ in P2
    __init__.py
    runner.py                   # placeholder (raises NotImplementedError until P2)
```

`docker-compose.yml` (P1): drop the `jobs` service. Add it back in P2.

This is purely an operational simplification. The package boundary remains clean: `apps/api/app/jobs/` imports from `packages/engine` like the rest of the API. Splitting it out in P2 is a `git mv` plus a service entry in `docker-compose.yml`.

The §18 v1.0 directory tree shows `apps/jobs/` for completeness; treat it as **P2-and-later** until P2 begins.

## 19. Implementation Order (Day-by-Day, Phase 0 + Phase 1)

This is a 35-day sequence for delivering Phase 0 + Phase 1 (the engine-first MVP). Phase 2/3/4 day-by-day plans are produced in subsequent planning sessions once Phase 1 ships.

## Phase 0 — Days 1-7

| Day | Deliverable | Files touched |
|---|---|---|
| 1 | pnpm + uv workspaces; `docker-compose.yml` stub; `.gitignore`; root `README.md`; root `Makefile` | `pnpm-workspace.yaml`, `pyproject.toml`, `docker-compose.yml`, `.gitignore`, `README.md` |
| 2 | Postgres schema (Alembic migration `0001_init`) covering ALL §6 tables; seed user; seed MSFT ticker config | `apps/api/app/db/migrations/versions/0001_init.py`, `apps/api/app/db/base.py`, `scripts/seed_local.py` |
| 3 | FastAPI shell: `main.py`, `/healthz`, `/version`, JWT scaffolding, settings via pydantic-settings | `apps/api/app/main.py`, `apps/api/app/core/{config,security}.py` |
| 4 | Next.js 16.2.4 shell + shadcn/ui + Tailwind + Disclaimer gate modal; auth pages stubs | `apps/web/app/layout.tsx`, `apps/web/components/ui/*`, `apps/web/components/today/DisclaimerFooter.tsx`, `apps/web/lib/auth.ts` |
| 5 | CI (`.github/workflows/ci.yml`): lint, typecheck, unit, integration. Pre-commit hooks (ruff, eslint, prettier). Dependabot config. | `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.github/dependabot.yml` |
| 6 | `regimes.py` enum + `REGIME_SPEC`; `profiles.py` types; root Pydantic schemas in `packages/engine/engine/types.py`; TS type generation script + check | `packages/engine/engine/regimes.py`, `packages/engine/engine/profiles.py`, `packages/engine/engine/types.py`, `packages/shared-types/scripts/generate.sh` |
| 7 | E2E smoke: `docker compose up`, hit `/healthz`, hit `/today` (placeholder), Playwright baseline test passes. Tag `v0.0.1-phase0` | `apps/web/tests/e2e/smoke.spec.ts` |

## Phase 1 Week 1 — Days 8-14: Market State Engine

| Day | Deliverable | Files |
|---|---|---|
| 8 | IV rank + IV percentile pure functions (`iv_metrics.py`); HV computations from price series. Unit tests with synthetic data. | `packages/engine/engine/market_state/iv_metrics.py`, tests |
| 9 | Max pain computation (sum-of-pain across strikes for an expiry); expected move (ATM straddle ± rule). | `market_state/max_pain.py`, `expected_move.py`, tests |
| 10 | PCR (volume + OI); trend strength proxy (ADX-style on price series); aggregate `MarketStateInputs` builder. | `market_state/pcr.py`, `trend.py` |
| 11 | Regime predicates: 6 score functions returning [0,1]. Unit tests on synthetic inputs. | `market_state/predicates.py` |
| 12 | `classify()` orchestrator: evaluate predicates, pick max with conservative tie-break, emit `tags`, `MarketStateResult`. | `market_state/__init__.py` |
| 13 | 24 regime fixtures: `tests/fixtures/regimes/*.json` (12 obvious + 12 edge cases). `test_market_state.py` validates ≥ 80% accuracy. | fixtures + `test_market_state.py` |
| 14 | `inputs_hash` utility (`utils/hashing.py`); persist `market_states` row from API; `POST /engine/market-state` route. | `engine/utils/hashing.py`, `apps/api/app/routers/engine.py` |

## Phase 1 Week 2 — Days 15-21: Flow Score + Payoff + Strike Selector

| Day | Deliverable | Files |
|---|---|---|
| 15 | OI walls computation (`oi_walls.py`); PCR breakdown by expiry; tests. | `flow_score/oi_walls.py`, tests |
| 16 | Dealer-gamma proxy; skew tilt; bias mapping; `compute()` for Flow Score; tests. | `flow_score/dealer_gamma.py`, `flow_score/__init__.py` |
| 17 | Black-Scholes (`black_scholes.py`) + Greeks (`greeks.py`); golden vector tests against py_vollib. | `payoff/black_scholes.py`, `payoff/greeks.py`, `tests/test_payoff.py` |
| 18 | IV solver (Brent) + property tests for round-trip. `terminal_pl()` + `breakevens()` for multi-leg. | `payoff/iv_solver.py`, `payoff/pl.py` |
| 19 | Strike Selector filters (`filters.py`): delta band, DTE band, OI/volume floors, spread floor. | `strike_selector/filters.py` |
| 20 | Strike Selector ranking (`ranking.py`): premium-per-day-per-delta + S/R alignment + tag bonuses. `select()` orchestrator. | `strike_selector/__init__.py`, `ranking.py` |
| 21 | `POST /engine/flow-score` + `POST /engine/strike-candidates` routes with input hydration; integration tests. | `apps/api/app/routers/engine.py`, `apps/api/app/services/decision_service.py` |

## Phase 1 Week 3 — Days 22-28: Recommendation + Confidence + Execution + Master Decision

| Day | Deliverable | Files |
|---|---|---|
| 22 | Strategy templates (8 of them: SELL_COVERED_CALL_PARTIAL, OPEN_COLLAR, ROLL_UP_AND_OUT, REDUCE_COVERAGE, …). Maps regime → strategy → action template. | `recommendation/strategy_templates.py` |
| 23 | `rules.yaml` with the 8 V1 rules (predicate + emit + rationale + risks + invalidation). YAML loader with schema validation. | `engine/config/rules.yaml`, `recommendation/rules_loader.py` |
| 24 | `recommend()` orchestrator: whitelist filter, rule-fire scoring, tie-break by drawdown impact, action assembly with selected strikes. Tests with positive + negative fixtures per rule. | `recommendation/__init__.py`, `tests/test_recommendation.py` |
| 25 | `confidence/components.py` (per-component pure fns); `confidence/weights.py` (loader + sum-to-1 validation); `compose()` returning `(confidence, ConfidenceBreakdown)`. Tests. | `confidence/*` + `tests/test_confidence.py` |
| 26 | Execution Feasibility: `liquidity.py` (liquidity_score), `slippage.py` (expected_slippage); `assess()` aggregator producing `Execution`. Tests. | `execution/*` + `tests/test_execution.py` |
| 27 | Execution downgrade callback: if any leg `fill_confidence < 0.5`, re-run Strike Selector with adjusted filters. Integration test. | `execution/__init__.py`, integration test |
| 28 | Master Decision Engine: `produce_daily_decision()` orchestrator that wires all engines + Confidence + Execution; assembles `DailyDecision` payload with `inputs_hash`, versions, `data_freshness`, disclaimers. | `decision/orchestrator.py`, `decision/__init__.py`, `decision/intent_inference.py` |

## Phase 1 Week 4 — Days 29-35: API + Today UI + Tests + Polish

| Day | Deliverable | Files |
|---|---|---|
| 29 | `POST /engine/daily-plan` (the headline endpoint) + `POST /engine/recommend` + `POST /engine/what-if` + `POST /engine/execution-check`. Persistence to `daily_decisions`. Integration tests. | `apps/api/app/routers/engine.py`, `services/decision_service.py` |
| 30 | `GET/PUT /profile`; `GET/POST/PATCH /outcomes`; CSV upload endpoints (`/data/positions/import-csv`, etc.). Multipart parsing + validation. | `routers/{profile,outcomes,data}.py`, `services/csv_import.py` |
| 31 | Today screen scaffolding: server-component `today/page.tsx` fetches DailyDecision; `DailyDecisionCard`, `MarketStateBadge`, `StrategyTitle`. Persona-tinted regime color tokens. | `apps/web/app/today/*`, `components/today/{DailyDecisionCard, MarketStateBadge, StrategyTitle}.tsx` |
| 32 | `ActionList` + `ActionRow` + `ExecutionBadge` (with fill-confidence icon, spread bps, suggested order type). | `components/today/{ActionList, ActionRow, ExecutionBadge}.tsx` |
| 33 | `ConfidenceBreakdownChart` (stacked bar with labels + numeric values, accessible) + `ExecutionFeasibilityPanel` + `WatchLevels` + `DataFreshnessBadge`. | `components/today/*`, `components/charts/StackedConfidenceBar.tsx` |
| 34 | Drawer components (Rationale, Risks, Invalidation, Next Trigger). Settings page with `UserStrategyProfileForm` + persona presets. Outcomes page (manual entry + history). | `components/today/{RationaleDrawer, RisksDrawer, InvalidationList}.tsx`, `app/settings/page.tsx`, `app/outcomes/page.tsx` |
| 35 | 12 golden DailyDecision snapshot tests; calibration test (regime accuracy on 24 fixtures); 4 Playwright E2E flows; bug bash; tag `v0.1.0-phase1`. | `tests/fixtures/decisions/*.json`, `tests/test_decision.py`, `apps/web/tests/e2e/*.spec.ts` |

## Daily ritual

Each day:
1. Branch from `staging` as `feat/M1.X-name`.
2. Implement smallest viable slice; commit with conventional-commit message.
3. Open PR; CI must be green; squash-merge to `staging`.
4. Smoke-test in staging.
5. Update Working Doc (\u00a710 in this thread) Plan Tasks to checked.
6. End-of-day: 1-paragraph "what shipped, what's blocked" note in `docs/dev-log/YYYY-MM-DD.md`.

## Definition of "Phase 1 Done"

- All 25 M1.* milestones merged to `main`.
- 24/24 regime fixtures pass with ≥ 80% accuracy.
- 12/12 golden DailyDecision snapshots match.
- 4/4 Playwright E2E flows green.
- `pytest --cov=packages/engine` ≥ 80%.
- `mypy --strict packages/engine` clean.
- One real CSV upload (Helen-shaped position) generates a coherent `DailyDecision` in < 5s on a M3 MacBook.
- Tag `v0.1.0-phase1`, deploy to staging, demo.

## 20. Risks & Open Questions

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **Regime mis-classification** — V1 deterministic predicates wrongly label a regime, leading to a wrong strategy whitelist | Med | High | 24 historical fixtures with ≥ 80% CI threshold; conservative tie-break; confidence breakdown forces explainability; Phase 4 ML upgrade path |
| 2 | **Confidence mis-calibration** — `confidence: 0.78` doesn't translate to 78% empirical success | High at first | Med | Outcome tracking from day 1 (manual P1, auto P3); calibration tests bin-by-confidence in CI; Phase 4 weight recalibration via CMA-ES |
| 3 | **Execution-layer over-confidence** — `fill_confidence: 0.75` doesn't translate to real-world fill | Med | Med | Conservative defaults; user can flag bad fills via outcomes; downgrade callback for `fill_confidence < 0.5`; tunable thresholds |
| 4 | **Data accuracy** — yfinance/Tradier delays; sparse OI/volume on illiquid strikes; missing IV history | High | High | Provider abstraction; staleness flags surfaced in UI; CSV manual fallback always available; `data_freshness` on every decision |
| 5 | **IV history availability** — backfilling 252-day IV history requires data we may not have for free | High | Med | Phase 2 paid Polygon for backfill; or compute forward-only with explicit "incomplete history" warning until 252 days accumulate |
| 6 | **Vendor API churn** — Tradier/Polygon API changes, deprecations | Med | Med | Provider abstraction; integration tests against recorded VCR responses; quarterly health check script |
| 7 | **Regulatory exposure** — even with disclaimers, options-recommendation language could attract scrutiny if monetized | Low (MVP, single user); Med (paid) | High | Educational framing; manual outcome entry; no execution; consult securities counsel before paid offering; consider RIA implications |
| 8 | **Outcome attribution noise** — short-horizon PnL is noisy; mis-labeling `decision_quality` | High | Med | Use 7+ day horizons by default; user manual override; bin-based calibration not point-based; multiple horizons in P3 |
| 9 | **Engine version drift** — old decisions evaluated under new weights or rules | Low | Med | `engine_version` + `weights_version` stamped on every row; replay tests gate weight changes; downgrade migrations required |
| 10 | **UI scope creep** — feature creep adding dashboards before engines stabilize | Med | High | Phase gates; PR template question "Is this engine-first?"; drill-downs locked to Phase 2+ |
| 11 | **Pricing model assumptions** — Black-Scholes ignores American exercise, dividends approximated | Always | Low (MVP) | Acknowledged in `payoff/` docstring; switch to binomial for ATM short-dated puts in P3; dividend yield configurable |
| 12 | **Performance at scale** — `option_chain_snapshots` grows fast (~200k rows/day per ticker if 30-min cadence) | Low (single user); High (multi-user) | Med | Partition by month in P2; archive >90 days to object storage; index review |
| 13 | **Disclaimer fatigue** — users dismiss without reading | High | Med | First-run modal with scroll-to-bottom; persistent footer; disclaimer also injected into `DailyDecision.disclaimers` so even API consumers see it |
| 14 | **Single-point-of-failure: engine maintainer** — encoded rules and weights are tacit knowledge | Med | Med | `rules.yaml` is plain-text and reviewable; `docs/engine.md` documents predicate intent; per-rule fixtures encode behavior |
| 15 | **Tax-aware advice could be wrong** | Low (MVP excludes); Med (P3) | High | Schema field exists in MVP but engine logic is P3; tax warnings only, not advice; user must consult tax pro |
| 16 | **Black-swan / model failure** — engine recommends in a market state it has never seen (COVID, flash crash) | Low | High | "Anomaly" tag (P4) flags unusual chains; explicit invalidation criteria on every decision; user-facing "low-confidence" UI state when components disagree |
| 17 | **Wrong delta target band defaults** for some users | Med | Low | Persona presets (Helen, Ravi, Diana) provide opinionated defaults; visible in Settings; tested as part of profile-change E2E |
| 18 | **CSV upload errors silently drop rows** | Med | Med | Multipart endpoint returns `{ inserted, updated, errors[] }`; UI shows error rows; refuse to compute decision if essential data missing |

## Open questions (carryover defaults; flag if any need to change before implementation)

1. **Single-user MVP, auth-ready architecture.** Confirm.
2. **Tradier sandbox as default Phase-2 chain provider.** Confirm or pick Polygon.
3. **EOD acceptable for MVP, intraday on demand.** Confirm.
4. **Hosting**: Vercel + Fly.io + Neon. Confirm or specify alt.
5. **Local-first via Docker Compose**. Confirm.
6. **Tax-aware roll enforcement** in Phase 3+, schema field in MVP. Confirm.
7. **MSFT-only UI; ticker-agnostic data model.** Confirm.
8. **Confidence weight defaults**: `w_flow=0.25, w_struct=0.20, w_regime=0.20, w_signal=0.15, w_event=0.10, w_liquidity=0.10`. Accept or adjust.
9. **Regime taxonomy** locked to 6: `HIGH_IV_EVENT`, `HIGH_IV_PIN`, `LOW_IV_TREND`, `LOW_IV_RANGE`, `BREAKOUT`, `POST_EVENT_REPRICE`. Accept or expand/rename.
10. **User Strategy Profile fields** as listed in §9.9. Accept or extend.
11. **Encoded V1 rules** — 8 in `rules.yaml`. Accept the eight from the brief or add/remove.
12. **6 named scenarios** in §12. Accept or adjust parameters.
13. **24 historical regime fixtures** — should I propose specific dates (e.g. earnings weeks of FY24-FY26) for the fixtures?
14. **Calibration thresholds** — regime accuracy ≥ 80% for CI green. Accept or pick a different bar.
15. **Persona presets** (Helen, Ravi, Diana) shipped in Settings UI. Accept the three or add more.
16. **PDF export** of playbook in P3 — mandatory or nice-to-have?
17. **Watch-level alerts** (P3) — email-only or also in-app? Push notifications later?
18. **LLM narration** (P4) — any constraint on which LLM (cost, on-prem, vendor)?

## Implementation kick-off prerequisites

Before any code is written, confirm:
- [ ] Hosting account access (Vercel, Fly.io, Neon) — or substitute targets
- [ ] Provider API keys decided (Tradier sandbox sufficient for P2?)
- [ ] Repo location (GitHub org / personal)
- [ ] Initial position CSV from the user (Helen-shape) for first golden test
- [ ] Domain name (optional for MVP; required for P2)

When the above are checked, the day-by-day plan in §19 starts at Day 1 (M0.1).

## 21. API Examples & Seed Data

All examples assume:
- API base: `http://localhost:8000/api/v1`
- JWT in shell env: `$TOKEN`
- User has uploaded positions + chain via `/data/*/import-csv` (or run `scripts/seed_local.py`)

## Health & version

```bash
curl http://localhost:8000/api/v1/health
```
```json
{ "status":"ok", "uptime_seconds": 3210, "db":"ok",
  "version":"0.1.0", "engine_version":"0.1.0", "weights_version":"v1.0" }
```

```bash
curl http://localhost:8000/api/v1/version
```
```json
{ "version":"0.1.0", "engine_version":"0.1.0", "weights_version":"v1.0",
  "git_sha":"a1b2c3d", "build_time":"2026-04-29T18:30:00Z" }
```

## DailyDecision (the headline endpoint)

```bash
curl -X POST http://localhost:8000/api/v1/engine/daily-plan \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "ticker": "MSFT" }'
```

Response (abridged for brevity; full schema in \u00a77 + \u00a79):

```jsonc
{
  "decision_id": "dd_2026_04_29_msft_001",
  "as_of": "2026-04-29T13:30:00Z",
  "ticker": "MSFT",
  "spot": 412.30,
  "user_profile_snapshot": {
    "style":"balanced", "max_coverage":0.6, "roll_aggressiveness":"medium",
    "drawdown_tolerance":0.15, "tax_sensitivity":"ltcg_aware",
    "iv_rank_sell_threshold":50, "delta_target_band":[0.15,0.30],
    "dte_band_days":[21,60]
  },
  "market_state": {
    "regime":"HIGH_IV_EVENT", "regime_score":0.82,
    "tags":["sell_vol_favorable","event_in_5d"],
    "iv_rank":78, "iv_percentile":84, "hv_30":0.221,
    "expected_move_pct":4.2, "max_pain":410, "max_pain_delta_pct":-0.56,
    "pcr_volume":0.82, "pcr_oi":0.95,
    "next_event":{"kind":"earnings","date":"2026-05-04"}
  },
  "flow_score": {
    "bullish_score": 58,
    "bearish_score": 36,
    "score": 22,
    "bias": "neutral_bullish",
    "pin_probability": 0.34,
    "gamma_risk": 0.42,
    "support_oi_wall": 405,
    "resistance_oi_wall": 420,
    "recommended_action": "sell_call_partial",
    "confidence": 0.71,
    "explanation": "Resistance wall at 420 with rising call OI; gamma neutral; pin pressure modest at 0.34."
  },
  "recommended_strategy": "ROLL_UP_AND_OUT_PARTIAL",
  "actions": [
    { "step":1, "verb":"BUY_TO_CLOSE", "leg":"short_call_415_2026-05-16",
      "qty":5, "limit_price_band":[3.10, 3.40] },
    { "step":2, "verb":"SELL_TO_OPEN",  "leg":"short_call_425_2026-06-20",
      "qty":5, "limit_price_band":[4.20, 4.60], "delta_target":0.25 }
  ],
  "coverage_after": 0.50,
  "confidence": 0.78,
  "confidence_breakdown": {
    "flow_alignment":0.80, "structure_alignment":0.70, "regime_match":0.90,
    "signal_alignment":0.75, "event_risk_penalty":0.10, "illiquidity_penalty":0.05,
    "weights_version":"v1.0"
  },
  "execution": {
    "aggregate_liquidity_score":0.81, "aggregate_fill_confidence":0.74,
    "suggested_order_type":"limit",
    "legs":[
      {"leg_id":"buy_to_close_415_2026-05-16","liquidity_score":0.86,"spread_bps":24,
       "fill_confidence":0.78,"expected_slippage":0.02,"suggested_order_type":"limit",
       "limit_price_band":[3.10,3.40],"size_warnings":[]},
      {"leg_id":"sell_to_open_425_2026-06-20","liquidity_score":0.76,"spread_bps":52,
       "fill_confidence":0.70,"expected_slippage":0.05,"suggested_order_type":"limit",
       "limit_price_band":[4.20,4.60],"size_warnings":[]}
    ],
    "notes":[]
  },
  "rationale":[
    "IV rank 78 above sell threshold 50",
    "Pre-earnings pin near 410 with modest pin probability",
    "Existing 415 short call within 1 expected move; rolling captures more upside"
  ],
  "risks":[
    "Earnings gap > expected move could leave new 425 ITM",
    "Net debit at midpoint if filled away from natural"
  ],
  "watch_levels":{"above":420,"below":405,"iv_rank_drop_below":50},
  "next_trigger":"Re-evaluate after earnings 2026-05-04 AMC, or on 420/405 cross",
  "invalidation":["Spot > 425 with > 2\u03c3 move","IVR drops < 40","Earnings beat > 8% gap up"],
  "weights_version":"v1.0", "engine_version":"0.1.0",
  "inputs_hash":"sha256:7c8e...d31a",
  "data_freshness":{"spot_age_seconds":47,"chain_age_seconds":1832,"iv_age_seconds":87400,"any_stale":false},
  "outcome": null,
  "disclaimers":["Educational only","Not financial advice","Verify with broker"]
}
```

## Collar Builder

```bash
curl -X POST http://localhost:8000/api/v1/engine/collar-builder \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "ticker":"MSFT", "intents":["zero_cost","income","defensive"], "horizon_days":30 }'
```

```jsonc
[
  {
    "name":"Zero-cost 30d collar 405/430",
    "intent":"zero_cost",
    "horizon_days":30,
    "long_put":{
      "kind":"PUT","side":"BUY","strike":405,"expiry":"2026-05-29","qty":50,
      "delta":-0.22,"iv":0.27,"bid":2.80,"ask":2.95,"mid":2.875,"premium":-2.85
    },
    "short_call":{
      "kind":"CALL","side":"SELL","strike":430,"expiry":"2026-05-29","qty":50,
      "delta":0.20,"iv":0.26,"bid":2.75,"ask":2.90,"mid":2.825,"premium":2.80
    },
    "net_debit_credit": -0.05,
    "max_gain": 8850, "max_loss": -3650,
    "upside_breakeven":412.35, "downside_breakeven":411.95,
    "capped_upside_pct":4.29, "protected_downside_pct":-1.78,
    "confidence":0.74,
    "confidence_breakdown":{"flow_alignment":0.78,"structure_alignment":0.72,
      "regime_match":0.85,"signal_alignment":0.70,"event_risk_penalty":0.10,
      "illiquidity_penalty":0.05,"weights_version":"v1.0"},
    "rationale":[
      "IVR 78 makes call premium attractive vs put protection cost",
      "Walls at 405 (support) / 420 (resistance) align with chosen strikes",
      "30d horizon covers earnings + post-earnings IV crush window"
    ],
    "risks":["Earnings beat > 5% leaves call deep ITM","Below 405, losses are bounded but real"],
    "invalidation":["Spot > 425 with > 2\u03c3 move","IVR drops < 40"],
    "execution":{"aggregate_liquidity_score":0.84,"aggregate_fill_confidence":0.79, "...":"..."}
  },
  { "intent":"income", "name":"Income collar 410/425", "net_debit_credit":-0.45, "...":"..." },
  { "intent":"defensive", "name":"Defensive collar 408/440", "net_debit_credit":+0.95, "...":"..." }
]
```

## Market latest snapshot

```bash
curl http://localhost:8000/api/v1/market/msft/latest -H "Authorization: Bearer $TOKEN"
```
```json
{ "as_of":"2026-04-29T13:30:00Z","ticker":"MSFT","spot":412.30,
  "iv_rank":78.4,"iv_percentile":84.1,"hv_30":0.221,"expected_move_pct":4.2,
  "max_pain":410,"pcr_volume":0.82,"pcr_oi":0.95,
  "next_event":{"kind":"earnings","date":"2026-05-04"},
  "data_freshness":{"any_stale":false,"spot_age_seconds":47,"chain_age_seconds":1832} }
```

## What-if (transient, not persisted)

```bash
curl -X POST http://localhost:8000/api/v1/engine/what-if \
  -H "Authorization: Bearer $TOKEN" \
  -d '{ "ticker":"MSFT", "overrides":{ "spot":425, "iv_rank":35 } }'
```
Returns a full `DailyDecision` reflecting the hypothetical state. Not persisted.

## Profile

```bash
curl -X PUT http://localhost:8000/api/v1/profile \
  -H "Authorization: Bearer $TOKEN" \
  -d '{ "style":"income", "max_coverage":0.7, "roll_aggressiveness":"high",
        "drawdown_tolerance":0.10, "tax_sensitivity":"ltcg_aware",
        "iv_rank_sell_threshold":40,
        "delta_target_band":[0.20,0.35], "dte_band_days":[14,45] }'
```

## Outcomes (manual entry)

```bash
curl -X POST http://localhost:8000/api/v1/outcomes \
  -H "Authorization: Bearer $TOKEN" \
  -d '{ "daily_decision_id":"dd_2026_04_29_msft_001", "horizon_days":7,
        "pnl_realized":425.10, "decision_quality":"good", "error_type":"none",
        "actual_regime_realized":"HIGH_IV_EVENT", "regime_match":true,
        "notes":"rolled at midpoint, filled in 2min" }'
```

## CSV upload

```bash
curl -X POST http://localhost:8000/api/v1/data/positions/import-csv \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@positions.csv"
```
```json
{ "inserted":1, "updated":0, "errors":[] }
```

---

## Seed data (`scripts/seed_local.py`)

For local dev, the seed script creates a Helen-shaped fixture so any developer can `docker compose up` and immediately get a coherent `DailyDecision`.

```
$ uv run python scripts/seed_local.py
Seeding...
  + user helen@example.test (password: changeme)
  + UserStrategyProfile (balanced, max_coverage=0.6)
  + position MSFT 5000 sh @ $400.12 (opened 2025-08-15)
  + option_position SHORT 5x CALL 415 expiring 2026-05-16 @ 2.85
  + chain snapshot: 3 expiries (2026-05-16, 2026-05-29, 2026-06-20), ~120 strikes
  + IV history: 60 trading days (synthetic but plausible)
  + events: earnings 2026-05-04, FOMC 2026-05-07, OpEx weekly 2026-05-02, OpEx monthly 2026-05-16
Done. Login: helen@example.test / changeme
```

Seed data shape (`scripts/seed_local.py` writes these directly via SQLAlchemy; equivalent CSVs in `seeds/csv/` for reference):

`seeds/csv/positions.csv`:
```
ticker,qty,avg_cost,opened_at
MSFT,5000,400.12,2025-08-15T00:00:00Z
```

`seeds/csv/option_positions.csv`:
```
ticker,side,kind,strike,expiry,qty,opened_at,opened_price,status
MSFT,SELL,CALL,415.00,2026-05-16,5,2026-04-15T15:30:00Z,2.85,OPEN
```

`seeds/csv/chain.csv` (excerpt):
```
ticker,fetched_at,expiry,strike,kind,bid,ask,last,oi,volume,iv,delta,gamma,theta,vega
MSFT,2026-04-29T13:30:00Z,2026-05-16,400,PUT, 1.95, 2.05, 2.00, 8500, 1820, 0.2920,-0.2812,0.0142,-0.0795,0.5821
MSFT,2026-04-29T13:30:00Z,2026-05-16,405,PUT, 2.80, 2.95, 2.85,12450, 2240, 0.2880,-0.2210,0.0123,-0.0876,0.6234
MSFT,2026-04-29T13:30:00Z,2026-05-16,410,PUT, 4.10, 4.30, 4.20,15200, 3110, 0.2840,-0.4521,0.0091,-0.0998,0.6521
MSFT,2026-04-29T13:30:00Z,2026-05-16,415,CALL,3.10, 3.40, 3.25,12450, 3210, 0.2812, 0.4521,0.0123,-0.0876,0.6234
MSFT,2026-04-29T13:30:00Z,2026-05-16,420,CALL,1.65, 1.80, 1.72, 9800, 2890, 0.2780, 0.2218,0.0109,-0.0834,0.6021
MSFT,2026-04-29T13:30:00Z,2026-05-16,425,CALL,0.78, 0.92, 0.85, 5400, 1450, 0.2752, 0.1242,0.0087,-0.0712,0.5520
...
```

`seeds/csv/iv_history.csv` (excerpt):
```
ticker,ts,atm_iv_30d,iv_rank,iv_percentile,hv_30
MSFT,2026-02-29T20:00:00Z,0.2154,32.1,38.4,0.1980
MSFT,2026-03-31T20:00:00Z,0.2440,55.6,62.8,0.2105
MSFT,2026-04-28T20:00:00Z,0.2814,78.4,84.1,0.2231
```

`seeds/csv/events.csv`:
```
ticker,kind,scheduled_at,source,notes
MSFT,earnings,2026-05-04T20:30:00Z,manual,Q3 FY26 print AMC
,fomc,2026-05-07T18:00:00Z,fred,Fed decision
MSFT,opex_weekly,2026-05-02T20:00:00Z,manual,
MSFT,opex_monthly,2026-05-16T20:00:00Z,manual,
```

After seeding, the very first call to `POST /engine/daily-plan` returns a fully-rendered `DailyDecision` (regime: `HIGH_IV_EVENT`, recommended strategy: `ROLL_UP_AND_OUT_PARTIAL` or `OPEN_COLLAR` depending on weight tuning). This is the smoke test for "engine works end-to-end."

## 22. Patch v1.2 — Audit Corrections (2026-05-09)

External plan audit (independent Claude Sonnet 4.6 review, 2026-05-09) identified 25 issues. v1.2 resolves all 25. Where v1.1 conflicts with v1.2, **v1.2 wins**. Implementers should treat this section as the canonical correction sheet — read it BEFORE writing any code.

## 22.0 Status

| Severity | Count | Resolved | Pending |
|---|---|---|---|
| P0 Blocker | 1 | 1 | 0 |
| Critical | 4 | 4 | 0 |
| High | 6 | 6 | 0 |
| Medium | 9 | 9 | 0 |
| Low | 5 | 5 | 0 |

Phase 1 day count unchanged at **35 working days** (v1.1's 5-week pace). v1.2 corrections are specifications, not new milestones — absorbed within existing M1.* time. Phase 1 ship target: **Day 40**.

## 22.1 C1 — Next.js version (RESOLVED — auditor was wrong)

**Audit claim**: "Next.js 16.2.4 does not exist; current stable is 15.x as of 2026-05-09."

**Verified directly against `https://registry.npmjs.org/next` on 2026-05-09**:
- Next.js 16.2.4 **exists** — released 2026-04-15.
- The current `latest` dist-tag is **16.2.6** — released 2026-05-07 (two days before the audit was written).
- Next.js 16.x became the stable line on 2025-10-22 (16.0.0). 27 stable releases in the 16.x line; 7 patches in 16.2.x.

The auditor's claim was incorrect (likely a stale knowledge cutoff). The user's original v1.1 pin of `16.2.4` is valid.

**Resolution**: lock to **`next@16.2.6`** (current `latest`, two patches ahead of `16.2.4`, no breaking changes within the minor line). All bug-fix improvements between 16.2.4 → 16.2.6 are free.

**Global substitution rule for the v1.0/v1.1 spec**: every reference to `Next.js 16.2.4` in §0, §5, §8, §17 (M0.4), §18 (`"next": "16.2.4" exact`), and §19 (Day 4) is read as **`Next.js 16.2.6`** under v1.2.

```jsonc
// apps/web/package.json
{
  "dependencies": {
    "next": "16.2.6",
    "react": "<paired version per Next 16 release notes>",
    "react-dom": "<paired version>"
  }
}
```

CI guard (`scripts/check_next_version.sh`):
```bash
#!/usr/bin/env bash
set -e
PINNED=$(jq -r '.dependencies.next' apps/web/package.json)
[ "$PINNED" = "16.2.6" ] || { echo "ERROR: next pin must be exactly 16.2.6"; exit 1; }
```

## 22.2 C2 — FlowScore schema (DB + Pydantic) reconciled

Delete the v1.0 `FlowScore` Pydantic schema in §7. The V1 contract from v1.1 patch (with `bullish_score`, `bearish_score`, `pin_probability`, `gamma_risk`, `recommended_action`, `explanation`) is the only canonical schema.

Replace the `flow_scores` DDL in §6 (apply to initial Alembic migration `0001_init` — do not write a separate ALTER):

```sql
CREATE TABLE flow_scores (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker        text NOT NULL,
  computed_at   timestamptz NOT NULL DEFAULT now(),
  bullish_score   numeric(6,3) NOT NULL,
  bearish_score   numeric(6,3) NOT NULL,
  score           numeric(8,3) NOT NULL,                  -- signed: -100..100
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
CREATE INDEX flow_scores_ticker_at_idx ON flow_scores(ticker, computed_at DESC);
```

The v1.0 `dealer_gamma_proxy text` field is dissolved into the new `gamma_risk numeric(6,4)`.

> **Forward reference (added 2026-05-10 per [ADR-0008](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/decisions/0008-enhancement-adoption-roadmap.md)):** the FlowScore V1 contract above is scheduled to be amended in **Phase 1.5** by the E1 (GEX) follow-up ADR. The `gamma_risk` field stays, but its origin shifts from a `dealer_gamma_proxy` heuristic to a real `GexResult` (gamma flip, call/put walls, `gex_em_ratio`). Schema-level: a `gex_context jsonb` column is added to `flow_scores`. The V1 contract is otherwise unchanged. See [`docs/enhancements/0001-assessment-and-adoption-decisions.md`](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/enhancements/0001-assessment-and-adoption-decisions.md) for the full rationale.

## 22.3 C3 — Market State Engine: extended `classify()` signature

Replace §9.2 `classify()` signature with:

```python
def classify(
    *,
    spot: Decimal,
    iv_rank: float, iv_percentile: float, hv_30: float,
    expected_move_pct: float,
    max_pain: Decimal,
    pcr_volume: float, pcr_oi: float,
    days_to_next_event: int | None, next_event_kind: str | None,
    trend_strength: float,                   # 0..1, see 22.5
    realized_vs_implied: float,
    days_since_event: int | None,
    # ADDED in v1.2:
    days_to_nearest_opex: int | None,        # for HIGH_IV_PIN
    iv_rank_change_1d: float | None,         # for POST_EVENT_REPRICE
    gap_pct: float | None,                   # post-event price gap
    breakout_signal: float,                  # 0..1, see 22.5
    oi_concentration_at_max_pain: float,     # 0..1, for pin_probability
) -> MarketStateResult: ...
```

`apps/api/app/services/decision_service.py` populates the new fields from most-recent snapshots before calling `classify()`.

## 22.4 C4a — `ChainSnapshot` and `ChainRow` (canonical types)

Add to `packages/engine/engine/types.py`:

```python
@dataclass(frozen=True)
class ChainRow:
    expiry: date
    strike: Decimal
    kind: Literal["PUT", "CALL"]
    bid: Decimal
    ask: Decimal
    last: Decimal | None
    mark: Decimal           # (bid + ask) / 2 if both present, else last
    oi: int
    volume: int
    iv: float | None        # market-provided; engine may solve if None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    source: str

@dataclass(frozen=True)
class ChainSnapshot:
    ticker: str
    fetched_at: datetime
    rows: tuple[ChainRow, ...]

    def lookup(self, leg_descriptor: str) -> ChainRow:
        # leg_descriptor: "{side}_{kind}_{strike}_{expiry}", e.g. "short_call_415_2026-05-16"
        ...
    def filter(self, *, expiry: date | None = None, kind: Literal["PUT","CALL"] | None = None) -> list[ChainRow]: ...
    def get_expiries(self) -> list[date]: ...
    def in_delta_band(self, *, kind: Literal["PUT","CALL"], delta_band: tuple[float,float], expiry: date) -> list[ChainRow]: ...
```

## 22.5 C4b — Specifications for previously undefined functions

```python
# packages/engine/engine/decision/intent_inference.py
def infer_intent(market_state: MarketStateResult, positions: PositionState,
                 profile: UserStrategyProfile) -> Literal["sell_call","buy_put","collar","sell_put"]:
    has_short_call = positions.has_open_option(side="SELL", kind="CALL")
    has_long_put   = positions.has_open_option(side="BUY",  kind="PUT")
    has_collar     = has_short_call and has_long_put
    r = market_state.regime
    if r == Regime.HIGH_IV_EVENT:       return "collar" if not has_collar else "sell_call"
    if r == Regime.HIGH_IV_PIN:         return "sell_call"
    if r == Regime.LOW_IV_TREND:        return "buy_put" if profile.style != "income" else "sell_call"
    if r == Regime.LOW_IV_RANGE:        return "sell_call"
    if r == Regime.BREAKOUT:            return "sell_call"   # roll-up intent
    if r == Regime.POST_EVENT_REPRICE:  return "collar"
    return "sell_call"

# packages/engine/engine/market_state/trend.py — Wilder ADX, normalized to [0,1]
def compute_trend_strength(high: list[float], low: list[float], close: list[float],
                           lookback: int = 14) -> float:
    if len(close) < 2 * lookback + 10:
        return 0.5  # insufficient history -> neutral
    adx = wilder_adx(high, low, close, lookback)
    return clip01((adx - 20.0) / 20.0)   # ADX>=40 -> 1; ADX<=20 -> 0; linear between

# packages/engine/engine/market_state/breakout.py
def compute_breakout_signal(*, spot: Decimal, spot_5d_ago: Decimal,
                            atm_iv_change_5d: float, oi_shift_ratio: float,
                            above_resistance: bool, above_resistance_pct: float) -> float:
    pct_move = float((spot - spot_5d_ago) / spot_5d_ago)
    move_signal  = clip01(abs(pct_move) / 0.05)
    vol_signal   = clip01(atm_iv_change_5d / 0.10)
    oi_signal    = clip01(abs(oi_shift_ratio))
    break_signal = clip01(above_resistance_pct / 0.02) if above_resistance else 0.0
    return clip01(0.35*move_signal + 0.20*vol_signal + 0.20*oi_signal + 0.25*break_signal)

# packages/engine/engine/execution/slippage.py
def expected_slippage(quote: ChainRow, qty: int) -> Decimal:
    impact = min(qty / max(quote.volume, 1), 1.0)
    half_spread = (quote.ask - quote.bid) / 2
    return half_spread * Decimal(str(0.5 + 0.5 * impact))

def size_warnings(quote: ChainRow, qty: int) -> list[str]:
    w = []
    if quote.oi < 100:
        w.append(f"Low OI ({quote.oi}) — thin market.")
    if quote.volume > 0 and qty > quote.volume * 0.30:
        w.append(f"Order size {qty}x is > 30% of today's volume ({quote.volume}).")
    spread_frac = (quote.ask - quote.bid) / max(quote.ask, Decimal("0.01"))
    if spread_frac > Decimal("0.10"):
        w.append(f"Wide spread ({int(spread_frac * 10000)} bps) — fill confidence reduced.")
    return w
```

The seed CSV (`iv_history.csv`) is extended in v1.2 to include OHLC columns for `trend_strength`:
```
ticker,ts,atm_iv_30d,iv_rank,iv_percentile,hv_30,high,low,close
```

## 22.6 C5 — `disclaimer_accepted_at` column

Update §6 `users` DDL:

```sql
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  strategy_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  disclaimer_accepted_at timestamptz,                    -- ADDED in v1.2
  created_at    timestamptz NOT NULL DEFAULT now()
);
```

Disclaimer gate logic: `if (user.disclaimer_accepted_at == null) showModal()`.

## 22.7 H1 — Phase 1 docker-compose simplified (no jobs, no redis)

Replace §14 `docker-compose.yml`:

```yaml
# docker-compose.yml — Phase 1 (no jobs, no redis)
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: msft_engine
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
  api:
    build: ./apps/api
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:dev@postgres:5432/msft_engine
      JWT_SECRET: dev-secret
    depends_on: [postgres]
    ports: ["8000:8000"]
    volumes: [./packages/engine:/code/packages/engine]
  web:
    build: ./apps/web
    environment:
      NEXT_PUBLIC_API_BASE: http://api:8000/api/v1
    depends_on: [api]
    ports: ["3000:3000"]
  # Phase 2: re-add redis + jobs services for scheduled ingestion + Arq.
  # redis: { image: redis:7-alpine, ports: ["6379:6379"] }
  # jobs:  { build: ./apps/jobs, depends_on: [postgres, redis] }
volumes:
  pgdata:
```

## 22.8 H2 — Eight V1 `rules.yaml` (complete)

```yaml
- id: high_iv_sell_call
  when: { regime: ["HIGH_IV_EVENT","HIGH_IV_PIN","LOW_IV_RANGE"], iv_rank_gte: 50, has_short_call: false }
  emit: SELL_COVERED_CALL_PARTIAL
  rationale: "IV rank {{iv_rank}} >= sell threshold {{profile.iv_rank_sell_threshold}}"
  risks: ["Capped upside on breakout","Assignment risk near expiry"]
  invalidation: ["IV rank < 40","Spot breaks resistance with volume"]

- id: roll_up_and_out_when_short_call_threatened
  when: { has_short_call_within_pct: 1.0, days_to_expiry_lte: 14 }
  emit: ROLL_UP_AND_OUT
  rationale: "Short call within 1% of spot with {{dte}} DTE; roll captures more upside"
  risks: ["Net debit if rolled at midpoint","New strike still ITM on continued rally"]
  invalidation: ["IVR < 30","Earnings miss gap-down"]

- id: reduce_coverage_on_breakout_post_event
  when: { regime: BREAKOUT, days_since_event_lte: 2, iv_rank_change_1d_lte: -15 }
  emit: REDUCE_COVERAGE
  rationale: "Post-event IV crush + breakout pattern; preserve upside"
  risks: ["Trend may stall — forgone premium"]
  invalidation: ["Trend fails — spot returns below resistance"]

- id: open_collar_pre_event
  when: { regime: HIGH_IV_EVENT, days_to_next_event_lte: 7, has_long_put: false }
  emit: OPEN_COLLAR
  rationale: "{{days_to_next_event}}d to {{event_kind}}; collar protects gap risk"
  risks: ["Collar caps both sides","Net debit if put cost > call premium"]
  invalidation: ["Event passes without expected move","IVR drops < 50"]

- id: buy_long_dated_put_low_iv_trend
  when: { regime: LOW_IV_TREND, iv_rank_lte: 30, has_long_put: false, drawdown_tolerance_lte: 0.20 }
  emit: BUY_LONG_DATED_PUT
  rationale: "IV rank {{iv_rank}} makes long puts cheap; trending market warrants tail hedge"
  risks: ["Premium decay if trend continues uninterrupted"]
  invalidation: ["Trend breaks","IVR > 50"]

- id: monetize_put_on_breakout
  when: { regime: BREAKOUT, has_long_put: true, put_pnl_pct_gte: 0.30 }
  emit: MONETIZE_PUT
  rationale: "Long put up {{put_pnl_pct}}; harvest gains, re-strike later if needed"
  risks: ["Trend reverses and we'd be unhedged"]
  invalidation: ["Trend fails immediately"]

- id: wheel_on_low_iv_range
  when: { regime: LOW_IV_RANGE, has_short_put: false, profile_style: "income" }
  emit: WHEEL_SHORT_PUT
  rationale: "Range market + income profile; sell puts at support"
  risks: ["Assignment at higher cost basis if range breaks down","Naked-put margin"]
  invalidation: ["Regime shifts to LOW_IV_TREND","Spot falls below support"]

- id: hold_no_op
  when: { confidence_lte: 0.30 }
  emit: NO_OP
  rationale: "Signal alignment too low ({{confidence}}); no high-conviction action"
  risks: []
  invalidation: ["Confidence rises above 0.50 on next compute"]
```

## 22.9 H3 — Max pain formula

```python
# packages/engine/engine/market_state/max_pain.py
def compute_max_pain(chain: ChainSnapshot, expiry: date) -> Decimal:
    """CBOE-style max pain: strike that minimizes total dollar pain to writers
    at expiration, summed across all open call/put OI for the given expiry."""
    rows = chain.filter(expiry=expiry)
    strikes = sorted({r.strike for r in rows})
    if not strikes:
        raise ValueError(f"No chain rows for expiry {expiry}")
    def pain_at(K: Decimal) -> Decimal:
        call_pain = sum(Decimal(r.oi) * max(K - r.strike, Decimal("0"))
                        for r in rows if r.kind == "CALL")
        put_pain  = sum(Decimal(r.oi) * max(r.strike - K, Decimal("0"))
                        for r in rows if r.kind == "PUT")
        return (call_pain + put_pain) * Decimal("100")   # contract multiplier
    return min(strikes, key=pain_at)
```

## 22.10 H4 — `MarketLatestSnapshot` source + staleness

`GET /market/{ticker}/latest` reads the most-recent rows across `option_chain_snapshots`, `iv_history`, `hv_history`, `events` and computes `max_pain` + `expected_move` on the fly (no engine calls):

```sql
WITH latest_chain AS (
  SELECT * FROM option_chain_snapshots WHERE ticker = :ticker
   ORDER BY fetched_at DESC LIMIT 1
), latest_iv AS (
  SELECT * FROM iv_history WHERE ticker = :ticker ORDER BY ts DESC LIMIT 1
), latest_hv AS (
  SELECT * FROM hv_history WHERE ticker = :ticker ORDER BY ts DESC LIMIT 1
), next_event AS (
  SELECT * FROM events WHERE (ticker = :ticker OR ticker IS NULL)
   AND scheduled_at > now() ORDER BY scheduled_at ASC LIMIT 1
)
SELECT * FROM latest_chain, latest_iv, latest_hv, next_event;
```

- If `iv_history` for the ticker has < 30 rows → HTTP 422 `"insufficient iv_history (n=X)"`.
- If `option_chain_snapshots` is empty for ticker → HTTP 422 `"chain not yet ingested for {ticker}"`.

Staleness thresholds in `data_freshness`:
- `chain_age_seconds > 7200` (2h) → tag `stale_chain`, `any_stale: true`
- `iv_age_seconds > 90000` (~25h) → tag `stale_iv`, `any_stale: true`

## 22.11 H5 — `underlying_qty` resolved at service layer

Remove `underlying_qty: int | None = None` from `CollarBuilderRequest`. The engine's `collar_builder.build()` accepts it as a required kwarg only.

```python
# apps/api/app/services/decision_service.py
def collar_builder_handler(request: CollarBuilderRequest, user_id: UUID) -> list[CollarStructure]:
    qty = db.get_total_shares(user_id=user_id, ticker=request.ticker)
    if qty < 100:
        raise HTTPException(422, detail=f"Insufficient {request.ticker} shares (need >= 100)")
    profile      = db.get_profile(user_id)
    coverage     = request.coverage_ratio or profile.max_coverage
    horizon      = request.horizon_days  or profile.dte_band_days[1]
    chain        = db.get_latest_chain(request.ticker)
    market_state = db.get_latest_market_state(request.ticker)
    spot         = db.get_latest_spot(request.ticker)
    return collar_builder.build(
        spot=spot, underlying_qty=qty, chain=chain, profile=profile,
        market_state=market_state, intents=request.intents,
        horizon_days=horizon, coverage_ratio=coverage,
    )
```

## 22.12 H6 — IV history validation

CSV upload (`POST /data/iv/import-csv`) validates row count post-insert:

```python
def validate_iv_history(ticker: str) -> ValidationStatus:
    n = db.count_iv_history(ticker)
    if n < 30:  return ValidationStatus(level="block", reason=f"IV rank/percentile require >= 30 days; only {n} present.")
    if n < 60:  return ValidationStatus(level="warn",  reason=f"IV percentile less reliable with {n} < 60 days.")
    if n < 252: return ValidationStatus(level="info",  reason=f"IV rank uses {n}-day lookback (target: 252).")
    return ValidationStatus(level="ok")
```

`POST /engine/daily-plan` returns HTTP 422 when `level=block`. Below 60 days, the engine adds a warning to `data_freshness.warnings`.

## 22.13 §8 audit — Confidence Composer redesigned (multiplicative penalties; true [0,1])

The v1.0/v1.1 formula has an achievable raw range of `[-0.20, +0.80]`, so confidence post-clip is bounded at 0.80 — not 1.0. v1.2 redesigns with **multiplicative penalties** for true [0,1]:

```yaml
# packages/engine/engine/config/weights.yaml (v2.0)
version: "v2.0"
positive_weights:        # sum = 1.0
  flow:    0.30
  struct:  0.25
  regime:  0.25
  signal:  0.20
penalty_caps:            # max reduction each penalty can apply
  event:    0.30         # event_risk_penalty=1.0 reduces confidence by 30%
  liquidity: 0.25        # illiquidity_penalty=1.0 reduces confidence by 25%
```

```python
def compose(c: ConfidenceInputs, w: Weights) -> tuple[float, ConfidenceBreakdown]:
    positive = clip01(
        w.positive_weights.flow   * c.flow_alignment +
        w.positive_weights.struct * c.structure_alignment +
        w.positive_weights.regime * c.regime_match +
        w.positive_weights.signal * c.signal_alignment
    )
    penalty_mult = ((1.0 - w.penalty_caps.event     * c.event_risk_penalty) *
                    (1.0 - w.penalty_caps.liquidity * c.illiquidity_penalty))
    confidence = clip01(positive * penalty_mult)
    breakdown = ConfidenceBreakdown(
        flow_alignment=c.flow_alignment, structure_alignment=c.structure_alignment,
        regime_match=c.regime_match, signal_alignment=c.signal_alignment,
        event_risk_penalty=c.event_risk_penalty, illiquidity_penalty=c.illiquidity_penalty,
        positive_score=positive,                  # NEW field: pre-penalty
        penalty_multiplier=penalty_mult,          # NEW field: applied multiplier
        weights_version=w.version,
    )
    return confidence, breakdown
```

Worked example (matching §21):
- positive = 0.30·0.80 + 0.25·0.70 + 0.25·0.90 + 0.20·0.75 = **0.79**
- penalty_mult = (1 − 0.30·0.10) · (1 − 0.25·0.05) = 0.97 · 0.9875 = **0.9579**
- confidence = clip01(0.79 · 0.9579) ≈ **0.76** (was 0.78 under v1.0/v1.1; update §21 example)

UI: stack 4 positive components as a bar; render the penalty multiplier as a darker overlay reducing the final width. More intuitive than v1.0's signed-weight chart.

## 22.14 Medium-severity fixes (M1–M9)

**M1 — Phase 1 Done updated.** Replace §19 "Definition of Phase 1 Done":
- All **32** M1.* milestones (25 v1.0 + 7 v1.1).
- 24/24 regime fixtures pass with ≥ 80% accuracy.
- 12/12 golden DailyDecision snapshots match.
- 5/5 scoring functions at 100% line coverage.
- 3/3 Collar Builder intents return valid structures on seed fixture.
- 4/4 Playwright E2E flows green.
- `pytest --cov=packages/engine` ≥ **85%**.
- `mypy --strict packages/engine` clean.
- One CSV upload (Helen-shaped) generates DailyDecision and collar set in < 5s on M3 MacBook.
- Tag `v0.1.0-phase1`, deploy to staging, demo.

**M2 — Redis dropped from P1.** Per §22.7. Engine cache referenced in §5 also deferred to P2.

**M3 — Scenario IV shift documented as approximation.** Add to §12 docstring: "Phase 1 simplification: uniform IV shift across all strikes/expiries. Real IV crush is non-uniform (ATM crushes most, deep OTM puts retain skew, short-dated crush faster). Phase 4 SVI surface fitting (§16.7) replaces with strike-specific shifts. UI tooltip notes the approximation."

**M4 — `actual_regime_realized` typed.** §6:
```sql
CREATE TYPE regime AS ENUM ('HIGH_IV_EVENT','HIGH_IV_PIN','LOW_IV_TREND','LOW_IV_RANGE','BREAKOUT','POST_EVENT_REPRICE');
-- in outcomes:
actual_regime_realized regime  -- was: text
```

**M5 — `/market/{ticker}/latest`.** Rename from `/market/msft/latest`. Phase 1 returns 404 for non-MSFT tickers: `"ticker not enabled (MVP is MSFT-only)"`. UI hardcodes "MSFT" until P4 multi-ticker.

**M6 — Scoring wiring matrix corrected** (§9.11). `flow_score` is the orchestrator only, not also a primitive column:

| Consumer | iv | structure | gamma | event |
|---|---|---|---|---|
| Market State Engine | x | x |   | x |
| Flow Score Engine (orchestrator) | x |   | x |   |
| Recommendation Engine |   | x |   |   |
| Confidence Composer | x | x |   | x |
| Collar Builder | x |   |   | x |
| Strike Selector | x |   |   |   |

**M7 — `MarketPriceImpliedVolError` defined.**
```python
# packages/engine/engine/payoff/iv_solver.py
class MarketPriceImpliedVolError(ValueError):
    """IV solver could not converge or result was out of bounds [1e-4, 5.0]."""
    def __init__(self, *, market_price: float, bounds: tuple[float, float], reason: str):
        super().__init__(f"IV solve failed: price={market_price}, bounds={bounds}, reason={reason}")
        self.market_price, self.bounds, self.reason = market_price, bounds, reason
```
Surfaced via API as HTTP 422 with `type: "...iv-solve-failed"`.

**M8 — Collar Builder grid pre-filter.** §9.10 algorithm updated:
1. Eligible puts = `kind="PUT"`, `delta in [-0.40, -0.10]`, `strike < spot`, passes liquidity floor.
2. Eligible calls = `kind="CALL"`, `delta in [0.10, 0.40]`, `strike > spot`, passes liquidity floor.
3. Grid = eligible_puts × eligible_calls (typically 15-25 each → 225-625 pairs).
4. For each pair: compute `net_debit_credit`, `max_gain`, `max_loss`; filter by intent; rank.

Worst-case ~625 × 3 intents = 1,875 evaluations — sub-second.

**M9 — `is_transient` enforced at service layer.** Remove the `__transient: true` payload convention.

```python
# decision_service.py
def produce(*, user_id, ticker, overrides=None, persist: bool = True) -> DailyDecision:
    decision = engine.produce_daily_decision(...)
    if persist:
        db.persist_daily_decision(decision, user_id)
    return decision

# routes/engine.py — what-if explicitly does not persist
@router.post("/engine/what-if")
def what_if(req, user) -> DailyDecision:
    return decision_service.produce(user_id=user.id, ticker=req.ticker,
                                    overrides=req.overrides, persist=False)
```

## 22.15 Low-severity fixes (L1–L5)

**L1 — Day order.** Reorder §19 Days 4-7:
- Day 4: Next.js shell + shadcn + Tailwind + Disclaimer gate + **placeholder** TS types (`packages/shared-types/src/index.ts: export {}`).
- Day 5: regimes.py, profiles.py, types.py (incl. ChainSnapshot), TS type generator → real `index.ts`.
- Day 6: CI pipelines (typecheck against generated types).
- Day 7: smoke test.

**L2 — engine_version bump policy.** Add `scripts/check_engine_version_bump.sh`:
```bash
#!/usr/bin/env bash
set -e
CHANGED=$(git diff --cached --name-only -- 'packages/engine/engine/')
if [ -n "$CHANGED" ] && ! git diff --cached -- packages/engine/engine/version.py | grep -q '^+__version__'; then
  echo "ERROR: changes to packages/engine/engine/ require __version__ bump"
  echo "$CHANGED"; exit 1
fi
```
Wire into `.pre-commit-config.yaml`. Bump conventions: patch (bug fix), minor (new engine/score/fn), major (schema/rename/semantics).

**L3 — `breakevens()` usage documented.** §11 "Used by" expanded:
- Strike Selector, What-If endpoint, Scenario Simulator, Recommendation Engine (net debit estimation), **Collar Builder** (`upside_breakeven`/`downside_breakeven` on every CollarStructure).

**L4 — Persona UI labels.** Internal enum stays `PersonaPreset.HELEN | RAVI | DIANA`. UI labels in `apps/web/components/settings/PersonaPresetButtons.tsx`:
```typescript
const PERSONA_LABELS: Record<PersonaPreset, string> = {
  HELEN: "Conservative — balanced",
  RAVI:  "Growth — learner",
  DIANA: "Income — RIA-style",
};
```

**L5 — LTCG holding period.** The IRS rule is "MORE than one year" — exactly one year is NOT LTCG. The auditor's suggestion of `+365 days` would qualify positions one day too early. v1.0's `+366 days` is closer but breaks on leap-year acquisitions (off by 1 day). Most precise:
```sql
-- §6 lots:
ltcg_eligible_at timestamptz GENERATED ALWAYS AS (opened_at + interval '1 year' + interval '1 day') STORED
-- handles leap years correctly. US convention; international users override via P3 tax module.
```

## 22.16 Status after v1.2

- **0** P0 blockers open
- **0** Critical issues open
- **0** High issues open
- **0** Medium issues open
- **0** Low issues open

All audit findings resolved. Phase 1 ship target unchanged: **Day 40** (v1.1's 5-week extension still applies).

## 22.17 Auditor accuracy review (lessons for next audit)

The audit was high-quality overall — 24 of 25 findings were real and actionable, including the subtle Confidence Composer math issue that v1.0/v1.1 missed. The one error worth noting:

**C1 (Next.js version)** — claim was that 16.2.4 doesn't exist and current stable is 15.x. Direct registry query (2026-05-09) shows 16.2.6 is current `latest`, 16.2.4 was released 2026-04-15, and 16.x has been stable since 2025-10-22. The auditor appears to have asserted version availability from prior model knowledge rather than verifying — a class of error worth catching: **never assert package versions without `npm view` / `pip index` / direct registry query**. v1.2 adds `scripts/check_next_version.sh` as a CI guard precisely because this is the kind of mistake worth automating against.

Other minor disagreement: **L5 (LTCG)** — the auditor suggested `+365 days`, which would qualify positions one day too early under IRS "more than one year" rule. v1.2 settles on `+ interval '1 year' + interval '1 day'` which handles leap years correctly. Low-stakes call but documenting the reasoning.

## 23. Enhancement Roadmap (E1–E9, post-Phase-0)

The base plan ships through Phase 4 unchanged. After Phase 0 was complete (PR #22 merged 2026-05-10), an enhancement spec was uploaded ([`04-msft-engine-enhancement-spec-0509.md`](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/enhancements/04-msft-engine-enhancement-spec-0509.md)) proposing nine analytical modules. Each was assessed against four tests: plan-v1.2 conflict, engineering principles (ADR-0001 to ADR-0007), user value vs. user risk, and data dependency.

The canonical adoption record is **[ADR-0008 — Enhancement-spec adoption roadmap](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/decisions/0008-enhancement-adoption-roadmap.md)**. The full per-enhancement assessment lives at [`docs/enhancements/0001-assessment-and-adoption-decisions.md`](https://github.com/csupenn/option-mgmt-2026/blob/main/docs/enhancements/0001-assessment-and-adoption-decisions.md).

## Outcome (6 adopt, 2 defer, 0 reject)

| # | Title | Decision | Phase |
|---|---|---|---|
| **E1** | GEX Module (gamma exposure, flip, call/put walls) | **Adopt** | **Phase 1.5** (post-M1.25) |
| **E2** | Vol Surface & Skew Analytics | **Adopt** | **Phase 2** |
| **E3** | PnL Surface & Greeks Engine | **Adopt — partial** (2D + scenarios first; 3D conditional) | **Phase 2** (2D); **Phase 3** (3D, conditional) |
| **E4** | Earnings Expectation Gap Score | **Adopt — display-only** (NOT folded into Confidence Composer math) | **Phase 2–3** |
| **E5** | Realized vs. Implied Vol Premium Tracker | **Adopt** (bundled with E2) | **Phase 2** |
| **E6** | Multi-Expiry Strategy View | **Defer** (re-evaluate post-Phase-3) | — |
| **E7** | Historical Earnings Backtest | **Defer** (re-evaluate post-Phase-3) | — |
| **E8** | Dividend-Aware Pricing | **Adopt** | **Phase 2–3** |
| **E9** | Assignment Risk Module | **Adopt** | **Phase 3** |

## Key non-trivial calls (recorded here, detailed in ADR-0008)

1. **E1 requires a follow-up ADR** amending the FlowScore V1 contract (§22.2 / C2 above). The `dealer_gamma_proxy` placeholder is replaced by a `gex_context: GexResult | None` field; `gamma_risk` is computed from the GEX result. The amendment ships in the same PR as the Phase 1.5 integration — see ME1.0 in §17.

2. **E4 stays display-only.** The source spec proposes folding `earnings_gap.score` into the Confidence Composer's `event_risk_penalty` via `max(...)`. That's an ADR-0003 amendment we explicitly are NOT making in V1. Composite-score-into-Confidence-math compounds calibration error across five inputs. Helen sees the score on the Today screen during event windows; the engine doesn't act on it. Revisit at V2 weights calibration when real outcome data exists.

3. **E3's 3D Plotly surface waits for evidence** of user need from the Phase 2 2D drill-down click-through. The 2D `PnLByPriceChart` + `ScenarioTable` cover the persona's actual decision questions ("if earnings beat +6% with IV crush, where do I land?") in a glanceable, mobile-readable format.

4. **E6 (multi-expiry) and E7 (backtest) are deferred, not rejected.** E6: validate single-expiry recommendation flow first; staggering is a power-user feature without demand signal. E7: historical backtests carry high misleading-output risk under the educational-disclaimer framework — the M0.4 Outcome Tracker is a better teacher (real outcomes from real decisions, not simulated).

## Schema additions (all additive)

Per ADR-0008, no migration breakage on top of `0001_init`. Each migration goes through its own revision file (per the discipline established in M0.7's UTC-anchoring fix):

- E1 — `gex_snapshots` table (optional persistence) + `flow_scores.gex_context jsonb` column (Phase 1.5).
- E4 — `market_states.earnings_gap_score numeric` + `earnings_gap_context jsonb` columns (Phase 2–3).
- E8 — `dividend_schedules` table (Phase 2–3).
- E7 — `backtest_runs` table (only if/when E7 un-defers).

## Engine purity (ADR-0005) preserved

Every adopted enhancement is implementable as a pure function operating on `EngineInputs` (chain, IV history, HV history, events, profile, dividend schedule). None require I/O, network, or DB access from inside the engine. The boundary holds.
