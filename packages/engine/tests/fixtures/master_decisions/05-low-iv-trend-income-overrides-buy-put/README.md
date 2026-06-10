# Fixture 05 — LOW_IV_RANGE, income style → sell covered call partial

**Scenario scope refined after spec review.** The original M1.24 spec framed
this fixture as `LOW_IV_TREND + style=income → SELL_COVERED_CALL_PARTIAL`,
but `rules.yaml` shows `high_iv_sell_call` only fires for regimes in
`{HIGH_IV_EVENT, HIGH_IV_PIN, LOW_IV_RANGE}` — NOT `LOW_IV_TREND`. With
`LOW_IV_TREND + iv_rank=55 + style=income` no rule matches and the pipeline
falls through to `hold_no_op` (which duplicates fixture 11's coverage).

To exercise the `high_iv_sell_call` rule under an income profile, we use
`LOW_IV_RANGE` instead (distinct from fixture 03's `HIGH_IV_PIN` setup by
regime AND by profile style: balanced → income).

| | |
|---|---|
| **Regime** | `LOW_IV_RANGE` |
| **Expected matched rule** | `high_iv_sell_call` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `SELL_COVERED_CALL_PARTIAL` |
| **M1.11b path exercised** | not exercised (non-collar emit) |
| **M1.12 path exercised** | not exercised (chain healthy) |

## Scenario

A range-bound market with elevated IV (above the 50 sell-premium threshold),
held by an income-style portfolio. The M1.9 `high_iv_sell_call` rule fires
(regime ∈ `{HIGH_IV_EVENT, HIGH_IV_PIN, LOW_IV_RANGE}` AND `iv_rank ≥ 50`
AND `has_short_call=False`), emitting `SELL_COVERED_CALL_PARTIAL`. The
dispatcher routes through `select_strikes(intent="sell_call")` to pick an
OTM call.

This fixture is distinct from fixture 03 (HIGH_IV_PIN, balanced) by both
regime and profile style — exercises the rule's regime-allowlist disjunction
on the LOW_IV_RANGE arm, and verifies that an income profile doesn't change
the matched rule when IV is high enough.

## Engineered chain (`spot = 410.0`, expiry 2026-06-19, ~30 DTE)

OTM calls priced for a clean SELL_COVERED_CALL_PARTIAL pick around the
profile's `delta_target_band`. Standard 8-strike layout (4 puts below spot,
4 calls above spot).

| Strike | Type | bid | ask | mid | OI | Vol |
|---|---|---|---|---|---|---|
| 380 | PUT  | 0.495 | 0.505 | 0.500 | 5000 | 1000 |
| 390 | PUT  | 0.795 | 0.805 | 0.800 | 5000 | 1000 |
| 400 | PUT  | 1.495 | 1.505 | 1.500 | 5000 | 1000 |
| 405 | PUT  | 2.495 | 2.505 | 2.500 | 5000 | 1000 |
| 415 | CALL | 2.495 | 2.505 | 2.500 | 5000 | 1000 |
| 420 | CALL | 1.495 | 1.505 | 1.500 | 5000 | 1000 |
| 425 | CALL | 0.795 | 0.805 | 0.800 | 5000 | 1000 |
| 435 | CALL | 0.295 | 0.305 | 0.300 | 5000 | 1000 |

## Inputs notes

- `regime = LOW_IV_RANGE` is in the `high_iv_sell_call` rule's regime allowlist.
- `iv_rank = 55.0` (≥ 50 triggers the rule).
- `has_short_call = False` is the rule's required position state.
- `style = income` (distinct from fixture 03's `balanced`).
- `days_to_next_event = 35` keeps us out of `open_collar_pre_event`'s
  `days_to_next_event_lte: 7` window.
- `iv_rank = 55` is above `wheel_on_low_iv_range`'s implicit IV ceiling (the
  rule has no IV upper bound, but rule-evaluation order picks the
  higher-priority `high_iv_sell_call` first when both could match —
  verify on first regen).
