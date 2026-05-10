# Engineering Principles

These principles are **mandatory** for every code change in this codebase. They translate seven universal principles into concrete enforcement rules tied to our specific architecture: `apps/web` (Next.js 16.2.6), `apps/api` (FastAPI), `packages/engine` (pure-function Python), `packages/shared-types` (TypeScript generated from Pydantic).

## Core Principles

You must follow these principles for every code change:

### 1. Single Source of Truth (SSOT)

- Do not duplicate business state across frontend, backend, cache, and database without naming the authoritative owner.
- Derived values should be computed from canonical data unless explicitly persisted for audit or performance reasons.

### 2. Separation of Concerns

- UI components must not contain business rules, database logic, authorization logic, or external API orchestration.
- Business logic belongs in services / domain modules.
- Database access belongs in repositories or data-access modules.
- API routes / controllers should be thin.

### 3. Contract-First API Design

- Any API change must update the request / response schema first.
- Frontend code must use typed API clients or shared types where available.
- Do not silently change response semantics.

### 4. Security by Design

- Never trust client-side validation.
- Backend must enforce authentication and authorization.
- Never log secrets, tokens, credentials, or raw PII.
- Validate all external inputs.
- Use least privilege for new integrations.

### 5. Test-Driven Development

- For new business logic, write failing tests first.
- Implement the smallest code necessary to pass tests.
- Refactor only after tests pass.
- Do not remove or weaken tests to make implementation pass.

### 6. Observability

- Important backend flows must include structured logs.
- Errors must include safe diagnostic context and request IDs.
- Do not expose stack traces to users.

### 7. Simplicity

- Prefer simple modular design over premature microservices or over-abstraction.
- Do not introduce new dependencies unless justified.

## Required Workflow

**Before editing code:**

1. Summarize the relevant existing architecture (what's there, what's authoritative).
2. Identify the source of truth for the affected data (see [`ssot-constants-map.md`](./ssot-constants-map.md)).
3. Identify files likely to change.
4. Propose test cases.
5. Wait only if the task is ambiguous or high-risk.

**During implementation:**

1. Add or update tests first.
2. Make minimal implementation changes.
3. Run relevant tests:
   ```bash
   # Engine + API (M0.6+)
   cd apps/api && uv run pytest -q
   # Web
   cd apps/web && pnpm test
   ```
4. Run lint / typecheck:
   ```bash
   cd apps/api && uv run ruff check . && uv run mypy --strict .
   cd apps/web && pnpm lint && pnpm typecheck
   ```
5. Update `docs/` or API schemas if behavior changes.

**Before final response (PR description):**

1. Summarize changed files.
2. Summarize tests added / updated.
3. Report commands run and results.
4. List any remaining risks or assumptions.
5. List `docs/` files updated (or explicitly state "no docs change required" with reasoning).

---

## Project-Specific Enforcement

The sections below translate each general principle into concrete rules for this codebase. They are **mandatory**, not suggestions.

---

### SSOT — Single Source of Truth (project rules)

**Rule: Define once, import everywhere. Never copy-paste a value.**

**Checklist before introducing any constant:**

1. Run `grep -r "THE_VALUE" apps/ packages/` — does it already exist?
2. If yes, import it. Do not create a second definition.
3. If no, write it in the canonical file (see [`ssot-constants-map.md`](./ssot-constants-map.md)), then import.

**SSOT violation pattern to reject:**

```python
# ❌ WRONG — Regime redefined in apps/api when packages/engine owns it
class RegimeEnum(str, Enum):
    HIGH_IV_EVENT = "HIGH_IV_EVENT"
    HIGH_IV_PIN = "HIGH_IV_PIN"
    # ...
```

```python
# ✅ CORRECT
from engine.regimes import Regime  # canonical, M0.6+
```

```typescript
// ❌ WRONG — regime colors duplicated as raw hex in a component
const HIGH_IV_EVENT_COLOR = "#f59e0b";
```

```typescript
// ✅ CORRECT — Tailwind class wired to the CSS variable in globals.css
<div className="bg-regime-high-iv-event" />
```

