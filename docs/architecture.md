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
|  CORE ENGINES  (the product, packages/engine, M0.6+)      |
|   1. Market State Engine    -> regime + scoring vector    |
|   2. Flow Score Engine      -> directional bias           |
|   3. Strike Selector        -> ranked candidates          |
|   4. Recommendation Engine  -> structured action          |
|   5. Master Decision Engine -> unified DailyDecision      |
|   +. Collar Builder (v1.1)  -> ranked collar structures   |
+-----------------------------------------------------------+
|  CROSS-CUTTING MODULES (consumed by engines)              |
|   A. User Strategy Profile  <- settings                   |
|   B. Confidence Composer    -> formal scoring             |
|   C. Execution Feasibility  -> liquidity / slippage       |
|   D. Outcome Tracker        -> learning loop (P3+)        |
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
| `packages/engine` | Pure Python (numpy, scipy, py_vollib in M0.6+) | The product. Pure functions. No I/O. |
| `packages/shared-types` | TypeScript generated from Pydantic (M0.6+ via datamodel-code-generator) | Type safety end-to-end |
| Postgres 16 | Managed (Neon planned) or local Docker | Source of truth |
| Redis | Optional, Phase 2+ | Engine cache (5-min TTL on `/engine/daily-plan`) |

## Data flow (request lifecycle)

1. **Ingestion** — cron job (`apps/jobs`, P2+) calls `MarketDataProvider.get_chain()` etc. and writes snapshots to Postgres. In MVP this is replaced by user CSV upload.
2. **User opens `/today`** — Next.js server component calls `POST /api/v1/engine/daily-plan { ticker: "MSFT" }`.
3. **API loads inputs** — most-recent rows from `positions`, `option_positions`, `option_chain_snapshots`, `iv_history`, `events`, `users.strategy_profile`.
4. **API calls `engine.decision.produce_daily_decision(...)`** which orchestrates Market State → Flow Score → Strike Selector → Recommendation → Confidence + Execution annotation.
5. **API persists** the full `DailyDecision` payload to `daily_decisions` with `inputs_hash`, `engine_version`, `weights_version`. Returns the payload.
6. **Today screen renders** the `DailyDecision`. Drill-down links route to `/chain`, `/iv`, etc. (Phase 2+).
7. **Later**, the user (Phase 1) or an auto-fill heuristic (Phase 3) writes a row to `outcomes` linked to `daily_decision_id`. Phase 4 ML consumes `(state, decision, outcome)` triples.

## Versioning rules

- **`engine_version`** (semver, e.g. `0.1.0`) bumps on any change to `packages/engine/engine/`. Enforced by `scripts/check_engine_version_bump.sh` (M0.5+).
- **`weights_version`** (e.g. `v2.0`) bumps on any change to `packages/engine/engine/config/weights.yaml`.
- **`inputs_hash`** is a SHA-256 over the canonical JSON of all inputs (positions, chain, IV, events, profile snapshot at decision time). Enables exact replay.
- **`next` pin** is enforced by `scripts/check_next_version.sh`. Currently `16.2.6`.

## Key design invariants

1. **Engine-first**: `packages/engine` is pure-function Python. NO I/O, NO DB, NO NETWORK. ML upgrades in Phase 4 replace specific nodes without changing this invariant. (See [ADR-0001](./decisions/0001-engine-first-architecture.md).)
2. **Single-output principle**: every API response that includes a recommendation is a `DailyDecision` per plan §7. Sub-objects exist for explainability, not as standalone outputs.
3. **Auditable**: every persisted `DailyDecision` carries `inputs_hash`, `engine_version`, `weights_version` for exact replay.
4. **No execution**: this codebase has no broker write paths. Enforced via `scripts/check_no_broker_imports.sh` (M0.5+).
5. **Disclaimer gate**: every UI surface and every API response includes the disclaimer text (per plan §15 + [`disclaimers.md`](./disclaimers.md)).
6. **Locked taxonomies**: 6 regimes (see [ADR-0002](./decisions/0002-regime-taxonomy.md)), 8 V1 rules, 6 scenarios.

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
