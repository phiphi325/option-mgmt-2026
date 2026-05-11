# SSOT Constants Map

**Define once, import everywhere.** This file is the index — it doesn't contain the values, it points to where they live. Updated alongside any new constant; PR reviewers reject any value that exists in two places.

## Backend (apps/api)

| Category | Canonical file | Key |
|---|---|---|
| API URL prefix | `apps/api/app/main.py` | `API_PREFIX = "/api/v1"` |
| API version | `apps/api/app/core/config.py` | `Settings.api_version` (env-overridable) |
| Engine version | `apps/api/app/core/config.py` (M0.5); engine source-of-truth is `packages/engine/engine/version.py` (M0.6+, currently `1.1.0`) | `Settings.engine_version` |
| Weights version | `apps/api/app/core/config.py` (M0.5); engine source-of-truth is `packages/engine/config/weights.yaml` (M1.10+, currently `v2.0`) | `Settings.weights_version = "v2.0"` |
| JWT secret min length | `apps/api/app/core/config.py` | `Field(min_length=16)` on `jwt_secret` |
| JWT algorithm | `apps/api/app/core/config.py` | `jwt_algorithm = "HS256"` |
| JWT TTL seconds | `apps/api/app/core/config.py` | `jwt_access_token_ttl_seconds = 60*60*24*30` (30 days, plan §15) |
| CORS origins | `apps/api/app/core/config.py` | `cors_origins` (env-driven, defaults to `localhost:3000`) |
| DB regime enum | `apps/api/app/db/migrations/versions/0001_init.py` | `CREATE TYPE regime AS ENUM (...)` |
| Default DB URL | `apps/api/app/db/migrations/env.py` | `DEFAULT_DATABASE_URL` |
| RFC 7807 envelope | `apps/api/app/schemas/error.py` | `ProblemDetails` |
| Boot time (uptime) | `apps/api/app/routers/health.py` | `_BOOT_TIME` (process-local, monotonic) |
| Auth stub detail message | `apps/api/app/routers/auth.py` | `_NOT_IMPLEMENTED_DETAIL` |

## Engine (packages/engine)

