# Tutorials

Long-form, pedagogical material targeting first-year master's students in
financial engineering (or any reader who wants to understand *why* the engine
makes the decisions it does, not just *how* to call it).

Tutorials are deliberately deeper than the API references in `docs/` — they
cover the financial fundamentals, the design methodology, and the worked
examples a course instructor would want to assign as reading.

## Index

| Tutorial | Audience | Reading time |
|---|---|---|
| [market-state-engine.md](./market-state-engine.md) | 1st-year MFE, quant developers, options traders | ~75 min careful read · ~25 min skim |
| [scoring-primitives.md](./scoring-primitives.md) | Same audience; read after `market-state-engine.md` (depends on §2 input vocabulary) | ~50 min careful read · ~20 min skim |

## How tutorials relate to the rest of the docs

| Doc family | Purpose | Length |
|---|---|---|
| `tutorials/` (this folder) | Pedagogical, "learn the engine" | Long-form |
| `architecture.md` | Layer cake / data flow reference | Medium |
| `decisions/*.md` (ADRs) | Locked decisions, one per file | Short |
| `enhancements/*` | Spec assessments | Short |
| `thread-transitions/` | Agent handoff records | Medium |

If a tutorial references a locked decision, it links to the ADR; the ADR
remains the source of truth. Tutorials explain; ADRs commit.

## Conventions

- Math uses LaTeX-style `$inline$` and `$$display$$` blocks (GitHub renders).
- Code snippets quote real engine code; tutorials are kept in sync when the
  engine changes (the same PR updates both).
- Every tutorial has an explicit **disclaimer** linking to
  [`docs/disclaimers.md`](../disclaimers.md): tutorials are educational
  material, not investment advice.
