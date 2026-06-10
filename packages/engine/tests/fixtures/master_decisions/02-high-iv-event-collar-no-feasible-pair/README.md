# Fixture 02 — HIGH_IV_EVENT, no feasible collar (M1.11b degrade path)

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[02-high-iv-event-collar-no-feasible-pair]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | `HIGH_IV_EVENT` |
| **Expected matched rule** | `open_collar_pre_event` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `OPEN_COLLAR` |
| **M1.11b path exercised** | **degraded** — `collar_structures[0]` is None; `_dispatch_open_collar` returned an empty `StrikeSelection` with `skipped_reason="collar_builder_no_feasible_pair"`. |
| **M1.12 path exercised** | not exercised (collar dispatch bypasses the ladder) |

## Scenario

Same setup as fixture 01 (HIGH_IV_EVENT, pre-event, no long put) but with chain prices engineered so no put/call pair clears the collar builder's 0.40 liquidity floor AND the zero-cost `|net_debit_credit| ≤ $0.10` band simultaneously. The dispatcher receives an empty `build()` result and produces a synthetic empty `StrikeSelection` + trivially-fillable `Execution`.

## Trigger conditions

Same regime + position predicates as fixture 01, but the chain has either (a) very low OI / volume on all OTM strikes, or (b) put / call premiums that don't pair to ≈ $0.00 for any feasible delta-band combination.

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 02-high-iv-event-collar-no-feasible-pair`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `open_collar_pre_event`. Commit both files.
