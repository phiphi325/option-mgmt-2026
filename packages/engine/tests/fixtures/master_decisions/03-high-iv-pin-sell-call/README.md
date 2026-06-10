# Fixture 03 — HIGH_IV_PIN, sell covered call (partial)

| | |
|---|---|
| **Regime** | `HIGH_IV_PIN` |
| **Expected matched rule** | `high_iv_sell_call` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `SELL_COVERED_CALL_PARTIAL` |
| **M1.11b path exercised** | not exercised (non-collar emit) |
| **M1.12 path exercised** | not exercised (chain is healthy) |

## Scenario

Mid-cycle, near monthly opex, spot pinned near max-pain, elevated IV. The
M1.9 `high_iv_sell_call` rule fires (regime ∈ `{HIGH_IV_EVENT, HIGH_IV_PIN,
LOW_IV_RANGE}` AND `iv_rank ≥ 50` AND `has_short_call=False`), emitting
`SELL_COVERED_CALL_PARTIAL`.

The dispatcher routes this through the standard `downgrade_if_needed` →
`select_strikes` path; chain is liquid enough that no ladder downgrade
fires. The Confidence Composer's `illiquidity_penalty` stays near 0.

## Engineered chain (`spot = 415.0`, expiry 2026-06-19, ~30 DTE)

OTM calls priced for a clean `SELL_COVERED_CALL_PARTIAL` pick around the
profile's `delta_target_band`. Same 8-strike layout as fixture 01 but with
the spot shifted up so different strikes are OTM.

| Strike | Type | bid | ask | mid | OI | Vol |
|---|---|---|---|---|---|---|
| 380 | PUT  | 0.495 | 0.505 | 0.500 | 5000 | 1000 |
| 390 | PUT  | 0.795 | 0.805 | 0.800 | 5000 | 1000 |
| 400 | PUT  | 0.995 | 1.005 | 1.000 | 5000 | 1000 |
| 410 | PUT  | 1.795 | 1.805 | 1.800 | 5000 | 1000 |
| 420 | CALL | 2.995 | 3.005 | 3.000 | 5000 | 1000 |
| 425 | CALL | 1.995 | 2.005 | 2.000 | 5000 | 1000 |
| 430 | CALL | 0.995 | 1.005 | 1.000 | 5000 | 1000 |
| 440 | CALL | 0.395 | 0.405 | 0.400 | 5000 | 1000 |

## Inputs notes

- `iv_rank = 60.0` (≥ 50 triggers `high_iv_sell_call`).
- `regime = HIGH_IV_PIN` is in the rule's regime allowlist.
- `has_short_call = False` is the rule's required position state.
- `days_to_next_event = 21` keeps us out of `open_collar_pre_event`'s
  `days_to_next_event_lte: 7` window so the collar rule doesn't pre-empt.
- All other inputs use plausible mid-range values.
