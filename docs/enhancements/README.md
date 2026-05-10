# Enhancement specs

Post-base-plan analytical enhancements proposed beyond the v1.2 plan. Each spec arrives as a separate document, gets a feasibility assessment, and lands an adoption decision recorded in `docs/decisions/`. The spec itself is preserved verbatim alongside the assessment, so future contributors can read the original proposal and the decision rationale side-by-side.

## Adoption status — current

The current canonical adoption record is [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md). Status reflects the post-Phase-0 main (`fa68a4c`) plus this directory's contents.

| # | Title | Status | Phase | Source spec | Decision record |
|---|---|---|---|---|---|
| E1 | GEX Module (gamma exposure, flip, walls) | Adopted | **1.5** | [`04-...spec-0509.md` §1](./04-msft-engine-enhancement-spec-0509.md) | ADR-0008 |
| E2 | Vol Surface & Skew Analytics | Adopted | **2** | §2 | ADR-0008 |
| E3 | PnL Surface & Greeks Engine | Adopted (partial — 3D deferred) | **2** (2D); **3** (3D, conditional) | §3 | ADR-0008 |
| E4 | Earnings Expectation Gap Score | Adopted (display-only — not folded into Confidence math) | **2–3** | §4 | ADR-0008 |
| E5 | Vol Premium Tracker (IV − HV) | Adopted (bundled with E2) | **2** | §5 | ADR-0008 |
| E6 | Multi-Expiry Strategy View | Deferred (re-evaluate post-Phase-3) | — | §6 | ADR-0008 |
| E7 | Historical Earnings Backtest | Deferred (re-evaluate post-Phase-3) | — | §7 | ADR-0008 |
| E8 | Dividend-Aware Pricing | Adopted | **2–3** | §8 | ADR-0008 |
| E9 | Assignment Risk Module | Adopted | **3** | §9 | ADR-0008 |

## How this directory is organized

```
docs/enhancements/
├── README.md                                       — this file (the index)
├── 04-msft-engine-enhancement-spec-0509.md        — source spec, verbatim (1,434 lines)
├── 0001-assessment-and-adoption-decisions.md      — feasibility assessment + per-enhancement reasoning
└── (future) E1-design.md, E2-design.md, ...       — per-enhancement design notes, written when work starts
```

## Conventions for future enhancement work

1. **Source-spec-as-uploaded is preserved.** When a new spec arrives, drop it here verbatim with its original filename. Don't summarize, don't condense. Future contributors need the original framing.
2. **Assessments live next to specs.** Per-spec assessment is a new numbered file (`0002-...md`, etc.). It does the four-test check (plan-v1.2 conflict, engineering principles, value vs. risk, data dep) per item and lands an adopt/defer/reject recommendation. The summary table is the contract; the prose is the reasoning.
3. **Decisions go in ADRs.** The actual adopt/defer/reject + phasing lives in `docs/decisions/0NNN-*.md`. The ADR is one page; it references the assessment for analysis. ADR is canonical; assessment is showing-of-work.
4. **Per-enhancement design docs are written when the work starts.** Don't write `E1-design.md` until the Phase 1.5 milestone is opened — premature design docs go stale.
5. **Implementation lives elsewhere.** Source code and tests follow the milestone branch + PR convention. Cross-reference the milestone PR back to the design doc and the ADR.

## See also

- [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) — canonical adoption decisions for E1–E9.
- [`docs/decisions/`](../decisions/) — full ADR index.
- [`docs/architecture.md`](../architecture.md) — layer cake every enhancement plugs into.
- [`docs/engineering-principles.md`](../engineering-principles.md) — principles every adoption is checked against.
- [`docs/ssot-constants-map.md`](../ssot-constants-map.md) — register new constants from adopted enhancements here.
