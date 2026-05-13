# Memories — Thread Export (2026-05-13)

## active_work

### M1.16a shipped — Collar Builder API endpoint (PR #60)

| | |
|---|---|
| **Memory ID** | `CWpSOo6j` (pending user confirmation at thread close) |
| **Category** | `active_work` |
| **Importance** | 0.95 |
| **Tags** | `option-mgmt-2026`, `M1.16a`, `collar-builder`, `handoff`, `M1.11b-next` |
| **When to use** | When starting a new thread for the option-mgmt-2026 project, especially for M1.11b or any subsequent milestone. Provides current state of main, what shipped in M1.16a, what's next, and critical gotchas. |
| **Created** | 2026-05-13 |

**Content:**

```
## M1.16a shipped — Collar Builder API endpoint (PR #60)

**Current state on `main`:** Commit `c90444f` (docs update after `9c63a15` merge).
Engine `1.5.0`. ~840 tests. **18 API endpoints** live (M1.14–M1.17.5 + M1.16a).
The Collar Builder has both an engine module (`engine.collar_builder.build()`,
M1.11a / PR #56) and an API endpoint (`POST /engine/collar-builder`, M1.16a / PR #60).

**What's next:** M1.11b — wire Collar Builder into `produce_daily_decision()`. The
recommendation engine's `OPEN_COLLAR` emit should dispatch to
`collar_builder.build(intents=[ZERO_COST])` and attach the resulting structure(s)
to the `DailyDecision`. This is engine version `1.6.0` (minor: new integration, no
schema break). After M1.11b, the frontier moves to M1.19 (ActionList UI component).

**Critical references:** plan v1.2 §9.10 (Collar Builder spec), §22.11 H5
(underlying_qty from DB), §17 M1.11b row, ADR-0005 (engine purity + version discipline).

**Workflow:** Branch `feat/m1.11b-collar-decision-integration`, squash-merge to `main`.
Bump `engine/version.py` → `1.6.0`. CI: ruff + mypy + pytest + smoke.

**Known debt:** `CHANGELOG.md` is missing the `[1.5.0]` entry for M1.11a — add it
alongside the `[1.6.0]` entry for M1.11b.

**Gotchas from M1.16a thread:**
- Ruff I001: aliased imports must be split into separate `from` lines and sorted
  case-sensitively (uppercase before lowercase).
- ProblemDetails (RFC 7807): custom handler in `app/main.py` puts error strings in
  "title" field, not "detail". Tests must assert `resp.json()["title"]`.
- `_SUPPORTED_TICKERS` in collar_builder_service.py is a local frozenset (MSFT-only
  Phase 1); unify with market_service in Phase 2.

**Thread transition doc:**
`docs/thread-transitions/2026-05-13-t02-m1.16a-collar-builder-endpoint.md`
**Plan doc:** Hyperagent thread `cmokf2twq0gsv06adlij0glqs`
```
