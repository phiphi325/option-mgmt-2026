# Architecture

This document mirrors plan v1.2 §5 (System Architecture). Read the plan in the Hyperagent thread `cmokf2twq0gsv06adlij0glqs` for full context; this is the day-to-day reference.

## Layer cake (top = primary surface; bottom = supporting)

```
+-----------------------------------------------------------+
|  TODAY SCREEN  (single DailyDecision card)                |
|  primary UI surface                                        |
+-----------------------------------------------------------+
|  /engine/* Decision API  |  /data/* Data API (drill-down) |
+-----------------------------------------------------------+
|  CORE ENGINES  (the product, packages/engine)             |
|   * Type vocabulary         shipped M0.6                  |
|     - Regime + REGIME_COLORS (6 locked, ADR-0002)         |
|     - UserStrategyProfile + ProfileStyle (frozen, ADR-0005)|
|     - OptionContract / ChainSnapshot                      |
|   1. Market State Engine    -> MarketStateResult     [M1.4]  |
|   2. Flow Score Engine      -> FlowScore             [M1.5b] |
|   3. Strike Selector        -> StrikeSelection       [M1.7]  |
|   4. Recommendation Engine  -> RecommendationResult  [M1.8/M1.9] |
|   5. Master Decision Engine -> DailyDecision         [M1.13 - shipped] |
|   +. Collar Builder (v1.1)  -> ranked collar structures   |
+-----------------------------------------------------------+
|  CROSS-CUTTING MODULES (consumed by engines)              |
|   A. User Strategy Profile  <- settings                   |
|   B. Confidence Composer    -> confidence + breakdown    [M1.10] |
|   C. Execution Feasibility  -> liquidity + downgrade ladder [M1.11+M1.12] |
|   D. Outcome Tracker        -> learning loop (P3+)        |
|   E. Black-Scholes Greeks   -> delta/gamma/vega/...      [M1.6]  |
|   F. Scoring primitives     -> iv/structure/event/gamma  [M1.4a/M1.5a] |
+-----------------------------------------------------------+
|  Data ingestion + provider abstraction                    |
|  Postgres 16  |  Redis (Phase 2+, optional cache)         |
+-----------------------------------------------------------+
```

## Component map

| Component | Tech | Role |
|---|---|---|
| `apps/web` | Next.js 16.2.6 (App Router), TypeScript, Tailwind v3, shadcn/ui, Radix | Today screen + Settings + Outcomes; drill-downs (P2+) |
| `apps/api` | FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic | REST API, RFC 7807 error envelope, JWT auth (M1.x+) |
| `apps/jobs` | Python (Arq) | Scheduled ingestion (P2+); consolidated into `apps/api/app/jobs/` for P1 per v1.2 §22.7 |
| `packages/engine` | Pure Python (Pydantic v2 in M0.6; numpy, scipy, py_vollib in M1+) | The product. Pure functions. No I/O. |
| `packages/shared-types` | TypeScript generated from Pydantic via custom `scripts/generate.py` (deterministic, drift-checked in CI) | Type safety end-to-end |
| Postgres 16 | Managed (Neon planned) or local Docker | Source of truth |
| Redis | Optional, Phase 2+ | Engine cache (5-min TTL on `/engine/daily-plan`) |

## Data flow (request lifecycle)

1. **Ingestion** — cron job (`apps/jobs`, P2+) calls `MarketDataProvider.get_chain()` etc. and writes snapshots to Postgres. In MVP this is replaced by user CSV upload.
2. **User opens `/today`** — Next.js server component calls `POST /api/v1/engine/daily-plan { ticker: "MSFT" }`.
3. **API loads inputs** — most-recent rows from `positions`, `option_positions`, `option_chain_snapshots`, `iv_history`, `events`, `users.strategy_profile`.
4. **API calls `engine.decision.produce_daily_decision(...)`** (M1.13) which orchestrates: pre-computed `MarketStateResult` + `FlowScore` → tentative `recommend()` (M1.9, with `illiquidity_penalty=0`) → per-action `downgrade_if_needed()` (M1.12, which wraps M1.7 `select_strikes()` + M1.11 `assess()`) → final `compose()` (M1.10) with the aggregate post-downgrade penalty → `DailyDecision` with the three-pin replay lock.
5. **API persists** the full `DailyDecision` payload to `daily_decisions` with `inputs_hash`, `engine_version`, `weights_version`. Returns the payload.
6. **Today screen renders** the `DailyDecision`. Drill-down links route to `/chain`, `/iv`, etc. (Phase 2+).
7. **Later**, the user (Phase 1) or an auto-fill heuristic (Phase 3) writes a row to `outcomes` linked to `daily_decision_id`. Phase 4 ML consumes `(state, decision, outcome)` triples.

## Versioning rules

