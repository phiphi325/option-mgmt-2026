# Changelog

All notable changes to the engine package (`packages/engine/engine/__version__`) and to top-level project shape are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); engine versioning follows [SemVer](https://semver.org/) per [ADR-0005](./docs/decisions/0005-engine-pure-function-discipline.md).

Version bump rules (per ADR-0005 + plan v1.2 §22.15 L2):

- **patch** (`0.x.y → 0.x.y+1`) — bug fix, no schema change
- **minor** (`0.x.0 → 0.x+1.0`) — new engine, score, or public function
- **major** (`x.0.0 → x+1.0.0`) — schema change, removed/renamed fields, semantic shift

CI guard `scripts/check_engine_version_bump.sh` enforces a version bump on every change under `packages/engine/engine/`.

---

## [0.10.0] — 2026-05-10

### Added (engine — `engine.greeks`)

- **`greeks.delta()`** — Black-Scholes-Merton delta for European options with continuous dividend yield. Signature: `delta(*, spot, strike, tau, iv, r, q, option_type) -> float`. Call: `Δ_c = e^(-qτ) · N(d1)` in `(0, 1)`. Put: `Δ_p = -e^(-qτ) · N(-d1)` in `(-1, 0)`. Standard equity-option convention (call deltas positive, put deltas negative). Validated property: put-call parity `Δ_c - Δ_p = e^(-qτ)` holds for any valid input (asserted via Hypothesis with 100 examples).
- **`greeks.gamma()`** — BSM gamma; identical for calls and puts. `Γ = e^(-qτ) · n(d1) / (S · σ · √τ)`. Peaks near ATM.
- **`greeks.vega()`** — BSM vega per 1-unit IV change. `ν = S · e^(-qτ) · n(d1) · √τ`. Divide by 100 for "per 1% IV". Increases with `√τ`.
- **`greeks.theta()`** — BSM theta per year. Both call and put are negative for typical inputs (time decay). Divide by 365 for "per calendar day" or by 252 for "per trading day".
- **`greeks.rho()`** — BSM rho per 1-unit rate change. Call positive, put negative. Divide by 100 for "per 1%".
- **`greeks.time_to_expiry_years()`** — Year-fraction time-to-expiry using CBOE 365-day convention: `τ = max((expiry - as_of).days, 1) / 365.0`. The 1-day floor keeps BS math defined on expiration-day chains (defensive — the data layer should filter expired contracts upstream).

All Greeks are pure functions (per [ADR-0005](./docs/decisions/0005-engine-pure-function-discipline.md)) — no I/O, no DB, no clock, no env. Standard normal CDF / PDF implemented via stdlib `math.erf` and `math.exp` (no scipy dependency — keeps the engine's dependency surface minimal).

Validation surface: every Greeks function raises `ValueError` on non-positive `spot`, `strike`, `tau`, or `iv`. `r` and `q` accept any real value (negative rates are legal — e.g. Eurozone).

### Changed (engine — `engine.flow_score.skew`)

- **`skew_25d()` V1 stub replaced with the real implementation.** The function now uses `engine.greeks.delta` to identify the strike whose BS delta is closest to ±0.25 on each side of the chain for each focus expiry. Per-strike IV is used for that strike's delta (the empirical smile is honored, not flattened to ATM vol). Per-expiry skew = `IV(25-Δ put) − IV(25-Δ call)`. Final value = average across qualifying focus expiries.
- **Signature change (additive — backward-compatible at the source level via `compute()` defaults):** `skew_25d` now requires `spot` and `as_of`, and accepts optional `risk_free_rate` (default `0.05`) and `dividend_yield` (default `0.0`). Direct callers of `skew_25d` must pass the new positional arguments; `compute()` was updated to thread them from `chain_snapshot.as_of` plus its own new `risk_free_rate` / `dividend_yield` kwargs.
- Edge cases preserved gracefully: empty `expiry_focus` → 0; expiries with no contracts or only one side → skipped; contracts with `iv=None` or `iv=0` → filtered; flat smile → 0 (no smile = no skew).
- The historic V1 stub returned 0 unconditionally. With M1.6 the 0.20-weight skew component is now **active** in `compute()` and contributes proportionally to the bullish/bearish formulas per §9.3a. The bullish/bearish score range expands from `[0, 65]` to `[0, 85]` (both sides). **No threshold recalibration was needed** — the existing bias and decision-tree thresholds were calibrated assuming the full 5-component formula, so they fit naturally as components come online (per the design promise made in the M1.5b tutorial §9.1).

### Changed (engine — `engine.flow_score.compute`)

- **`compute()` signature extended (additive, backward-compatible):** accepts optional `risk_free_rate: float = 0.05` and `dividend_yield: float = 0.0` kwargs. Both default to V1 priors matching the early-2026 SOFR baseline and a sensible MSFT-class default. The values are threaded to the M1.6 `skew_25d` for BS delta computation. Existing callers that omit these kwargs get the same priors.
- Internal step 4 ("V1 stubs") renamed to "skew + basis stub" — `skew_25d` is now an active producer, only `futures_basis` remains a stub awaiting Phase 2.
- 1 test in `test_flow_score_compute.py` refactored to cover the new M1.6 `skew_25d` edge cases (one test split into two: `test_skew_25d_returns_zero_when_no_focus` and `test_skew_25d_returns_zero_with_only_calls`). All 7 `compute()` integration tests and the Hypothesis property test continue to pass — the existing synthetic chains use `iv=0.30` on every contract (flat smile), so the real skew computes to 0 and the M1.5b worked-example numbers are preserved.

### Changed (engine — `engine.__init__`)

- New top-level re-exports: `delta`, `gamma`, `vega`, `theta`, `rho`, `time_to_expiry_years` from `engine.greeks`. The Greek `gamma` does NOT collide with the `gamma_score` re-export from `engine.scoring` — they have distinct names.

### Tests

- 43 new tests in `packages/engine/tests/test_greeks.py`:
  - 4 `time_to_expiry_years` tests (typical 30-day, 1-year, same-day floor, past-expiry floor).
  - 5 `_norm_cdf` / `_norm_pdf` sanity tests (zero, symmetry, known percentiles).
  - 7 `delta` hand-computed reference tests (ATM call/put 30 DTE 30% vol matched to textbook, deep ITM, deep OTM, bound checks, dividend yield shift).
  - 1 Hypothesis property test (100 examples) asserting `Δ_c − Δ_p = e^(−qτ)` (put-call parity for delta).
  - 3 `gamma` tests (ATM positive, always positive, peaks-near-ATM).
  - 3 `vega` tests (ATM positive, always positive, increases with √τ).
  - 3 `theta` tests (call ATM negative, put ATM negative, OTM less-negative).
  - 2 `rho` tests (call positive, put negative).
  - 8 validation tests covering every bound that raises (`spot`, `strike`, `tau`, `iv` × every Greek).
  - 2 25-Δ strike-selection smoke tests (call 25-Δ above spot; put 25-Δ below spot) demonstrating the use case `skew_25d` consumes.
  - **100% line coverage** on `engine.greeks`.

- 13 new tests in `packages/engine/tests/test_flow_score_skew.py`:
  - Baseline: flat smile → 0 skew.
  - Put-side rich: positive skew (bearish flow); call-side rich: negative skew.
  - Typical equity smile (downward-sloping puts; flatter calls) → +0.05 skew at the 25-Δ wings.
  - Multi-expiry averaging.
  - Edge cases: empty focus, only-calls, only-puts, `iv=None` filtered, `iv=0` filtered.
  - Validation: non-positive spot rejected.
  - `dividend_yield` override changes 25-Δ strike selection.
  - End-to-end integration: `compute()` propagates `chain_snapshot.as_of` + `spot` to `skew_25d` and the breakdown's `bearish_skew` reflects the real value.
  - **100% line coverage** on `engine.flow_score.skew`.

- 58 `test_flow_score_compute.py` tests preserved (the one stub-specific test refactored into two). M1.5b synthetic chain numerics unchanged because all test fixtures use flat IV.

### Docs

- `docs/tutorials/flow-score-engine.md` updated to reflect M1.6:
  - Header: engine version coverage now lists `0.9.0` AND `0.10.0`; mentions `engine.greeks` module.
  - §1.3 design objective 3 (forward-compat): rewritten to note skew is now active and only `futures_basis` remains a stub.
  - §3 orchestrator step 4: renamed "Stubs" → "Skew (active, M1.6) + basis stub".
  - §4.3 Component 3 (IV skew): rewritten — header now says "active from M1.6", new content explains the smile-aware 25-Δ strike-selection procedure with signature, the V1 priors for r/q, and the smile-aware vs flat-vol-naive design choice.
  - §9 V1 stubs: section title kept; §9.1 rewritten to explain why skew was a stub in M1.5b and how M1.6 resolved it (preserving the "no recalibration" promise); §9.2 expanded to be consistent.
  - §9.4 (validation): note that `skew_25d` now validates `spot > 0` at the boundary.
  - §10 worked example step 4: now explains why skew=0 on the flat-IV synthetic chain and what a real smile would change.
  - Exercise 7 rewritten: was "Skew goes live (hypothetical)", now "Skew is live (M1.6)" with a hand-computed example using put-rich IV=0.35 vs call-side IV=0.30.
  - §12 Further reading: lists the new test files; adds Hull *Options, Futures, and Other Derivatives* for the Greeks reference.
  - §13 Glossary: `skew` entry updated ("real impl from M1.6"); adds new symbols `Δ_BS(c)`, `τ`, `r`, `q`.

### Plan refs

v1.2 §9 (Greeks module), §9.3 step 3 (skew component), §9.3a (V1 LOCKED contract), §17 M1.6, ADR-0005 (pure-function discipline + SemVer).

PR: [#35](https://github.com/csupenn/option-mgmt-2026/pull/35)

---

## [0.9.0] — 2026-05-10

### Added (engine — `engine.flow_score.compute`)

- **`flow_score.compute()`** — V1 LOCKED Flow Score Engine orchestrator per plan v1.2 §9.3 + §9.3a. The single public entry point that synthesizes OI walls, volume imbalances, IV skew, futures basis, put–call ratios, dealer gamma exposure, and pin pressure into a `FlowScore` result. Pure function (per [ADR-0005](./docs/decisions/0005-engine-pure-function-discipline.md)) — no I/O, no clock, no env. Kwargs-only signature: `compute(*, chain_snapshot, spot, expiry_focus, dte_to_nearest_opex=None)`. Twelve-step orchestration: (1) `compute_oi_walls` → (2) `compute_max_pain` → (3) `pcr_volume`/`pcr_oi` → (4) `skew_25d`/`futures_basis` stubs → (5) `compute_dealer_gamma_proxy` → (6) `gamma_score` → (7) 5-component bullish/bearish formulas → (8) `sigmoid_pin` → (9) bias bucketing → (10) decision tree → (11) confidence → (12) `render_explanation`.
- **`flow_score.FlowScore`** — V1 LOCKED contract dataclass per plan §22.2 (frozen). Eleven fields: `score` (signed, `[-100, 100]`), `bullish_score` / `bearish_score` (`[0, 100]`), `bias`, `recommended_action`, `pin_probability` (`[0, 1]`), `gamma_risk` (magnitude, `[0, 1]`), `gamma_sign` (`{-1, 0, +1}`), `confidence` (`[0, 1]`), `explanation` (human-readable string), and `breakdown` (13-key stable dict). Field names and semantics are schema-locked for downstream Postgres / TypeScript codegen / Recommendation Engine `rules.yaml` stability.
- **`flow_score.Bias`** — StrEnum: `BULLISH` / `NEUTRAL` / `BEARISH` / `PIN_RISK`. Wire-stable values. `PIN_RISK` is a first-class fourth state (not a modifier on the other three) because the Recommendation Engine's strategy whitelist for pinned chains is qualitatively different.
- **`flow_score.RecommendedAction`** — StrEnum: `SELL_CALL_AGGRESSIVE` / `SELL_CALL_PARTIAL` / `WAIT` / `BUY_PROTECTION` / `REDUCE_COVERAGE` / `MONITOR`. Six values; first-match-wins from the §9.3a decision tree. `MONITOR` is the catch-all floor.
- **`flow_score.sigmoid_pin()`** — multiplicative pin-probability estimator in `[0, 1]`. Three factors: `dist_factor` (piecewise-linear in spot-to-max-pain percentage; saturates at 1.0 within 2%, decays to 0 at 5%), `opex_factor` (linear to 1.0 at `dte = 0`, 0 beyond 14 trading days; identically 0 if `dte ≥ 30` or `None`), and `oi_factor` (the supplied `oi_concentration_at_max_pain`). Multiplicative-not-additive blend so that any one factor being weak kills the joint signal — a real pin requires *all three* in alignment.
- **`flow_score.skew_25d()`** — **V1 stub**, returns `0.0`. The §9.3a formula treats `skew = avg over expiries of IV(25-Δ put) − IV(25-Δ call)`, but real 25-delta strike identification requires Black–Scholes delta, which lands in M1.6 Greeks. Until then, the stub honors the §9.3a contract's "0 if unavailable" semantics. Signature is the eventual M1.6 signature so callers don't need to change. When M1.6 lands and the body becomes a real Greeks-based implementation, the bullish/bearish formulas naturally pick up the 0.20-weight contribution **without recalibration** of any threshold.
- **`flow_score.futures_basis()`** — **V1 stub**, returns `0.0`. The §9.3a formula uses `basis = (futures - spot) / spot` from the front-month equity-index future. Phase 1 of option-mgmt-2026 does not provision a futures-data service (`apps/api/app/services/futures_service.py` lands in Phase 2). The §9.3a formula explicitly says "0 if futures unavailable." Eagerly validates `spot > 0` at the boundary so callers can't accidentally pass invalid input and get a silent 0 back. When Phase 2 ships the service, replacing the stub adds the 0.15-weight basis contribution.
- **`flow_score.render_explanation()`** — human-readable rationale builder. Returns a 2-to-4 sentence space-joined string. Always present: composite-score sentence and one of four wall sentences. Conditional: dealer-gamma sentence (when `gamma.sign != 0`) and pin sentence (when `pin_probability ≥ 0.6`). The string is **stable across patch bumps** — UI snapshot tests and downstream NLP / disclosure templates may anchor on phrases. Shares `_PIN_EXPLAIN_THRESHOLD = 0.6` with the bias bucketer, so `bias == PIN_RISK` ⇔ pin sentence present (test-asserted invariant).

### Changed

- `engine.flow_score.__init__` re-exports `compute`, `FlowScore`, `Bias`, `RecommendedAction`, `sigmoid_pin`, `skew_25d`, `futures_basis`, `render_explanation` alongside the existing `compute_oi_walls` and `compute_dealer_gamma_proxy`.
- `engine.__init__` re-exports `compute`, `FlowScore`, `Bias`, `RecommendedAction` at the top level (consistent with the M1.4 `MarketStateResult` / `classify` precedent).
- 57 new tests in `packages/engine/tests/test_flow_score_compute.py`: 4 `_volume_shares` tests, 4 `_dist_to_wall_norm` tests, 3 `_oi_concentration_at_max_pain` tests, 9 parametrized bias-bucketing tests, 13 parametrized decision-tree tests, 2 stub tests, 7 `sigmoid_pin` tests, 4 `render_explanation` tests, 7 `compute()` integration tests (shape, balanced→neutral, PCR=1.0 baseline asymmetry, bullish, bearish, pin_risk, confidence scaling, validation), 1 Hypothesis property test asserting bounded outputs across the input space with 100 examples. **96% line coverage** on `engine.flow_score` (the 4 uncovered lines are defensive fallbacks in upstream `oi_walls.py` and `dealer_gamma.py` unreachable when callers pass valid contracts).
- Engine version bumped to **0.9.0** per ADR-0005 (new public function / new schema → minor bump).

### Docs

- New `docs/tutorials/flow-score-engine.md` (~59 KB / 1382 lines) — comprehensive M1.5b tutorial targeting 1st-year MFE students. Same template as the Market State Engine + Scoring Primitives tutorials. Thirteen sections:
  1. **Why a Flow Score Engine?** — role in the architecture, §9.11 wiring matrix, design objectives.
  2. **The V1 LOCKED `FlowScore` contract (§22.2)** — every field explained, gamma sign/magnitude split rationale, breakdown key stability.
  3. **`compute()` — the orchestrator in twelve steps** — dependency DAG, validation, kwargs-only rationale.
  4. **The 5-component bullish + bearish formulas (§9.3a)** — each component walked through with weights, normalizations, design choices (wall distance, volume share, IV skew stub, futures basis stub, PCR asymmetry).
  5. **`sigmoid_pin()`** — three-factor multiplicative blend, design rationale, shared threshold with bias bucketer.
  6. **Bias bucketing** — pin precedence, ±20-point dead zone, why `NEUTRAL` is a first-class enum.
  7. **The §9.3a decision tree** — six rules table, gamma gates, `WAIT` vs `MONITOR`, scope rationale (no `BUY_CALL_*` in V1).
  8. **Confidence and the explanation builder** — OI-based confidence scaling, multiplicative chain implications, explanation stability invariant.
  9. **V1 stubs and forward compatibility** — why `skew_25d` and `futures_basis` return 0; how the formula activates naturally when M1.6 + Phase 2 land.
  10. **End-to-end worked example** — synthetic MSFT-like chain hand-traced through all 12 steps, verified against the rig (`score = +46.2`, `bias = BULLISH`, `action = SELL_CALL_AGGRESSIVE`, `gamma_sign = -1`, `confidence = 0.106`).
  11. **Hands-on exercises** — 9 exercises (symmetric chain, wall sensitivity, pin probability dimensions, `WAIT` vs `MONITOR`, sign-aware gating, confidence floor, skew goes live, explanation invariants, replay regression) with full solutions.
  12. **Further reading** — plan refs, ADRs, sibling tutorials, code paths, external academic references (Sinclair, Garleanu/Pedersen/Poteshman, Ni/Pearson/Poteshman, Bollen/Whaley, SpotGamma white papers).
  13. **Glossary** — every symbol used in the tutorial, every threshold constant.
- `docs/tutorials/README.md` — index updated to add the new tutorial alongside `market-state-engine.md` and `scoring-primitives.md`.

### Plan refs

v1.2 §9.3 (Flow Score Engine spec), §9.3a (V1 LOCKED contract), §22.2 (FlowScore schema reconciliation), §22.13 (breakdown for Confidence Composer), §17 M1.5b (size M acceptance), ADR-0003 (multiplicative Confidence Composer), ADR-0005 (pure-function discipline + SemVer), ADR-0008 (Phase 4 ML node-swap replaces `compute()` body, Phase 1.5 E1 GEX supplies real `GammaWall` records).

PR: [#34](https://github.com/csupenn/option-mgmt-2026/pull/34)

---

## [0.8.0] — 2026-05-10

### Added (engine — `engine.scoring.gamma`)

- **`scoring.gamma_score()`** — composite dealer-gamma exposure score in `[0, 1]` (magnitude) plus a `sign` field in `{-1, 0, +1}` (direction). Per plan v1.2 §9.11.
  - `proxy_magnitude` (weight 0.7) — `|dealer_gamma_proxy| / (spot · 10_000)` clipped to `[0, 1]`.
  - `walls_magnitude` (weight 0.3) — average absolute `|GammaWall.gamma_exposure|` normalized the same way.
  - **No weight redistribution** when `gamma_walls=[]` — `score = proxy_magnitude` directly. Avoids inflating proxy magnitude under V1 calibration; also avoids a discontinuity at the V1 → Phase 1.5 boundary when the E1 GEX module starts producing real walls.
  - `sign` field is strictly the sign of `dealer_gamma_proxy`: `+1` = dampener (dealer net long gamma), `-1` = amplifier (dealer net short gamma), `0` = neutral. The split keeps the Confidence Composer's positive-weights math (per §22.13) intact while letting direction-aware consumers (Flow Score Engine's `gamma_risk`, recommendation rules) read both pieces.
- **`scoring.GammaWall`** — frozen dataclass holding a strike-level gamma-exposure datum. Produced by the Phase 1.5 E1 GEX module (per [ADR-0008](./docs/decisions/0008-enhancement-adoption-roadmap.md)); V1 callers pass `gamma_walls=[]` and `gamma_score` degrades gracefully.
- **`scoring.GammaScoreResult`** — frozen dataclass: `score: float ∈ [0, 1]` + `sign: int ∈ {-1, 0, +1}` + `breakdown: dict[str, float]` with keys `proxy_magnitude` and `walls_magnitude`.

### Changed

- `engine.__init__` re-exports `gamma_score`, `GammaScoreResult`, `GammaWall`.
- `engine.scoring.__init__` re-exports the new symbols and updates the docstring (the wiring matrix now has all four scoring primitives shipped).
- 15 new tests in `packages/engine/tests/test_scoring_gamma.py`: 10 named hand-computed references (neutral / amplifier / dampener / saturation / walls-blend / sign-symmetry / multi-wall averaging / zero-proxy-with-walls / clipping / breakdown-key stability), 2 validation tests, 3 Hypothesis property tests asserting `score ∈ [0, 1]`, sign symmetry under proxy negation, and sign matching the proxy's sign.
- **100% line coverage** maintained on `engine.scoring` (CI step `Coverage check (engine.scoring 100%)` from §9.11 still green).

### Docs

- `docs/tutorials/scoring-primitives.md` extended with a new **§6 `gamma_score()` — dealer-gamma exposure**, covering: what it measures, inputs (`GammaWall` defined here), formula (with the `walls=[]` no-redistribution case), the score/sign split design choice, edge cases, V1 calibration caveat, worked example, code reference. Subsequent sections renumbered (§7 design philosophy, §8 worked example, §9 exercises, §10 further reading, §11 glossary). Updated:
  - Header (title now lists all 4 primitives; engine version coverage notes `0.5.0` AND `0.8.0`)
  - §1.1 (mentions `gamma_score`)
  - §1.2 (wiring matrix narrative — "all four are now on `main`")
  - §7.4 (test counts now include 15 gamma tests; 173 scoring tests overall)
  - §8 end-to-end worked example: extended with a `gamma_score` call against a synthetic `-200_000` proxy, hand-traced to `score=0.20, sign=-1`
  - Exercise 8 replaced (was "design a 4th scoring fn"); now two new exercises on sign/magnitude split and walls degradation, with detailed solutions
  - §10 Further reading: links to `test_scoring_gamma.py`; test count updated to 74 across scoring
  - §11 Glossary: adds `Π`, `D`, `𝒲`, `sign`

### Plan refs

v1.2 §9.11 (Scoring Functions Module — `gamma_score` signature & wiring), §17 M1.5a (size S, 100% coverage acceptance), §22.5 (clip01 reuse), §22.13 (breakdown for Confidence Composer), ADR-0008 (Phase 1.5 E1 GEX replaces the V1 proxy + introduces real `GammaWall` producers).

PR: [#33](https://github.com/csupenn/option-mgmt-2026/pull/33)

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
