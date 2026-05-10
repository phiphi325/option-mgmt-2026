# Thread t01 — Phase 0 foundation + plan v1.2 audit + Phase 1 M1.1→M1.3

| | |
|---|---|
| **Thread #** | t01 |
| **Date range** | 2026-04-29 → 2026-05-10 |
| **Close date** | 2026-05-10 |
| **Model** | Claude Opus 4.7 |
| **Agent** | Developer |
| **Engine version** | (none) → `0.4.0` |
| **Plan version** | v1.0 → v1.1 → v1.2 |
| **Test count (engine)** | 0 → 121 |

## Scope

The first dev thread for option-mgmt-2026. Started from a blank repo and the v1.0 plan; ended with Phase 0 fully shipped, plan v1.2 audit-corrected, and the first three Phase 1 engine-MVP milestones (M1.1 IV/HV, M1.2 max pain + expected move + PCR, M1.3 Wilder ADX trend_strength + breakout signal) merged on `main` with engine version `0.4.0` and 121 engine tests. Closed deliberately before starting M1.4 to keep context fresh for the architecturally consequential `classify()` work.

In scope but **not shipped** in this thread: M1.4 Market State Engine `classify()`, M1.4a scoring primitives, all of M1.5–M1.25, Phase 1.5 (E1 GEX), Phase 2+.

## Shipped

### Phase 0 — Foundation (all 7 milestones)

