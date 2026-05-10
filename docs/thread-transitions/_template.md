# Thread tNN — <short title>

| | |
|---|---|
| **Thread #** | tNN |
| **Date range** | YYYY-MM-DD → YYYY-MM-DD |
| **Close date** | YYYY-MM-DD |
| **Model** | _e.g._ Claude Opus 4.7 |
| **Agent** | _e.g._ Developer |
| **Engine version** | `<start>` → `<end>` |
| **Plan version** | _e.g._ v1.2 |
| **Test count (engine)** | `<start>` → `<end>` |

## Scope

One paragraph on what this thread set out to accomplish and what it actually delivered. Distinguish "in scope and shipped" from "in scope but deferred."

## Shipped

| | What | PR | Squash SHA on `main` | Engine |
|---|---|---|---|---|
| ✅ | _Milestone or scope_ | [#NN](https://github.com/csupenn/option-mgmt-2026/pull/NN) | `aaaaaaa` | `0.x.0` |

`main` HEAD at thread close: _SHA_, engine `0.x.0`, _N_ engine tests.

## Decisions made

Locked architectural / process decisions. Each should reference an ADR or plan section. If no new decisions were locked in this thread, write `(none — all decisions in scope of this thread already had ADRs or plan §refs)`.

- **<Decision title>** — _one-sentence summary_. Recorded in [ADR-NNNN](../decisions/NNNN-<slug>.md) / plan v1.X §N.

## Gotchas & non-obvious things

Things that bit during the thread and that future threads should know. Include workaround commits, sandbox quirks, sharp edges in the codebase, or counterintuitive plan-§ interactions.

- _Gotcha_: _what bit, why, what to do about it_.

## What's NOT done (deferred / next)

Items that were considered and explicitly deferred, or that are obvious next steps. Distinct from "everything else in the plan." Aim to capture the things the next thread might mistakenly think were already done.

- _Item_ — _why deferred or what triggers it_.

## Handoff brief — what the next thread needs

The minimum context for a fresh thread to be productive. Aim for ~150–300 words. This is the section that gets distilled into a memory or pasted into the new thread's first message. Use blockquote so it's copy-pasteable.

> **Current state on `main`:** ...
>
> **What's next:** ...
>
> **Critical references:** plan v1.X §..., ADR-NNNN, PR #NN, ...
>
> **Workflow conventions:** ...

## Pointers

- Plan doc: _ID or location_
- Thread Context Doc: _ID or location, plus a note about its scope (thread-only docs are not readable from a fresh thread)_
- Memory written for next thread: _ID, scope, importance — or n/a if none was written_
- This thread's transcript: _location, if applicable_

---

_Record written by `<model>` (the `<agent>` agent) on YYYY-MM-DD. Append-only — corrections via new records or ADRs._
