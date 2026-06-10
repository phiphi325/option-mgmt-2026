# Fixture 11 — Low confidence → NO_OP

| | |
|---|---|
| **Regime** | `LOW_IV_RANGE` (chosen so no specific rule fires for the position/profile combo) |
| **Expected matched rule** | `hold_no_op` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `NO_OP` |
| **M1.11b path exercised** | not exercised (no actions to dispatch) |
| **M1.12 path exercised** | not exercised (no per-action ladder runs) |

## Scenario

The market is range-bound with low IV, the user holds a small (200-share)
MSFT position with no existing puts or calls, and their profile style is
`balanced` (not `income`, so `wheel_on_low_iv_range` doesn't fire). With
flow score weak and the regime score modest, the composite tentative
confidence drops below the `hold_no_op` rule's `confidence_lte: 0.30`
threshold and the catch-all NO_OP rule fires.

The pipeline emits zero per-action selections (NO_OP has no legs), so
the parallel tuples (`strike_selections`, `downgrades`, `executions`,
`collar_structures`) are all empty. The Confidence Composer's
`illiquidity_penalty` is 0 (no actions to fill). The final composite
`confidence` matches `recommendation.confidence` exactly.

## Engineered chain (`spot = 405.0`, healthy but uninteresting)

Standard 8-strike layout, mid-OTM/ITM puts and calls, no exotic prices.
Chain is liquid (OI/volume populated) so liquidity is not the problem —
the LOW signal-alignment + flow-score combination is.

## Inputs notes

- `regime = LOW_IV_RANGE` + `style = balanced` → no `wheel_on_low_iv_range`
  match.
- `iv_rank = 25.0` (< 50, so `high_iv_sell_call` doesn't fire).
- `has_long_put = False` + `drawdown_tolerance = 0.30` → no
  `buy_long_dated_put_low_iv_trend` (requires `≤ 0.20`).
- `has_short_call = False`, `has_short_put = False`, `has_long_put = False`
  → none of the position-state-conditional rules fire.
- `flow_score.confidence = 0.15` + `regime_score = 0.45` → composite
  tentative confidence lands below 0.30, triggering `hold_no_op`.

## Notable assertions

- `recommendation.actions == []` (NO_OP emits no actions)
- `strike_selections == []`, `executions == []`, `downgrades == []`,
  `collar_structures == []`
- `confidence == recommendation.confidence` (no downgrade delta)
- `escalated == False`
