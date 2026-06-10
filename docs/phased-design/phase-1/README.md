# Phase 1 — Engine MVP

Phase 1 ships the engine-first MVP per master plan §17. Aggregate size: ~5 weeks (revised from 4 to absorb the v1.1 patch additions). Acceptance: see master plan §19 "Definition of Phase 1 Done".

## Milestone roster (from master plan §17)

| ID | Milestone | Size | Status | Dev spec |
|---|---|---|---|---|
| M1.1 | IV rank/percentile + HV computations | S | shipped | — (see retrospective) |
| M1.2 | Max pain + expected move + PCR | S | shipped | — |
| M1.3 | Trend strength proxy + technical context | S | shipped | — |
| M1.4 | Market State Engine + 24 regime fixtures | L | shipped | — |
| M1.4a | iv/structure/event scoring pure fns (v1.1 patch) | M | shipped | — |
| M1.5 | Flow Score Engine + OI walls + dealer-gamma proxy | M | shipped | — |
| M1.5a | gamma_score pure fn (v1.1 patch) | S | shipped | — |
| M1.5b | Flow Score V1 contract refit (v1.1 patch) | M | shipped | — |
| M1.6 | Black-Scholes + Greeks + IV solver | M | shipped | — |
| M1.7 | Strike Selector core | L | shipped | — |
| M1.8 | Recommendation Engine + regime-strategy whitelist | M | shipped | — |
| M1.9 | Recommendation Engine: 8 YAML rules + tests | M | shipped | — |
| M1.10 | Confidence Composer + weights.yaml | M | shipped | — |
| M1.11 | Execution Feasibility Module | M | shipped | — |
| M1.11a | Collar Builder engine (v1.1 patch) | L | shipped | [PR #56](https://github.com/csupenn/option-mgmt-2026/pull/56) → `951c206e`. [Dev spec](./m1.11a-collar-builder-engine.md) · [retrospective](./review/m1.11a-retrospective.md) · [tutorial](../../tutorials/collar-builder.md). Engine version `1.4.0` → `1.5.0`. 5-commit fix saga between initial push and CI green — see retrospective. |
| M1.11b | Collar Builder integration into Master Decision (v1.1) | M | shipped | [PR #58](https://github.com/csupenn/option-mgmt-2026/pull/58) → `80871b0b`. [Dev spec](./m1.11b-collar-builder-integration.md) (incl. post-ship reconciliation appendix). Engine version `1.5.0` → `1.6.0`. Wires `collar_builder.build(intents=[ZERO_COST])` into `decision.produce()` for `OPEN_COLLAR` emits via the new `_dispatch_open_collar` helper; `DailyDecision` gains `collar_structures: tuple[CollarStructure \| None, ...]` parallel to `strike_selections`. Doc-sync retrospective (CHANGELOG `[1.5.0]` + `[1.6.0]`, repo README + this README + thread-transition `t03`) followed up 2026-05-13. |
| M1.12 | Execution downgrade callback | S | shipped | — |
| M1.13 | Master Decision Engine orchestration | M | shipped | — |
| M1.14 | `/engine/daily-plan` + `/engine/recommend` endpoints | S | shipped | [PR #45](https://github.com/csupenn/option-mgmt-2026/pull/45) → `c0583ed` |
| M1.15 | `/engine/what-if` + `/engine/market-state` + `/engine/flow-score` | S | shipped | [PR #47](https://github.com/csupenn/option-mgmt-2026/pull/47) → `22b0033` |
| M1.16 | `/engine/strike-candidates` + `/engine/execution-check` (reduced scope — see dev spec) | S | shipped | [PR #48](https://github.com/csupenn/option-mgmt-2026/pull/48) → `726ec37`. Patch v1.1 companions: M1.16a awaits M1.11a; M1.16b `/market/msft/latest` bundled into M1.17 (this PR). M1.16b `/health` + `/healthz` + `/version` already shipped (M0.3-era). |
| M1.17 | `/profile` + `/outcomes` + 5 CSV import endpoints + `/market/{ticker}/latest` (M1.16b pickup) | M | shipped | [PR #50](https://github.com/csupenn/option-mgmt-2026/pull/50) → `6d2f77a`. Knock-on "`DailyPlanRequest.inputs` optional" shipped in M1.17.5 follow-up. |
| M1.17.5 | `DailyPlanRequest.inputs` optional + DB hydration (`inputs_hydration_service.py`) | S | shipped | [PR #51](https://github.com/csupenn/option-mgmt-2026/pull/51) → `1d442bd`. M1.17 knock-on. Hydrates `EngineInputs` from latest DB rows; reproduces `market_state.classify` + `flow_score.compute` server-side. 422 on `missing_positions` / `missing_chain` / `insufficient_iv_history`. |
| M1.18 | Today screen scaffolding + DecisionCard + StrategyTitle | M | shipped | [PR #53](https://github.com/csupenn/option-mgmt-2026/pull/53) → `c7712ed`. First Next.js milestone since M0.4. Uses M1.17.5 hydration path: `getDailyPlan({ticker})` from `lib/api/engine.ts` is server-only; the Today page server-renders, hands `DailyDecision` to the `DailyDecisionCard` client component. Error boundary surfaces hydration 422s (`missing_chain` / `missing_positions` / `insufficient_iv_history`) as actionable CTAs. |
| M1.19 | ActionList + ActionRow + ExecutionBadge | S | shipped | [PR #12](https://github.com/knowlingo/option-mgmt-2026/pull/12) → `cc15de5`. [Dev spec](./m1.19-action-list-execution-badge.md) (incl. post-ship reconciliation). Replaces the M1.18 placeholder; first consumer of `DailyDecision.collar_structures`. Plain Tailwind (no shadcn); numeric fields typed as JSON numbers; reuses `strategy-labels.formatStrategy`. |
| M1.20 | ConfidenceBreakdownChart + ExecutionFeasibilityPanel | S | shipped | [PR #13](https://github.com/knowlingo/option-mgmt-2026/pull/13) → `5862970`. [Dev spec](./m1.20-confidence-chart-execution-panel.md) (incl. post-ship reconciliation). Recharts `StackedConfidenceBar` (reuses OM-Y3 dep) + 6-segment breakdown + `positive_score × penalty_multiplier` caption + aggregate execution panel. Added the missing `--chart-1..5` CSS tokens. |
| M1.21 | WatchLevels + Drawer (Rationale, Risks, Invalidation) | S | shipped | [PR #15](https://github.com/knowlingo/option-mgmt-2026/pull/15) → `cebeab9`. [Dev spec](./m1.21-watch-levels-drawer.md) (incl. post-ship reconciliation). Fills the final M1.18 placeholder — card tree now complete (no `PlaceholderCard`). Native `<details>` drawers (no shadcn Collapsible); `WatchLevels` is a forward-typed seam (engine doesn't emit `watch_levels` yet — follow-up). |
| M1.22 | User Strategy Profile UI + persona presets | M | shipped | [PR #17](https://github.com/knowlingo/option-mgmt-2026/pull/17) → `a87fdfb`. [Dev spec](./m1.22-profile-ui-persona-presets.md) (incl. post-ship reconciliation). **Dependency-free (Path A)** `/settings`: native controlled inputs (`<select>` / range / checkbox) + a `saveProfile` **server action** — no RHF/zod/react-query/shadcn (none installed; lockfile not regenerable here). Real **8-field** `UserStrategyProfile` (the spec's persona/zod fields don't exist on the engine schema); components in `components/settings/`. Adds a Today · Settings nav. |
| M1.23 | Outcome manual entry + history view | M | shipped | [PR #19](https://github.com/knowlingo/option-mgmt-2026/pull/19) → `9e55168`. [Dev spec](./m1.23-outcome-tracker.md) (authored against the shipped API; incl. post-ship reconciliation). **Dependency-free (Path A)** `/outcomes`: manual entry + cursor-paginated history + inline edit + stats; mutations via server actions. Real `/outcomes` shapes (M1.17) — `pnl_*` are **JSON strings** (`Decimal`→string), not numbers; row shows the decision UUID (no decision-summary join exists). Components in `components/outcomes/`. Adds the Outcomes nav. |
| M1.24 | Golden tests (12 DailyDecision snapshots) + companion tooling housekeeping (CHANGELOG drift guard + `Settings` engine_version/weights_version consolidation) | M | shipped | [PR #3](https://github.com/knowlingo/option-mgmt-2026/pull/3) → `7fec498`. [Dev spec](./m1.24-master-decision-goldens.md) (incl. post-ship reconciliation). Engine `1.6.0` → `1.7.0`. 12 named fixtures under `tests/fixtures/master_decisions/` + parametrized `pytest` replay harness + `engine.decision.serialize_canonical` + regeneration script + suite-level meta tests. Bundles `scripts/check_changelog_entry.sh` and `Settings` consolidation. **Goldens regenerated via [PR #4](https://github.com/knowlingo/option-mgmt-2026/pull/4)** (phiphi325) which also fixed an `iv_rank`/`iv_percentile`/`iv_rank_change_1d` `[0-100]`→`[0-1]` fixture-scale bug. Closes 3 of the 4 remaining Phase 1 Done bar items; M1.25 closes the last (Playwright E2E). |
| M1.25 | Calibration tests + Playwright E2E + polish | M | planned | TBD — the Playwright E2E flows should also cover the **yearline evidence panel** (OM-Y3) on `/today`, including its empty/stale states (decide whether it gets its own flow). |

> **Yearline OM-Y4 sequencing — deferred until after Phase 1's decision + calibration surface.**
> The yearline **read-only** track (OM-Y0–Y3) is merged and parallel to Phase 1. The
> next yearline step, **OM-Y4 (gated engine consumption)**, is intentionally **held
> until after M1.25**, because:
> - OM-Y4 is the only *output-changing* yearline step — it touches `rules.yaml` + the
>   Confidence Composer (ADR-0003) + the replay hash + `weights_version`. Mutating the
>   decision mid-Phase-1 fights the M1.24 golden lock and the in-flight UI milestones.
> - Its own acceptance gate ("only if the signal earns it") needs Phase-1 infra that
>   isn't built yet — the **Outcome Tracker** (M1.23 + M1.17 data) and **Calibration**
>   (M1.25) are how you'd justify the gated component's weights instead of guessing them.
> - The read-only C-track already delivers the user value with zero decision risk.
>
> So: finish Phase 1 (esp. M1.25 calibration), then do OM-Y4 when the composer change
> can be calibrated. Full build steps + traps:
> [`docs/enhancements/yearline/implementation/HANDOFF.md`](../../enhancements/yearline/implementation/HANDOFF.md).

## Status legend

- **shipped** — merged to main; row in retrospective summary links to PR.
- **in-progress** — branch open, PR pending. The dev spec is the working contract.
- **planned** — dev spec authored, no branch yet. Awaiting the prior milestone to merge.

## Forward-looking dev spec template

Every forward dev spec under this folder follows the same eight-section template. Skim any one (e.g. [`m1.15-engine-readonly-endpoints.md`](./m1.15-engine-readonly-endpoints.md)) for the shape:

1. **Front matter** — id, size, dependencies, status, plan refs
2. **Goal** — 1–2 sentences
3. **What ships** — bulleted endpoints / migrations / services
4. **Request / response schemas** — Pydantic-shape pseudocode (canonical names from §7)
5. **DB migrations** — table/column/constraint deltas, or "no schema change"
6. **Tests** — unit + smoke matrix
7. **Acceptance criteria** — verifiable bullets
8. **Open questions / risks** — max 5 items

Target length: 2–4 printed pages each. Bigger is a sign the milestone should be split.

## Why M1.15 first, not data-import?

A common misconception (carried over from the M1.14 PR body): "M1.15+ hydrates from DB". That's wrong. Per master plan §17, M1.15 is the read-only engine sub-step endpoints, not data import. The data-import path is **M1.17** (CSV upload to `positions` / `option_positions` / `option_chain_snapshots`). The "`DailyPlanRequest.inputs` becomes optional" unblock waits for M1.17 to ship — see [`m1.17-profile-outcomes-csv-import.md`](./m1.17-profile-outcomes-csv-import.md) §"Unblocks".

## Phase 1.5 — GEX Module

Phase 1.5 (ME1.0 – ME1.7) ships after M1.25 per ADR-0008. It is NOT documented in this folder; when Phase 1.5 starts, create `docs/phased-design/phase-1.5/` with its own README and per-milestone docs.
