# Tutorials

Long-form, pedagogical material targeting first-year master's students in
financial engineering (or any reader who wants to understand *why* the engine
makes the decisions it does, not just *how* to call it).

Tutorials are deliberately deeper than the API references in `docs/` — they
cover the financial fundamentals, the design methodology, and the worked
examples a course instructor would want to assign as reading.

## Index

| Tutorial | Audience | Reading time |
|---|---|---|
| [market-state-engine.md](./market-state-engine.md) | 1st-year MFE, quant developers, options traders | ~75 min careful read · ~25 min skim |
| [scoring-primitives.md](./scoring-primitives.md) | Same audience; read after `market-state-engine.md` (depends on §2 input vocabulary) | ~50 min careful read · ~20 min skim |
| [flow-score-engine.md](./flow-score-engine.md) | Same audience; read after `market-state-engine.md` and `scoring-primitives.md` (depends on `*ScoreResult` pattern, `gamma_score` sign/magnitude split, OI walls, max pain, expected move) | ~70 min careful read · ~30 min skim |
| [confidence-composer.md](./confidence-composer.md) | Same audience; read after `market-state-engine.md`, `scoring-primitives.md`, and `flow-score-engine.md` (depends on `MarketStateResult.regime_score` / `trend_strength` / `breakout_signal` / `oi_concentration_at_max_pain` / `days_to_next_event`, `FlowScore.confidence` / `score`, and the §22.13 multiplicative-penalty redesign) | ~55 min careful read · ~20 min skim |
| [master-decision-engine.md](./master-decision-engine.md) | Same audience; **capstone** — read after all four upstream tutorials. Wires every engine into a single replayable `DailyDecision`. Covers the §9.6 pipeline, two-stage `compose()`, `inputs_hash` canonical JSON, `decision_id` determinism, and the three-pin replay lock. | ~50 min careful read · ~20 min skim |

### Reading order

The tutorials form a directed acyclic graph: each one references types
and patterns introduced by its prerequisites. The recommended sequence
for a new reader is:

1. **`market-state-engine.md`** — establishes the input vocabulary
   (`Regime`, `MarketStateResult`, classify(), 18 input fields).
2. **`scoring-primitives.md`** — introduces the `*ScoreResult` pattern,
   `clip01`, and how M1.4a primitives feed downstream consumers.
3. **`flow-score-engine.md`** — the first orchestrator
   (`compute()`); shows how scoring primitives stitch into a `FlowScore`.
4. **`confidence-composer.md`** — the second orchestrator (`compose()`),
   with the §22.13 multiplicative formula and the
   `(positive_score, penalty_multiplier)` decomposition.
5. **`master-decision-engine.md`** — the capstone (`produce_daily_decision()`);
   pulls all the above into a single `DailyDecision` with three-pin
   replay safety.

### Tutorials still to write

The following engine modules are shipped on `main` but don't yet have a
long-form tutorial. Adding them is a docs-only PR (no engine version
bump):

- **Execution Feasibility** (`engine.execution`, M1.11 + M1.12) —
  per-leg liquidity / spread / slippage / fill scoring; aggregate
  weakest-link rules; downgrade ladder with stricter liquidity floors.
  Bridges into the M1.10 Confidence Composer via `liquidity_penalty()`.
  Currently documented inline + via `tests/test_execution.py` and
  `tests/test_execution_downgrade.py`.
- **Recommendation Engine** (`engine.recommendation`, M1.8 + M1.9) —
  YAML rule pipeline with 8 V1 rules per §22.8, 15 clause vocabulary
  (`regime`, `iv_rank_gte/lte`, `has_short_call`, `confidence_lte`, etc.),
  first-match-wins evaluation. Most config-heavy module — users will
  edit `rules.yaml`. Currently documented inline + via `tests/test_recommendation.py`.
- **Strike Selector** (`engine.strike_selector`, M1.7) — BS-delta-matched
  strike picking; emits `StrikeSelection`. Lower priority — well-understood
  standard method. Documented inline + via `tests/test_strike_selector.py`.
- **Black-Scholes Greeks** (`engine.greeks`, M1.6) — `delta`, `gamma`,
  `vega`, `theta`, `rho`, `time_to_expiry_years`. Lowest priority —
  textbook material; the engine is a thin wrapper. Documented inline
  + via `tests/test_greeks.py`.

If you're contributing one, follow the [`master-decision-engine.md`](./master-decision-engine.md)
or [`confidence-composer.md`](./confidence-composer.md) template
(audience header → TOC → numbered sections → end-to-end worked
example → exercises → glossary).

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
