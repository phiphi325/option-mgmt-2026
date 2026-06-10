# Yearline integration — implementation record (as-built)

What has actually been built in `option-mgmt-2026` for the yearline integration,
milestone by milestone. This is the **as-built log** — the *why* lives in
[ADR-0009](../../../decisions/0009-adopt-yearline-statistical-context-provider.md)
and the [assessment](../../0002-yearline-context-assessment.md); the *plan* lives in
[`../integration_design_and_plan.md`](../integration_design_and_plan.md). Update this
file as each OM-Y milestone lands.

> Educational research only; not financial advice. Every yearline surface is
> `must_not_auto_execute: true` and **gated**.

## Status at a glance

| Milestone | Scope | Status | Engine ver | PR / branch |
|---|---|---|---|---|
| OM-Y0 | enhancement assessment + ADR (no code) | ✅ merged | — | PR #6 (`8566aa3`) |
| OM-Y1 | `YearlineContext` contract + TS codegen + contract test | ✅ merged | 1.8.0 | PR #7 (`7ce8902`, `e773d1d`) |
| OM-Y2 | ingestion + persistence + hydration | ✅ merged | 1.8.0 (no bump) | PR #8 (`325e518`) |
| OM-Y3 | read-only Today-screen evidence panel (card + headline line) | ✅ merged | 1.8.0 (no bump) | PR #9 |
| OM-Y4 | gated engine consumption (the prize) | ⏳ **deferred — after Phase 1 / M1.25 calibration** (see HANDOFF §1.5) | — | — |
| OM-Y5 | stretch (Market-State enrichment / collar intent) | ⏳ not started | — | — |

The hard rule, upheld throughout: **`packages/engine` never imports
yearline-universe** (ADR-0005). Coupling is a persisted, versioned artifact parsed
into the lightweight `engine.yearline.YearlineContext` value object.

---

## OM-Y0 — enhancement assessment + ADR (merged, PR #6)

Documentation only; no code. Promoted the yearline analysis out of scratch into the
committed tree and recorded the adoption decision.

- `docs/decisions/0009-adopt-yearline-statistical-context-provider.md` — the ADR
  (Status: **Proposed**), locking the 5 constraints: value-object boundary,
  jobs-layer producer, 4th replay pin (`yearline_context_version`), gate-respect,
  two-separate-artifacts.
- `docs/enhancements/0002-yearline-context-assessment.md` — the four-test feasibility
  assessment + adopt recommendation.
- `docs/enhancements/yearline/` — verbatim source analysis + `producer-handoff/` (the
  delivered V13.8 reference).
- Indexes updated; `docs/z_temp/` added to `.gitignore` + leaked scratch untracked.

---

## OM-Y1 — the `YearlineContext` contract (merged, PR #7)

The consumer-side contract + cross-language/cross-repo drift guards. **No
decision-behaviour change** — the engine does not yet consume it.

### What was built

| Path | Role |
|---|---|
| `packages/engine/engine/yearline/types.py` | frozen Pydantic `YearlineContext` (mirrors the V13.8 schema) + `PRetryBasis` StrEnum + `ACCEPTED_ADAPTER_VERSIONS` / `ACCEPTED_SCHEMA_VERSIONS` pins |
| `packages/engine/engine/yearline/__init__.py` | subpackage exports |
| `packages/shared-types/scripts/generate.py` | extended `_ts_type` with `dict[K,V] → Readonly<Record<string, V>>` and `Literal[…] → "a" | true`; wired in the yearline render + index export |
| `packages/shared-types/src/yearline.ts` | generated TS (`YearlineContext` + `PRetryBasis`) |
| `packages/engine/tests/fixtures/yearline/` | vendored V13.8 gated + stale fixtures + schema |
| `packages/engine/tests/test_yearline_contract.py` | 9-test cross-repo contract suite |

### Key implementation decisions

- **`frozen=True` + `extra="forbid"`** on the model — immutable (safe for the OM-Y4
  replay hash) and any un-pinned producer field fails loudly (the drift guard
  ADR-0009 calls for).
- **Nullable identity fields** (`as_of`/`ticker`/`schema_version`/`model_stack_version`
  typed `… | None`) to match the *delivered* V13.8 schema, not the non-null sketch in
  the plan. Real artifacts always populate them.
- **`PRetryBasis` as a StrEnum** (not a `Literal`) — idiomatic to the codebase and
  auto-handled by the existing enum codegen.
- **Horizon-keyed maps** (`p_retry`, `gate_passed`, `p_successful_reclaim`) use `int`
  keys; JSON string keys coerce on parse and round-trip back to strings via
  `model_dump(mode="json")`.
