# Enhancement Spec — Feasibility Assessment & Adoption Decisions

**Source spec**: [`04-msft-engine-enhancement-spec-0509.md`](./04-msft-engine-enhancement-spec-0509.md) (Claude Sonnet 4.6, 2026-05-09)
**Assessor**: Developer agent, post-Phase-0 (main at `fa68a4c`)
**Date**: 2026-05-10
**Status**: Accepted — see [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md)

---

## Why this document exists

The user uploaded a 1,434-line enhancement spec proposing nine new analytical modules (E1–E9). Their direction was clear: *"assess feasibility and priorities first before adopting."*

This document is that assessment. It walks each enhancement against four hard tests and lands on an adopt/defer/reject decision. The canonical decision record is [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md); this document is the *showing of work* that ADR-0008 references.

## The four tests applied to every enhancement

1. **Plan-v1.2 conflict?** Does it change a locked contract (FlowScore V1, Confidence Composer math, Regime taxonomy) or a shipped ADR? If yes, the conflict needs its own follow-up ADR before the enhancement can land.
2. **Engineering principles?** Engine purity (ADR-0005), simplicity, contract-first. Does adoption add complexity without removing existing complexity, or does it pay for itself?
3. **User value vs. user risk?** Helen is the primary persona (long-term MSFT holder, LTCG-aware). Does the enhancement materially improve her decisions, or does it add noise/cognitive load? Does it carry **misleading-output risk** (backtests, score composites) under the educational-disclaimer framework?
4. **Data dependency?** What provider does it need? yfinance (free, unreliable), Tradier (chain greeks), Polygon (history)? Phase 1 ships with CSV-only; reliable IV/greek history lands in Phase 2.

## Summary table

