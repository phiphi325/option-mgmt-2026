# Yearline statistical-context integration — source analysis

Verbatim analysis backing the adoption of **yearline-universe** as an external statistical-context
provider for option-mgmt-2026. The adopt/defer decision is recorded in
[ADR-0009](../../decisions/0009-adopt-yearline-statistical-context-provider.md); the consumer-side
feasibility assessment (the four-test check + recommendation) is
[`../0002-yearline-context-assessment.md`](../0002-yearline-context-assessment.md).

> Educational research only; not financial advice. Neither system executes. Every yearline surface
> carries `must_not_auto_execute: true` and is **gated** — consume `p_retry[h]` only where
> `gate_passed[h]`, and `p_success` only where `success_gate_passed`.

## What yearline is (one line)

A ticker-agnostic, headless **nightly batch** that scores the MA250 "yearline" repair/trend situation
per ticker and emits a small, versioned `YearlineContext` value object (a persisted JSON artifact).
option-mgmt ingests that artifact in its jobs layer, hydrates a Pydantic value object, and lets the
**pure engine** optionally consume it — **only where its trust gate passes**.

## Contents

| File | Role |
|---|---|
| [`assessment.md`](./assessment.md) | Deep assessment: what option-mgmt is, what yearline emits, what yearline adds, the boundary analysis (why not a library import), contract/determinism/gate-respect, fit/risk scorecard. |
| [`integration_design_and_plan.md`](./integration_design_and_plan.md) | The `YearlineContext` contract, ingestion/persistence, the replay-hash extension, three coupling options (A engine-input / B market-state / C read-only panel), the OM-Y0…Y5 roadmap, acceptance gates, risks. |
| [`two_repo_strategy_and_deployment.md`](./two_repo_strategy_and_deployment.md) | Two-repo topology (artifact-handoff vs package-dep vs monorepo vs submodule), deployment, and the "one app, yearline as an embedded evidence panel" UX decision. |
| [`producer-handoff/`](./producer-handoff/) | Producer-side reference mirrored from the **yearline-universe** repo's Phase 09 (the delivered V13.8 `YearlineContext` adapter handoff + the `YearlineTrendSeries` UX trend-plot analysis). |

> **Cross-links inside these files** reflect the originating yearline repo's directory structure and may
> not resolve here — they are preserved verbatim as the source record (per
> [`../README.md`](../README.md) convention #1).

## The one hard rule

`packages/engine` is pure, no-I/O, lean-deps (ADR-0005, CI-enforced). **Never import `yearline-universe`
into the engine.** It runs in the jobs/ingestion layer, persists its artifact, and the engine consumes
only the lightweight, gated `YearlineContext` value object — exactly how `MarketStateResult` /
`FlowScore` are hydrated today. The coupling is a **persisted, versioned artifact**, not a library
dependency.

## Roadmap (consumer side — option-mgmt-2026)

`OM-Y0` (this enhancement + ADR-0009, no code) → `OM-Y1` (Pydantic `YearlineContext` + TS codegen +
contract test) → `OM-Y2` (ingest + persist) → `OM-Y3` (read-only Today-screen evidence panel,
`DailyDecision` byte-identical) → `OM-Y4` (gated engine consumption — the prize) → `OM-Y5` (stretch).
Per [`../README.md`](../README.md) convention #4, per-milestone design docs are written when each
milestone opens, not before.