- **Engine version bump 1.7.0 → 1.8.0** (minor — new public contract, no existing-schema
  change). Required by `check_engine_version_bump.sh`; the 12 golden `expected.json`
  were regenerated (diff = `engine_version` stamp only; decision logic + `inputs_hash`
  byte-identical).

### Acceptance evidence

codegen drift gate green · `mypy --strict engine` clean · 831 engine tests pass ·
both pin guards (`check_engine_version_bump.sh`, `check_changelog_entry.sh`) green.

---

## OM-Y2 — ingestion + persistence + hydration (implemented, pending merge)

Lands the nightly artifact in Postgres and reads it back into the engine contract.
First milestone touching `apps/api` + the database. **No engine change** (so no
version bump). Mirrors `inputs_hydration_service` (MarketState / FlowScore).

### What was built

| Path | Role |
|---|---|
| `apps/api/app/db/migrations/versions/0004_yearline_context.py` | `yearline_context` table (`ticker, as_of, schema_version, model_stack_version, adapter_version, payload JSONB, payload_hash, ingested_at`); `UNIQUE(ticker, as_of)` + `(ticker, as_of DESC)` index |
| `apps/api/app/jobs/ingest_yearline.py` (+ `jobs/__init__.py`) | validate artifact vs `engine.yearline.YearlineContext`, pin `adapter_version`, idempotent upsert |
| `apps/api/app/services/yearline_hydration_service.py` | latest row → `YearlineContext | None` (graceful abstention) |
| `apps/api/tests/test_yearline_ingest.py` | 8 unit tests (pure validation + hashing) |
| `apps/api/tests/test_smoke_yearline.py` | 4 smoke tests (DB idempotency + hydration) |
| `apps/api/tests/fixtures/yearline/` | vendored gated + stale fixtures |

### Persistence / idempotency model

- **Idempotency key `(ticker, as_of)`** — one context per ticker per data date,
  matching the producer's "key the artifact by `{ticker}_{as_of}`."
- **Upsert with change detection:** `INSERT … ON CONFLICT (ticker, as_of) DO UPDATE …
  WHERE yearline_context.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash RETURNING
  (xmax = 0)`. This yields three honest outcomes:
  - `inserted` — new `(ticker, as_of)` row (`xmax = 0`)
  - `updated` — existing row's bytes changed → overwritten (`xmax ≠ 0`)
  - `unchanged` — identical bytes → the WHERE clause skips the write → no row returned
- **`payload_hash`** = `sha256:` over canonical (sorted-key) JSON of
  `model_dump(mode="json")` — deterministic, order-insensitive.
- **Validation before persistence:** `parse_artifact` rejects an incompatible
  `adapter_version`, a null `as_of`/`ticker` (un-persistable), and (via the model's
  `extra="forbid"`) any un-pinned producer field.

### Hydration / gate-respect on the read boundary

`hydrate_yearline_context(*, session, ticker, as_of=None, max_age_days=None)` returns
the latest usable `YearlineContext`, else **`None`** when:
- no row exists for the ticker, OR
- the latest row's payload is `is_stale: true` (the producer's freshness flag), OR
- `max_age_days` is set and the row's `as_of` is older than that window.

`None` flows straight into the engine's optional `yearline_context` kwarg (OM-Y4), so a
missing/stale context degrades to the pre-yearline decision — like the `futures_basis=0`
stub. The `as_of` upper bound prevents peeking at future data (replay determinism).

### Acceptance evidence

- **Verified against real Postgres** (not just unit-mocked): the 4 smoke tests pass —
  insert → unchanged → updated (exactly one row per `(ticker, as_of)`), hydrate returns
  the parsed context, stale row → `None`, missing ticker → `None`.
- Migration `0004` **up/down/up round-trips** cleanly.
- `ruff` clean · `mypy --strict app` clean (44 files) · api suite **92 passed, 28
  skipped** (smoke skipped without a live DB).
- A real bug was caught by the live-DB run: the hydration query's `:as_of IS NULL` gave
  psycopg an untyped NULL (error `f405`); fixed by casting both usages to `date`. The
  unit suite alone would not have surfaced it.

### Not in scope here (deferred to the named milestone)

- No HTTP endpoint or UI — that is **OM-Y3** (`GET /engine/yearline-context` + the
  Today-screen panel; the panel reads the raw row to *show* staleness, whereas this
  engine-facing hydration *abstains* on stale).
- No engine consumption / replay-hash extension — that is **OM-Y4**.
- No scheduled artifact reader (object-store / nightly cron) — the producer side stays
  `workflow_dispatch`-first until OM-Y2 is merged + a CI contract test is wired.

---

## OM-Y3 — read-only evidence panel (implemented, pending merge)

