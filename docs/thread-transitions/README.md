# Thread Transitions

Per-AI-agent-thread handoff records. One file per thread, written when the thread closes — typically because the context window is approaching its limit, a logical milestone has been reached, or the agent or user wants a clean break.

## Why this exists

option-mgmt-2026 is built primarily through long-running conversations with an AI dev agent. Each thread accumulates working memory: the decisions made, the gotchas encountered, the rationale behind code that's already merged. Without a deliberate handoff record, that memory is lost when the thread ends — only the commit messages and ADRs survive, and they're not the same thing as "the things the next thread needs to know."

This folder is the project's permanent log of those handoffs. Each record:

- Documents the thread's date range, milestones in scope, model, and agent.
- Lists what shipped (PRs merged with squash SHA).
- Captures the decisions made (with links to ADRs).
- Records gotchas / non-obvious things future threads should know.
- Includes a handoff brief — the minimum context the next thread needs to start fresh.

Records are append-only. Don't edit prior records to "correct" them; if a decision is later revised, that revision is documented in a new record (or an ADR).

## Distinction from `dev-log/` (planned)

`docs/dev-log/YYYY-MM-DD.md` (per plan §19) is a **per-day, per-developer** "what shipped today" log — human-oriented, day-bounded.

`docs/thread-transitions/YYYY-MM-DD-tNN-<slug>.md` (this folder) is a **per-AI-thread** handoff — agent-oriented, can span many days or be many threads in one day. The two are complementary; they answer different questions.

## Filename convention

```
YYYY-MM-DD-tNN-<short-slug>.md
```

- `YYYY-MM-DD` — the close date of the thread (when the record is written).
- `tNN` — sequential thread number across the project, zero-padded (`t01`, `t02`, …, `t99`).
- `<short-slug>` — kebab-case scope summary (e.g., `phase0-foundation-and-phase1-m1.1-to-m1.3`).

## How to write a record

1. **At thread close**, copy [`_template.md`](./_template.md) to a new file using the filename convention above.
2. Fill in every section. If a section truly doesn't apply to this thread, write `(none)` — don't delete the section.
3. The handoff brief is the most important section. Write it as if you're briefing a smart colleague who has the agent's identity and tools but zero memory of what happened in this thread. Keep it ~150–300 words.
4. Update the index table below with the new record's row.
5. Open a small docs-only PR to land the record on `main`.

## Index

| # | Date | Scope | Engine version range | Record |
|---|---|---|---|---|
| t01 | 2026-05-10 | Phase 0 (M0.1–M0.7) + plan v1.2 audit + Phase 1 M1.1/M1.2/M1.3 | scaffold → `0.4.0` | [`2026-05-10-t01-phase0-foundation-and-phase1-m1.1-to-m1.3.md`](./2026-05-10-t01-phase0-foundation-and-phase1-m1.1-to-m1.3.md) |
