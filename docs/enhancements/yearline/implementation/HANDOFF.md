# Yearline integration — handoff / resume-here

**For:** whoever (you, later) picks the yearline track back up — likely after a
spell of Phase-1 milestone work. This is the "where things stand + what's next +
the traps" doc. Pairs with the as-built [`README.md`](./README.md) (file maps +
acceptance evidence) and the decision record
[ADR-0009](../../../decisions/0009-adopt-yearline-statistical-context-provider.md).

> Educational research only; not financial advice. Every yearline surface is
> `must_not_auto_execute: true` and **gated**.

---

## 1. Where the track stands (2026-06-10)

| Milestone | Scope | Status |
|---|---|---|
| OM-Y0 | enhancement assessment + ADR-0009 (no code) | ✅ merged (PR #6) |
| OM-Y1 | `engine.yearline.YearlineContext` contract + TS codegen + contract test; engine 1.7.0→1.8.0 | ✅ merged (PR #7) |
| OM-Y2 | `yearline_context` table + ingest job + hydration service | ✅ merged (PR #8) |
| OM-Y3 | read-only Today panel (card + headline distance-to-MA250 line) | ✅ pushed, PR open (`feat/om-y3-yearline-panel`) |
| **OM-Y4** | **gated engine consumption — the prize** | ⏳ **not started** (next) |
| OM-Y5 | stretch: Market-State enrichment / collar-intent | ⏳ not started |

The **C-track (read-only) is essentially done**: ingest → persist → hydrate →
surface. OM-Y4 is the **A-track** (let the gated signal influence the decision).

**Branch state when this was written:** `feat/om-y3-yearline-panel` is rebased on
`upstream/main` (knowlingo) and carries one commit. Once it merges, branch OM-Y4
off the updated main.

---

## 2. How to resume — start OM-Y4

OM-Y4 is the only **output-changing** milestone. Acceptance bar: a decision made
**without** yearline context must hash **byte-identically** to today (back-compat),
and the gated signal influences a decision **only** where its trust gate passes.

### The build (per ADR-0009 + integration plan §3–§5)

1. **Pure optional kwarg.** Add `yearline_context: YearlineContext | None = None` to
   `engine.decision.produce_daily_decision(...)` — mirrors the `futures_basis=0`
   stub. Thread it through; `None` ⇒ the pre-yearline decision, unchanged.
2. **4th replay pin.** Extend `engine.decision.compute_inputs_hash()` to fold in a
   canonical hash of `{adapter_version, schema_version, model_stack_version}` + the
   consumed fields — **only when context is present**. Persist a new
   `yearline_context_version` pin on `DailyDecision`. **Reuse
   `engine.decision.serialize_canonical`** for the canonical hash (don't hand-roll).
3. **Gate-respect in the decision path.** New `rules.yaml` predicate clause(s) +
   evaluator(s) in `engine/recommendation/rules.py` that read `p_retry[h]` **only
   where `gate_passed[h]`**; a Confidence-Composer component active **only where the
   gate passes**. Ungated / dormant / stale ⇒ context-only (no influence). Unit-test
   the ungated-leak case explicitly.
4. **Confidence component shape (open decision — see §4).** ADR-0003's composer is
   multiplicative → the term is either a bounded penalty multiplier (recommended:
   a *gated defensive temper*) or a positive-score contributor. Bumps
   `weights_version` (and `weights.yaml`).
5. **Version + docs.** Engine `__version__` minor bump (1.8.0 → 1.9.0) + a matching
   `CHANGELOG.md [1.9.0]` entry (both CI guards enforce this — see §3). ADR note.

### The non-negotiable regression guard

After wiring OM-Y4, **regenerate the M1.24 golden suite** and confirm the only diff
on the no-yearline fixtures is the `engine_version` stamp — the decision bytes +
`inputs_hash` must be otherwise identical. The 12 goldens in
`packages/engine/tests/fixtures/master_decisions/` are exactly the net that proves
back-compat. (Consider adding a 13th fixture *with* a yearline_context to lock the
gated path.)

---

## 3. Traps & lessons (paid for already — don't re-pay)

- **Any change under `packages/engine/engine/` requires a `__version__` bump**
  (`scripts/check_engine_version_bump.sh`) **and** a matching `CHANGELOG.md`
  `## [x.y.z] — DATE` entry (`scripts/check_changelog_entry.sh`). Both are CI
  guards. A version bump also means **regenerating the 12 golden `expected.json`**
  (their `engine_version` stamp changes) — run
  `uv run python packages/engine/scripts/regenerate_decision_goldens.py --all`.
- **`apps/api` and `apps/web` have separate gates.** api: `ruff` + `mypy --strict
  app` + `pytest`. web: `pnpm lint` + `tsc --noEmit` + `vitest` + `next build` +
  shared-types typecheck. The `web` CI job runs `pnpm install --frozen-lockfile` — a
  dep change must commit the updated **root** `pnpm-lock.yaml`.
- **Generated TS (`shared-types`).** A new/changed engine Pydantic model must be
  added to `packages/shared-types/scripts/generate.py` and the `.ts` regenerated, or
  the codegen drift gate fails. (OM-Y1 taught the generator `dict` + `Literal`.)
- **psycopg + untyped NULL params.** A `text()` query with `:p IS NULL OR col <= :p`
  fails (`f405`) when `:p` is NULL — psycopg can't infer the type. Cast both:
  `CAST(:p AS date) IS NULL OR col <= CAST(:p AS date)`. (Cost an OM-Y2 smoke fail.)
- **Verify DB/HTTP paths against a real Postgres**, not just unit mocks — the
  untyped-NULL bug only surfaced live. Recipe in §5.
- **shared-types `tsc: not found` locally** is a non-issue — that package has no
  local `node_modules`; CI resolves `tsc` via the workspace install. The web
  typecheck importing `YearlineContext` already proves the generated TS is valid.

---

## 4. Open questions still pending (decide at OM-Y4)

These were raised in the assessment §5 and remain the consumer's call:

1. **Delivery mechanism** for the nightly artifact: object-store / release-asset vs a
   producer-written row. (Ingest currently takes a dict / file path; nothing reads a
   schedule yet — see §6.)
2. **Which fields influence the decision** vs display-only. *Recommendation:* only
   **gated `p_retry[h]` + repair/trend state** at first; hold `p_success` / composite.
3. **Confidence-component shape:** gated defensive **penalty multiplier**
   (recommended) vs positive-score contributor. Bumps `weights_version`.
4. **MSFT-only vs universe:** contract is MSFT-shaped (Phase 1); the producer must
   still run the pooled universe nightly (MSFT's gate trust depends on pooling).

---

## 5. Verification recipe (local live-DB smoke)

There is a running Postgres container `reflexivity-pg` (creds `postgres:dev`, port
5432). To run the yearline smoke tests end-to-end:

```bash
docker exec reflexivity-pg psql -U postgres -c "CREATE DATABASE yln_smoke_test"
docker exec reflexivity-pg psql -U postgres -d yln_smoke_test -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
cd apps/api
export DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/yln_smoke_test"
export JWT_SECRET="test-jwt-secret-at-least-16-chars-long"
uv run alembic upgrade head
# start uvicorn (port 8077) in the background, then:
export SMOKE_API_URL="http://127.0.0.1:8077/api/v1"
uv run pytest tests/test_smoke_yearline.py tests/test_smoke_yearline_panel.py -p no:cacheprovider
# teardown: kill uvicorn; docker exec reflexivity-pg psql -U postgres -c "DROP DATABASE yln_smoke_test"
```

Smoke tests gate on `SMOKE_API_URL` (skipped without it), so they no-op in the unit
`api` CI job and run in the `smoke` job.

---

## 6. Producer side (yearline-universe repo) — not wired yet

The producer (V13.8 adapter, `YearlineContext` + `YearlineTrendSeries` artifacts) is
**delivered** but its nightly GitHub Action is **not scheduled**. Per the handoff:
keep it `workflow_dispatch`-first; flip to `schedule:` only once OM-Y2 ingest is live
(it is now) **and** a cross-repo contract test runs in the producer's CI. The
consumer ingest jobs (`app/jobs/ingest_yearline.py`) currently take a dict or a file
path — there is **no scheduled/object-store reader yet**; that wiring is a small
follow-up when you turn the nightly on.

---

## 7. Pointers

- Decision + boundary: [ADR-0009](../../../decisions/0009-adopt-yearline-statistical-context-provider.md)
- Feasibility (four-test): [`../../0002-yearline-context-assessment.md`](../../0002-yearline-context-assessment.md)
- Source analysis + producer handoff: [`../`](../) (`assessment.md`, `integration_design_and_plan.md`, `two_repo_strategy_and_deployment.md`, `producer-handoff/`)
- As-built file maps + acceptance: [`./README.md`](./README.md)
- Engine contract: `packages/engine/engine/yearline/`
- API ingest/hydrate/panel: `apps/api/app/jobs/ingest_yearline.py`, `apps/api/app/services/yearline_{hydration,panel}_service.py`, `apps/api/app/routers/engine.py` (`GET /engine/yearline-context`)
- Web panel: `apps/web/components/today/yearline/`, `apps/web/lib/yearline-types.ts`
