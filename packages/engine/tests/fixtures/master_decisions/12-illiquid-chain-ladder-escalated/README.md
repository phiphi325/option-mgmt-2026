# Fixture 12 — Healthy regime + illiquid chain → ladder escalated (M1.12)

**STATUS: SCENARIO SPEC ONLY.** `inputs.json` to be authored in a follow-up
commit before the M1.24 PR flips from draft → ready-for-review. The replay
harness `test_master_decision_goldens.py::test_golden_decision_matches[12-illiquid-chain-ladder-escalated]`
soft-skips while `inputs.json` is absent.

| | |
|---|---|
| **Regime** | ``HIGH_IV_PIN` (or any regime where a non-collar rule fires on the position state)` |
| **Expected matched rule** | `high_iv_sell_call (or another non-collar rule)` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `varies (whichever non-collar rule fires)` |
| **M1.11b path exercised** | not exercised (non-collar emit) |
| **M1.12 path exercised** | **escalated=True** — the M1.12 downgrade ladder ran through its 2 rungs (per `liquidity_score / fill_confidence < 0.50`) without finding a fillable selection. |

## Scenario

A healthy regime triggers a non-collar emit (e.g. `SELL_COVERED_CALL_PARTIAL`) but the chain is so illiquid (OI ≤ 10, volume ≤ 5, spread > 1000 bps) that every candidate strike fails the M1.11 execution feasibility check. The M1.12 ladder retries with relaxed filters but still can't find a fill, escalates, and `DailyDecision.escalated = True`.

## Trigger conditions

Same regime + profile as fixture 03 (HIGH_IV_PIN, iv_rank=60), but chain prices set so all OTM calls have OI ≤ 10 + volume ≤ 5 + spread_bps ≥ 1000. The illiquidity penalty trickles through M1.10 confidence composer to a near-zero final confidence.

## TODO before authoring `inputs.json`

1. Pick a `spot` + 8-strike chain layout that places the rule's required
   strikes in plausible OTM/ITM zones.
2. Construct `MarketStateResult` with field values that produce the target
   regime (`regime_score` should dominate `all_scores` to make the choice
   unambiguous, even though the engine only reads `regime` directly).
3. Pick `PositionState` flags that satisfy this rule's predicates WITHOUT
   accidentally tripping a higher-priority rule's predicates.
4. Mirror the field shape from fixture 01 / 03 / 11 (already authored).
5. Run `uv run python scripts/regenerate_decision_goldens.py --fixture 12-illiquid-chain-ladder-escalated`
   locally to produce `expected.json`. Verify the recommendation engine
   matched `high_iv_sell_call (or another non-collar rule)`. Commit both files.
