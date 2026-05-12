# Tutorials

Two complementary doc styles live under this folder:

1. **Engine-layer tutorials** (original set, M1.4–M1.13) — long-form pedagogical material targeting first-year master's students in financial engineering. They teach *why* the engine makes the decisions it does. ~50–75 min careful read each.
2. **API-layer references** (new with M1.16) — developer-facing reference docs covering *how* to call the engine via HTTP. Shorter, JSON-heavy, organized around endpoints rather than financial concepts. ~35 min careful read.

Both styles are deliberately deeper than the auto-generated OpenAPI spec — they cover financial fundamentals (engine layer) and end-to-end client workflows (API layer) that a course instructor or onboarding engineer would want as assigned reading.

## Index — engine-layer tutorials

| Tutorial | Audience | Reading time |
|---|---|---|
| [market-state-engine.md](./market-state-engine.md) | 1st-year MFE, quant developers, options traders | ~75 min careful read · ~25 min skim |
| [scoring-primitives.md](./scoring-primitives.md) | Same audience; read after `market-state-engine.md` (depends on §2 input vocabulary) | ~50 min careful read · ~20 min skim |
| [flow-score-engine.md](./flow-score-engine.md) | Same audience; read after `market-state-engine.md` and `scoring-primitives.md` (depends on `*ScoreResult` pattern, `gamma_score` sign/magnitude split, OI walls, max pain, expected move) | ~70 min careful read · ~30 min skim |
| [confidence-composer.md](./confidence-composer.md) | Same audience; read after `market-state-engine.md`, `scoring-primitives.md`, and `flow-score-engine.md` (depends on `MarketStateResult.regime_score` / `trend_strength` / `breakout_signal` / `oi_concentration_at_max_pain` / `days_to_next_event`, `FlowScore.confidence` / `score`, and the §22.13 multiplicative-penalty redesign) | ~55 min careful read · ~20 min skim |
| [master-decision-engine.md](./master-decision-engine.md) | Same audience; **capstone** — read after all four upstream tutorials. Wires every engine into a single replayable `DailyDecision`. Covers the §9.6 pipeline, two-stage `compose()`, `inputs_hash` canonical JSON, `decision_id` determinism, and the three-pin replay lock. | ~50 min careful read · ~20 min skim |

## Index — API-layer references

| Tutorial | Audience | Reading time | Covers |
|---|---|---|---|
| [engine-api-reference.md](./engine-api-reference.md) | Full-stack engineers integrating against the engine HTTP surface; PR reviewers for the M1.14–M1.16 endpoint work | ~35 min careful read · ~15 min skim | All seven currently-shipped `/api/v1/engine/*` endpoints (M1.14 `/daily-plan` + `/recommend`; M1.15 `/what-if` + `/market-state` + `/flow-score`; M1.16 `/strike-candidates` + `/execution-check`). Prerequisite: read the [Master Decision Engine](./master-decision-engine.md) tutorial first. |

### Reading order

The engine-layer tutorials form a directed acyclic graph: each one references types and patterns introduced by its prerequisites. The recommended sequence for a new reader is:

1. **`market-state-engine.md`** — establishes the input vocabulary (`Regime`, `MarketStateResult`, `classify()`, 18 input fields).
2. **`scoring-primitives.md`** — introduces the `*ScoreResult` pattern, `clip01`, and how M1.4a primitives feed downstream consumers.
3. **`flow-score-engine.md`** — the first orchestrator (`compute()`); shows how scoring primitives stitch into a `FlowScore`.
4. **`confidence-composer.md`** — the second orchestrator (`compose()`), with the §22.13 multiplicative formula and the `(positive_score, penalty_multiplier)` decomposition.
5. **`master-decision-engine.md`** — the capstone (`produce_daily_decision()`); pulls all the above into a single `DailyDecision` with three-pin replay safety.
6. **`engine-api-reference.md`** *(API layer)* — how to call all of the above via `/api/v1/engine/*`. Builds on `master-decision-engine.md`'s mental model. Skip the engine-layer tutorials and come straight here if you only need to integrate the API, not extend it.