| Category | Canonical file | Key | Status |
|---|---|---|---|
| Regime enum (Python) | `packages/engine/engine/regimes.py` | `class Regime(StrEnum)` | shipped M0.6 |
| Regime UI color tokens | `packages/engine/engine/regimes.py` | `REGIME_COLORS: dict[Regime, str]` | shipped M0.6 |
| Regime spec table | `packages/engine/engine/regimes.py` | `REGIME_SPEC: dict[Regime, RegimeSpec]` (incl. `allowed_strategies`) | shipped M1.4 |
| User strategy profile | `packages/engine/engine/profiles.py` | `UserStrategyProfile`, `RiskTolerance`, `IncomeNeed`, **`ProfileStyle`** | shipped M0.6 (`drawdown_tolerance` + `style` added M1.9) |
| Option contract type | `packages/engine/engine/types.py` | `OptionContract`, `OptionType` | shipped M0.6 |
| Chain snapshot type | `packages/engine/engine/types.py` | `ChainSnapshot` | shipped M0.6 |
| Engine version (semver) | `packages/engine/engine/version.py` | `__version__` | shipped M0.6 (currently `1.1.0`) |
| `clip01` saturator | `packages/engine/engine/_utils.py` | `clip01(x: float) -> float` | shipped M1.3 |
| Black-Scholes Greeks | `packages/engine/engine/greeks.py` | `delta`, `gamma`, `vega`, `theta`, `rho`, `time_to_expiry_years` | shipped M1.6 |
| Market State result | `packages/engine/engine/market_state/classify.py` | `MarketStateResult`, `classify()` | shipped M1.4 |
| Scoring primitives | `packages/engine/engine/scoring/` | `iv_score`, `structure_score`, `event_score`, `gamma_score` (+ `*ScoreResult` types) | shipped M1.4a, M1.5a (100% coverage CI-enforced) |
| Flow Score Engine | `packages/engine/engine/flow_score/` | `FlowScore`, `Bias`, `RecommendedAction`, `compute()` | shipped M1.5b |
| Strike Selector | `packages/engine/engine/strike_selector/` | `select_strikes()`, `StrikeSelection`, `StrikeLeg`, `LegSide` | shipped M1.7 (PR #37) |
| Recommendation rules | `packages/engine/config/rules.yaml` | 8 V1 rule entries per plan §22.8 | shipped M1.9 |
| Recommendation Engine | `packages/engine/engine/recommendation/` | `recommend()`, `RecommendationResult`, `Action`, `EmittedAction`, `RuleSpec`, `MatchedRule`, `PositionState` + `load_default_rules()` | shipped M1.9 (engine `1.0.0`) |
| Confidence weights | `packages/engine/config/weights.yaml` | `version`, `positive_weights.{flow,struct,regime,signal}`, `penalty_caps.{event,liquidity}` (v2.0 per plan §22.13) | shipped M1.10 |
| Confidence Composer | `packages/engine/engine/confidence/` | `compose()`, `ConfidenceInputs`, `ConfidenceBreakdown`, `Weights`, `DEFAULT_WEIGHTS`, `compute_confidence_inputs()` + 6 per-component fns + `load_default_weights()` | shipped M1.10 (engine `1.1.0`) |
| Execution feasibility | `packages/engine/engine/execution/` | `assess()`, `ExecutionFeasibilityResult` | M1.11 (planned) |
| Master Decision Engine | `packages/engine/engine/decision.py` | `produce_daily_decision()`, `DailyDecision` | M1.13 (planned) |
| Six scenarios (P3) | `packages/engine/engine/scenarios/__init__.py` | `class ScenarioId(str, Enum)`, `SCENARIO_PARAMS` | M3.x |

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

## Shared types (packages/shared-types)

| Category | Canonical file | Key | Status |
|---|---|---|---|
| Generated TS index | `packages/shared-types/src/index.ts` | re-exports `regimes`, `profiles`, `types` | shipped M0.6 |
| Regime + colors (TS) | `packages/shared-types/src/regimes.ts` | generated from `engine/regimes.py` | shipped M0.6 |
| User profile (TS) | `packages/shared-types/src/profiles.ts` | generated from `engine/profiles.py` | shipped M0.6 |
| Chain snapshot (TS) | `packages/shared-types/src/types.ts` | generated from `engine/types.py` | shipped M0.6 |
| Codegen script | `packages/shared-types/scripts/generate.py` | walks Pydantic + StrEnum, emits deterministic TS; `--check` mode for CI drift | shipped M0.6 |
| Web smoke import | `apps/web/lib/regime-meta.ts` | imports `Regime` + `REGIME_COLORS` from `option-mgmt-shared-types` | shipped M0.6 |

## Pin guards

| Pin | Canonical file | Verifier |
|---|---|---|
| `next` version (`16.2.6`) | `apps/web/package.json` `"next"` | `scripts/check_next_version.sh` (CI + pre-commit) |
| `engine_version` bump on engine changes | `packages/engine/engine/version.py` | `scripts/check_engine_version_bump.sh` (M0.5+, active M0.6+) |
| No broker imports | code-wide grep | `scripts/check_no_broker_imports.sh` (M0.5+) |
| Shared-types not drifting from engine | `packages/shared-types/src/*.ts` | `packages/shared-types/scripts/generate.py --check` (M0.6+) |
| Confidence weights not drifting | `packages/engine/config/weights.yaml` ↔ `engine.confidence.DEFAULT_WEIGHTS` | `tests/test_confidence.py::test_default_weights_matches_yaml_drift_check` (M1.10+) |
| `engine.scoring` line coverage = 100% | `packages/engine/engine/scoring/` | CI `pytest --cov=engine.scoring` step (M1.4a+) |
| Python (`3.14`) | `apps/api/.python-version` + `pyproject.toml` `requires-python` + `Dockerfile` | manual review (post-M0.7 stretch: `scripts/check_python_version.sh`) — see [ADR-0007](./decisions/0007-python-version-pin.md) |
| Node (`22.x`) | `apps/web/Dockerfile` `FROM node:22-alpine` | manual review |
| pnpm (`9.12.0` in Dockerfile, `10.x` in dev) | `apps/web/Dockerfile` `corepack prepare pnpm@9.12.0` | manual review |

## Cross-language constants

The following constants exist in both Python and TypeScript and require contract comments in the TypeScript files:

### Regime enum

- Python (canonical): `packages/engine/engine/regimes.py:Regime`
- TypeScript (generated): `packages/shared-types/src/regimes.ts`
- Database: `apps/api/app/db/migrations/versions/0001_init.py:CREATE TYPE regime`

The TS file is deterministically regenerated from the Python via `packages/shared-types/scripts/generate.py`. CI runs the generator with `--check` to fail any commit where Python and TS have drifted.

```typescript
// In apps/web, import the canonical Regime from the workspace dep:
import { Regime, REGIME_COLORS } from "option-mgmt-shared-types";
// Or via the apps/web wrapper that adds UI labels:
import { Regime, REGIME_COLORS, REGIME_LABELS } from "@/lib/regime-meta";
```

### Disclaimer text

- Canonical source: [`docs/disclaimers.md`](./disclaimers.md)
- Web (modal): `apps/web/components/today/DisclaimerGate.tsx`
- Web (footer): `apps/web/components/today/DisclaimerFooter.tsx`
- API (M1.x): `DailyDecision.disclaimers[]` field

When the text changes, all consumers update in the same PR. M0.6+ extracts the canonical strings to `apps/web/lib/disclaimers.ts` so the UI imports rather than inlines them.

### Confidence weights version

- Python (source-of-truth): `packages/engine/config/weights.yaml` `version` field (currently `"v2.0"`, per plan §22.13). Loaded by `engine.confidence.yaml_loader.load_default_weights()`. The on-disk file MUST match the in-code `engine.confidence.DEFAULT_WEIGHTS` constant — `tests/test_confidence.py::test_default_weights_matches_yaml_drift_check` enforces drift detection.
- Python (consumer): `engine.confidence.compose()` stamps `weights.version` onto every `ConfidenceBreakdown`; M1.13 will persist it on `DailyDecision.weights_version`.
- TypeScript (display only): `apps/web/lib/api.ts` reads `weights_version` from `/version` response (M1.x).
- These don't need to match locally — backend is authoritative; frontend just renders.

## Future enhancement modules (per ADR-0008)

Constants and contracts for adopted enhancements (E1–E9) land here as the work ships. The canonical adoption record is [ADR-0008](./decisions/0008-enhancement-adoption-roadmap.md); the per-enhancement assessment is [`docs/enhancements/0001-assessment-and-adoption-decisions.md`](./enhancements/0001-assessment-and-adoption-decisions.md).

| Phase | Enhancement | Constants will live in |
|---|---|---|
| 1.5 | E1 GEX | `packages/engine/engine/gex/` (`GexResult`, regime tags); requires follow-up ADR amending FlowScore V1 contract (replaces `dealer_gamma_proxy` with `gex_context`) |
| 2 | E2 Vol Surface + E5 Vol Premium | `packages/engine/engine/vol_surface/` (term-structure slope literals, skew constants); `packages/engine/engine/scoring/vol_premium.py` (premium percentile tags) |
| 2 | E3 partial (2D PnL + scenarios) | `packages/engine/engine/payoff/surface.py`; `MSFT_DEFAULT_SCENARIOS` 7-row constant lives there |
| 2–3 | E4 Earnings Gap (display-only) | `packages/engine/engine/scoring/earnings_gap.py`; default weights YAML versioned `v1.0` |
| 2–3 | E8 Dividend-Aware Pricing | `packages/engine/engine/payoff/dividend.py`; `DividendSchedule` table seeds for MSFT |
| 3 | E9 Assignment Risk | `packages/engine/engine/assignment/`; lot-selection heuristics (FIFO default, ltcg_aware override) |
| 3 | E3 remainder (3D surface) | `apps/web/app/payoff/page.tsx` only — engine math is already in place from Phase 2 |

Deferred (E6 Multi-Expiry, E7 Backtest) remain in the spec but do not have a registered home. Re-evaluate post-Phase-3.

## Open gaps

- **engine_version + weights_version ownership** — currently lives in `Settings` (apps/api). Engine source-of-truth is `packages/engine/engine/version.py` (`1.1.0`) and `packages/engine/config/weights.yaml` (`v2.0`). The next API change should make `Settings` import from `engine.version` and read `weights_version` from `engine.confidence.DEFAULT_WEIGHTS.version` rather than carrying its own copies. Tracked for M1.13–M1.15 (when the first decision endpoint lands).
- **`weights.yaml` hot-swap path** — ADR-0008 Phase 1.5 plans to move `packages/engine/config/weights.yaml` to `apps/api/app/config/weights.yaml` so ops can hot-swap without bumping engine version. The engine package will still ship its packaged default; production callers will use `load_weights_yaml(path)` once at API startup and pass the result through `recommend(weights=...)`.
- **Disclaimer text consolidation** — still duplicated between `DisclaimerGate.tsx` and `DisclaimerFooter.tsx`. Will be consolidated to `apps/web/lib/disclaimers.ts` in M1.x.
- **Persona preset labels** — `apps/web/components/settings/PersonaPresetButtons.tsx` lands when the Settings page is built (M2.x).