| | What | PR | Engine |
|---|---|---|---|
| ✅ | M0.1 — pnpm + uv monorepo, Docker Compose, Makefile | [#1](https://github.com/csupenn/option-mgmt-2026/pull/1) | — |
| ✅ | M0.2 — Postgres schema + Alembic migration `0001_init` | [#2](https://github.com/csupenn/option-mgmt-2026/pull/2) | — |
| ✅ | M0.3 — FastAPI shell + `/health` `/healthz` `/version` + JWT scaffolding | [#3](https://github.com/csupenn/option-mgmt-2026/pull/3) | — |
| ✅ | M0.4 — Next.js 16.2.6 shell + Disclaimer gate + Tailwind + Vitest | [#4](https://github.com/csupenn/option-mgmt-2026/pull/4) | — |
| ✅ | docs foundation + ADRs 0001–0006 | [#5](https://github.com/csupenn/option-mgmt-2026/pull/5) | — |
| ✅ | M0.5 — CI pipelines + pre-commit + Dependabot + policy guards | [#6](https://github.com/csupenn/option-mgmt-2026/pull/6) | — |
| ✅ | M0.6 — Engine types: regimes, profiles, ChainSnapshot, TS codegen | [#17](https://github.com/csupenn/option-mgmt-2026/pull/17) | `0.1.0` |
| ✅ | M0.7 — End-to-end smoke test | [#22](https://github.com/csupenn/option-mgmt-2026/pull/22) | — |

### Plan + ADR work (mid-thread)

| | What | PR |
|---|---|---|
| ✅ | Plan v1.2 audit — 25 findings; 24 resolved in §22, 1 (Next.js version) verified independently | (in-thread, not a PR) |
| ✅ | docs — ADR-0008 enhancement-spec adoption roadmap (6 adopt, 2 defer, 0 reject) | [#23](https://github.com/csupenn/option-mgmt-2026/pull/23) |

### Phase 1 — Engine MVP (in progress)

| | What | PR | Engine |
|---|---|---|---|
| ✅ | M1.1 — IV rank/percentile + HV (close-to-close + Parkinson) + 252-day MSFT IV history seed | [#24](https://github.com/csupenn/option-mgmt-2026/pull/24) | `0.1.0` → `0.2.0` |
| ✅ | M1.2 — max pain + expected move (ATM straddle + forward-IV) + PCR (volume + OI) | [#25](https://github.com/csupenn/option-mgmt-2026/pull/25) | `0.2.0` → `0.3.0` |
| ✅ | M1.3 — Wilder ADX `trend_strength` + 4-component `breakout_signal` + `clip01` helper | [#26](https://github.com/csupenn/option-mgmt-2026/pull/26) | `0.3.0` → `0.4.0` |

`main` HEAD at thread close: `95c49a9` (squash of PR #26), engine `0.4.0`, 121 engine tests, ruff/mypy clean, codegen drift exit 0.

## Decisions made

- **Engine-first architecture.** Recorded in [ADR-0001](../decisions/0001-engine-first-architecture.md). The product is a decision engine; APIs and UI exist to surface or input to it.
- **6 named regimes** (`HIGH_IV_EVENT`, `HIGH_IV_PIN`, `LOW_IV_TREND`, `LOW_IV_RANGE`, `BREAKOUT`, `POST_EVENT_REPRICE`) implemented as a typed enum in `packages/engine/engine/regimes.py`. [ADR-0002](../decisions/0002-regime-taxonomy.md).
- **Confidence is multiplicative**, not subtractive. positive_weights (sum = 1.0) and penalty_caps (max-reduction multipliers); true `[0, 1]` range achievable. [ADR-0003](../decisions/0003-confidence-composer-multiplicative.md).
- **Disclaimer gate fail-open** with explicit `disclaimer_accepted_at` column on users. [ADR-0004](../decisions/0004-disclaimer-fail-open.md).
- **Engine pure-function discipline.** No I/O, no DB, no network in `packages/engine/`. SemVer-strict version-bump rules with CI guard `scripts/check_engine_version_bump.sh`. [ADR-0005](../decisions/0005-engine-pure-function-discipline.md).
- **API errors use RFC 7807 `application/problem+json`.** [ADR-0006](../decisions/0006-rfc-7807-error-envelope.md).
- **Python pinned to 3.14**, Next.js to 16.2.6. [ADR-0007](../decisions/0007-python-version-pin.md) + plan v1.2 §22.1.
- **Enhancement-spec adoption roadmap.** 6 adopt (1 partial, 1 display-only), 2 defer, 0 reject. E1 GEX → Phase 1.5; E2/E3p/E4d/E5/E8 → Phase 2; E9 → Phase 3; E6/E7 deferred post-Phase-3. [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md).
- **Plan v1.2 audit-corrected.** External Sonnet 4.6 review flagged 25 issues; 24 resolved in §22, 1 (Next.js version) verified independently against npm registry. v1.0/v1.1 references to "Next.js 16.2.4" read as "16.2.6" globally per §22.1.
- **`engine._utils.clip01` is the canonical `[0, 1]` saturation.** Plan v1.2 §22.5 + §22.13 reference it directly. M1.4 scoring functions and the Confidence Composer should import from there — don't reinvent in each module.

## Gotchas & non-obvious things

- **Wilder ADX needs `2n + 10` bars to stabilize**, not `2n + 1` (the mathematical minimum). `compute_trend_strength` returns a `0.5` neutral sentinel below threshold rather than raising — this is a deliberate non-raising path so M1.4 `classify()` keeps running against partial data. `wilder_adx` itself raises below `2n + 1`. Plan v1.2 §22.5.
- **Sandbox is Python 3.9; project targets 3.14.** Caused issues with `zip(..., strict=True)` (added in 3.10) — landed `# noqa: B905` with an explanatory comment in `trend_strength.py`. Don't strip the noqa without restoring `strict=True`. The equal-length invariant is established locally by construction (all three RMA series come from `_wilder_rma(<same-length>, n)`).
- **The §22.3 `classify()` signature has 18 inputs**, not the 13 in v1.0/v1.1. M1.3 added `trend_strength` and `breakout_signal`; M1.4 wires them all together.
- **CI takes ~3 minutes.** Five jobs run in parallel: guards, api, engine, web, smoke. The engine job includes a codegen drift check — any change to `packages/engine/engine/{regimes,profiles,types,version}.py` requires regenerating `packages/shared-types/src/`.
- **Engine version bump is enforced by CI.** Any change under `packages/engine/engine/` must bump `__version__` per the SemVer rules in ADR-0005 / plan §22.15 L2. `scripts/check_engine_version_bump.sh` validates.
- **Squash-merge convention.** PR #N's squash commit message on `main` is the comprehensive recap (multi-paragraph: scope, modules, tests, plan refs). The PR body has the human-friendly summary.
- **Hyperagent Thread Context Docs are thread-scoped by default**, meaning the next thread cannot read this thread's working-memory doc directly. Bridge with a memory or by promoting the doc to project/global scope. (See "Pointers" below.)

## What's NOT done (deferred / next)

- **M1.4 — Market State Engine `classify()`** is the immediate next milestone. Wires the §22.3 18-input signature and returns one of the 6 named regimes plus `regime_score ∈ [0, 1]` plus `tags[]`. Plan §17 lists 24 regime fixture tests. Engine bumps to `0.5.0`.
- **M1.4a — `iv_score`, `structure_score`, `event_score`** scoring primitives in `packages/engine/engine/scoring/` (required at 100% line coverage). **Open question for next thread:** ship M1.4a before or after M1.4 `classify()`. Both paths are valid; M1.4a-first reduces churn when classify() wires everything together. The user explicitly wants to choose, not be defaulted into one path.
- **M1.5–M1.25** — Flow Score, Strike Selector, Recommendation, Decision, Confidence Composer, Execution Feasibility, `/engine/*` APIs, Today screen. Per plan v1.2 §17.
- **`iv_history.csv` seed is currently 252 days, MSFT only.** M1.4 may want to extend to seed multi-regime fixtures.
- **Phase 1.5 — E1 GEX Module.** Per ADR-0008. Starts after M1.7. Includes a follow-up ADR amending the FlowScore V1 contract (`dealer_gamma_proxy` → `gex_context`).

## Handoff brief — what the next thread needs

> **Current state on `main` (post-M1.3 squash `95c49a9`):** engine `0.4.0`; 121 engine tests; 8 ADRs (0001–0008); plan v1.2 with §22 audit corrections complete; Phase 0 done; Phase 1 milestones M1.1/M1.2/M1.3 done.
>
> **Engine modules in place:** `_utils.clip01`; `regimes`; `profiles`; `types`; `version`; `market_state.{iv, hv, expected_move, max_pain, pcr, trend_strength, breakout}`. All pure functions, no I/O, ruff/mypy-strict clean.
>
> **What's next:** M1.4 — Market State Engine `classify()` per plan v1.2 §22.3 + §17. Returns one of the 6 named regimes plus `regime_score ∈ [0, 1]` plus `tags[]`. 24 regime fixture tests required. Engine bumps to `0.5.0`. **Open question** the user wants to make explicitly: ship M1.4a (`iv_score` + `structure_score` + `event_score` in `packages/engine/engine/scoring/`, 100% line coverage) before or after M1.4. Both paths are valid; M1.4a-first reduces churn.
>
> **Critical references:** plan v1.2 §17 (milestone table), §22.3 (extended classify signature), §22.5 (canonical formulas + 0.5 sentinel rule), §22.13 (clip01 reuse). ADR-0001 (engine-first), ADR-0002 (6 regimes), ADR-0005 (pure-function discipline + version-bump rules). PRs #24/25/26 for the M1.x pattern + squash-message convention.
>
> **Workflow conventions:** branch `feat/<milestone>-<slug>`; squash-merge with comprehensive recap as the squash message; CI 5/5 must be green before merging; post-merge update `CHANGELOG.md` + `docs/thread-transitions/` (this folder) when the thread closes.

## Pointers

- **Plan doc** (Hyperagent, attached to the Developer agent — auto-carries to the new thread): `cmokf2twq0gsv06adlij0glqs`
- **Thread Context Doc** (Hyperagent, **thread-scoped — NOT readable from the new thread**): `cmokdnanj0dh306adirj1vtfn`. Contains the full evolution log of plan v1.0 → v1.1 → v1.2 with the 25-finding audit log.
- **Memory written for next thread:** Phase 1 state snapshot — to be drafted as the last action of this thread, importance high so it injects upfront in the new thread.
- **This thread's transcript:** Hyperagent thread under the Developer agent (`cmokdknut0eko07addjy570hz`).

---

_Record written by Claude Opus 4.7 (the Developer agent) on 2026-05-10. Append-only — corrections via new records or ADRs._
