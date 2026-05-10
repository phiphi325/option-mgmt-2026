# option-mgmt-2026

**MSFT Option Risk Management Engine** — a decision engine that answers a single question every day for a long-term MSFT holder: **"What should I do today?"**

Long equity + tactical options overlay. Deterministic, audit-trail-first, engine-first system. Not a trading bot; not a Bloomberg-clone dashboard. Educational decision-support only.

## Status

**Phase 1 — Engine MVP. In progress.** Engine `0.4.0`, 121 tests on `main`. See [`CHANGELOG.md`](./CHANGELOG.md) for per-version detail and [`docs/thread-transitions/`](./docs/thread-transitions/) for thread-by-thread handoff records.

### Phase 0 — Foundation ✅ (all 7 milestones merged)

| | What | PR |
|---|---|---|
| ✅ | M0.1 — pnpm + uv monorepo, Docker Compose, Makefile | [#1](https://github.com/csupenn/option-mgmt-2026/pull/1) |
| ✅ | M0.2 — Postgres schema + Alembic migration `0001_init` | [#2](https://github.com/csupenn/option-mgmt-2026/pull/2) |
| ✅ | M0.3 — FastAPI shell, `/health` `/healthz` `/version`, JWT scaffolding, auth stubs | [#3](https://github.com/csupenn/option-mgmt-2026/pull/3) |
| ✅ | M0.4 — Next.js 16.2.6 shell, Disclaimer gate, Tailwind, Vitest | [#4](https://github.com/csupenn/option-mgmt-2026/pull/4) |
| ✅ | docs foundation + 6 ADRs (engineering principles + architecture + SSOT map) | [#5](https://github.com/csupenn/option-mgmt-2026/pull/5) |
| ✅ | M0.5 — CI pipelines + pre-commit + Dependabot + policy guards | [#6](https://github.com/csupenn/option-mgmt-2026/pull/6) |
| ✅ | M0.6 — Engine types: regimes, profiles, ChainSnapshot, TS type generation | [#17](https://github.com/csupenn/option-mgmt-2026/pull/17) |
| ✅ | M0.7 — End-to-end smoke test | [#22](https://github.com/csupenn/option-mgmt-2026/pull/22) |

### Phase 1 — Engine MVP (in progress)

| | What | PR | Engine |
|---|---|---|---|
| ✅ | docs — enhancement-spec adoption roadmap (ADR-0008): 6 adopt, 2 defer, 0 reject | [#23](https://github.com/csupenn/option-mgmt-2026/pull/23) | — |
| ✅ | M1.1 — IV rank/percentile + HV (close-to-close + Parkinson) + 252-day seed | [#24](https://github.com/csupenn/option-mgmt-2026/pull/24) | `0.2.0` |
| ✅ | M1.2 — max pain + expected move + put/call ratios | [#25](https://github.com/csupenn/option-mgmt-2026/pull/25) | `0.3.0` |
| ✅ | M1.3 — Wilder ADX trend strength + 4-component breakout signal + `clip01` helper | [#26](https://github.com/csupenn/option-mgmt-2026/pull/26) | `0.4.0` |
| ⏭️ | M1.4 — Market State Engine `classify()` + 24 regime fixtures | — | `0.5.0` |
| | M1.5 — Flow Score Engine + OI walls + dealer-gamma proxy | — | — |
| | M1.6–M1.25 — Strike Selector, Recommendation, Decision, Confidence Composer, Execution Feasibility, `/engine/*` APIs, Today screen | — | — |

See plan v1.2 §17 for the full milestone table; §22 is the canonical correction sheet (audit-resolved 2026-05-09).

## Stack

| Layer | Pin | Source of truth |
|---|---|---|
| Python | **3.14** ([ADR-0007](./docs/decisions/0007-python-version-pin.md)) | `apps/api/.python-version`, `pyproject.toml`, `apps/api/Dockerfile` |
| Next.js | **16.2.6** ([ADR § plan v1.2 §22.1](./docs/ssot-constants-map.md)) | `apps/web/package.json` + `scripts/check_next_version.sh` |
| React | `^19.0.0` (paired with Next 16) | `apps/web/package.json` |
| Node | `26.x` (web runtime) | `apps/web/Dockerfile` |
| pnpm | `9.12.0` (Docker), `10.x` accepted in dev | `apps/web/Dockerfile` |
| PostgreSQL | `16-alpine` | `docker-compose.yml` |
| Tailwind | `^3.4` | `apps/web/package.json` |
| FastAPI | `>=0.115` | `apps/api/pyproject.toml` |
| SQLAlchemy | `>=2.0` (async) | `apps/api/pyproject.toml` |

## Documentation

Read [`docs/`](./docs/) before any code change:

- [`docs/engineering-principles.md`](./docs/engineering-principles.md) — **mandatory** principles + project rules.
- [`docs/architecture.md`](./docs/architecture.md) — layer cake + component map + data flow.
- [`docs/ssot-constants-map.md`](./docs/ssot-constants-map.md) — canonical home for every shared constant.
- [`docs/disclaimers.md`](./docs/disclaimers.md) — full educational-use disclaimer text.
- [`docs/decisions/`](./docs/decisions/) — ADRs (engine-first, regime taxonomy, confidence composer, ...).
- [`docs/enhancements/`](./docs/enhancements/) — third-party enhancement specs + per-spec assessments. Adoption decisions live in ADRs.
- [`docs/thread-transitions/`](./docs/thread-transitions/) — per-AI-thread handoff records. One file per thread, capturing what shipped + decisions + handoff brief.
- [`CHANGELOG.md`](./CHANGELOG.md) — per-engine-version changelog (Keep a Changelog format).

The full development plan v1.2 lives in the Hyperagent thread `cmokf2twq0gsv06adlij0glqs`.

## Repo layout

```
apps/
  web/              # Next.js 16.2.6 (App Router) — Today screen        [shipped M0.4]
  api/              # FastAPI — engine endpoints                        [shipped M0.3]
  jobs/             # (Phase 2) scheduled ingestion — consolidated into apps/api/app/jobs/ in P1
packages/
  engine/           # Python — the product (pure functions, no I/O)     [scaffolded M0.6, growing]
    engine/
      _utils.py             # clip01() — engine-wide [0,1] saturation   [M1.3]
      regimes.py            # 6 locked regimes (per ADR-0002)           [M0.6]
      profiles.py           # UserStrategyProfile (frozen Pydantic)     [M0.6]
      types.py              # OptionContract + ChainSnapshot            [M0.6]
      version.py            # __version__ — bumped per ADR-0005         [M0.6 → 0.4.0]
      market_state/
        iv.py               # IV rank + IV percentile                   [M1.1]
        hv.py               # close-to-close + Parkinson HV             [M1.1]
        expected_move.py    # ATM straddle + forward-IV expected move   [M1.2]
        max_pain.py         # CBOE-style total-OI loss minimization     [M1.2]
        pcr.py              # put/call ratios (volume + OI)             [M1.2]
        trend_strength.py   # Wilder ADX, normalized [0,1]              [M1.3]
        breakout.py         # 4-component composite breakout signal     [M1.3]
  shared-types/     # TS types generated from Pydantic                  [shipped M0.6]
    src/            # generated regimes.ts / profiles.ts / types.ts
    scripts/
      generate.py   # the codegen — single source of truth bridge
seeds/csv/          # local-dev seed data per §21 of the plan           [iv_history M1.1]
docs/               # principles, architecture, ADRs, SSOT map, transitions
scripts/            # dev tooling + CI guards + run_smoke.sh             [shipped M0.4–M0.7]
.github/workflows/  # CI                                                 [shipped M0.5]
docker-compose.yml  # Phase 1 simplified (postgres + api + web)
Makefile            # common dev commands
pnpm-workspace.yaml # JS/TS workspace
pyproject.toml      # Python (uv) workspace root
pnpm-lock.yaml      # workspace pnpm lockfile (root, not per-app)        [shipped M0.5]
CHANGELOG.md        # per-engine-version changelog
```

## Quick start

```bash
# Bring up postgres + api + web:
docker compose up --build
# web:      http://localhost:3000   (disclaimer gate, then /today placeholder)
# api:      http://localhost:8000/api/v1/health
# postgres: localhost:5432

# Run migrations once (first boot):
docker compose up -d postgres
cd apps/api && uv sync --dev && uv run alembic upgrade head
```

Local dev outside Docker:

```bash
# api
cd apps/api && uv sync --dev && uv run uvicorn app.main:app --reload

# web
cd apps/web && pnpm install && pnpm dev

# engine (pure-function tests)
cd packages/engine && uv sync --dev && uv run pytest -q
```

## Make targets

| Command | Effect |
|---|---|
| `make dev` | `docker compose up` |
| `make test` | pytest (api + engine) + vitest (web) |
| `make smoke` | end-to-end smoke: postgres + alembic + uvicorn + httpx pytest |
| `make lint` | ruff (api + engine) + eslint (web) |
| `make typecheck` | mypy --strict (api + engine) + tsc --noEmit (web + shared-types) |
| `make migrate` | alembic upgrade head |
| `make clean` | down volumes, prune build artifacts |

## CI / local quality gate

Every PR runs through GitHub Actions (`.github/workflows/ci.yml`):

- **guards** — `check_next_version.sh`, `check_no_broker_imports.sh`, `check_engine_version_bump.sh`
- **api** — ruff + mypy --strict + pytest
- **engine** — ruff + mypy --strict + pytest + shared-types codegen drift check
- **web** — eslint + tsc + vitest + next build (apps/web), tsc (packages/shared-types)
- **smoke** — real Postgres + alembic upgrade + uvicorn + httpx pytest

Locally, `pre-commit install` wires the same guards as git hooks. Run the cross-stack smoke test locally with `make smoke` (requires Docker).

After editing any engine type (`packages/engine/engine/{regimes,profiles,types,version}.py`):

```bash
cd packages/engine
uv run python ../shared-types/scripts/generate.py
git add packages/shared-types/src
```

CI's drift check fails any commit that updates the Python without regenerating the TS.

## Conventions

- **Engine-first.** `packages/engine` is pure-function Python with no I/O. Every API and UI piece exists to surface or input to engine outputs.
- **Auditable.** Every `DailyDecision` is persisted with `inputs_hash`, `engine_version`, `weights_version` for exact replay.
- **No execution.** This codebase has no broker write paths. CI guard (`scripts/check_no_broker_imports.sh`, M0.5) enforces it.
- **Deterministic V1 → ML in Phase 4.** ML upgrades replace specific engine nodes without changing interfaces.
- **Branch + PR workflow.** Every milestone is a branch named `feat/<milestone-id>-<slug>`, merged via squash into `main`. Conventional-commit messages.
- **Engine version bump on every `packages/engine/engine/` change.** Per [ADR-0005](./docs/decisions/0005-engine-pure-function-discipline.md). CI guard enforces.

## Disclaimers

Educational and decision-support only. **Not financial advice.** Options involve risk. Verify with a broker and a registered advisor. Data may be delayed or inaccurate. No guarantee of outcomes.

## License

TBD.
