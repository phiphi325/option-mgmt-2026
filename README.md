# option-mgmt-2026

**MSFT Option Risk Management Engine** — a decision engine that answers a single question every day for a long-term MSFT holder: **"What should I do today?"**

Long equity + tactical options overlay. Deterministic, audit-trail-first, engine-first system. Not a trading bot; not a Bloomberg-clone dashboard. Educational decision-support only.

## Status

**Phase 0 — Foundation. M0.1 (this PR): monorepo + Docker + Makefile scaffold.**

Phase 1 (engine MVP) starts after M0.1–M0.7 land. See the v1.2 plan for the full 5-phase roadmap; section §22 is the canonical correction sheet.

## Repo layout

```
apps/
  web/              # Next.js 16.2.6 (App Router) — Today screen        [M0.4+]
  api/              # FastAPI — engine endpoints                        [M0.3+]
  jobs/             # (Phase 2) scheduled ingestion                     [P2]
packages/
  engine/           # Python — the product (pure functions, no I/O)     [M1.x]
  shared-types/     # TS types generated from Pydantic                  [M0.6]
seeds/csv/          # local-dev seed data per §21 of the plan           [M1.x]
docs/               # architecture, ops, runbooks
scripts/            # dev tooling
.github/workflows/  # CI                                                [M0.5]
docker-compose.yml  # Phase 1 simplified (postgres + api + web)
Makefile            # common dev commands
pnpm-workspace.yaml # JS/TS workspace
pyproject.toml      # Python (uv) workspace root
```

## Quick start

```bash
# After M0.2 (schema lands), bring up postgres for migrations:
docker compose up -d postgres

# After M0.3 / M0.4 land, full stack:
docker compose up
# web:      http://localhost:3000
# api:      http://localhost:8000/api/v1/health
# postgres: localhost:5432
```

In M0.1 (this PR), `apps/api` and `apps/web` are scaffolded with placeholder Dockerfiles only; full content arrives in M0.3 (api shell) and M0.4 (web shell).

## Make targets

| Command | Effect | Available |
|---|---|---|
| `make dev` | docker compose up | M0.1 |
| `make test` | pytest + vitest | M0.5+ |
| `make lint` | ruff + eslint | M0.5+ |
| `make typecheck` | mypy --strict + tsc --noEmit | M0.5+ |
| `make migrate` | alembic upgrade head | M0.2+ |
| `make clean` | down volumes, prune build artifacts | M0.1 |

## Conventions

- **Engine-first.** `packages/engine` is pure-function Python with no I/O. Every API and UI piece exists to surface or input to engine outputs.
- **Auditable.** Every `DailyDecision` is persisted with `inputs_hash`, `engine_version`, `weights_version` for exact replay.
- **No execution.** This codebase has no broker write paths. CI guard (`scripts/check_no_broker_imports.sh`, M0.5) enforces it.
- **Deterministic V1 → ML in Phase 4.** ML upgrades replace specific engine nodes without changing interfaces.
- **Branch + PR workflow.** Every milestone is a branch named `feat/<milestone-id>-<slug>`, merged via squash into `main`. Conventional-commit messages.

## Disclaimers

Educational and decision-support only. **Not financial advice.** Options involve risk. Verify with a broker and a registered advisor. Data may be delayed or inaccurate. No guarantee of outcomes.

## License

TBD.
