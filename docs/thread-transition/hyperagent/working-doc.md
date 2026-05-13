# Thread Context — Working Doc Snapshot

**Document ID:** `cmp013uxw1jsy06advu82hr79`  
**Snapshot taken:** 2026-05-13  
**Version:** 85

---

## Numbers & Values

Current state on main (after M1.9 merge):
- Engine version: 1.0.0 (major bump on M1.9 — breaking contract change in recommend())
- Repo HEAD: fbc3998073e56a69dd0cd73b0a1f32f85461c58c (squash of PR #38)
- Branch convention: feat/<milestone>-<slug>; squash-merge with comprehensive recap message
- CI gates: 5 jobs (guards, api, engine, web, smoke); all 5 must be green
- Test count on engine: ~390 (162 added in M1.9)
- shared-types codegen: regimes.ts, profiles.ts, types.ts, index.ts (CI verifies no drift)

M1.x shipped milestones (per plan v1.2 §17):
- M0.6: shared types + codegen bridge
- M1.1-M1.3: foundation primitives
- M1.4: Market State Engine classify()
- M1.4a: scoring primitives (iv/structure/event)
- M1.5b: Flow Score Engine
- M1.6: Black-Scholes Greeks (replaced skew_25d stub)
- M1.7: Recommendation Engine (originally labeled M1.8 — milestone-numbering swap corrected in CHANGELOG 1.0.0)
- M1.8: Strike Selector (originally labeled M1.7 — same swap)
- M1.9: YAML rules + plan-true recommend() contract refactor (this thread)

M1.x remaining (per plan §17):
- M1.10: Confidence Composer + weights.yaml + 7 component fns (§9.7 + ADR-0003) — size M
- M1.11: Execution Feasibility Module (§9.8) — size M
- M1.12: Execution downgrade callback into Strike Selector — size S
- M1.13: Master Decision Engine + DailyDecision schema (§9.6) — size L

M1.14 shipped (2026-05-12, PR #45 → main commit c0583ed):
- Engine version: 1.0.0 (unchanged — no engine/ changes in M1.14)
- API now exposes POST /api/v1/engine/daily-plan + POST /api/v1/engine/recommend
- daily_decisions has UNIQUE (user_id, inputs_hash) for idempotent persistence
- Alembic head: 0002_dd_unique_user_hash (note: revision ids must be ≤32 chars, alembic_version VARCHAR(32))
- packages/engine is now an installable uv workspace package (hatchling build-system, packages = ["engine"])
- CI smoke job pytest step now sets DATABASE_URL + JWT_SECRET (smoke tests open their own psycopg connections)
- 4 commits squashed: 1d04c8d (initial) + 9c006bc (engine pyproject) + 1d7a588 (revision id) + 9425ccc (CI env)
- 21 new tests total: 16 unit (test_engine_endpoints.py) + 5 smoke (test_smoke_engine.py)

M1.15 shipped (2026-05-12, PR #47 → main commit 22b0033):
- Three new POST endpoints: /engine/what-if, /engine/market-state, /engine/flow-score
- 14 new unit tests + 3 new smoke tests (no migration, no engine version bump)
- CI 5/5 green on first push (no fix commits needed)
- Dev-spec deviation logged: FlowScoreRequest does NOT carry `profile` (engine.flow_score.compute() doesn't take one; §9.3a is the source of truth). Follow-up: patch the dev spec to drop the profile field from its schema section.
- After M1.15, 5 of 8 engine sub-step endpoints are HTTP-reachable (daily-plan, recommend, what-if, market-state, flow-score). Remaining 3 ship in M1.16: strike-candidates, execution-check, collar-builder.

M1.16 shipped (2026-05-12, PR #48 → main commit 726ec37, reduced scope):
- 2 new POST endpoints: /engine/strike-candidates, /engine/execution-check
- 10 new unit tests + 2 new smoke tests
- CI 5/5 green on first push (twice in a row after M1.15 — pattern holding)
- Bundled docs corrections: removed M1.11a/M1.11b "shipped" rows from retrospective (they never shipped); corrected engine version trajectory 1.0.0 → 1.4.0 (M1.10/M1.11/M1.12/M1.13 minor bumps); flipped M1.15 to shipped in Phase 1 README
- Deferred from original M1.16 scope: M1.16a /collar-builder (engine module missing), M1.16b /market/msft/latest (bundle with M1.17)
- After M1.16, 7 of 8 §7 engine sub-step endpoints are HTTP-reachable. Only missing: /engine/collar-builder. Engine sub-step API surface essentially complete except for collar-builder.
- Engine version stays at 1.4.0. alembic_heads stays at 0002_dd_unique_user_hash.

Important correction logged in retrospective summary doc:
- M1.11a (Collar Builder engine) and M1.11b (Collar Builder integration into Master Decision) were NEVER shipped, despite being listed as such in my original retrospective summary. The packages/engine/engine/collar_builder/ module does not exist on main. These remain blocker dependencies for any future /engine/collar-builder endpoint work.

Tutorial added (2026-05-12, PR #49 → main commit 3b3df37):
- docs/tutorials/engine-api-reference.md (960 lines, ~42 KB, ~35 min read)
- Covers all 7 currently-shipped /api/v1/engine/* endpoints (M1.14 + M1.15 + M1.16)
- Introduces a new doc style: API-layer reference complementing the original engine-layer pedagogical tutorials
- README split into engine-layer + API-layer indexes; "still to write" list reorganized into the same two categories
- Engine-module entries in "still to write" cross-link to the corresponding API-reference sections that already document those modules at the HTTP level
- New API-layer follow-up entries for M1.17 (CSV-import companion) and M1.18 (Today screen client tutorial) when those ship
- CI 5/5 green first try (4th consecutive feature/docs PR with clean first-try CI)

M1.17 shipped (2026-05-12, PR #50 → main commit 6d2f77a, reduced scope):
- 10 new endpoints across 4 routers
  * GET/PUT /api/v1/profile
  * GET/POST/PATCH /api/v1/outcomes[/{outcome_id}] (cursor-paginated)
  * POST /api/v1/data/{positions,option-positions,chain,iv,events}/import-csv
  * GET /api/v1/market/{ticker}/latest (M1.16b pickup)
- Migration 0003_imp_unique_constraints (28 chars; positions + option_positions UNIQUE)
- alembic_heads: 0002_dd_unique_user_hash → 0003_imp_unique_constraints
- 23 unit tests + 5 smoke tests
- Engine version stays at 1.4.0 (no engine/ touch)

M1.17 required 2 fix commits before merging:
- Fix #1 (6149c91): ruff 59 errors + mypy --strict 6 errors. Mostly inline-semicolons in csv_import_service.py + import sorting + missing type parameters.
- Fix #2 (e042cfd): two pytest tests reached DB-touching paths. Root cause: Starlette TestClient defaults to raise_server_exceptions=True. Fixes: added API-layer ProfileUpdateRequest BaseModel with extra="forbid"; removed test_market_latest_returns_422_on_missing_data unit test.

Deferred to M1.17.5 follow-up: making DailyPlanRequest.inputs optional with DB-driven hydration.

Architectural lesson for future M1.x endpoints: when adding routes whose handler bodies touch the DB, write unit tests ONLY for paths that fail BEFORE the session dep is exercised (auth 401, Pydantic 422, FastAPI Query 422, file-size 413). Anything that reaches `session.execute()` must be smoke-tested.

M1.17.5 shipped (2026-05-12, PR #51 → main commit 1d442bd):
- DailyPlanRequest.inputs: EngineInputs → EngineInputs | None = None
- New app/services/inputs_hydration_service.py (~480 lines)
- Public API: hydrate_engine_inputs(*, session, user_id, ticker, as_of) -> EngineInputs
- 3 prerequisite 422s: missing_chain, insufficient_iv_history, missing_positions
- V1 simplifying assumptions: breakout_signal=0.0, oi_concentration=0.0, gap_pct=None, trend_strength=0.5 (engine fallback)
- Spot derivation: highest-OI strike at nearest expiry (mirrors market_service)
- 4 new smoke tests; required 1 fix commit (b8de3ff): pinned as_of in idempotency test

API tutorial extended for M1.17 + M1.17.5 (2026-05-12, PR #52 → main commit 2f1f518):
- docs/tutorials/engine-api-reference.md: 960 → 1413 lines (~42 → ~62 KB)
- 5 new sections (§§12-16)
- §20 Glossary added 16 new terms

M1.18 shipped 2026-05-12: PR #53 (00063c9 → c7712ed) — first frontend milestone since M0.4
- 16 files: 7 source + 6 test + 2 mod + 1 doc; +1,085 / -55 lines
- CI 5/5 green on first push; zero fix commits

M1.18 retrospective shipped: PR #54 (b2afe22 → 1ca17a6) — README flipped M1.17.5 + M1.18 to shipped
Current main HEAD at M1.18 close: 1ca17a601e007dbd151d858ce12a466630487274
Engine version at M1.18 close: 1.4.0

---

*(Entries below added in this thread — M1.11a + M1.16a work)*

M1.11a shipped (PR #56 → main, engine 1.5.0):
- `engine.collar_builder.build()` — grid-search solver, 3 intents (zero_cost / income / defensive)
- Per plan v1.2 §9.10

M1.16a shipped (2026-05-13, PR #60 → main commit 9c63a15):
- `POST /engine/collar-builder` — thin service layer + Pydantic schemas + router + 9 tests
- §22.11 H5 enforced: underlying_qty from DB positions table (never from request body)
- CollarBuilderRequest uses extra="forbid"
- Guard sequence: ticker ∈ _SUPPORTED_TICKERS → IV history ≥ 30 → underlying_qty ≥ 100 → ValueError → 422
- Reuses _hydrate_* helpers from inputs_hydration_service.py
- 2 CI fix commits: ruff I001 (aliased import split) + ProblemDetails title vs detail
- Engine version unchanged: 1.5.0. alembic_heads unchanged: 0003_imp_unique_constraints
- API endpoint count: 17 → 18
- Test count: ~830 → ~840

Post-merge docs commit (2026-05-13, commit c90444f):
- README.md: M1.16a row added, Status + Where we are updated (17→18 endpoints)
- docs/thread-transitions/2026-05-13-t02-m1.16a-collar-builder-endpoint.md: full handoff record

---

## Corrections

*(empty)*

---

## Constraints

- Engine pure-function discipline (ADR-0005): no I/O, no DB, no network in packages/engine/
- Any engine change must bump packages/engine/engine/version.py per SemVer rules; CI guard scripts/check_engine_version_bump.sh enforces
- Codegen drift: changes to regimes.py / profiles.py / types.py / version.py require regenerating packages/shared-types/src/
- Sandbox is Python 3.9 but project targets 3.14 — zip(..., strict=True) requires noqa B905 with explanatory comment
- Wilder ADX needs 2n + 10 bars to stabilize (not 2n + 1); compute_trend_strength returns 0.5 sentinel below threshold rather than raising
- Branch convention: feat/<milestone>-<slug>; squash-merge with comprehensive recap as squash-commit message
- CI: 5 jobs (guards, api, engine, web, smoke) ~3 min; all 5 must be green before merge
- Post-merge: update CHANGELOG.md plus docs/thread-transitions/ when thread closes
- engine._utils.clip01 is the canonical [0,1] saturation
- M1.4a scoring functions land in packages/engine/engine/scoring/ at 100% line coverage

---

## Key Entities

- Repo: csupenn/option-mgmt-2026 (default branch main)
- Engine package: packages/engine/engine/ (pure functions per ADR-0005, ruff + mypy-strict)
- Engine version on main at thread close: 1.5.0
- Plan doc: cmokf2twq0gsv06adlij0glqs (v1.2 — canonical milestone + contract source)
- Thread-transition docs: docs/thread-transitions/ (t01 = Phase 0 + M1.1-M1.3; t02 = M1.16a this thread)
- Cached plan markdown: /agent/stored_files/cmp1qcrht00n507adz52we01i_msft-option-risk-management-engine-phased-development-plan.md

---

## Decisions

Locked architecture (do not relitigate):
- ADR-0001: engine-first architecture
- ADR-0002: 6-regime taxonomy
- ADR-0003: multiplicative Confidence Composer (M1.10 formalizes)
- ADR-0004: disclaimer fail-open
- ADR-0005: engine pure-function discipline; filesystem boundary confined to yaml_loader.py
- ADR-0006: API errors RFC 7807
- ADR-0007: Python 3.14 + Next.js 16.2.6
- ADR-0008: Phase 1.5 rules.yaml hot-swap; Phase 4 ML node-swap

M1.9 decisions (locked):
- Plan-true recommend() signature: kwargs-only; returns RecommendationResult
- Eight V1 rules in packages/engine/config/rules.yaml per §22.8; first-match-wins evaluation
- 15 clause vocabulary in engine.recommendation.rules._CLAUSE_EVALUATORS
- EmittedAction StrEnum replaces M1.7's StrategyClass
- _composite_confidence is a placeholder stub returning a clamped product; M1.10 replaces it

M1.16a decisions (confirmed, not new):
- §22.11 H5: underlying_qty always from DB, never from request body
- Service reuses _hydrate_* helpers from inputs_hydration_service.py
- Guard sequence: ticker → IV history ≥ 30 → underlying_qty ≥ 100 → ValueError → 422
- _SUPPORTED_TICKERS = frozenset({"MSFT"}) — Phase 1 MSFT-only; unify with market_service in Phase 2

M1.18 decisions (locked):
- Server-only enforcement via cookies() from next/headers (no server-only npm package)
- Regime color palette: 6 regimes mapped to static Tailwind class strings (JIT-visible)
- STRATEGY_LABELS map for 9 known M1.9 emit codes + humanizeSnakeCase fallback
- DailyDecision types: permissive [k: string]: unknown indexer on V1 interfaces

---

## Plan Overview

Post-merge documentation for M1.16a. Update README.md, CHANGELOG.md, create transition doc, and create handoff memory for next thread.

---

## Plan Tasks

- [x] Fetch current README.md from main and add M1.16a milestone row
- [x] Check for and update CHANGELOG.md (no entry needed — M1.16a is API-only, no engine version bump; noted 1.5.0 gap as known debt)
- [x] Check for thread-transitions directory and create transition doc
- [x] Commit all doc updates to main via GitHub (commit c90444f)
- [x] Create handoff memory for next thread

---

## Plan Context

*(empty)*
