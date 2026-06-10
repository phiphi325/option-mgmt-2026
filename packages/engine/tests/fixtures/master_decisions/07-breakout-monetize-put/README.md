# Fixture 07 — BREAKOUT with existing long put up 35% → harvest

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[07-breakout-monetize-put]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | `BREAKOUT` |
| **Expected matched rule** | `monetize_put_on_breakout` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `MONETIZE_PUT` |
| **M1.11b path exercised** | not exercised |
| **M1.12 path exercised** | not exercised |

## Scenario

A breakout regime where the user already holds a long put that has gained 30%+ as the market rallied. The M1.9 rule `monetize_put_on_breakout` fires (regime = `BREAKOUT` AND `has_long_put = True` AND `long_put_pnl_pct ≥ 0.30`), emitting `MONETIZE_PUT`. The dispatcher closes the existing put position.

## Trigger conditions

`regime = BREAKOUT`, `breakout_signal = 0.80` (high), `has_long_put = True`, `long_put_pnl_pct = 0.35`. Chain should have a healthy put strike matching the user's open position so the close has good execution feasibility.

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 07-breakout-monetize-put`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `monetize_put_on_breakout`. Commit both files.
