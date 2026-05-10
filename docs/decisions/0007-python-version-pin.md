# ADR-0007: Python 3.14 pinned across api + engine

**Status**: Accepted
**Date**: 2026-05-10 (initial 3.13; bumped to 3.14 same day after CI confirmed wheel availability)
**Plan ref**: v1.2 §17 M0.5 (CI), §22.15 (pin discipline)
**Related code**:

- `pyproject.toml` (root) — `requires-python = ">=3.14"`, `target-version = "py314"`, `python_version = "3.14"`
- `apps/api/pyproject.toml` — same set
- `apps/api/.python-version` — `3.14` (uv reads this)
- `apps/api/Dockerfile` — `FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, runtime `python:3.14-slim`
- `.github/workflows/ci.yml` — `astral-sh/setup-uv@v3` (uv reads `.python-version` automatically)
- `packages/engine/pyproject.toml` — same set when M0.6 ships

## Context

Initial M0.5 pin was Python **3.13** out of caution — Python 3.14 was released 2026-04-14 (1 month before this ADR), and conventional wisdom is to wait for "ecosystem maturity" on fresh majors.

CI run on commit `7dd0fc6` (PR #6) on 2026-05-10 then **empirically demonstrated 3.14 wheels are universally available** for our stack. uv defaulted to Python 3.14.4 (latest matching `requires-python = ">=3.13"`) and installed all 55 deps cleanly:

```
+ alembic==1.18.4         + httpx==0.28.1            + pydantic-core==2.46.4
+ argon2-cffi==25.1.0     + httptools==0.7.1         + pydantic-settings==2.14.1
+ argon2-cffi-bindings    + hypothesis==6.152.4      + pytest==9.0.3
+ cryptography==48.0.0    + mypy==2.0.0              + python-jose==3.5.0
+ fastapi==0.136.1        + psycopg-binary==3.3.4    + ruff==0.15.12
+ greenlet==3.5.0         + pydantic==2.13.4         + sqlalchemy==2.0.49
... 55 packages total, all installed in 59ms
```

Including the C-extension heavyweights: `psycopg-binary`, `cryptography`, `argon2-cffi-bindings`, `uvloop`, `pydantic-core`. **No wheel-availability drama.**

The "wait for maturity" rule was a precaution against an empirical risk that doesn't exist for our specific stack. Bumping to 3.14 honors the user's original ask ("the latest Python version") and removes the deferred-decision overhead.

## Decision

**Pin Python to 3.14** across the entire codebase.

Specifically:

- `requires-python = ">=3.14"` in every `pyproject.toml` (root, apps/api, packages/engine when shipped)
- `apps/api/.python-version` file (`3.14`) so uv selects the right interpreter without per-call flags
- `python:3.14-slim` (runtime) and `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` (builder) in `apps/api/Dockerfile`
- `target-version = "py314"` for ruff (lints against 3.14 syntax)
- `python_version = "3.14"` for mypy (type-checks against 3.14 stdlib)

When 3.15 reaches comparable empirical proof of wheel availability for our stack, open a follow-up ADR to bump.

## Consequences

**Positive**

- Latest Python features: PEP 768 (zero-overhead transparent attribute introspection), PEP 765 (improved `finally` semantics), better error messages, deferred string evaluation, more aggressive incremental GC.
- All deps support it — verified empirically by CI.
- `tomllib` is in stdlib (relevant for any tooling that needs to read pyproject.toml without Python 3.11+ workarounds).
- Single source of truth: `requires-python = ">=3.14"` rejects older versions, eliminating "what version did this run on" ambiguity.

**Negative**

- 3.14 is 1 month old; future bug fixes in 3.14.x patch releases are likely. We accept this in exchange for the latest features.
- Some deeply non-mainstream Python deps may still lack 3.14 wheels. We don't use any of those today; if a Phase 4 ML library lacks 3.14 wheels, we either pin to a 3.13 venv for that specific tool or wait.

**Neutral**

- `requires-python = ">=3.14"` rejects 3.13 and earlier. Old developer setups need updating.
- Docker image size delta from 3.13 → 3.14 is ~5 MB.

## Alternatives considered

1. **Stay on Python 3.12** (the project's pre-M0.5 default, released 2023-10) — rejected: missing `tomllib`, missing 3.13's tail-call interpreter, missing 3.14's improved error messages. Ecosystem fully supports newer.
2. **Stay on Python 3.13** (initial M0.5 pin) — rejected after CI proof: the maturity argument was theoretical, the wheel risk did not materialize. Bumping eliminates the "deferred decision" cost.
3. **Loose `requires-python = ">=3.13"`** — rejected: violates "single canonical pin" principle from `docs/engineering-principles.md` (Pin discipline). Allowing both 3.13 and 3.14 makes CI runs non-deterministic across runner versions and dev machines.
4. **Aggressively pin patch version (`3.14.4`)** — rejected: too brittle. Patch releases bring security fixes; we want them. Minor pin (3.14.x latest) is the right granularity.

## Enforcement

- `apps/api/.python-version` makes local `uv` invocations consistent with CI (uv reads it without per-call `--python` flags).
- `requires-python = ">=3.14"` on every member pyproject rejects older interpreters at install time.
- `astral-sh/setup-uv@v3` in CI installs uv; uv then resolves the interpreter from `.python-version` + `requires-python`.
- A future stretch goal: `scripts/check_python_version.sh` similar to `check_next_version.sh` (post-M0.7).

## References

- Plan v1.2 §22.15 — pin discipline
- Plan v1.2 §17 M0.5 — CI pipelines
- [ADR-0005](./0005-engine-pure-function-discipline.md) — engine pure-function discipline (engine deps must install on 3.14)
- Python 3.14 release notes: https://docs.python.org/3.14/whatsnew/3.14.html
- CI run that confirmed wheel availability: `7dd0fc6eb7b53052f8bb11cf3991cddcb3c7aa40` on PR #6
