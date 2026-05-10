# ADR-0008: Enhancement-spec adoption roadmap (E1–E9)

**Status**: Accepted
**Date**: 2026-05-10
**Plan ref**: addendum to v1.2; per-enhancement decisions in [`docs/enhancements/0001-assessment-and-adoption-decisions.md`](../enhancements/0001-assessment-and-adoption-decisions.md)
**Related code**: `packages/engine/engine/{gex,vol_surface,payoff,scoring,multi_expiry,backtest,assignment}/` (future), `apps/api/app/routers/engine.py` (future)

## Context

A 1,434-line enhancement spec (`04-msft-engine-enhancement-spec-0509.md`) was authored by Claude Sonnet 4.6 and uploaded for review. It proposes nine analytical modules (E1–E9) with priorities, integration points, schema additions, API endpoints, and UI components.

The user's direction: *"assess feasibility and priorities first before adopting."*

The full assessment lives at [`docs/enhancements/0001-assessment-and-adoption-decisions.md`](../enhancements/0001-assessment-and-adoption-decisions.md). That document walks each enhancement against four tests (plan-v1.2 conflict, engineering principles, value vs. risk, data dep) and lands the per-enhancement decision. This ADR captures only the binary outcomes and their phasing — the canonical decision record.

## Decision

Adopt six enhancements (one partially, one display-only). Defer two. Reject none.

| # | Enhancement | Decision | Phase |
|---|---|---|---|
| E1 | GEX Module — gamma exposure, flip, walls | **Adopt** | **Phase 1.5** |
| E2 | Vol Surface & Skew Analytics | **Adopt** | **Phase 2** |
| E3 | PnL Surface & Greeks Engine | **Adopt — partial** | **Phase 2** (2D + scenarios); Phase 3 (3D, conditional on user evidence) |
| E4 | Earnings Expectation Gap Score | **Adopt — display-only** | **Phase 2–3** (do NOT fold into Confidence Composer math) |
| E5 | Vol Premium Tracker (IV − HV) | **Adopt** | **Phase 2** (bundled with E2) |
| E6 | Multi-Expiry Strategy View | **Defer** | **Phase 3+** (re-evaluate after single-expiry produces outcome data) |
| E7 | Historical Earnings Backtest | **Defer** | **Phase 3+** (re-evaluate after Phase 2 data providers + Phase 1 Outcome Tracker) |
| E8 | Dividend-Aware Pricing | **Adopt** | **Phase 2–3** |
| E9 | Assignment Risk Module | **Adopt** | **Phase 3** (depends on E8) |

### Implementation gate per adopted enhancement

1. **E1 requires a follow-up ADR** amending the FlowScore V1 contract (plan v1.2 §22.2 / C2). The contract currently locks `dealer_gamma_proxy`; E1 replaces it with `gex_context: GexResult | None`. The ADR ships in the same PR as the integration.

2. **E4 stays display-only** until V2 weights calibration. Folding `earnings_gap.score` into the Confidence Composer (`event_risk_penalty = max(event_score, earnings_gap.score)`, as the source spec proposes) is an ADR-0003 amendment we're explicitly not making in V1. Helen sees the score; the engine doesn't act on it.

3. **E3's 3D Plotly surface waits for evidence** of user need — sourced from Phase 2 drill-down click-through and outcome-tracker patterns. The 2D `PnLByPriceChart` + `ScenarioTable` ship in Phase 2 and cover the scenario-question surface for the persona.

4. **E6 and E7** are not rejected — they're parked. Both are re-evaluated after Phase 3, conditional on demand signals (E6) or data-provider maturity + outcome-tracker coverage (E7).

### Phasing summary

| Phase | Adopted enhancement work |
|---|---|
| **Phase 1** (current) | None — ship M1.1–M1.7 engine MVP per plan v1.2 §17. |
| **Phase 1.5** (~2 weeks after Phase 1) | E1 (GEX) — engine module, integrations, endpoint, drill-down, follow-up ADR. |
| **Phase 2** | E2 (vol surface) + E5 (vol premium, bundled) + E3 partial (2D PnL + scenarios) + E4 display-only + E8 (dividend-aware). |
| **Phase 3** | E9 (assignment risk) + E3 remainder (3D, conditional). |
| **Deferred** | E6, E7. |