The first user-visible value + the first `apps/web` work. **Scope chosen: card +
headline line** (the single distance-to-MA250 line; the remaining §6 panels are a
follow-up). Charting: **Recharts** (3.8.x, React-19 compatible). Trend series:
**persisted** in its own table (symmetric with OM-Y2). Read-only — `DailyDecision`
is untouched. No engine change (no version bump).

### Backend

| Path | Role |
|---|---|
| `apps/api/app/db/migrations/versions/0005_yearline_trend_series.py` | `yearline_trend_series` table; `UNIQUE(ticker, as_of)` + index |
| `apps/api/app/schemas/yearline.py` | `YearlineTrendSeriesModel` (presentation-only, `extra="forbid"`) + `ACCEPTED_SERIES_VERSIONS` + `YearlinePanelResponse` |
| `apps/api/app/jobs/ingest_yearline.py` | + `parse_trend_series` / `ingest_yearline_trend_series` (idempotent upsert; rejects `available:false`, un-pinned `series_version`, missing ticker/as_of) |
| `apps/api/app/services/yearline_panel_service.py` | display reads — latest **raw** context (incl. stale) + latest series |
| `apps/api/app/routers/engine.py` | `GET /engine/yearline-context?ticker=…` → `YearlinePanelResponse` (auth-gated; returns raw context + series, either may be `null`) |

The panel endpoint reads the **raw** context (shows staleness honestly), distinct
from the engine-facing hydration which abstains on stale.

### Frontend (`apps/web`)

| Path | Role |
|---|---|
| `lib/yearline-types.ts` | `YearlineTrendSeries` + `YearlinePanelResponse` TS types; `toDistancePoints` (pure, null-preserving) |
| `lib/api/yearline.ts` | server-only `getYearlineContext` (JWT cookie, `no-store`) |
| `components/today/yearline/YearlineCard.tsx` | current-state card — gated `P(retry≤H)` bars (withheld where un-gated), stale badge, dormant→trend-state, basis chip, `P(success)` only where gated, disclaimer |
| `components/today/yearline/YearlineTrendChart.tsx` | Recharts headline distance-to-MA250 line; 0% reference line (the yearline); `connectNulls={false}` gaps |
| `components/today/yearline/YearlinePanel.tsx` | container — unavailable placeholder / card / chart-empty states |
| `app/today/page.tsx` | fetches the panel alongside the daily plan; a yearline failure degrades to no panel (never breaks the decision) |
| `package.json` / `pnpm-lock.yaml` | `recharts ^3.8.1` |

### Gate-respect on the display boundary (UX §4.1 / §6.3)

- per-horizon `P(retry≤H)` shown only where `gate_passed[h]`; else **"withheld ·
  building evidence"** (never hidden — the withheld state is the signal).
- `P(success)` / composite shown only where `success_gate_passed`.
- dormant (`repair_active=false`) → trend state, no synthesized retry prob.
- `is_stale` → explicit badge. Trend line **gaps** `null` (no interpolation).

### Acceptance evidence

- **Verified end-to-end against real Postgres + a live uvicorn**: 7 smoke tests
  pass (OM-Y2's 4 + OM-Y3's 3), including the full HTTP `GET /engine/yearline-context`
  round-trip (auth → DB reads → serialized panel payload) and trend-series ingest
  idempotency. Migration `0005` up/down round-trips.
- **api**: `ruff` clean · `mypy --strict app` clean (47 files) · suite **98 passed,
  31 skipped** (14 new yearline unit tests).
- **web**: `tsc --noEmit` clean · `eslint` clean · `vitest` **70 passed** (12 files;
  new YearlineCard/YearlinePanel/`toDistancePoints` tests) · `next build` succeeds
  (Recharts SSR + the `"use client"` boundary).

### Deferred to a follow-up

- The remaining §6 panels (price/MA overlay, 0-1 trend scores, gated-risk hazard /
  `p_retry_40d`) + regime-band shading + the "today blended" marker. The headline
  line + the full card ship here.

---

## Cross-cutting invariants (held by every milestone above)

- **No engine import of yearline-universe** (`check_no_broker_imports` + lean-deps gates).
- **Gate-respect:** consume `p_retry[h]` only where `gate_passed[h]`; `p_success` only
  where `success_gate_passed`; dormancy/staleness are honest abstention, not zero.
- **`must_not_auto_execute: true`** preserved on the contract (a `false` payload fails
  validation).
- **Determinism:** the contract is frozen + canonically hashed; the OM-Y4 replay pin
  will fold it into `inputs_hash`, with no-yearline decisions provably unchanged
  (guarded by the M1.24 golden suite).
