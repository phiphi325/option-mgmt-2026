# ADR-0001: Engine-first architecture

**Status**: Accepted
**Date**: 2026-04-29
**Plan ref**: v1.2 §1 (Product Brief) + §5 (System Architecture) + §3 (Phase 1 Hard Contract)
**Related code**: `packages/engine/`, `apps/api/app/services/`, `apps/web/app/today/`

## Context

The original v1.0 plan framed the product as an "MSFT Option Risk Management Dashboard" — a Bloomberg-lite analytics tool. Mid-planning review reframed this as a **decision engine** that answers a single question: *"What should I do today?"*

The architectural implication: the product IS the engine. Dashboards (Chain, IV Profile, Max Pain, Payoff) are drill-downs that explain decisions, not the primary surface.

## Decision

Adopt an engine-first layer cake:

1. **Top layer**: Today screen — single `DailyDecision` card.
2. **Primary API**: `/engine/*` namespace.
3. **Core**: `packages/engine` — pure-function Python; FIVE engines (Market State, Flow Score, Strike Selector, Recommendation, Master Decision) + ONE specialty engine (Collar Builder, added v1.1).
4. **Cross-cutting modules**: Confidence Composer, Execution Feasibility, User Strategy Profile, Outcome Tracker.
5. **Secondary API**: `/data/*` for drill-downs.
6. **Bottom**: Postgres + provider abstraction.

The **Phase 1 Hard Contract** (plan §3) explicitly excludes drill-down dashboards from the MVP. PR template asks: *"does this advance the Today screen rendering a coherent DailyDecision?"*

The engine is **pure-function Python with no I/O, no DB, no network**. ML upgrades in Phase 4 replace specific nodes (regime classifier, flow score model, confidence weight calibration) without changing this invariant.

## Consequences

**Positive**

- Clear product positioning: *"decision engine, not dashboard"*.
- Engine pure-function discipline → testable, ML-upgradeable nodes.
- Single output (`DailyDecision`) keeps the API surface focused.
- Auditable: every persisted decision carries `inputs_hash`, `engine_version`, `weights_version` for exact replay.

**Negative**

- More upfront design work (5 engines + cross-cutting modules) before any UI is shippable.
- Phase 1 takes 5 weeks vs. a quick dashboard MVP.

**Neutral**

- Drill-down screens deferred to Phase 2. They exist as planned components but don't ship in MVP.

## Alternatives considered

1. **Dashboard-first** (original v1.0 framing) — rejected: produces a Bloomberg-lite tool that doesn't differentiate from existing options analytics platforms.
2. **Monolithic recommendation engine** (no separation between Market State, Flow Score, etc.) — rejected: blocks ML-node-by-node upgrades in Phase 4 and is harder to test with golden fixtures.
3. **No Today screen, API-only product** — rejected: the user is a long-term holder who wants a daily check-in, not a CLI consumer.

## References

- Plan v1.2 §1 — Product Brief
- Plan v1.2 §5 — System Architecture (layer cake)
- Plan v1.2 §3 — Phase 1 Hard Contract (anti-creep guard)
- Original engine-first reframe: Hyperagent thread `cmokf2twq0gsv06adlij0glqs`, planning round 2.
