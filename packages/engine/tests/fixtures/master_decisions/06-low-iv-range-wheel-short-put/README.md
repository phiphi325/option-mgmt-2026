# Fixture 06 — LOW_IV_RANGE, income style → wheel (sell cash-secured put)

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[06-low-iv-range-wheel-short-put]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | `LOW_IV_RANGE` |
| **Expected matched rule** | `wheel_on_low_iv_range` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `WHEEL_SHORT_PUT` |
| **M1.11b path exercised** | not exercised |
| **M1.12 path exercised** | not exercised |

## Scenario

Range-bound market, low IV, user wants income. The M1.9 rule `wheel_on_low_iv_range` fires (regime = `LOW_IV_RANGE` AND `has_short_put=False` AND `profile_style = income`), emitting `WHEEL_SHORT_PUT`. The dispatcher routes through `select_strikes(intent="sell_put")` to pick a put strike below spot aligned with the profile's delta band.

## Trigger conditions

`regime = LOW_IV_RANGE`, `iv_rank = 30.0`, `trend_strength = 0.20` (flat), `style = income`, `has_short_put = False`, `has_long_put = False`. The position state should NOT have a long put (otherwise `buy_long_dated_put_low_iv_trend` would have the wrong regime; we're already in `LOW_IV_RANGE` not `LOW_IV_TREND`, so this isn't a concern).

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 06-low-iv-range-wheel-short-put`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `wheel_on_low_iv_range`. Commit both files.
