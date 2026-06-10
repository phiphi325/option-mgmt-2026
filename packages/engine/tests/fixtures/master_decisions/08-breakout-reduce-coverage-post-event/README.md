# Fixture 08 — BREAKOUT, IV crush after recent event → unwind some coverage

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[08-breakout-reduce-coverage-post-event]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | `BREAKOUT` |
| **Expected matched rule** | `reduce_coverage_on_breakout_post_event` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `REDUCE_COVERAGE` |
| **M1.11b path exercised** | not exercised |
| **M1.12 path exercised** | not exercised |

## Scenario

Post-event breakout with significant IV crush — the user previously sold calls into elevated IV, those positions are now favorable to close. The M1.9 rule `reduce_coverage_on_breakout_post_event` fires (regime = `BREAKOUT` AND `days_since_event ≤ 2` AND `iv_rank_change_1d ≤ -0.15` on the [0,1] scale, or ≤ -15 on the [0,100] scale).

## Trigger conditions

`regime = BREAKOUT`, `days_since_event = 1`, `iv_rank_change_1d = -0.20` (sharp drop), `has_short_call = True` (so there is coverage to reduce). The dispatcher closes some short-call contracts; `strike_selections` reflects the close legs.

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 08-breakout-reduce-coverage-post-event`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `reduce_coverage_on_breakout_post_event`. Commit both files.