**Cross-language constants** (same value in Python and TypeScript) must have a contract comment in the TypeScript file:

```typescript
// Generated from packages/engine/engine/regimes.py:Regime.
// Verify: cd apps/api && uv run python -c "from engine.regimes import Regime; print([r.value for r in Regime])"
import type { Regime } from "option-mgmt-shared-types"; // M0.6+
```

The full canonical map lives in [`ssot-constants-map.md`](./ssot-constants-map.md) and must be updated alongside any new constant.

---

### Separation of Concerns (project rules)

**React components (apps/web):**

- Components receive data via props or hooks. **No direct `fetch()` inside component bodies** — wrap in a hook (`useDailyDecision`) or call from a server component.
- **No business logic in JSX.** Compute in hooks or `lib/` transforms.
- CSS colors live in `app/globals.css` as CSS variables. Components reference Tailwind classes (`bg-primary`, `text-regime-breakout`), never raw hex.
- Regime colors via the `regime-*` Tailwind tokens, NEVER raw hex (per plan v1.2 §8).

**FastAPI routers (apps/api/app/routers/):**

- **Route handlers ≤ 30 lines.** Anything longer goes into `services/`.
- Routers call services, not engine modules directly. Exception: trivial reads (`db.get_user(id)`).
- Auth + validation enforced via `Depends(get_authenticated_user_id)` + Pydantic models.
- No business logic inline. Delegate to the appropriate service.

**Services (apps/api/app/services/):**

- One service per domain concept. `decision_service.py` orchestrates `produce_daily_decision()`; `csv_import.py` handles uploads. **Don't mix.**
- Services orchestrate `packages/engine` (pure Python) + `app.db` (SQLAlchemy).
- **Dependency flow: routers → services → (engine | db).** Engine and db do not depend on each other; engine does not import from `app.db`.
- Services do not import from routers.

**Engine (packages/engine/engine/):**

- **Pure functions only. No I/O. No DB. No network. No clocks.**
- This is the V1 deterministic core. ML upgrades in Phase 4 replace specific nodes (regime classifier, flow score model, confidence weights) without changing this invariant.
- Inputs are dataclasses; outputs are dataclasses. The API service layer hydrates inputs from the DB and persists outputs.
- Engine modules MAY import from each other (e.g. `decision/` imports from `market_state/`, `flow_score/`, ...). Engine modules MUST NOT import from `apps/api` or `apps/web`.

---

### Contract-First API Design (project rules)

**Adding a backend endpoint:**

1. Define the response shape in `apps/api/app/schemas/<domain>.py` (Pydantic).
2. Add the request shape if non-trivial (anything beyond a single string param).
3. Implement the router with a typed return value.
4. Regenerate TS types (M0.6+ via `packages/shared-types/scripts/generate.sh`).
5. Add the function signature + return type to `apps/web/lib/api.ts`.
6. Implement the frontend consumer.
7. Run `pnpm typecheck` to confirm TS agrees with the actual API shape.

**Changing an existing response:**

- **Never silently drop or rename a field.** Frontend will break at runtime, not at build time.
- Removed field: update Pydantic schema first → regenerate TS → TypeScript highlights every consumer that breaks.
- Renamed field: same as above, **plus** bump `engine_version` (per `scripts/check_engine_version_bump.sh`, M0.5+).

**Legacy → canonical mapping** (per plan v1.2 §22.1) lives in `docs/api/legacy.md` (M0.5+).

---

### Security by Design (project rules)