| # | Enhancement | Decision | Phase | Why |
|---|---|---|---|---|
| **E1** | GEX Module (gamma exposure, flip, walls) | **Adopt** | **1.5** | Real upgrade over the `dealer_gamma_proxy` placeholder; foundational for E3/E6/E9. Requires a follow-up ADR for the FlowScore V1 contract change. |
| **E2** | Vol Surface & Skew Analytics | **Adopt** | **2** | Term structure + skew is directly actionable; needs reliable IV history (Phase 2 data providers). |
| **E3** | PnL Surface & Greeks Engine | **Adopt — partial** | **2** | Ship `pnl_by_price` + `scenario_table` + 2D chart in Phase 2. Defer 3D PnL surface to Phase 3 pending evidence of user need. |
| **E4** | Earnings Expectation Gap Score | **Adopt — display-only** | **2–3** | Adopt as a *displayed metric* on the Today screen during event windows. **Do NOT fold into Confidence Composer math** until V2 weights calibration; that's an ADR-0003 change. |
| **E5** | Vol Premium Tracker (IV − HV) | **Adopt** | **2** (with E2) | Bundle with E2 — same data dep, complementary signal. |
| **E6** | Multi-Expiry Strategy View | **Defer** | **3+** | Adds significant complexity to Strike Selector, Collar Builder, and Today UI. Validate single-expiry recommendation flow first; revisit only if user requests it. |
| **E7** | Historical Earnings Backtest | **Defer** | **3+** | High misleading-output risk (look-ahead bias, fill assumptions, slippage). Worth doing eventually, behind a feature flag, with hardened disclaimers — but not until Phase 2 data providers + Phase 1 outcome tracker reveal what backtest framing best supports learning. |
| **E8** | Dividend-Aware Pricing | **Adopt** | **2–3** | Real correctness fix; the hardcoded `q=0.0075` is wrong near ex-dividend dates and that distortion compounds in early-assignment math. |
| **E9** | Assignment Risk Module | **Adopt** | **3** | Real gap for tax-sensitive users (Helen's profile). Depends on E8 for the dividend signal and on Phase 2's collar builder + recommendation engine. |

**Adopted: 6 (one partial, one display-only).** **Deferred: 2.** **Rejected: 0.**

---

## Per-enhancement assessment

### E1 — GEX Module (Gamma Exposure)

**Decision: Adopt in Phase 1.5.**

**Why it's the right call now.** The base plan's Flow Score uses a `dealer_gamma_proxy` (signed sum of γ × OI × distance from spot) with a normalized `gamma_score`. This is a heuristic placeholder. It produces a directional bias but cannot answer the three questions a real GEX implementation answers:
- "At what level does dealer hedging flip from stabilizing to amplifying?" (gamma flip)
- "Where is the largest OI-weighted gamma concentration above and below spot?" (call wall / put wall)
- "Is the wall meaningfully close to current price action?" (gex_em_ratio)

For Helen specifically, placing a covered-call short leg inside a GEX call wall means selling into structural buying pressure — exactly what a long-term holder doesn't want. The base plan can't see this; E1 lights it up.

**Where it bites.** The spec proposes *replacing* `dealer_gamma_proxy` in the FlowScore V1 contract — that contract is locked in plan v1.2 §22.2 / C2. Replacing a contract field is a real change. We need an ADR amending the FlowScore V1 contract before the integration commits, not after.

**What I'd lock down before the work starts.**
- Open Question #1 in §14 of the spec ("expiry weighting") — pick OI-weighted, document the rationale, move on.
- Open Question #2 ("flip stability") — current flip + 5-day moving average, surface both. The MA dampens daily OI churn for the Today-screen badge.
- gamma source quality flag (`chain_provided` vs. `bs_estimated`) ships as a first-class field in `GexByStrike` from day one — don't hide the heuristic.

**Phasing.** Phase 1.5 (immediately after Phase 1 ships M1.7 Today screen). E1 needs the chain ingestion path to exist (Phase 1 M1.6 `/engine/daily-plan` reads chain) but doesn't need fully reliable IV history (Phase 2). Tradier provides chain gamma; for yfinance fallback, the BS-computed gamma path is acceptable with the source-quality flag set.

**ADRs / docs implied.**
1. Follow-up ADR amending FlowScore V1 contract (`dealer_gamma_proxy` → `gex_context: GexResult | None`).
2. Update `docs/architecture.md` layer cake to include `engine.gex` as a Layer 1 scoring primitive.
3. Update `docs/ssot-constants-map.md` to register `packages/engine/engine/gex/` constants.

### E2 — Vol Surface & Skew Analytics

**Decision: Adopt in Phase 2.**

**Why.** Collapsing the vol surface to `atm_iv_30d` loses three actionable signals: term-structure slope (inverted = sell near-term now), 25-delta skew (puts pricing more fear than calls), and the IV smile shape (does the GEX wall coincide with a vol kink?). For a premium-selling strategy on a long-term holding, these are first-order — not nice-to-haves.

**Why Phase 2, not 1.5.** The spec correctly flags that yfinance IV history is unreliable. Building term-structure analysis on bad data produces bad decisions confidently. Tradier/Polygon integration is on the Phase 2 data-provider milestone. E2 lands when it does.

**What survives the wait.** E5 (Vol Premium Tracker) is bundled with E2 — same data dependency, complementary output. Ship them together.

### E3 — PnL Surface & Greeks Engine

**Decision: Adopt partially. Phase 2: 2D PnL + scenario table. Phase 3: 3D surface (only if user evidence demands it).**

**Why the split.** The scenario table answers Helen's actual questions ("what if earnings beat +6% with IV crush?") in a glanceable, accessible format. The 2D PnL-by-price chart with terminal vs. theoretical lines covers the next layer of nuance. The 3D PnL surface (price × IV × DTE → P&L) is genuinely informative but is also (a) a big UI lift (Plotly Surface3D), (b) hard to read on mobile, and (c) often confusing to non-options-fluent users — the very audience the disclaimer framework exists to protect.

**What I'd build first.**
- `pnl_by_price()` (100-point grid).
- `scenario_table()` with the 7-scenario MSFT default set (good defaults; ship those).
- `PayoffPreviewStrip` on the Today screen showing: max gain, breakeven(s), max loss, post-earnings IV-crush P&L. One line, no chart.
- `/payoff` drill-down with the 2D chart + scenario table.

**What waits.**
- Plotly 3D surface — until we see Today-screen users actually clicking through to the drill-down and asking for IV-axis exploration.

### E4 — Earnings Expectation Gap Score

**Decision: Adopt as a display-only metric in Phase 2–3. Do NOT fold into Confidence Composer math.**

**Why caution.** E4 is a five-input composite: `iv_rank` × `vol_premium` × `runup_30d` × `call_volume_ratio` × `put_call_ratio`. Each input has its own calibration error. Multiplying them produces a signal that *looks* precise but compounds noise. The spec proposes injecting this into the `event_risk_penalty` of the Confidence Composer:

> `event_risk_penalty = max(event_score, earnings_gap.score)`

That's an ADR-0003 change (Confidence Composer is locked at multiplicative penalties with calibrated weights). It can't go in lightly.

**What I'd ship instead.** During event windows (`days_to_next_event ≤ 14` and `next_event_kind == "earnings"`), surface the score on the Today screen as a contextual metric — "Earnings expectation gap: 0.71 (potential vol overpricing)". Helen sees it; the engine doesn't act on it. When V2 weights calibration arrives (with real outcome data from the M0.4 Outcome Tracker), revisit folding it in.

**Caveat language.** The score is a heuristic, not a probability. The interpretation copy must say so explicitly.

### E5 — Realized vs. Implied Vol Premium Tracker

**Decision: Adopt with E2 in Phase 2.**

**Why.** This is the actual edge a premium-seller harvests. Quantifying "what percentile is today's IV − HV vs. trailing 12 months" lets Helen distinguish "rich premium, sell now" from "thin premium, wait" — the question covered calls turn on. Small module, high leverage.

**Bundled with E2** because the data dep is the same (reliable IV history) and the integration point is the same (`iv_score`).

### E6 — Multi-Expiry Strategy View

**Decision: Defer to Phase 3+.**

**Why defer.** The spec proposes adding a `recommended_secondary` expiry to enable staggered collars (sell 30d calls now, also sell 60d calls). That's three layers of additional complexity:
1. **Engine API** — Strike Selector and Collar Builder both currently optimize for a single `profile.dte_band_days` window. Adding a secondary expiry changes the contract.
2. **UI cognitive load** — Today screen currently shows one decision. Two recommended structures asks Helen to compare and choose, raising the complexity floor of the product.
3. **Calibration** — staggered coverage changes max-coverage math, premium math, and event-exposure math. New tests, new edge cases.

I haven't seen demand for this. Helen's persona is "single decision per day". Get single-expiry working, validate it, *then* revisit. If validation reveals "users keep manually creating staggered positions", that's the signal to build E6.

### E7 — Historical Earnings Backtest

**Decision: Defer to Phase 3+. Re-evaluate after Phase 2 data providers ship.**

**The asymmetric risk.** Backtests look authoritative. The disclaimer block in §7.2 is excellent but it doesn't undo the cognitive anchor that "this strategy worked 7 of 10 times in the past." Users will weight it. They will weight it *more* because of the win-rate framing. For an *educational* product, that's the wrong shape of nudge.

**The implementation gap.** Even with the spec's clear framing ("simulation, not ML training"), historical chain quality is poor without paid data. yfinance has approximate IV but missing greek snapshots. Reconstructing what the engine *would* have recommended at each pre-earnings date requires re-running the engine on partial inputs — that's its own correctness surface.

**What I'd require before starting.**
- Phase 1 outcome-tracker data (lots of users → forward-looking patterns).
- Phase 2 data providers (Polygon historical chains).
- An ADR explicitly defining the backtest's UI framing — what's surfaced, what's hidden, what disclaimers gate access.

Until then, the M0.4 Outcome Tracker is the better teacher: it surfaces *real* outcomes from *real* decisions, not hypotheticals.

### E8 — Dividend-Aware Pricing

**Decision: Adopt in Phase 2–3.**

**Why.** The plan's `q = 0.0075` is wrong. MSFT's dividend is discrete and quarterly; the days before an ex-dividend date carry meaningful early-assignment risk on short calls that a flat continuous-yield model can't see. The Merton-with-discrete-dividend approach in §8.2 is well-understood and correct for this problem domain.

**Phasing.** Land it after the core engines work with the placeholder, but before E9 (Assignment Risk) — E9 depends on the dividend context to compute early-assignment incentive.

### E9 — Assignment Risk Module

**Decision: Adopt in Phase 3.**

**Why.** Helen has 5,000 MSFT shares with cost basis. Early assignment of a short call delivers shares away — potentially triggering large LTCG events at the wrong moment, or, worse, bumping short-term lots that should have been preserved for LTCG. The lot-level analysis is in scope for the engine; lot-selection is the broker's choice (and the user's, via lot-selection tools). E9 frames the analysis correctly — provide options, never instruct.

