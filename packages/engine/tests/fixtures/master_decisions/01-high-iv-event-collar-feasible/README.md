# Fixture 01 — HIGH_IV_EVENT, collar feasible

| | |
|---|---|
| **Regime** | `HIGH_IV_EVENT` |
| **Expected matched rule** | `open_collar_pre_event` (per `rules.yaml` + plan v1.2 §22.8) |
| **Expected emit** | `OPEN_COLLAR` |
| **M1.11b path exercised** | feasible — `collar_structures[0]` is a non-None `CollarStructure` with `intent=ZERO_COST` |
| **M1.12 path exercised** | not exercised (collar dispatch bypasses the ladder per §9.10) |

## Scenario

A pre-earnings setup: the user holds 200 MSFT shares with no existing put
protection, the market is in the `HIGH_IV_EVENT` regime (high IV + scheduled
near-term event), and earnings is 3 days out. The M1.9 `open_collar_pre_event`
rule fires (regime ∈ `HIGH_IV_EVENT` AND `days_to_next_event ≤ 7` AND
`has_long_put=False`), emitting `OPEN_COLLAR`.

The M1.11b dispatcher routes this to
`collar_builder.build(intents=[ZERO_COST])`, which finds a feasible zero-cost
collar pair on the engineered chain (4 puts × 4 calls with prices set so a
short call premium covers a long put within ±$0.10).

## Engineered chain (`spot = 400.0`, expiry 2026-06-19, 30 DTE)

| Strike | Type | bid | ask | mid | OI | Vol |
|---|---|---|---|---|---|---|
| 360 | PUT  | 0.495 | 0.505 | 0.500 | 5000 | 1000 |
| 370 | PUT  | 0.795 | 0.805 | 0.800 | 5000 | 1000 |
| 380 | PUT  | 0.995 | 1.005 | 1.000 | 5000 | 1000 |
| 390 | PUT  | 1.495 | 1.505 | 1.500 | 5000 | 1000 |
| 405 | CALL | 3.995 | 4.005 | 4.000 | 5000 | 1000 |
| 410 | CALL | 2.995 | 3.005 | 3.000 | 5000 | 1000 |
| 420 | CALL | 0.995 | 1.005 | 1.000 | 5000 | 1000 |
| 430 | CALL | 0.395 | 0.405 | 0.400 | 5000 | 1000 |

The collar builder's zero-cost solver picks the `380P / 420C` pair: `net_debit_credit ≈ 0.00` per share.

## Inputs notes

- `iv_rank = 40.0` (below 50 so `high_iv_sell_call` doesn't pre-empt
  `open_collar_pre_event`).
- `days_to_next_event = 3` triggers the collar rule's `days_to_next_event_lte: 7`
  predicate.
- `has_long_put = False` triggers the rule's `has_long_put: false` predicate.
- All other engine inputs use plausible mid-range values; none of them flip
  any other rule's predicate.

## Replay

```bash
cd packages/engine
uv run pytest tests/test_master_decision_goldens.py::test_golden_decision_matches -q -k 01-high-iv-event-collar-feasible
```

## Regenerate (after engine schema change)

```bash
cd packages/engine
uv run python scripts/regenerate_decision_goldens.py --fixture 01-high-iv-event-collar-feasible
```
