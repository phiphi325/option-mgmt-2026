# Phased Design — index

This folder is the canonical home of the project's phased development plan.

## Files

| Path | Purpose |
|---|---|
| [`msft-option-risk-management-engine-phased-plan.md`](./msft-option-risk-management-engine-phased-plan.md) | The master plan (v1.2, locked). 20 sections + §22 audit corrections. Source of truth. Read §22 first. |
| [`phase-1/`](./phase-1/) | Phase 1 dev specs. One retrospective summary for M1.0–M1.14 (shipped) plus four forward-looking dev plans for M1.15–M1.18. |

## How to read

1. **Implementers** start at the master plan's §22 (audit corrections) → §17 (milestone roster) → the per-milestone doc under `phase-1/` for the work they're about to ship.
2. **Reviewers** look at the matching `phase-1/m1.XX-*.md` doc *before* the PR to verify scope, acceptance criteria, and test plan match what shipped.
3. **Newcomers** start at the master plan §1 (Product Brief) → §2 (Personas) → §3 (MVP Scope) → `phase-1/m1.0-m1.14-shipped-summary.md` for current state.

## Conventions

- **Plan refs.** Every dev spec links back to master-plan sections by `§N` notation (e.g. `§7`, `§9.6`, `§22.14`). The master plan never re-numbers.
- **Status field.** Every forward dev spec carries a `Status:` field at the top — one of `planned`, `in-progress`, `shipped`. The retrospective is `shipped` only.
- **Naming.** Per-milestone files are `m1.XX-<kebab-slug>.md`. The slug captures the milestone's deliverable, not its size.
- **No editorial changes to the master plan.** This folder commits the v1.2 plan verbatim. Errata go in a `phase-1/errata.md` or a follow-up plan version, never as silent edits.

## When to add a new file here

| Trigger | Add this |
|---|---|
| Starting work on a milestone M1.X (X ≥ 15) | `phase-1/m1.X-*.md` if it doesn't exist; otherwise update `Status: planned → in-progress` |
| Shipping a milestone | Update `Status: in-progress → shipped`; link the merged PR; note any deviations from the spec |
| Starting Phase 2 | Create `phase-2/` with its own README + per-milestone docs |
| Master plan reaches v1.3 | Save the new version alongside v1.2 (don't overwrite); annotate which version each spec targets |

## What's out of scope here

- ADRs (decision records) live in [`../decisions/`](../decisions/), not here. The master plan references ADRs; dev specs may also.
- Enhancement-roadmap (E1–E9) details live in the master plan §23 and in ADR-0008. Phase 1.5's GEX module (ME1.0–ME1.7) will get its own subfolder when work starts.
- Phase 2/3/4 dev specs are NOT created yet — write them at the start of each phase, not before.