**Dependencies.** Needs E8 (dividend context) for the early-assignment-incentive math, and needs the M1.x Collar Builder + Recommendation Engine to be live so there are short calls to assess.

---

## Cross-cutting concerns

### Engine purity (ADR-0005)

Every adopted enhancement is implementable as a pure function operating on `EngineInputs` (chain, IV history, HV history, events, profile, etc.). None require I/O, network, or DB access from inside the engine. That's preserved.

E7 (Backtest) is the closest call — it ingests historical data — but the spec correctly frames the backtest engine as orchestration around pure-function `simulate_single_event` calls. The data ingestion lives outside the engine boundary.

### FlowScore V1 contract (plan v1.2 §22.2 / C2)

E1 modifies it. Adopting E1 requires a follow-up ADR amending the contract. That ADR is a deliverable of the Phase 1.5 E1 milestone, not a prerequisite for it — but it must land in the same PR that flips the field name.

### Confidence Composer (ADR-0003)

E1's `gex_alignment` enhancement to `structure_alignment` is additive and weighted (0.6 × base + 0.4 × gex). That's a refinement, not a contract change.

E4's proposed `event_risk_penalty = max(event_score, earnings_gap.score)` IS a contract change. **We're not doing that** — see E4 decision above.

### Regime taxonomy (ADR-0002)