### Tutorials still to write

#### Engine-layer (shipped engine modules without a long-form tutorial)

These engine modules are on `main` but don't yet have a pedagogical tutorial. Adding one is a docs-only PR (no engine version bump):

- **Execution Feasibility** (`engine.execution`, M1.11 + M1.12) — per-leg liquidity / spread / slippage / fill scoring; aggregate weakest-link rules; downgrade ladder with stricter liquidity floors. Bridges into the M1.10 Confidence Composer via `liquidity_penalty()`. Currently documented inline + via `tests/test_execution.py` and `tests/test_execution_downgrade.py`. **Now also exposed via the API**: see [`engine-api-reference.md` §8.4](./engine-api-reference.md#84-post-engineexecution-check-m116).
- **Recommendation Engine** (`engine.recommendation`, M1.8 + M1.9) — YAML rule pipeline with 8 V1 rules per §22.8, 15-clause vocabulary (`regime`, `iv_rank_gte/lte`, `has_short_call`, `confidence_lte`, etc.), first-match-wins evaluation. Most config-heavy module — users will edit `rules.yaml`. Currently documented inline + via `tests/test_recommendation.py`. **Also exposed**: see [`engine-api-reference.md` §6](./engine-api-reference.md#6-post-enginerecommend--rule-pipeline-only-m114).
- **Strike Selector** (`engine.strike_selector`, M1.7) — BS-delta-matched strike picking; emits `StrikeSelection`. Lower priority — well-understood standard method. Documented inline + via `tests/test_strike_selector.py`. **Also exposed**: see [`engine-api-reference.md` §8.3](./engine-api-reference.md#83-post-enginestrike-candidates-m116).
- **Black-Scholes Greeks** (`engine.greeks`, M1.6) — `delta`, `gamma`, `vega`, `theta`, `rho`, `time_to_expiry_years`. Lowest priority — textbook material; the engine is a thin wrapper. Documented inline + via `tests/test_greeks.py`.

#### API-layer (endpoints shipped or planned but not yet covered)

- **CSV-import + profile + outcomes** (`/api/v1/{profile, outcomes, data/*}`, M1.17 — not yet shipped). When M1.17 lands, write a companion to `engine-api-reference.md` covering the data-import workflow + how it lights up the "optional `inputs`" path on the engine endpoints.
- **Today screen client integration** (Next.js consumer of `/engine/daily-plan`, M1.18 — not yet shipped). When M1.18 lands, write a tutorial covering the typed-client patterns (server-component fetch, RFC 7807 error handling, `data_freshness` badge rendering).

#### Templates

If you're contributing one:
- For an engine-layer tutorial: follow [`master-decision-engine.md`](./master-decision-engine.md) or [`confidence-composer.md`](./confidence-composer.md) (audience header → TOC → numbered sections → end-to-end worked example → exercises → glossary).
- For an API-layer reference: follow [`engine-api-reference.md`](./engine-api-reference.md) (same structure but JSON-heavy and endpoint-organized, ~35 min target read).

## How tutorials relate to the rest of the docs

| Doc family | Purpose | Length |
|---|---|---|
| `tutorials/` (this folder) | Pedagogical, "learn the engine" | Long-form |
| `architecture.md` | Layer cake / data flow reference | Medium |
| `decisions/*.md` (ADRs) | Locked decisions, one per file | Short |
| `enhancements/*` | Spec assessments | Short |
| `thread-transitions/` | Agent handoff records | Medium |

If a tutorial references a locked decision, it links to the ADR; the ADR
remains the source of truth. Tutorials explain; ADRs commit.

## Conventions

- Math uses LaTeX-style `$inline$` and `$$display$$` blocks (GitHub renders).
- Code snippets quote real engine code; tutorials are kept in sync when the
  engine changes (the same PR updates both).
- Every tutorial has an explicit **disclaimer** linking to
  [`docs/disclaimers.md`](../disclaimers.md): tutorials are educational
  material, not investment advice.
