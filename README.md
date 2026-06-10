# option-mgmt-2026

**MSFT Option Risk Management Engine** — a decision engine that answers a single question every day for a long-term MSFT holder: **"What should I do today?"**

Long equity + tactical options overlay. Deterministic, audit-trail-first, engine-first system. Not a trading bot; not a Bloomberg-clone dashboard. Educational decision-support only.

## Status

**Phase 1 — Engine MVP. In progress.** Engine `1.7.0`. The decision pipeline is feature-complete end-to-end through M1.13, the **Master Decision Engine auto-dispatches `OPEN_COLLAR` emits** to the Collar Builder (M1.11b — `produce_daily_decision()` attaches a `CollarStructure` to `DailyDecision.collar_structures` when the rule pipeline emits `OPEN_COLLAR`), the **public API surface is shipped** (M1.14–M1.17.5 + M1.16a: 18 endpoints), the **Today screen scaffolding is live** (M1.18), the **Collar Builder is engine + dispatch + API complete** (M1.11a engine + M1.11b dispatch + M1.16a endpoint), and the **M1.24 golden `DailyDecision` suite is locked** (12 regenerated snapshots + `engine.decision.serialize_canonical` + CHANGELOG-drift CI guard). Next up: **M1.19 (ActionList + ActionRow + ExecutionBadge)** — the first frontend consumer of `DailyDecision.collar_structures`.

See [`CHANGELOG.md`](./CHANGELOG.md) for per-version detail and [`docs/thread-transitions/`](./docs/thread-transitions/) for thread-by-thread handoff records.

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

### Phase 1 — Engine MVP (decision pipeline complete; API + UI in progress)