- **Never trust client validation.** Pydantic models in `apps/api/app/schemas/` are the source of truth for request validation. Web's zod schemas (M0.6+ generated) match Pydantic but ALSO get validated server-side.
- **Authentication enforced at the dependency level.** `Depends(get_authenticated_user_id)` on every protected route. Never check JWT inline in handlers.
- **Authorization scoped per user.** Every query in services filters by `user_id` matching the authenticated user. Cross-tenant access is impossible.
- **Never log secrets.** `JWT_SECRET`, API keys, OAuth tokens, password hashes. CI guard `scripts/check_no_secret_logs.sh` (M0.5+) greps for known anti-patterns.
- **Never log raw PII.** Email is OK; password hash is OK. Passwords (even briefly), SSNs, account numbers, full position dollar values to external sinks are NOT OK.
- **Validate all external inputs.** CSV uploads, query params, URL paths.
- **Least privilege** for new integrations. Tradier dev-tier (read-only), not full read-write. Brokerage integrations in P4 are read-only first; CI guard `scripts/check_no_broker_imports.sh` (M0.5+) enforces no broker write paths exist.
- **Disclaimer is a hard gate.** First-run modal cannot be dismissed via ESC or click-outside. Disclaimer text is the canonical source in [`disclaimers.md`](./disclaimers.md).

---

### Test-Driven Development (project rules)

**Order: Red → Green → Refactor.**

**Backend** (cd apps/api):

```bash
uv run pytest -q                                      # all tests
uv run pytest tests/test_health.py                    # single file
uv run pytest -q --cov=app --cov-report=term-missing  # with coverage
```

**Engine** (cd packages/engine, M0.6+):

```bash
uv run pytest -q
uv run pytest tests/test_market_state.py
```

**Frontend** (cd apps/web):

```bash
pnpm test                                             # vitest run
pnpm test:watch                                       # watch mode
pnpm typecheck                                        # tsc --noEmit
pnpm build                                            # next build (catches more than tsc)
```

**Test discipline:**

- New service method → write test first, then implement.
- New API endpoint → write integration test first.
- New engine function → write golden-fixture test first.
- Bug fix → write a test that reproduces the bug **before** fixing it.
- Never mock the database in integration tests — use a transactional Postgres fixture (planned for M0.5).
- Never weaken or skip tests to make implementation pass.

**Coverage targets** (per plan v1.2 §22.14 M1):

- `packages/engine` ≥ 85% line coverage.
- `packages/engine/engine/scoring/` 100% line coverage (per v1.2 §9.11).
- `apps/api` ≥ 70% (engine logic dominates; API is mostly orchestration).
- `apps/web`: smoke tests of critical UI flows. E2E in Playwright (M1.34+).

---

### Observability (project rules)

**Structured logging (apps/api):**

```python
import logging
logger = logging.getLogger(__name__)

logger.info("user=%s ticker=%s daily_plan_generated", user_id, ticker)
logger.warning("ticker=%s iv_history_insufficient n=%d", ticker, n)
logger.error("decision_service.produce failed", exc_info=True)
```

Use `%s` formatting (NOT f-strings) so the logger can defer string construction when the level is disabled.

**Never log:**

- `Settings.jwt_secret`, API keys, OAuth tokens, password hashes, password plaintext.
- Full traceback text in structured fields — use `exc_info=True` on the call.
- User-supplied ticker strings before validation (rare in MSFT-only MVP).
- Raw `inputs` blob from `market_states` (it's persisted in the DB; logging duplicates).

**Errors:**

- `apps/api` returns RFC 7807 `ProblemDetails` (per plan §7).
- Stack traces never reach users; in dev (`Settings.is_dev=True`) the exception message goes in `detail`.
- M0.5+ wires Sentry; the `request_id` (added M0.5) goes in every log line and every 500 response.

---

### Simplicity (project rules)

- **No new Python deps** without adding to `apps/api/pyproject.toml` (or `packages/engine/pyproject.toml` once it ships) AND documenting the justification in the PR description.
- **No new npm packages** without adding to `apps/web/package.json` AND documenting the justification.
- **Helper functions used in only one file stay in that file.** Extract only when used in 2+ files.
- **Three similar lines is better than a premature abstraction.** Add abstraction when the third repetition appears.
- **Scripts in `scripts/`** are one-shot operational tools, not production code. They may be simpler and less abstracted.
- **Phase 1 Hard Contract** (per plan §3): no drill-down dashboards in MVP. Every PR opened during Phase 1 must answer "does this advance the Today screen rendering a coherent DailyDecision?" If no, the PR is rejected.
