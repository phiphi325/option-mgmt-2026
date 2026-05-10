# Changelog

All notable changes to the engine package (`packages/engine/engine/__version__`) and to top-level project shape are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); engine versioning follows [SemVer](https://semver.org/) per [ADR-0005](./docs/decisions/0005-engine-pure-function-discipline.md).

Version bump rules (per ADR-0005 + plan v1.2 §22.15 L2):

- **patch** (`0.x.y → 0.x.y+1`) — bug fix, no schema change
- **minor** (`0.x.0 → 0.x+1.0`) — new engine, score, or public function
- **major** (`x.0.0 → x+1.0.0`) — schema change, removed/renamed fields, semantic shift

CI guard `scripts/check_engine_version_bump.sh` enforces a version bump on every change under `packages/engine/engine/`.

---

## [0.7.0] — 2026-05-10

### Added (engine — `engine.flow_score`)

- **`flow_score.compute_oi_walls()`** — OI-derived support / resistance levels around spot, per plan v1.2 §9.3 step 1.
  - Aggregates OI per strike across calls + puts in the focus expiries.
  - Threshold = `percentile_threshold` (default `0.90`, top decile per §9.3) quantile of the per-strike OI distribution.
  - Strict-`>` rule (per plan): only strikes with OI **strictly above** the threshold qualify as walls. Naturally handles flat distributions (no strike exceeds its own percentile → no walls); the trade-off is that tied peaks at the very top of the OI distribution sit AT the percentile and need a lower threshold to be picked up.
  - `support` = nearest qualifying strike strictly below spot; `resistance` = nearest qualifying strike strictly above. Either may be `None`. A strike sitting on spot is neither.
  - Reuses the existing `engine.scoring.structure.OiWalls` dataclass (no duplication). The §9.11 wiring matrix names `flow_score` as the *producer* and `structure_score` as the *consumer*.
- **`flow_score.compute_dealer_gamma_proxy()`** — V1 signed proxy for dealer net gamma exposure, per plan v1.2 §9.3 step 4.
  - Formula: `Σ sign(c) · OI(c) · (strike(c) - spot)` over contracts in `expiry_focus`, where `sign = -1` for calls and `+1` for puts.
  - Negative result = net short gamma above spot (vol amplifier — dealer chases spot to delta-hedge); positive = net long gamma (vol dampener).
  - Constant-gamma proxy (γ ≡ 1 per contract). The plan §9.3 formula uses BS gamma, which lands in M1.6; the full Phase 1.5 E1 GEX module replaces this proxy with proper signed gamma per ADR-0008.
  - Magnitude is unbounded and not unit-meaningful — downstream consumers normalize before use.

### Changed

- `engine.__init__` re-exports `compute_oi_walls` and `compute_dealer_gamma_proxy`.
- 34 new tests (245 → 279 total in `packages/engine/tests/`). 97% line coverage on `engine.flow_score` (the 2 uncovered lines are defensive `_percentile_value` fallback for empty input + a `per_strike_oi` empty branch — both unreachable when callers pass valid contracts).

### Plan refs

v1.2 §9.3 step 1 (OI walls) + step 4 (dealer-gamma proxy), §17 M1.5 (size M), §9.11 wiring matrix (flow_score is OiWalls producer; structure_score is consumer), ADR-0008 (E1 GEX in Phase 1.5 replaces the V1 dealer-gamma proxy).

### Deferred

- **M1.5a** — `scoring.gamma_score()` pure fn + tests. Lands separately as a scoring primitive.
- **M1.5b** — Flow Score Engine `compute()` orchestrator returning the full §9.3a V1 contract (bullish/bearish/score/bias/pin_probability/gamma_risk/recommended_action/explanation). Requires M1.5a's `gamma_score`.

PR: [#32](https://github.com/csupenn/option-mgmt-2026/pull/32)

---

## [0.6.0] — 2026-05-10

### Added (engine — `engine.market_state.classify`)

- **`market_state.classify()`** — full Market State Engine entry point. 18-input signature per plan v1.2 §22.3. Computes per-regime score predicates (per §9.2) for all six regimes, picks the winning regime via max-score-with-priority-tie-break, generates advisory tags, and echoes the input vector for explainability + replay.
- **`market_state.MarketStateResult`** — frozen dataclass carrying:
  - Engine output: `regime: Regime`, `regime_score: float ∈ [0, 1]`, `all_scores: dict[Regime, float]`, `tags: tuple[str, ...]`.
  - Echoed inputs: `spot`, `iv_rank`, `iv_percentile`, `hv_30`, `expected_move_pct`, `max_pain`, `max_pain_delta_pct` (computed), `pcr_volume`, `pcr_oi`, `trend_strength`, `realized_vs_implied`, `breakout_signal`, `oi_concentration_at_max_pain`, `days_to_next_event`, `next_event_kind`, `days_since_event`, `days_to_nearest_opex`, `iv_rank_change_1d`, `gap_pct`.
- **Per-regime score predicates** (private — `_score_<regime>`):
  - `HIGH_IV_EVENT`: `0.5 · sigmoid((iv_rank − 0.70) / 0.10) + 0.5 · near_event_flag` (event within 7 days).
  - `HIGH_IV_PIN`: `0.4 · sigmoid((iv_rank − 0.60) / 0.10) + 0.4 · pin_close + 0.2 · near_expiry` (pin tolerance 1%, opex horizon 5 days).
  - `LOW_IV_TREND`: `0.5 · sigmoid((0.30 − iv_rank) / 0.10) + 0.5 · trend_strength`.
  - `LOW_IV_RANGE`: `0.4 · iv_low + 0.3 · (1 − trend_strength) + 0.3 · (1 − |realized_vs_implied − 1|)`.
  - `BREAKOUT`: `clip01(breakout_signal)` — defers entirely to the §22.5 composite.
  - `POST_EVENT_REPRICE`: `0.6 · clip01(−iv_rank_change_1d / 0.20) + 0.4 · big_gap_flag` when `days_since_event <= 1`. Note: plan §9.2's sketched `1 − x / -20` is sign-flipped; the corrected formula is documented at the call site.
- **Tie-break priority** (`_TIE_BREAK_PRIORITY`): when the runner-up's score is within `0.10` of the leader, resolves toward the more conservative regime in this order: `HIGH_IV_EVENT > HIGH_IV_PIN > POST_EVENT_REPRICE > BREAKOUT > LOW_IV_TREND > LOW_IV_RANGE` (per §9.2).
- **Tag generation** (advisory, consumed by Strike Selector + Recommendation + Confidence Composer):
  - `sell_vol_favorable` (iv_rank ≥ 0.70), `sell_vol_unfavorable` (iv_rank ≤ 0.30)
  - `event_in_<N>d` when `days_to_next_event ≤ 14`
  - `post_event_window` when `days_since_event ≤ 2`
  - `pin_risk` when `|spot − max_pain|/spot ≤ 0.005` and `dte_to_nearest_opex ≤ 5`
  - `breakout_active` (breakout_signal ≥ 0.70)
  - `trending` (trend_strength ≥ 0.70) / `ranging` (trend_strength ≤ 0.30)
  - `concentrated_oi_at_pin` (oi_concentration_at_max_pain ≥ 0.60)
- **`engine._utils.sigmoid()`** — standard logistic helper, numerically stable for extreme inputs (branches on sign so `math.exp` always sees a non-positive argument).

### Scale conventions (documented in classify docstring)

- `iv_rank`, `iv_percentile`, `trend_strength`, `breakout_signal`, `oi_concentration_at_max_pain` all in `[0, 1]` (engine-canonical, matches `engine.market_state.iv.iv_rank`).
- `iv_rank_change_1d` in `[-1, 1]` (delta of `iv_rank`); a 20pp IV crush = `-0.20`.
- `gap_pct` is signed fraction of spot (`0.025 = 2.5%`).
- `expected_move_pct` is fraction of spot.
- `spot`, `max_pain` are floats in dollars (matches `engine.market_state.compute_max_pain` and `OptionContract.strike`); plan §22.3's `Decimal` is aspirational.

### Changed

- `engine.__init__` re-exports `classify` and `MarketStateResult`.
- `engine.market_state.__init__` re-exports `classify` and `MarketStateResult` (M1.4 section in the module docstring).
- 65 new tests (180 → 245 total in `packages/engine/tests/`). 24 regime fixtures (4 per regime, plan §17 acceptance), 12 tag tests, tie-break behaviour tests, echoed-input tests, parametrized validation tests, Hypothesis property test asserting `regime_score == all_scores[regime]` and all values in `[0, 1]`.
- `engine.market_state.classify`: 99% line coverage; the 2 uncovered lines are a defensive fallback in `_select_regime` that's unreachable when `_TIE_BREAK_PRIORITY` covers all six regimes (left in for safety against future regressions).

### Plan refs

v1.2 §22.3 (extended 18-input signature), §9.2 (per-regime predicate sketches with the §22-noted scale + sign-error corrections), §17 M1.4 (size L, 24 regime fixtures), §22.5 (`clip01` reuse), §22.13 (`MarketStateResult` echoed inputs power Confidence Composer breakdowns).

PR: [#29](https://github.com/csupenn/option-mgmt-2026/pull/29)

---

## [0.5.0] — 2026-05-10

### Added (engine — `engine.scoring`)

- **`scoring.iv_score()`** — composite IV-favorability score in `[0, 1]` from `iv_rank`, `iv_percentile`, `hv_30`, `atm_iv_30d`. Higher = more favorable for selling premium.
  - rank component (weight 0.40), percentile component (weight 0.30), IV/HV premium component (weight 0.30; ratio anchors 0.7 → 0.0, 1.5 → 1.0).
  - Constant-prices fallback (`hv_30 == 0`) → premium component clamps to 0.5 (the "no information" prior).
- **`scoring.structure_score()`** — composite options-structure score in `[0, 1]` from `oi_walls`, `max_pain`, `spot`, `expected_move_pct`, `dte_to_nearest_opex`. Higher = more constrained structural environment.
  - wall proximity (weight 0.30) — distance to nearest OI wall normalized by 2·EM
  - pin alignment (weight 0.25) — distance from spot to max_pain normalized by EM
  - opex proximity (weight 0.20) — `[NEAR=2, FAR=14]` trading-day band
  - EM containment (weight 0.25) — `[TIGHT=2%, WIDE=10%]` band
  Handles one-sided walls (only support OR resistance present), zero-EM (zero-DTE) edge case correctly.
- **`scoring.event_score()`** — composite event-uncertainty score in `[0, 1]` from `days_to_event`, `event_kind`, `event_history`. Higher = larger event-driven risk premium in the chain.
  - Multiplicative proximity gate: `days_to_event is None` or `>= 30` collapses score to 0.
  - Inner blend: `0.5 · kind_weight + 0.5 · magnitude` where magnitude saturates at `avg_abs_return_pct ≥ 5%`.
  - Negative `days_to_event` (event already past) clamps to 0 (defensive — event-calendar service should advance promptly).
- **`scoring.OiWalls`** — frozen dataclass holding OI-derived support/resistance levels. Either side may be `None`; `structure_score` handles missing walls correctly. Produced by Flow Score Engine in M1.5; consumed by `structure_score` here.
- **`scoring.EventStats`** — frozen dataclass holding historical event-day stats (`avg_abs_return_pct`, `iv_runup_pct`, `sample_count`).
- **`scoring.EventKind`** — `StrEnum` of recognized event kinds (`earnings`, `fomc`, `cpi`, `guidance`, `ex_dividend`, `other`).
- **`scoring.EVENT_KIND_WEIGHTS`** — V1 weight prior table (`earnings=1.0`, `fomc=0.7`, `cpi=0.6`, `guidance=0.5`, `ex_dividend=0.3`, `other=0.5`). Replaced in Phase 4 by the M4.5 event-impact estimator (per plan §16).
- **Result types**: `IvScoreResult`, `StructureScoreResult`, `EventScoreResult`. Each carries `score: float ∈ [0, 1]` plus a `breakdown: dict[str, float]` mapping component names to their values (consumed by Confidence Composer for explainability per §22.13).

### Changed

- `engine.__init__` re-exports the new scoring symbols.
- 59 new tests (121 → 180 total in `packages/engine/tests/`). 100% line coverage on `engine.scoring` (per plan v1.2 §9.11 acceptance bar).

### CI

- New step `Coverage check (engine.scoring 100%)` enforces the 100% line-coverage requirement from plan v1.2 §9.11 via `pytest --cov=engine.scoring --cov-fail-under=100`.
- `pytest-cov` added to `packages/engine/pyproject.toml` dev dependencies.

### Plan refs

v1.2 §9.11 (Scoring Functions Module spec), §17 M1.4a (size M), §22.5 (`clip01` reuse), §22.13 (breakdown for Confidence Composer).

PR: [#28](https://github.com/csupenn/option-mgmt-2026/pull/28)

---

## [0.4.0] — 2026-05-10

### Added (engine — `engine.market_state`)

- **`trend_strength.compute_trend_strength()`** — J. Welles Wilder Jr.'s ADX (1978), normalized to `[0, 1]`. ADX ≤ 20 → 0.0; ADX ≥ 40 → 1.0; linear between. Returns `0.5` sentinel when history < `2n + 10` bars (deliberate non-raising path per plan §22.5 so M1.4 `classify()` keeps running against partial data).
- **`trend_strength.wilder_adx()`** — exposed publicly as a diagnostic helper. Raises below the mathematical minimum of `2n + 1` bars.
- **`breakout.compute_breakout_signal()`** — 4-component composite, `[0, 1]`:
  - move (weight 0.35) — `|Δspot / spot_5d_ago| / 0.05`
  - vol (weight 0.20) — `atm_iv_change_5d / 0.10` (negatives clipped to 0)
  - oi (weight 0.20) — `|oi_shift_ratio|`
  - break (weight 0.25) — `above_resistance_pct / 0.02`, gated on `above_resistance` flag
  Weights sum to 1.0. Raises on non-positive `spot` or `spot_5d_ago`.
- **`engine._utils.clip01()`** — engine-wide `[0, 1]` saturation helper, centralized for reuse by M1.4 scoring functions and the Confidence Composer (per plan v1.2 §22.5 + §22.13).

### Changed

- 31 new tests added (90 → 121 total in `packages/engine/tests/`).

### Plan refs

v1.2 §9.1, §17 M1.3 (size S), §22.3 (extended `classify()` signature names `trend_strength` + `breakout_signal`), §22.5 (canonical formulas).

PR: [#26](https://github.com/csupenn/option-mgmt-2026/pull/26)

---

## [0.3.0] — 2026-05-10

### Added (engine — `engine.market_state`)

- **`max_pain.compute_max_pain()`** — CBOE-style total-OI loss minimization across the strike grid.
- **`expected_move.compute_expected_move()`** — ATM straddle method + forward-IV method, with cross-validation between the two.
- **`pcr.compute_pcr()`** — put/call ratios on volume and open interest (separate fields).

### Plan refs

v1.2 §9.1, §17 M1.2, §22.3.

PR: [#25](https://github.com/csupenn/option-mgmt-2026/pull/25)

---

## [0.2.0] — 2026-05-10

### Added (engine — `engine.market_state`)

- **`iv.compute_iv_rank()`** + **`iv.compute_iv_percentile()`** — 252-day rank and percentile from `iv_history` series.
- **`hv.compute_hv_30()`** — annualized close-to-close standard deviation.
- **`hv.compute_hv_30_parkinson()`** — Parkinson high-low range estimator (~5× more efficient than close-to-close).

### Added (seeds)

- 252-day MSFT IV history seed CSV per plan v1.2 §21.

### Plan refs

v1.2 §9.1, §17 M1.1, §22.5 (IV rank formula).

PR: [#24](https://github.com/csupenn/option-mgmt-2026/pull/24)

---

## [0.1.0] — 2026-05-10

Initial engine scaffold (M0.6).

### Added

- `engine.regimes` — 6 named regimes per [ADR-0002](./docs/decisions/0002-regime-taxonomy.md): `HIGH_IV_EVENT`, `HIGH_IV_PIN`, `LOW_IV_TREND`, `LOW_IV_RANGE`, `BREAKOUT`, `POST_EVENT_REPRICE`.
- `engine.profiles.UserStrategyProfile` — frozen Pydantic v2 model (style, max_coverage, roll_aggressiveness, drawdown_tolerance, tax_sensitivity, delta/DTE bands).
- `engine.types` — `OptionContract`, `ChainSnapshot`, `ChainRow`.
- `engine.version` — `__version__` constant; bumped per ADR-0005 / plan §22.15 L2.
- `packages/shared-types/` — TS types generated from Pydantic via `scripts/generate.py`. CI drift check.

### Plan refs

v1.2 §17 M0.6, §22.2 (FlowScore V1 contract names), §22.3 (`classify()` signature shape).

PR: [#17](https://github.com/csupenn/option-mgmt-2026/pull/17)

---

## Pre-engine — Phase 0 foundation (no engine version)

Phase 0 milestones M0.1–M0.5 + M0.7 + the docs foundation (ADRs 0001–0007) shipped before the engine package was scaffolded; they're tracked in [`README.md` § Status](./README.md#status), not here. The engine version line begins at `0.1.0` (M0.6).

| Date | What | PR |
|---|---|---|
| 2026-05-10 | docs — enhancement-spec adoption roadmap (ADR-0008) | [#23](https://github.com/csupenn/option-mgmt-2026/pull/23) |
| 2026-05-10 | M0.7 — end-to-end smoke test | [#22](https://github.com/csupenn/option-mgmt-2026/pull/22) |
| 2026-05-10 | M0.5 — CI + pre-commit + Dependabot + policy guards | [#6](https://github.com/csupenn/option-mgmt-2026/pull/6) |
| 2026-05-10 | docs foundation + ADRs 0001–0006 | [#5](https://github.com/csupenn/option-mgmt-2026/pull/5) |
| 2026-05-10 | M0.4 — Next.js shell + disclaimer gate + Tailwind + Vitest | [#4](https://github.com/csupenn/option-mgmt-2026/pull/4) |
| 2026-05-10 | M0.3 — FastAPI shell + auth scaffolding | [#3](https://github.com/csupenn/option-mgmt-2026/pull/3) |
| 2026-05-10 | M0.2 — Postgres schema + Alembic init | [#2](https://github.com/csupenn/option-mgmt-2026/pull/2) |
| 2026-05-10 | M0.1 — monorepo scaffold | [#1](https://github.com/csupenn/option-mgmt-2026/pull/1) |