| | What | PR | Engine |
|---|---|---|---|
| ✅ | docs — enhancement-spec adoption roadmap (ADR-0008): 6 adopt, 2 defer, 0 reject | [#23](https://github.com/csupenn/option-mgmt-2026/pull/23) | — |
| ✅ | M1.1 — IV rank/percentile + HV (close-to-close + Parkinson) + 252-day seed | [#24](https://github.com/csupenn/option-mgmt-2026/pull/24) | `0.2.0` |
| ✅ | M1.2 — max pain + expected move + put/call ratios | [#25](https://github.com/csupenn/option-mgmt-2026/pull/25) | `0.3.0` |
| ✅ | M1.3 — Wilder ADX trend strength + 4-component breakout signal + `clip01` helper | [#26](https://github.com/csupenn/option-mgmt-2026/pull/26) | `0.4.0` |
| ✅ | M1.4a — Scoring primitives (`iv_score` / `structure_score` / `event_score`) + 100% coverage gate | [#28](https://github.com/csupenn/option-mgmt-2026/pull/28) | `0.5.0` |
| ✅ | M1.4 — Market State Engine `classify()` + 24 regime fixtures + REGIME_SPEC | — | `0.6.0` |
| ✅ | M1.5 — Flow Score Engine scaffold + types (`FlowScore`, `Bias`, `RecommendedAction`) | — | `0.7.0` |
| ✅ | M1.5a — `gamma_score` (magnitude + sign split) + dealer-gamma proxy + OI walls | — | `0.8.0` |
| ✅ | M1.5b — Flow Score Engine `compute()` orchestrator + 5-component bullish/bearish formula | — | `0.9.0` |
| ✅ | M1.6 — Black-Scholes Greeks (`delta` / `gamma` / `vega` / `theta` / `rho`); activates `skew_25d` | — | `0.10.0` |
| ✅ | M1.7 — Strike Selector (`select_strikes()`) — BS delta-matching against `target_delta` + DTE matching | [#37](https://github.com/csupenn/option-mgmt-2026/pull/37) | `0.12.0` |
| ✅ | M1.8 — Recommendation Engine (initial: regime-strategy whitelist + Python rules) | [#36](https://github.com/csupenn/option-mgmt-2026/pull/36) | `0.11.0` |
| ✅ | M1.9 — Recommendation Engine plan-true: 8 YAML rules + 15-clause predicate vocabulary + plan-true `recommend()` contract | [#38](https://github.com/csupenn/option-mgmt-2026/pull/38) | `1.0.0` |
| ✅ | M1.10 — Confidence Composer (multiplicative §22.13) + `weights.yaml` + 6 component scoring fns | [#39](https://github.com/csupenn/option-mgmt-2026/pull/39) | `1.1.0` |
| ✅ | M1.11 — Execution Feasibility Module (`assess()`; per-leg liquidity / spread / slippage / fill; `liquidity_penalty()` bridge to composer) | [#41](https://github.com/csupenn/option-mgmt-2026/pull/41) | `1.2.0` |
| ✅ | M1.12 — Execution downgrade callback (`downgrade_if_needed()` + 2-rung liquidity ladder; pre-filters chain when any leg fill < 0.50) | [#42](https://github.com/csupenn/option-mgmt-2026/pull/42) | `1.3.0` |
| ✅ | M1.13 — Master Decision Engine (`produce_daily_decision()` + `DailyDecision` + `compute_inputs_hash()`; three-pin replay lock) | [#43](https://github.com/csupenn/option-mgmt-2026/pull/43) | `1.4.0` |
| ✅ | M1.14 — `POST /engine/daily-plan` + `POST /engine/recommend` (wires `produce_daily_decision()` into FastAPI) | [#45](https://github.com/csupenn/option-mgmt-2026/pull/45) | — |
| ✅ | M1.15 — `/engine/what-if` + `/engine/market-state` + `/engine/flow-score` (read-only sub-step endpoints) | [#47](https://github.com/csupenn/option-mgmt-2026/pull/47) | — |
| ✅ | M1.16 — `/engine/strike-candidates` + `/engine/execution-check` (reduced scope; collar-builder endpoint deferred to M1.16a) | [#48](https://github.com/csupenn/option-mgmt-2026/pull/48) | — |
| ✅ | M1.17 — `/profile` + `/outcomes` + 5 CSV import endpoints + `/market/{ticker}/latest` (M1.16b pickup) | [#50](https://github.com/csupenn/option-mgmt-2026/pull/50) | — |
| ✅ | M1.17.5 — `DailyPlanRequest.inputs` optional + DB hydration (`inputs_hydration_service.py`); 422 on `missing_chain` / `missing_positions` / `insufficient_iv_history` | [#51](https://github.com/csupenn/option-mgmt-2026/pull/51) | — |
| ✅ | M1.18 — Today screen scaffolding (`DailyDecisionCard` + `MarketStateBadge` + `StrategyTitle` + 6 regime colors; first Next.js milestone since M0.4) | [#53](https://github.com/csupenn/option-mgmt-2026/pull/53) | — |
| ✅ | M1.11a — Collar Builder engine module (`engine.collar_builder.build()`; 3 intents: `zero_cost`/`income`/`defensive`; grid-search solver per §9.10) | [#56](https://github.com/csupenn/option-mgmt-2026/pull/56) | `1.5.0` |
| ✅ | M1.16a — `POST /engine/collar-builder` (thin service + Pydantic schemas + router; §22.11 H5 `underlying_qty` from DB only; 9 tests) | [#60](https://github.com/csupenn/option-mgmt-2026/pull/60) | — |
| ✅ | M1.11b — Collar Builder integration into Master Decision (`_dispatch_open_collar` helper in `produce.py`; `DailyDecision.collar_structures` parallel tuple; 2-leg `StrikeSelection` projection via `_project_collar_to_strike_selection`; `underlying_qty < 100` falls back to 100 per shipped impl) | [#58](https://github.com/csupenn/option-mgmt-2026/pull/58) | `1.6.0` |
| ✅ | M1.24 — Golden `DailyDecision` suite (`engine.decision.serialize_canonical` + 12 regenerated fixtures + parametrized replay harness + suite-level meta tests + regen script) + companion tooling (`scripts/check_changelog_entry.sh`, `Settings` engine_version/weights_version consolidation) | [#3](https://github.com/knowlingo/option-mgmt-2026/pull/3) | `1.7.0` |
| | M1.19–M1.23, M1.25 — ActionList, ConfidenceBreakdownChart, WatchLevels, Profile UI, Outcome Tracker, Calibration + Playwright | — | — |

**Where we are.** The decision pipeline is end-to-end live in production. `produce_daily_decision()` (M1.13) wires Market State → Flow Score → Recommendation → Strike Selector → Execution Feasibility + Downgrade → Confidence Composer into one `DailyDecision` with three-pin replay safety. **M1.11b** (PR #58) added collar dispatch: when the M1.9 rule pipeline emits `OPEN_COLLAR` (regime ∈ {`HIGH_IV_EVENT`, `POST_EVENT_REPRICE`} AND no existing collar legs), `produce_daily_decision()` now calls `collar_builder.build(intents=[ZERO_COST])` via the `_dispatch_open_collar` helper and attaches the resulting two-leg `CollarStructure` to `DailyDecision.collar_structures` (parallel to `strike_selections`). M1.14–M1.17.5 + M1.16a expose every engine sub-step over HTTP (18 endpoints). M1.18 ships the Today screen scaffolding with `getDailyPlan()` server-rendering the headline card. M1.11a shipped the Collar Builder engine module; M1.16a adds the API endpoint (`POST /engine/collar-builder`) with thin service layer + §22.11 H5 `underlying_qty`-from-DB enforcement. **M1.24** (PR #3, engine `1.7.0`) locks the `DailyDecision` wire shape with 12 golden snapshots replayed through `engine.decision.serialize_canonical` (canonical JSON, 6-decimal float rounding) — the meta tests assert coverage of all 8 emit codes, both collar paths, M1.12 escalation, and all 6 regimes — plus a `check_changelog_entry.sh` CI guard and `Settings` version consolidation so `/version` reports the live engine value.

**Milestone-numbering correction.** PRs #36 and #37 were originally labeled "M1.7" and "M1.8" respectively; per plan v1.2 §17 the actual milestone numbers are swapped (Strike Selector is M1.7 size L; Recommendation Engine is M1.8 size M). The functional code is correct in both PRs — only the PR titles + branch names mis-labeled the milestone. The table above shows the canonical plan §17 mapping; CHANGELOG `[1.0.0]` documents the correction.

See plan v1.2 §17 for the full milestone table; §22 is the canonical correction sheet (audit-resolved 2026-05-09).

### Yearline integration (enhancement track, parallel to Phase 1) — OM-Y0…Y5

Adopts **yearline-universe** (an external MA250 repair/retry statistical-context engine) as a jobs-layer-hydrated, **gated** `YearlineContext` value object the pure engine optionally consumes. External provider → its own ADR + folder, not part of the E1–E9 spec series. Boundary, gate-respect, and the 4th replay pin are locked in [ADR-0009](./docs/decisions/0009-adopt-yearline-statistical-context-provider.md).

| | What | PR | Engine |
|---|---|---|---|
| ✅ | OM-Y0 — enhancement assessment + ADR-0009 (no code) | [#6](https://github.com/knowlingo/option-mgmt-2026/pull/6) | — |
| ✅ | OM-Y1 — `engine.yearline.YearlineContext` contract + Pydantic→TS codegen (`dict`/`Literal` support) + cross-repo contract test | [#7](https://github.com/knowlingo/option-mgmt-2026/pull/7) | `1.8.0` |
| ✅ | OM-Y2 — `yearline_context` table + idempotent ingest job + hydration service (`→ YearlineContext \| None`) | [#8](https://github.com/knowlingo/option-mgmt-2026/pull/8) | — |
| ✅ | OM-Y3 — read-only Today-screen evidence panel: card + headline distance-to-MA250 line (Recharts) + `GET /engine/yearline-context`; `DailyDecision` byte-identical | (PR open) | — |
| | OM-Y4 — **gated engine consumption** (`produce_daily_decision(..., yearline_context=)`, 4th replay pin, `rules.yaml` clauses + gated Confidence component; output-changing) | — | — |
| | OM-Y5 — stretch: Market-State enrichment (ADR-0002 amendment) / collar-intent keyed off yearline readiness | — | — |

**The hard rule:** `packages/engine` never imports yearline-universe (ADR-0005). Coupling is a persisted, versioned artifact. **Resume point + traps:** [`docs/enhancements/yearline/implementation/HANDOFF.md`](./docs/enhancements/yearline/implementation/HANDOFF.md).

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
| PyYAML | `>=6.0` (engine runtime; loads `rules.yaml` + `weights.yaml`) | `packages/engine/pyproject.toml` |

## Documentation

Read [`docs/`](./docs/) before any code change:

- [`docs/engineering-principles.md`](./docs/engineering-principles.md) — **mandatory** principles + project rules.
- [`docs/architecture.md`](./docs/architecture.md) — layer cake + component map + data flow.
- [`docs/ssot-constants-map.md`](./docs/ssot-constants-map.md) — canonical home for every shared constant.
- [`docs/disclaimers.md`](./docs/disclaimers.md) — full educational-use disclaimer text.
- [`docs/decisions/`](./docs/decisions/) — ADRs (engine-first, regime taxonomy, confidence composer, ...).
- [`docs/enhancements/`](./docs/enhancements/) — third-party enhancement specs + per-spec assessments. Adoption decisions live in ADRs. Includes the [`yearline/`](./docs/enhancements/yearline/) integration track (assessment, ADR-0009, [`implementation/`](./docs/enhancements/yearline/implementation/) as-built record + [`HANDOFF.md`](./docs/enhancements/yearline/implementation/HANDOFF.md) resume-point).
- [`docs/thread-transitions/`](./docs/thread-transitions/) — per-AI-thread handoff records. One file per thread, capturing what shipped + decisions + handoff brief.
- [`docs/tutorials/`](./docs/tutorials/) — long-form pedagogical tutorials (Market State, Scoring Primitives, Flow Score, Confidence Composer, Master Decision Engine, **Collar Builder**) + the [`engine-api-reference.md`](./docs/tutorials/engine-api-reference.md) covering M1.14–M1.17.5's 17 HTTP endpoints.
- [`docs/phased-design/phase-1/`](./docs/phased-design/phase-1/) — milestone roster + per-milestone dev specs (M1.15–M1.18, M1.11a, M1.11b). The [`review/`](./docs/phased-design/phase-1/review/) subfolder hosts post-merge code-quality retrospectives.
- [`CHANGELOG.md`](./CHANGELOG.md) — per-engine-version changelog (Keep a Changelog format).

The full development plan v1.2 lives in the Hyperagent thread `cmokf2twq0gsv06adlij0glqs`.

## Repo layout

```
apps/
  web/              # Next.js 16.2.6 (App Router) — Today screen        [shipped M0.4]
  api/              # FastAPI — engine endpoints                        [shipped M0.3]
  jobs/             # (Phase 2) scheduled ingestion — consolidated into apps/api/app/jobs/ in P1
packages/
  engine/           # Python — the product (pure functions, no I/O)     [scaffolded M0.6; engine 1.8.0]
    config/         # YAML configs (filesystem boundary per ADR-0005)
      rules.yaml            # Recommendation Engine V1 rules            [M1.9]
      weights.yaml          # Confidence Composer V1 weights (v2.0)     [M1.10]
    engine/
      _utils.py             # clip01() — engine-wide [0,1] saturation   [M1.3]
      regimes.py            # 6 locked regimes + REGIME_SPEC table      [M0.6 / M1.4]
      profiles.py           # UserStrategyProfile + ProfileStyle        [M0.6 / M1.9]
      types.py              # OptionContract + ChainSnapshot            [M0.6]
      version.py            # __version__ — bumped per ADR-0005         [M0.6 → 1.8.0]
      yearline/             # YearlineContext gated value object         [OM-Y1; engine 1.8.0]
      greeks.py             # BS delta/gamma/vega/theta/rho             [M1.6]
      market_state/         # M1.1-M1.4 — produces MarketStateResult
        iv.py               # IV rank + IV percentile                   [M1.1]
        hv.py               # close-to-close + Parkinson HV             [M1.1]
        expected_move.py    # ATM straddle + forward-IV expected move   [M1.2]
        max_pain.py         # CBOE-style total-OI loss minimization     [M1.2]
        pcr.py              # put/call ratios (volume + OI)             [M1.2]
        trend_strength.py   # Wilder ADX, normalized [0,1]              [M1.3]
        breakout.py         # 4-component composite breakout signal     [M1.3]
        classify.py         # 6-regime classifier + MarketStateResult   [M1.4]
      scoring/              # M1.4a + M1.5a — *ScoreResult primitives
        iv.py               # IV score (rank/percentile/HV blend)       [M1.4a]
        structure.py        # Wall/pin/opex/EM structure score          [M1.4a]
        event.py            # Event proximity × magnitude × kind        [M1.4a]
        gamma.py            # Dealer gamma magnitude + sign             [M1.5a]
      flow_score/           # M1.5-M1.5b — Flow Score Engine
        compute.py          # 5-component bullish/bearish orchestrator  [M1.5b]
        oi_walls.py         # Open-interest wall identification         [M1.5a]
        dealer_gamma.py     # Dealer-gamma proxy                        [M1.5a]
        skew.py             # 25-delta call/put skew (BS-driven)        [M1.6]
        futures_basis.py    # V1 stub — futures-service lands in P2     [M1.5b]
        pin_probability.py  # Spot-to-max-pain × opex × OI blend        [M1.5b]
        explanation.py      # Human-readable rationale builder          [M1.5b]
        types.py            # FlowScore + Bias + RecommendedAction      [M1.5]
      strike_selector/      # M1.7 — BS delta-matched strike picking
        select.py           # select_strikes(*, action, chain, ...)     [M1.7]
        types.py            # StrikeSelection + StrikeLeg + LegSide     [M1.7]
      recommendation/       # M1.8 + M1.9 — YAML-driven rule pipeline
        recommend.py        # recommend() orchestrator                  [M1.9]
        rules.py            # 15-clause evaluator + rule selection      [M1.9]
        rationale.py        # Mustache-style {{var}} substitution       [M1.9]
        warnings.py         # Caveat-string builder                     [M1.9]
        yaml_loader.py      # rules.yaml filesystem boundary            [M1.9]
        types.py            # RuleSpec, Action, EmittedAction, ...      [M1.9]
      confidence/           # M1.10 — multiplicative composer (§22.13)
        compose.py          # compose() — the formula                   [M1.10]
        components.py       # 6 per-component scoring functions         [M1.10]
        yaml_loader.py      # weights.yaml filesystem boundary          [M1.10]
        types.py            # ConfidenceInputs + Weights + Breakdown    [M1.10]
      execution/            # M1.11 + M1.12 — fill-feasibility + downgrade
        assess.py           # assess() per-leg + aggregate + composer bridge [M1.11]
        liquidity.py        # norm_oi/norm_volume/spread_bps/liquidity   [M1.11]
        slippage.py         # expected_slippage = half-spread + size impact [M1.11]
        fill.py             # fill_confidence + order-type + threshold [M1.11]
        size.py             # tick_size/limit_price_band/size_warnings  [M1.11]
        downgrade.py        # downgrade_if_needed() + filter_chain_…    [M1.12]
        types.py            # Execution + ExecutionLeg + OrderType      [M1.11]
      decision/             # M1.13 — Master Decision Engine + replay; M1.11b — Collar dispatch
        produce.py          # produce_daily_decision() orchestrator    [M1.13 / M1.11b collar dispatch]
        hashing.py          # compute_inputs_hash() (canonical JSON)   [M1.13]
        serialize.py        # serialize_canonical() golden serializer  [M1.24]
        types.py            # DailyDecision frozen dataclass           [M1.13 / M1.11b +collar_structures]
      collar_builder/       # M1.11a — first-class structural-strategy engine
        build.py            # build() entry; dispatches per-intent     [M1.11a]
        structures.py       # zero_cost / income / defensive solvers   [M1.11a]
        leg_factory.py      # OptionContract → CollarLeg helpers       [M1.11a]
        types.py            # CollarIntent + CollarLeg + CollarStructure [M1.11a]
  shared-types/     # TS types generated from Pydantic                  [shipped M0.6]
    src/            # generated regimes.ts / profiles.ts / types.ts
    scripts/
      generate.py   # the codegen — single source of truth bridge
seeds/csv/          # local-dev seed data per §21 of the plan           [iv_history M1.1]
docs/               # principles, architecture, ADRs, SSOT map, transitions, tutorials
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

Hello-world `DailyDecision` (Python):

```python
from datetime import datetime
from engine import (
    produce_daily_decision, ChainSnapshot, OptionContract, OptionType,
    PositionState, UserStrategyProfile, RiskTolerance, IncomeNeed, ProfileStyle,
    MarketStateResult, Regime, FlowScore, Bias, RecommendedAction,
)

# (caller hydrates upstream engine outputs — typically the FastAPI service)
chain = ChainSnapshot(...)              # from option_chain_snapshots
positions = PositionState(...)          # from option_positions
profile = UserStrategyProfile(...)      # from users.strategy_profile
market_state = MarketStateResult(...)   # from engine.market_state.classify()
flow_score = FlowScore(...)             # from engine.flow_score.compute()

decision = produce_daily_decision(
    as_of=datetime.utcnow(),
    ticker="MSFT",
    chain_snapshot=chain,
    positions=positions,
    profile=profile,
    market_state=market_state,
    flow_score=flow_score,
)
# decision.confidence   → post-downgrade composite [0, 1]
# decision.inputs_hash  → sha256:<64hex>, ready for idempotent persistence
# decision.escalated    → True iff fill quality couldn't be rescued
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
- **engine** — ruff + mypy --strict + pytest + 100% coverage on `engine.scoring` + shared-types codegen drift check
- **web** — eslint + tsc + vitest + next build (apps/web), tsc (packages/shared-types)
- **smoke** — real Postgres + alembic upgrade + uvicorn + httpx pytest

Locally, `pre-commit install` wires the same guards as git hooks. Run the cross-stack smoke test locally with `make smoke` (requires Docker).

After editing any engine type (`packages/engine/engine/{regimes,profiles,types,version}.py`):

```bash
cd packages/engine
uv run python ../shared-types/scripts/generate.py
git add packages/shared-types/src
```

CI's drift check fails any commit that updates the Python without regenerating the TS. A parallel drift gate covers Confidence Composer weights: `tests/test_confidence.py::test_default_weights_matches_yaml_drift_check` asserts `engine.confidence.DEFAULT_WEIGHTS == load_default_weights()`, so edits to `packages/engine/config/weights.yaml` without updating `engine/confidence/__init__.py` (or vice versa) fail CI.

## Conventions

- **Engine-first.** `packages/engine` is pure-function Python with no I/O. Every API and UI piece exists to surface or input to engine outputs. Two filesystem-boundary modules (`engine/recommendation/yaml_loader.py`, `engine/confidence/yaml_loader.py`) handle the `rules.yaml` / `weights.yaml` reads; callers pass the parsed values to `recommend()` / `produce_daily_decision()`.
- **Auditable.** Every `DailyDecision` is persisted with `inputs_hash`, `engine_version`, `weights_version` for exact replay. The three pins together identify a unique replayable decision; the M1.13 `compute_inputs_hash()` produces cross-environment-deterministic canonical-JSON SHA-256 over all engine inputs.
- **No execution.** This codebase has no broker write paths. CI guard (`scripts/check_no_broker_imports.sh`, M0.5) enforces it.
- **Deterministic V1 → ML in Phase 4.** ML upgrades replace specific engine nodes without changing interfaces. V1 stubs (`futures_basis = 0` until P2 futures service) are plumbed through explicit kwargs so the M1.x → V2 hand-off is a one-line callsite change.
- **Branch + PR workflow.** Every milestone is a branch named `feat/<milestone-id>-<slug>`, merged via squash into `main`. Conventional-commit messages.
- **Engine version bump on every `packages/engine/engine/` change.** Per [ADR-0005](./docs/decisions/0005-engine-pure-function-discipline.md). CI guard enforces. Bump rules: patch (bug fix, no schema change), minor (new engine, score, or public function), major (schema change, removed/renamed fields, semantic shift).

## Disclaimers

Educational and decision-support only. **Not financial advice.** Options involve risk. Verify with a broker and a registered advisor. Data may be delayed or inaccurate. No guarantee of outcomes.

## License

TBD.
