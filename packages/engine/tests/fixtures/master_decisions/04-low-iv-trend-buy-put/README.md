# Fixture 04 — LOW_IV_TREND, conservative profile → buy long-dated put

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[04-low-iv-trend-buy-put]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | `LOW_IV_TREND` |
| **Expected matched rule** | `buy_long_dated_put_low_iv_trend` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `BUY_LONG_DATED_PUT` |
| **M1.11b path exercised** | not exercised (non-collar emit) |
| **M1.12 path exercised** | not exercised (chain healthy) |

## Scenario

A trending market with low IV and a conservative profile (drawdown tolerance ≤ 0.20). The M1.9 rule `buy_long_dated_put_low_iv_trend` fires (regime = `LOW_IV_TREND` AND `iv_rank ≤ 30` AND `has_long_put=False` AND `drawdown_tolerance ≤ 0.20`), emitting `BUY_LONG_DATED_PUT`. The dispatcher routes through `select_strikes(intent="buy_put")` and picks a deep-OTM put aligned with the profile's delta band.

## Trigger conditions

`regime = LOW_IV_TREND`, `iv_rank = 25.0` (≤ 30), `trend_strength = 0.65` (high), `has_long_put = False`, `drawdown_tolerance = 0.15`, `style = balanced` (so `wheel_on_low_iv_range` doesn't preempt — it requires `LOW_IV_RANGE` regime anyway, but worth being explicit).

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 04-low-iv-trend-buy-put`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `buy_long_dated_put_low_iv_trend`. Commit both files.
