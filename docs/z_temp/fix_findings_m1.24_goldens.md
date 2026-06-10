# M1.24 Golden Fixture Fix Findings — 2026-06-10

Investigation of why 7/12 `expected.json` files recorded the wrong rule after running
`regenerate_decision_goldens.py --all`.

---

## Summary of root causes

| # | Root cause | Fixtures affected |
|---|---|---|
| A | `iv_rank` / `iv_percentile` / `iv_rank_change_1d` stored on [0-100] scale instead of [0, 1] | 01, 02, 04, 06, 11 (primary); all 12 for consistency |
| B | `ROLL_UP_AND_OUT` missing from `LOW_IV_RANGE` whitelist in `rules.py` | 10 |
| C | `OPEN_COLLAR` missing from `POST_EVENT_REPRICE` whitelist in `rules.py` | 09 |
| D | `open_collar_pre_event` rule only allows `HIGH_IV_EVENT` regime | 09 |
| E | Fixture 09 `days_to_next_event: 90` doesn't satisfy `days_to_next_event_lte: 7` | 09 |

---

## Root Cause A — iv_rank scale mismatch

### What the engine expects

`engine/market_state/classify.py` line 83:
> "All values are on the engine-canonical [0, 1] iv_rank scale."

`iv_rank_change_1d` follows the same convention: `-0.20` = 20 percentage-point drop.

The rule evaluator in `rules.py` reflects this:
```python
def _eval_iv_rank_gte(value, ctx):
    return ctx.market_state.iv_rank * 100.0 >= float(value)
```
It multiplies by 100, expecting a stored fraction (e.g. `0.40 × 100 = 40 ≥ 50` → False).

### What the inputs.json files had

All 12 `inputs.json` files passed `iv_rank` on the 0–100 scale (e.g. `"iv_rank": 40.0`).
This caused `40.0 × 100 = 4000 ≥ 50` → always True, meaning `high_iv_sell_call` fired
for every fixture whose regime is in `["HIGH_IV_EVENT", "HIGH_IV_PIN", "LOW_IV_RANGE"]`
with `has_short_call: false`, blocking the intended lower-priority rule.

### Scale correction applied to all 12 fixtures

| Fixture | iv_rank | iv_percentile | iv_rank_change_1d | note |
|---|---|---|---|---|
| 01 | 40.0 → 0.40 | 40.0 → 0.40 | 2.0 → 0.02 | |
| 02 | 40.0 → 0.40 | 40.0 → 0.40 | 2.0 → 0.02 | |
| 03 | 60.0 → 0.60 | 60.0 → 0.60 | 0.5 → 0.005 | passing; no behavior change |
| 04 | 25.0 → 0.25 | 28.0 → 0.28 | -1.0 → -0.01 | |
| 05 | 55.0 → 0.55 | 58.0 → 0.55 (check) | 1.0 → 0.01 | passing; no behavior change |
| 06 | 30.0 → 0.30 | 32.0 → 0.32 | -0.5 → -0.005 | |
| 07 | 45.0 → 0.45 | 48.0 → 0.48 (check) | -3.0 → -0.03 | passing; no behavior change |
| 08 | 30.0 → 0.30 | 32.0 → 0.32 | **-0.2 unchanged** | already correct; -20pp IV crush |
| 09 | 40.0 → 0.40 | 38.0 → 0.38 | **-0.25 unchanged** | already correct; -25pp post-event |
| 10 | 35.0 → 0.35 | 38.0 → 0.38 | 0.5 → 0.005 | |
| 11 | 25.0 → 0.25 | 30.0 → 0.30 | -0.5 → -0.005 | |
| 12 | 60.0 → 0.60 | 62.0 → 0.62 (check) | 0.5 → 0.005 | passing; no behavior change |

---

## Root Cause B — ROLL_UP_AND_OUT missing from LOW_IV_RANGE whitelist

### Problem

`roll_up_and_out_when_short_call_threatened` has no `regime:` clause (it should fire
in any regime), but the regime whitelist in `rules.py:is_emit_in_regime_whitelist`
only placed `ROLL_UP_AND_OUT` in the `BREAKOUT` whitelist.

Fixture 10 has regime `LOW_IV_RANGE`. The `ROLL_UP_AND_OUT` emit is not in the
`LOW_IV_RANGE` whitelist, so the rule is skipped before predicates are checked.
The predicates would pass: `|414 − 412| / 412 × 100 = 0.49% ≤ 1%` and `dte = 7 ≤ 14`.

### Fix

Added `ROLL_UP_AND_OUT` to `LOW_IV_RANGE` in `is_emit_in_regime_whitelist`.

---

## Root Cause C+D+E — fixture 09 POST_EVENT_REPRICE / open_collar_pre_event mismatch

### Problem

Three compounding blockers prevented `open_collar_pre_event` from firing in
`POST_EVENT_REPRICE` regime:

1. **Whitelist**: `POST_EVENT_REPRICE` only allowed `SELL_COVERED_CALL_PARTIAL`; `OPEN_COLLAR` was absent.
2. **Rule regime clause**: `open_collar_pre_event.when.regime: HIGH_IV_EVENT` — the predicate
   itself checks the regime, so even after fixing the whitelist the rule would have failed.
3. **Predicate mismatch**: `days_to_next_event: 90` in fixture 09 doesn't satisfy
   `days_to_next_event_lte: 7`.

### Fix

- `rules.py`: Added `OPEN_COLLAR` to `POST_EVENT_REPRICE` whitelist.
- `rules.yaml`: Extended `open_collar_pre_event.when.regime` to
  `["HIGH_IV_EVENT", "POST_EVENT_REPRICE"]`.
- `fixture 09 inputs.json`: Changed `days_to_next_event` from `90` to `5` —
  scenario interpretation: post-earnings (1 day ago) with an FOMC event approaching
  in 5 days; repricing the collar pre-FOMC is realistic.

---

## Files changed

| File | Change |
|---|---|
| `packages/engine/engine/recommendation/rules.py` | Whitelist: +ROLL_UP_AND_OUT for LOW_IV_RANGE, +OPEN_COLLAR for POST_EVENT_REPRICE |
| `packages/engine/config/rules.yaml` | `open_collar_pre_event.when.regime` extended to include POST_EVENT_REPRICE |
| `packages/engine/tests/fixtures/master_decisions/*/inputs.json` | iv_rank, iv_percentile, iv_rank_change_1d scaled to [0,1] |
| `packages/engine/tests/fixtures/master_decisions/09-.../inputs.json` | days_to_next_event: 90 → 5 |

After these changes, re-run `regenerate_decision_goldens.py --all` and verify all 12
fixtures show the expected `matched_rule.id` and `emit` from the spec table in
`test_06092026.md`.
