# Fixture 09 — POST_EVENT_REPRICE, no put → open zero-cost collar

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[09-post-event-reprice-collar]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | `POST_EVENT_REPRICE` |
| **Expected matched rule** | `open_collar_pre_event (regime allowlist includes POST_EVENT_REPRICE per §9.10 integration rule)` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `OPEN_COLLAR` |
| **M1.11b path exercised** | **feasible** — second collar fixture, distinct from 01 by regime + post-event context |
| **M1.12 path exercised** | not exercised |

## Scenario

Just after an earnings event the user wants insurance — the gap behavior and residual IV crush make a zero-cost collar attractive. The M1.11b dispatcher routes the `OPEN_COLLAR` emit through `collar_builder.build(intents=[ZERO_COST])` for the second time in the suite. Distinct from fixture 01 because the regime context exercises the §9.10 Integration rule's full disjunction.

## Trigger conditions

`regime = POST_EVENT_REPRICE`, `days_since_event = 1`, `iv_rank_change_1d = -0.25`, `gap_pct = 0.03`, `has_long_put = False`, `iv_rank = 40.0` (below `high_iv_sell_call` threshold).

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 09-post-event-reprice-collar`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `open_collar_pre_event (regime allowlist includes POST_EVENT_REPRICE per §9.10 integration rule)`. Commit both files.