- **`engine_version`** (semver, e.g. `1.4.0`) bumps on any change to `packages/engine/engine/`. Enforced by `scripts/check_engine_version_bump.sh` (M0.5+).
- **`weights_version`** (e.g. `v2.0`) bumps on any change to `packages/engine/config/weights.yaml`. Stamped on every `ConfidenceBreakdown` produced by the Confidence Composer (M1.10) and persisted on each `DailyDecision`. A unit test (`tests/test_confidence.py::test_default_weights_matches_yaml_drift_check`) enforces that the on-disk YAML and the in-code `engine.confidence.DEFAULT_WEIGHTS` constant stay in sync.
- **`inputs_hash`** is a SHA-256 over the canonical JSON of all engine inputs (`as_of`, `ticker`, `chain_snapshot`, `positions`, `profile`, `market_state`, `flow_score`) computed by `engine.decision.compute_inputs_hash(...)` (M1.13). Returns `"sha256:" + 64-char-hex` (71 chars). Canonical JSON conventions (sorted keys, no whitespace, naive datetimes assumed UTC, frozensets sorted by repr) give cross-environment determinism — same logical inputs → same hash on Python 3.9/3.11/3.14. The three pins (`engine_version`, `weights_version`, `inputs_hash`) together identify a unique replayable decision. The `decision_id` is derived deterministically from `inputs_hash[:12] + as_of.timestamp()` for idempotent persistence via `INSERT ... ON CONFLICT (user_id, inputs_hash) DO RETURNING`.
- **`next` pin** is enforced by `scripts/check_next_version.sh`. Currently `16.2.6`.

## Key design invariants

1. **Engine-first**: `packages/engine` is pure-function Python. NO I/O, NO DB, NO NETWORK in the core decision path. ML upgrades in Phase 4 replace specific nodes without changing this invariant. (See [ADR-0001](./decisions/0001-engine-first-architecture.md), [ADR-0005](./decisions/0005-engine-pure-function-discipline.md).) Two filesystem-boundary modules (`engine.recommendation.yaml_loader`, `engine.confidence.yaml_loader`) load YAML config; their callers pass the parsed values into pure-function entry points (`recommend()` takes `Sequence[RuleSpec]` and optional `Weights`, not a path).
2. **Single-output principle**: every API response that includes a recommendation is a `DailyDecision` per plan §7. Sub-objects exist for explainability, not as standalone outputs. The Confidence Composer's `ConfidenceBreakdown` (M1.10) is one such sub-object, persisted on every decision row.
3. **Auditable**: every persisted `DailyDecision` carries `inputs_hash`, `engine_version`, `weights_version` for exact replay. `weights_version` is the v2.0 string from `packages/engine/config/weights.yaml` and is stamped on every `ConfidenceBreakdown` by the M1.10 composer.
4. **Multiplicative confidence**: per [ADR-0003](./decisions/0003-confidence-multiplicative.md) and plan §22.13, confidence is `clip01(positive × penalty_mult)` with a true `[0, 1]` codomain. The v1.0 additive form (range `[-0.20, +0.80]` post-clip) is superseded.
5. **No execution**: this codebase has no broker write paths. Enforced via `scripts/check_no_broker_imports.sh` (M0.5+).
6. **Disclaimer gate**: every UI surface and every API response includes the disclaimer text (per plan §15 + [`disclaimers.md`](./disclaimers.md)).
7. **Locked taxonomies**: 6 regimes (see [ADR-0002](./decisions/0002-regime-taxonomy.md)), 8 V1 rules (`packages/engine/config/rules.yaml`, M1.9), 6 scenarios.
8. **Two-stage `compose()` in the Master Decision Engine** (M1.13): the orchestrator calls `compose()` once internally to `recommend()` (with `illiquidity_penalty=0` so the rule pipeline can use its `confidence_lte:` clause) and once externally with the post-downgrade `liquidity_penalty(execution)`. `recommendation.confidence` (pre-execution) stays in the payload for UI drill-down; `decision.confidence` (post-execution) is the user-facing number. Documented in CHANGELOG `[1.4.0]`.

## Caching

- **MVP**: no cache; recompute on every request (sub-5s on a single user, Helen-shaped fixture).
- **Phase 2**: Redis cache keyed on `(user_id, ticker, inputs_hash)` with 5-min TTL.
- **Cache invalidation**: on profile mutation, position mutation, weights change, or engine version bump.

## Deployment topology

| Env | Web | API | DB | Branch |
|---|---|---|---|---|
| Local | `next dev` | `uvicorn --reload` | Postgres in Docker | any |
| Staging | Vercel preview | Fly.io app `msft-engine-api-stg` (planned) | Neon staging branch | `staging` |
| Prod | Vercel | Fly.io app `msft-engine-api` (planned) | Neon main branch | `main` |

## See also

- [`engineering-principles.md`](./engineering-principles.md) — mandatory engineering principles + project rules.
- [`ssot-constants-map.md`](./ssot-constants-map.md) — canonical constants.
- [`decisions/`](./decisions/) — Architecture Decision Records.
- Plan v1.2 (Hyperagent thread `cmokf2twq0gsv06adlij0glqs`) — full spec.
