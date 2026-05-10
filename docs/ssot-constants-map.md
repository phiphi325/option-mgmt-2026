# SSOT Constants Map

**Define once, import everywhere.** This file is the index — it doesn't contain the values, it points to where they live. Updated alongside any new constant; PR reviewers reject any value that exists in two places.

## Backend (apps/api)

| Category | Canonical file | Key |
|---|---|---|
| API URL prefix | `apps/api/app/main.py` | `API_PREFIX = "/api/v1"` |
| API version | `apps/api/app/core/config.py` | `Settings.api_version` (env-overridable) |
| Engine version | `apps/api/app/core/config.py` (M0.5); will move to `packages/engine/engine/version.py` (M0.6+) | `Settings.engine_version` |
| Weights version | `apps/api/app/core/config.py` (M0.5); will move to `packages/engine/engine/config/weights.yaml` (M0.6+) | `Settings.weights_version = "v2.0"` |
| JWT secret min length | `apps/api/app/core/config.py` | `Field(min_length=16)` on `jwt_secret` |
| JWT algorithm | `apps/api/app/core/config.py` | `jwt_algorithm = "HS256"` |
| JWT TTL seconds | `apps/api/app/core/config.py` | `jwt_access_token_ttl_seconds = 60*60*24*30` (30 days, plan §15) |
| CORS origins | `apps/api/app/core/config.py` | `cors_origins` (env-driven, defaults to `localhost:3000`) |
| DB regime enum | `apps/api/app/db/migrations/versions/0001_init.py` | `CREATE TYPE regime AS ENUM (...)` |
| Default DB URL | `apps/api/app/db/migrations/env.py` | `DEFAULT_DATABASE_URL` |
| RFC 7807 envelope | `apps/api/app/schemas/error.py` | `ProblemDetails` |
| Boot time (uptime) | `apps/api/app/routers/health.py` | `_BOOT_TIME` (process-local, monotonic) |
| Auth stub detail message | `apps/api/app/routers/auth.py` | `_NOT_IMPLEMENTED_DETAIL` |

## Engine (packages/engine, M0.6+)

| Category | Canonical file | Key |
|---|---|---|
| Regime enum (Python) | `packages/engine/engine/regimes.py` | `class Regime(str, Enum)` |
| Regime spec table | `packages/engine/engine/regimes.py` | `REGIME_SPEC: dict[Regime, RegimeSpec]` |
| User strategy profile | `packages/engine/engine/profiles.py` | `class UserStrategyProfile` |
| Confidence weights | `packages/engine/engine/config/weights.yaml` | `version`, `positive_weights.*`, `penalty_caps.*` |
| Recommendation rules | `packages/engine/engine/config/rules.yaml` | rule entries (8 in v1) |
| ChainSnapshot type | `packages/engine/engine/types.py` | `ChainSnapshot`, `ChainRow` |
| Engine version (semver) | `packages/engine/engine/version.py` | `__version__` |
| Six scenarios (P3) | `packages/engine/engine/scenarios/__init__.py` | `class ScenarioId(str, Enum)`, `SCENARIO_PARAMS` |

## Web (apps/web)

| Category | Canonical file | Key |
|---|---|---|
| API base URL (env-driven) | `apps/web/lib/api.ts` | `API_BASE` |
| `cn()` helper | `apps/web/lib/utils.ts` | `cn()` |
| Disclaimer storage key | `apps/web/components/today/DisclaimerGate.tsx` | `STORAGE_KEY = "disclaimerAcceptedAt_v1"` |
| Regime CSS variables (light + dark) | `apps/web/app/globals.css` | `--regime-high-iv-event`, `--regime-high-iv-pin`, `--regime-low-iv-trend`, `--regime-low-iv-range`, `--regime-breakout`, `--regime-post-event-reprice` |
| Regime Tailwind colors | `apps/web/tailwind.config.ts` | `theme.extend.colors.regime.*` |
| Light/dark CSS vars | `apps/web/app/globals.css` | `--background`, `--foreground`, ... (shadcn slate base) |
| Persona presets (UI labels) | `apps/web/components/settings/PersonaPresetButtons.tsx` (M0.6+) | `PERSONA_LABELS` (per v1.2 §22.15 L4) |

## Shared types (packages/shared-types, M0.6+)

| Category | Canonical file | Key |
|---|---|---|
| Generated TS types | `packages/shared-types/src/index.ts` | re-exports from generated `*.ts` files |
| Generation script | `packages/shared-types/scripts/generate.sh` | reads `apps/api/app/schemas/*.py` and `packages/engine/engine/types.py` |

## Pin guards

| Pin | Canonical file | Verifier |
|---|---|---|
| `next` version (`16.2.6`) | `apps/web/package.json` `"next"` | `scripts/check_next_version.sh` (CI + pre-commit) |
| `engine_version` bump on engine changes | `packages/engine/engine/version.py` | `scripts/check_engine_version_bump.sh` (M0.5+) |
| No broker imports | code-wide grep | `scripts/check_no_broker_imports.sh` (M0.5+) |
| Python (`3.14`) | `apps/api/.python-version` + `pyproject.toml` `requires-python` + `Dockerfile` | manual review (post-M0.7 stretch: `scripts/check_python_version.sh`) — see [ADR-0007](./decisions/0007-python-version-pin.md) |
| Node (`22.x`) | `apps/web/Dockerfile` `FROM node:22-alpine` | manual review |
| pnpm (`9.12.0` in Dockerfile, `10.x` in dev) | `apps/web/Dockerfile` `corepack prepare pnpm@9.12.0` | manual review |

## Cross-language constants

The following constants exist in both Python and TypeScript and require contract comments in the TypeScript files:

### Regime enum

- Python: `packages/engine/engine/regimes.py:Regime` (M0.6+)
- TypeScript: `packages/shared-types/src/regimes.ts` (generated M0.6+)
- Database: `apps/api/app/db/migrations/versions/0001_init.py:CREATE TYPE regime`

Contract comment in TS:
```typescript
// Generated from packages/engine/engine/regimes.py.
// Verify: cd apps/api && uv run python -c "from engine.regimes import Regime; print([r.value for r in Regime])"
import type { Regime } from "option-mgmt-shared-types";
```

### Disclaimer text

- Canonical source: [`docs/disclaimers.md`](./disclaimers.md)
- Web (modal): `apps/web/components/today/DisclaimerGate.tsx`
- Web (footer): `apps/web/components/today/DisclaimerFooter.tsx`
- API (M1.x): `DailyDecision.disclaimers[]` field

When the text changes, all consumers update in the same PR. M0.6+ extracts the canonical strings to `apps/web/lib/disclaimers.ts` so the UI imports rather than inlines them.

### Confidence weights version

- Python (consumer): `packages/engine/engine/confidence/__init__.py` reads `weights.yaml`
- TypeScript (display only): `apps/web/lib/api.ts` reads `weights_version` from `/version` response
- These don't need to match locally — backend is authoritative; frontend just renders.

## Open gaps

- **Until M0.5**, no automated SSOT enforcement. `scripts/check_constants_drift.sh` is on the M0.5 backlog as a stretch goal.
- **Until M0.6**, `engine_version` and `weights_version` are owned by `Settings` (apps/api). Once `packages/engine` ships, ownership moves there and `Settings` imports from it.
- **Until M0.6**, the disclaimer text is duplicated between `DisclaimerGate.tsx` and `DisclaimerFooter.tsx`. Will be consolidated to `apps/web/lib/disclaimers.ts`.