## Consequences

### Positive

- Phase 1 stays focused. No premature integration of nine modules into an unbuilt engine.
- E1's gamma-flip and call/put walls give the recommendation engine real GEX context — the placeholder `dealer_gamma_proxy` was a known weakness.
- E2/E5 close the IV surface gap that the scalar `atm_iv_30d` left open.
- E3's scenario table answers Helen's actual decision questions ("if earnings beat +6% with IV crush, where do I land?") in a glanceable, accessible format.
- E8/E9 give tax-sensitive users (Helen's persona) the lot-level + assignment-risk visibility the long-term-holder use case demands.
- All adopted enhancements are pure-function-implementable and respect ADR-0005 engine purity.
- All schema additions are additive — no migration breakage on top of `0001_init`.

### Negative

- E1 requires an ADR amending plan v1.2 §22.2 / C2 — real coordination cost. Mitigation: ADR ships in the same PR as the contract change.
- Deferring E6 means staggered collars are a manual user decision until Phase 3+. Acceptable for V1 (Helen's persona is "single decision per day"; staggering is a power-user feature).
- Deferring E7 means no historical credibility check at launch. Mitigated by the M0.4 Outcome Tracker, which surfaces real (not simulated) outcomes from the user's own decisions.
- Phase 2 scope expands relative to the original base-plan §17 sizing. Mitigation: Phase 2 already plans data-provider + drill-downs; E2/E3/E5/E4/E8 land in that natural envelope.

### Neutral

- The deferred enhancements (E6, E7) remain in the spec for future reference; the source document is preserved verbatim at `docs/enhancements/04-msft-engine-enhancement-spec-0509.md`.
- The 3D PnL surface (E3 remainder) is a UI investment, not engine work — easier to evaluate later when the 2D chart usage data exists.

## Alternatives considered

1. **Adopt all nine enhancements as-specified.** Rejected. The spec is well-thought-through but several pieces (E4 into Confidence math, E6, E7, E3 3D) carry real downside at V1 scale. Adopting everything compounds calibration error (E4) and misleading-output risk (E7) faster than the disclaimer framework can absorb.

2. **Reject all and finish base-plan v1.2 first.** Rejected. E1 (GEX) and E5 (vol premium) close known analytical gaps in the base plan itself — postponing them would mean shipping a Phase 1 engine with weaker primitives than necessary. E8 fixes a real correctness bug (hardcoded `q`).

3. **Adopt E1 + E2 + E3 only (a "minimum viable enhancement" set).** Considered but rejected. E5 is too small and too useful to defer (S effort, bundles with E2). E8 is a correctness fix. E9 is a real gap for tax-sensitive users that Helen's persona surfaces directly. Cutting them produces a smaller but lopsided enhancement set.

4. **Adopt every enhancement as display-only (no engine math changes).** Rejected. E1's whole point is to fix `dealer_gamma_proxy`; making it display-only leaves the existing weak primitive in place. E8 needs to flow into pricing math to be useful. The "display-only" treatment is reserved for E4 specifically because composite-score-into-Confidence-math is the highest-risk integration in the spec.

## References

- [`docs/enhancements/0001-assessment-and-adoption-decisions.md`](../enhancements/0001-assessment-and-adoption-decisions.md) — full assessment.
- [`docs/enhancements/04-msft-engine-enhancement-spec-0509.md`](../enhancements/04-msft-engine-enhancement-spec-0509.md) — source spec (preserved verbatim).
- [ADR-0001](./0001-engine-first-architecture.md) — engine-first architecture (every adopted enhancement plugs into Layer 1 or Layer 2).
- [ADR-0002](./0002-regime-taxonomy.md) — regime taxonomy (untouched by every enhancement).
- [ADR-0003](./0003-confidence-composer-multiplicative.md) — Confidence Composer math (E4 explicitly does NOT amend this ADR).
- [ADR-0005](./0005-engine-pure-function-discipline.md) — engine purity (every adoption preserved).
- Plan v1.2 §22.2 / C2 — FlowScore V1 contract (E1 amends this; follow-up ADR required).
