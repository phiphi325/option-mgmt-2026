# ADR-0005: `packages/engine` pure-function discipline (no I/O)

**Status**: Accepted
**Date**: 2026-04-29
**Plan ref**: v1.2 §1 + §5 + §16 (ML upgrade path)
**Related code**:

- `packages/engine/` (entire package, conceptually — content lands M0.6+)
- `apps/api/app/services/decision_service.py` (the I/O boundary, M0.6+)
- `apps/api/app/db/session.py` (the only place SQLAlchemy is allowed to live)

## Context

The engine is the product (per [ADR-0001](./0001-engine-first-architecture.md)). Phase 4 plans to replace specific engine nodes with ML models without changing the engine's external interface. Two requirements drop out:

1. **Testability**: every engine function must be unit-testable without spinning up a database, network, or clock. Golden fixtures (input → output) enable replay-style tests that catch regressions cheaply.
2. **Replay-ability**: every persisted `DailyDecision` carries `inputs_hash`. Replaying `produce_daily_decision(inputs)` against the same inputs must produce a byte-equivalent result. This is impossible if the engine reads anything from outside its arguments.

If the engine could call `db.get_user(...)`, hit the network, read environment variables, or sample non-seeded random values, those requirements break.

## Decision

`packages/engine/engine/**` follows strict purity rules:

**Allowed:**

- Imports from `numpy`, `scipy`, `pandas`, `py_vollib`, `mibian`, stdlib, and other engine modules.
- Pure functions over typed inputs (frozen `@dataclass` or Pydantic) → typed outputs.
- Deterministic computation given identical inputs.

**Forbidden:**

- Imports from `apps/api` or `apps/web`.
- Database access (no `sqlalchemy`, no `psycopg`, no direct file/HTTP DB clients).
- Network calls (no `requests`, no `httpx`, no provider SDKs — those live in `packages/engine/engine/providers/` interfaces, but their concrete implementations live in `apps/api` or `apps/jobs`).
- Filesystem reads/writes (no `open()`, no `Path.read_text()` against arbitrary paths).
- `os.environ` reads (config flows in as a parameter, not via env).
- `datetime.now()` / `time.time()` (`as_of` flows in as a parameter).
- `random.*` without an explicit, seeded `Random` instance passed as a parameter.

**The boundary**: `apps/api/app/services/decision_service.py` (lands M0.6+) hydrates inputs from the DB, calls the engine, persists the output. The engine doesn't know the DB exists.

**Single permitted exception**: `packages/engine/engine/config/` may load YAML config files (`weights.yaml`, `rules.yaml`) at startup. Config loading is a one-time bootstrap, not per-request I/O. This will be revisited in M0.6 — the cleaner pattern is to load config in the API layer and pass it in as a parameter, but the alternative (every API call wires weights through 5 layers of function arguments) is uglier in practice.

## Consequences

**Positive**

- Engine tests don't need a database, fixtures, or mocks. They run as fast pure-Python tests with golden vectors.
- Phase 4 ML node swaps preserve the interface; only the implementation changes. Old golden fixtures remain valid as regression tests if the deterministic V1 fallback stays available behind a feature flag.
- `inputs_hash` truly captures the full input space — every byte of the output is determined by the hash.
- Easier to vendorize the engine into a Jupyter notebook for one-off analysis or paper trading.

**Negative**

- Some convenience helpers (e.g. "look up user's profile") must live in the API service layer, not the engine. The engine receives `profile: UserStrategyProfile` as a parameter, never `user_id: UUID`.
- Adding `as_of` / `random_seed` parameters to engine entry points is slightly more verbose at call sites in the service layer.
- Config loading is the one violation; if the config layer grows beyond YAML files, we revisit the boundary.

**Neutral**

- Discipline is enforced primarily by code review and `mypy --strict` (catches accidental `os.environ` reads via type hints in many cases). M0.5+ stretch: `scripts/check_engine_purity.sh` greps for forbidden imports (e.g. `from sqlalchemy`, `import requests`, `os.environ`).

## Alternatives considered

1. **Allow DB access from engine** — rejected: blocks Phase 4 ML node swaps (ML serving needs different I/O patterns) and breaks `inputs_hash` semantics.
2. **Allow `datetime.now()` / `os.environ` for convenience** — rejected: makes replay tests fail; the same `inputs_hash` could produce different outputs over time as the wall clock drifts or env vars change.
3. **Use dependency injection (pass `db_session` into engine functions)** — rejected: still requires the engine to know about DB sessions, and complicates function signatures. Pre-hydrating inputs is cleaner.
4. **Hexagonal architecture (formal ports + adapters)** — rejected: more ceremony than this codebase needs at MVP scale. The "engine is pure, API is the boundary" rule is the same idea expressed lighter.

## References

- Plan v1.2 §1 — Product Brief (engine-first)
- Plan v1.2 §5 — System Architecture (layer cake; engine is below `/data/*` API)
- Plan v1.2 §16 — Future ML / AI enhancements (node swaps preserve interface)
- [ADR-0001](./0001-engine-first-architecture.md) — engine-first product framing
- [`docs/engineering-principles.md`](../engineering-principles.md) — Separation of Concerns, Engine section
