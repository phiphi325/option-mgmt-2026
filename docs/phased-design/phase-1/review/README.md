# Phase 1 — Post-merge code reviews

Brief, candid retrospectives on milestones after they land. Each file
covers:

1. What actually shipped vs. the dev spec.
2. The fix saga (if any) — what failed in CI and what we learned.
3. Code-quality findings — deviations, risks, open follow-ups.
4. Recommendations for downstream milestones.

These are **post-mortem** reviews, not pre-merge code reviews. They exist
so future readers (and future authors) can see the friction surfaces
that the squashed merge commit hides.

## Index

| Review | Milestone | PR | Engine | Length |
|---|---|---|---|---|
| [`m1.11a-retrospective.md`](./m1.11a-retrospective.md) | M1.11a — Collar Builder engine module | [#56](https://github.com/csupenn/option-mgmt-2026/pull/56) → `951c206e` | `1.4.0` → `1.5.0` | 5-commit fix saga; 4 deviations from dev spec; recommendations for M1.11b. |

## When to add a review

Any milestone where one or more of the following is true:

- More than 2 fix commits between the initial push and CI green.
- Any deviation from the dev spec — a constant lowered, a section
  deferred, a test simplified — that future readers should know about.
- An unexpected interaction with an upstream module (M1.11a hit M1.11's
  `§9.8` liquidity formula in a way the dev spec didn't anticipate).
- A judgment call that traded contract strictness for shippability and
  may need to be revisited (e.g., a calibration constant softened).

If none of those apply, the squashed merge commit + the dev spec are
sufficient — no review file needed.

## Format

Use [`m1.11a-retrospective.md`](./m1.11a-retrospective.md) as the
template. Roughly:

```
# M1.<X> retrospective
| Field | Value | (front matter: PR, SHA, engine, status)

## What landed                  (1 short paragraph)
## Fix saga                     (commit-by-commit table + analysis)
## Code-quality findings        (numbered list of deviations / risks)
## Acceptance criteria vs ship  (table)
## Recommendations              (bullets aimed at the next milestone)
```

Target length: **3–10 KB**. Anything longer is probably hiding a
recommendation that should be its own decision doc.