Untouched by every enhancement. The 6 locked regimes remain canonical.

### Schema additions

From the spec's §10.3:
- E1 `gex_snapshots` — additive, no migration breakage. Optional persistence.
- E4 `market_states.earnings_gap_score` + `earnings_gap_context` — column additions (compatible with existing `0001_init`).
- E7 `backtest_runs` — new table, additive.
- E8 `dividend_schedules` — new table, additive.

All additive. None require `0001_init` rewrite. Each migration goes through its own revision file (per the discipline established in M0.7's UTC-anchoring fix commit message).

### Disclaimer framework (ADR-0004 + plan §15)

Every new analytical output surfaces with the language guard: no "buy", "sell", "recommend". The spec acknowledges this in §13.

Two outputs need extra care:
- `EarningsGapScore.interpretation` — composite metric; copy must say "score is heuristic, not a probability".
- `BacktestSummary.disclaimer` — non-optional, enforced by Pydantic validator. The `data_quality_caveat` text is mandatory.

---

## Implementation roadmap (revised)

This roadmap supersedes §11 of the source spec, applying the adoption decisions above.

### Phase 1 (current) — engine MVP

No enhancement work. Ship M1.1–M1.7 per plan v1.2 §17. Single-expiry, single decision, Today screen renders.

### Phase 1.5 — GEX (E1)

Single milestone batch, ~2 weeks:
- Follow-up ADR: FlowScore V1 contract amendment (replace `dealer_gamma_proxy` with `gex_context`).
- `packages/engine/engine/gex/` module with `compute_gex()` + `GexResult`.
- Integration into Flow Score, Strike Selector, Collar Builder, Recommendation rules.
- `POST /engine/gex` endpoint.
- `DailyDecision.gex_context` + Today screen `GexContextStrip`.
- `/gex` drill-down page.

### Phase 2 — Vol surface, PnL, earnings gap, vol premium (E2/E3 partial/E4 display/E5)

Aligns with Phase 2 of the base plan (data providers + drill-downs):
- E2 vol surface + skew + term structure.
- E5 vol premium tracker (bundled with E2).
- E3 partial: `pnl_by_price()` + `scenario_table()` + 2D drill-down.
- E4 display-only: `EarningsGapScore` surfaced when `event_in_14d`.
- E8 dividend-aware pricing (preferably here so Phase 3's E9 has it).

### Phase 3 — Assignment risk + 3D PnL (E9 + E3 remainder)

After E8 is live and the recommendation engine has matured:
- E9 Assignment Risk Module.
- E3 Phase 3 remainder: Plotly Surface3D drill-down (only if user evidence supports it).

### Deferred (re-evaluate post-Phase-3)

- E6 Multi-Expiry — re-evaluate after single-expiry has produced 3+ months of outcome data.
- E7 Backtest — re-evaluate after Phase 2 data providers + Phase 1 outcome tracker.

---

## Open questions resolved (vs. §14 of source spec)

| # | Source question | Decision |
|---|---|---|
| 1 | GEX expiry weighting | OI-weighted across `expiry_focus`. Document rationale in the Phase 1.5 ADR. |
| 2 | Gamma flip stability | Surface both *current* and *5-day MA*. Today-screen strip uses MA; drill-down shows both. |
| 3 | Vol surface IV source warning | Yes — surface a `data_quality: Literal["chain_native", "imputed", "estimated"]` flag on every `VolSurfaceResult`. |
| 4 | Backtest exit rule | Deferred with E7. |
| 5 | Earnings gap when no event | No — score only computes during event windows. Outside event windows, the field is `None`. |
| 6 | Assignment risk lot disclosure | Show *which lots might be affected* with explicit "lot selection is your broker's decision" framing. |
| 7 | Multi-expiry stagger phasing | Deferred to post-Phase-3 (E6 decision). |
| 8 | PnL surface grid cap | 50×20 default; 100×40 hard cap; 422 above. Document in OpenAPI. |

---

## What's NOT in scope

Per the spec's own framing (§0), this assessment also doesn't address:
- ML upgrades (Phase 4 of base plan).
- Brokerage integration.
- Multi-ticker UI.

Those remain governed by the base plan v1.2.

## See also

- [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) — the canonical adoption decisions.
- [`04-msft-engine-enhancement-spec-0509.md`](./04-msft-engine-enhancement-spec-0509.md) — the source spec (preserved verbatim).
- [`docs/engineering-principles.md`](../engineering-principles.md) — the principles every adoption is checked against.
- [`docs/architecture.md`](../architecture.md) — the layer cake every enhancement plugs into.
