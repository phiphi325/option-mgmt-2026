# Fixture 10 — Short call within 1% of spot, near expiry → roll up and out

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[10-roll-up-and-out-threatened-short-call]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | `any (rule triggers on position state, not regime; fixture uses `LOW_IV_RANGE` for variety)` |
| **Expected matched rule** | `roll_up_and_out_when_short_call_threatened` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `ROLL_UP_AND_OUT` |
| **M1.11b path exercised** | not exercised |
| **M1.12 path exercised** | not exercised (chain healthy) |

## Scenario

The user previously sold a covered call; spot has rallied and is now within 1% of the short-call strike, with DTE ≤ 14. The M1.9 rule `roll_up_and_out_when_short_call_threatened` fires (`has_short_call_within_pct: 1.0` AND `days_to_expiry_lte: 14`), emitting `ROLL_UP_AND_OUT`. The dispatcher routes through `select_strikes(intent="sell_call")` to pick a new higher-strike, longer-dated call to roll into.

## Trigger conditions

`has_short_call = True`, `nearest_short_call_strike ≈ spot * 1.005`, `nearest_short_call_dte = 7`. Choose `regime = LOW_IV_RANGE` + `iv_rank = 35.0` (below 50) so `high_iv_sell_call` doesn't pre-empt.

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 10-roll-up-and-out-threatened-short-call`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `roll_up_and_out_when_short_call_threatened`. Commit both files.
