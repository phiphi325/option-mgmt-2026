# Tutorial: Master Decision Engine (`produce_daily_decision()` + `DailyDecision` + replay)

> **Audience.** First-year master's students in financial engineering; quant-developer onboarding; anyone consuming `DailyDecision` downstream (Today-screen UI, persistence layer, ML retrainer in Phase 4).
> **Prerequisites.** Read the [Market State](./market-state-engine.md), [Scoring Primitives](./scoring-primitives.md), [Flow Score](./flow-score-engine.md), and [Confidence Composer](./confidence-composer.md) tutorials first. You should be comfortable with `MarketStateResult`, `FlowScore`, the M1.9 `RecommendationResult` (matched-rule + actions), the M1.10 multiplicative composer, and the M1.11 + M1.12 execution + downgrade pipeline.
> **Reading time.** ~50 min careful read with the exercises; ~20 min skim.
> **Engine version covered.** `1.4.0` (M1.13) onward. The orchestrator and supporting types live in [`packages/engine/engine/decision/`](../../packages/engine/engine/decision); the persisted Postgres shape is defined in [`apps/api/app/db/migrations/versions/0001_init.py`](../../apps/api/app/db/migrations/versions/0001_init.py).
>
> **Disclaimer.** This tutorial is **educational material**. The Master Decision Engine is a decision-support component, not investment advice. See [`docs/disclaimers.md`](../disclaimers.md).

---

## Table of contents

1. [Why a Master Decision Engine?](#1-why-a-master-decision-engine)
2. [The `DailyDecision` contract](#2-the-dailydecision-contract)
3. [The §9.6 pipeline — wiring seven engines](#3-the-96-pipeline--wiring-seven-engines)
4. [Two-stage `compose()` — rule selection vs. execution feasibility](#4-two-stage-compose--rule-selection-vs-execution-feasibility)
5. [`inputs_hash` — canonical JSON and cross-environment determinism](#5-inputs_hash--canonical-json-and-cross-environment-determinism)
6. [`decision_id` — deterministic IDs and idempotent persistence](#6-decision_id--deterministic-ids-and-idempotent-persistence)
7. [The `escalated` flag — UI signal for low-liquidity decisions](#7-the-escalated-flag--ui-signal-for-low-liquidity-decisions)
8. [Replay safety — the three-pin lock](#8-replay-safety--the-three-pin-lock)
9. [End-to-end worked example](#9-end-to-end-worked-example)
10. [Plan deviations](#10-plan-deviations)
11. [Hands-on exercises](#11-hands-on-exercises)
12. [Further reading](#12-further-reading)
13. [Glossary](#13-glossary)

---

## 1. Why a Master Decision Engine?

### 1.1 The role in the architecture

By the time the decision pipeline reaches the Master Decision Engine,
six upstream engines have already done their jobs:

- **Market State Engine** has classified one of six `Regime`s.
- **Flow Score Engine** has produced a signed score + bias + confidence.
- **Recommendation Engine** has run the YAML rule pipeline.
- **Strike Selector** can pick concrete legs given an `Action`.
- **Execution Feasibility Module** can score liquidity / fill on those legs.
- **Confidence Composer** can multiplicatively combine six components.

What's missing is one function that knows _the order_, knows _which
outputs feed which inputs_, and produces a single `DailyDecision`
record that the API layer can persist for exact replay. That is the
Master Decision Engine's job:

```
MarketStateResult ──┐
FlowScore ──────────┤
PositionState ──────┼──► produce_daily_decision() ──► DailyDecision
UserStrategyProfile ┤
ChainSnapshot ──────┘                                    │
                                                         ▼
                                              daily_decisions row
                                              (Postgres, JSONB payload)
                                                         │
                                                         ▼
                                              Today-screen UI
                                              ML retrainer (Phase 4)
                                              what-if endpoint (M1.16)
```

`produce_daily_decision()` is the **single public entry point** to the
engine for the Today-screen flow. Same inputs → byte-identical
`DailyDecision`. That property is what makes the M1.16
`/engine/what-if` endpoint cacheable and what makes the Phase 4 ML
retrainer reproducible — every persisted decision can be re-derived
exactly from `(engine_version, weights_version, inputs_hash)` plus
the source-of-truth inputs.

### 1.2 Where it sits in the architecture

The Master Decision Engine is the top of the engine layer in the §5
layer cake. Above it sits the FastAPI service that hydrates inputs
from Postgres and persists results. Below it sit every other engine
module:

```
┌───────────────────────────────────────────────┐
│ FastAPI route /engine/daily-plan (M1.14)      │  ← hydrates inputs, persists output
├───────────────────────────────────────────────┤
│ engine.decision.produce_daily_decision()      │  ← M1.13 (this tutorial)
├───────────────────────────────────────────────┤
│ engine.recommendation.recommend()             │  ← M1.9
│ engine.execution.downgrade_if_needed()        │  ← M1.12
│   wraps engine.strike_selector.select_strikes │  ← M1.7
│   wraps engine.execution.assess()             │  ← M1.11
│ engine.confidence.compose()                   │  ← M1.10
├───────────────────────────────────────────────┤
│ engine.market_state.classify()  (caller-supplied) │  ← M1.4
│ engine.flow_score.compute()    (caller-supplied)  │  ← M1.5b
├───────────────────────────────────────────────┤
│ engine.scoring.* / engine.greeks / engine._utils  │  ← M1.1-M1.6
└───────────────────────────────────────────────┘
```

### 1.3 Design objectives

The Master Decision Engine inherits ADR-0005 (pure-function
discipline) plus four of its own:

1. **One call, one row.** The API layer makes one function call
   per request. The result is a single `DailyDecision` that maps 1-to-1
   to a `daily_decisions` Postgres row.
2. **Three-pin replay lock.** Every decision carries
   `(engine_version, weights_version, inputs_hash)` so the exact bytes
   can be regenerated from the persisted inputs at any future date.
3. **No silent loss of information.** The persisted row carries
   every upstream engine's output (echoed in fields like
   `market_state`, `flow_score`, `recommendation`, `executions`)
   for UI drill-down and Phase 4 ML training. The wire format is
   denormalized on purpose.
4. **Determinism over performance.** The pipeline is single-pass with
   one deliberate two-stage step (the [two-stage `compose()`](#4-two-stage-compose--rule-selection-vs-execution-feasibility)).
   It runs in under 100 ms on a single user; we trade modest extra
   work for byte-identical idempotency.

---

## 2. The `DailyDecision` contract

The §7 `DailyDecision` schema is the wire format. The engine ships a
frozen dataclass with the same field names; the API layer projects to
a Pydantic model for JSON serialization. Same shape both ways.

```python
@dataclass(frozen=True)
class DailyDecision:
    # Identity
    decision_id: str
    as_of: datetime
    ticker: str
    spot: float

    # Upstream echoes (denormalized for UI drill-down + replay)
    user_profile_snapshot: UserStrategyProfile
    market_state: MarketStateResult
    flow_score: FlowScore
    recommendation: RecommendationResult

    # Per-action concrete legs and execution feasibility (parallel tuples,
    # zip 1:1 with `recommendation.actions`).
    strike_selections: tuple[StrikeSelection, ...]
    downgrades: tuple[DowngradeResult, ...]
    executions: tuple[Execution, ...]

    # Final scoring (post-downgrade)
    confidence: float
    confidence_breakdown: ConfidenceBreakdown

    # Replay pins
    inputs_hash: str
    engine_version: str
    weights_version: str

    # Operational metadata
    data_freshness: tuple[tuple[str, int | float | bool], ...] = ()
    disclaimers: tuple[str, ...] = ()
    escalated: bool = False
```

Twenty fields, grouped by purpose. Three things worth noting:

### 2.1 Why so many fields?

The engine could have produced a leaner output — just `actions`,
`confidence`, `disclaimers` would technically suffice for the Today
screen. But:

- **Replay** needs the original inputs (`user_profile_snapshot`,
  `market_state`, `flow_score`) so we can re-run the engine after a
  weights bump and compare.
- **UI drill-down** lets the user click "why was this recommended?"
  and walk back through every upstream signal.
- **Phase 4 ML** consumes `(state, decision, outcome)` triples.
  Without the upstream state in the row, you'd need to JOIN four
  other tables on `inputs_hash` to reconstruct the picture.
- **Debug-by-row.** A single SELECT against `daily_decisions`
  carries everything to reproduce the decision offline.

The denormalization cost is JSONB bytes. The savings are debuggability
and audit-readiness.

### 2.2 Why frozen dataclasses (not Pydantic)?

The engine convention is frozen `dataclasses` per ADR-0005 (the same
choice as `MarketStateResult`, `FlowScore`, `RecommendationResult`,
`Execution`, `DowngradeResult`). Three reasons:

1. **No runtime validation cost** — Pydantic v2 is fast but still
   validates on construction; the engine already validates upstream
   (range checks in `ConfidenceInputs.__post_init__`, etc.).
2. **Cheaper hashing** — frozen dataclasses are immediately
   `inputs_hash`-friendly via `dataclasses.fields()` introspection.
3. **Same field names as the Pydantic projection** — the API layer
   does `model.model_validate(asdict(decision))` and the names line
   up 1:1. No transformation, just type-system translation.

### 2.3 Parallel tuples for per-action data

`strike_selections`, `downgrades`, and `executions` are all
`tuple[T, ...]` with the same length as `recommendation.actions`. The
i-th entry of each tuple describes the i-th action. This pattern
shows up in three places on `DailyDecision` and is the most natural
fit for the M1.9 multi-action emit codes:

```python
for i, action in enumerate(decision.recommendation.actions):
    print(action.emit)                       # e.g. SELL_COVERED_CALL_PARTIAL
    print(decision.strike_selections[i])     # concrete strike
    print(decision.downgrades[i].iterations) # 0 = no retry, 1+ = ladder ran
    print(decision.executions[i].suggested_order_type)  # LIMIT / MARKETABLE_LIMIT
```

For `OPEN_COLLAR` (which has two legs), the i-th `StrikeSelection`
contains both legs inside its `.legs` tuple; the action itself stays
single.

---

## 3. The §9.6 pipeline — wiring seven engines

The orchestrator runs in four stages. Each stage's output feeds the
next stage's input. The whole thing is one pure function:

```
                              ┌────────────────────────────────────┐
                              │ STAGE 1: tentative recommendation │
                              ├────────────────────────────────────┤
MarketStateResult  ────────► │                                    │
FlowScore          ────────► │  recommend(market_state, flow_score,│
PositionState      ────────► │            positions, profile,      │
UserStrategyProfile ───────► │            rules,                   │
RuleSpec[]         ────────► │            weights,                 │
Weights            ────────► │            illiquidity_penalty=0)   │
                              └──────────┬─────────────────────────┘
                                         │
                                         ▼ tentative `RecommendationResult`
                                          (one or more `Action`s)
                              ┌────────────────────────────────────┐
                              │ STAGE 2: per-action downgrade      │
                              ├────────────────────────────────────┤
                              │  for each action:                   │
                              │    downgrade_if_needed(action,      │
                              │                       chain_snapshot)│
                              │                                    │
                              │  → DowngradeResult per action:      │
                              │    (final_selection, final_execution,│
                              │     iterations, escalated, notes)   │
                              └──────────┬─────────────────────────┘
                                         │
                                         ▼ per-action `Execution`s
                              ┌────────────────────────────────────┐
                              │ STAGE 3: final compose()           │
                              ├────────────────────────────────────┤
                              │  illiquidity_penalty =              │
                              │    max(liquidity_penalty(ex)        │
                              │        for ex in executions)        │
                              │                                    │
                              │  inputs = compute_confidence_inputs(│
                              │    market_state, flow_score,        │
                              │    profile, illiquidity_penalty)    │
                              │                                    │
                              │  (final_confidence, breakdown) =    │
                              │    compose(inputs, weights)         │
                              └──────────┬─────────────────────────┘
                                         │
                                         ▼ final `(confidence, ConfidenceBreakdown)`
                              ┌────────────────────────────────────┐
                              │ STAGE 4: assembly                  │
                              ├────────────────────────────────────┤
                              │  inputs_hash = compute_inputs_hash(.│
                              │  decision_id = "dd_" + h[:12] + "_"│
                              │                + as_of.timestamp() │
                              │  escalated = any(dr.escalated …)   │
                              │  return DailyDecision(…)            │
                              └────────────────────────────────────┘
```

### 3.1 Why is `market_state` + `flow_score` an input, not computed inline?

`engine.market_state.classify()` takes 18 inputs (per §22.3 — `iv_rank`,
`iv_percentile`, `hv_30`, `expected_move_pct`, `max_pain`, …).
`engine.flow_score.compute()` takes a `ChainSnapshot` plus options.

Threading those 25+ arguments through `produce_daily_decision()` would
add nothing the API layer doesn't already track. The API service in
`apps/api` already hydrates those values from Postgres rows (per
`/data/market/latest` + `/data/iv/history` + the user's profile and
positions). The clean separation: **the API layer composes upstream
engines; M1.13 stitches their results together**.

This also keeps `produce_daily_decision()`'s signature stable across
schema changes to upstream engines. When M1.5c adds a new field to
`FlowScore`, the orchestrator's signature doesn't change — only the
API hydration code does.

### 3.2 Why call `recommend()` before `select_strikes()`?

Plan §9.6 sketches `select_strikes()` running before `recommend()`. The
modern engine inverts this:

- The M1.9 rule pipeline emits `EmittedAction` codes
  (`SELL_COVERED_CALL_PARTIAL`, `ROLL_UP_AND_OUT`, `OPEN_COLLAR`, …)
  that drive leg structure.
- The M1.7 Strike Selector reads an `Action` (with `parameters.target_delta`
  + `parameters.target_dte`) and picks concrete contracts.

So the rule pipeline must run first — there's no `Action` to pass to
`select_strikes()` until `recommend()` has emitted one. M1.13 calls
`recommend()` once with `illiquidity_penalty=0.0`, then iterates over
its emitted actions to drive the strike selector via `downgrade_if_needed()`.

### 3.3 Empty-action shortcuts

Three emit codes produce zero legs in V1: `REDUCE_COVERAGE`,
`MONETIZE_PUT`, and `NO_OP`. They represent "close an existing leg"
(REDUCE / MONETIZE) or "do nothing today" (NO_OP). The orchestrator
handles them cleanly:

- The M1.7 Strike Selector returns `StrikeSelection(emit=...,
  legs=(), skipped_reason="...")`.
- The M1.12 downgrade callback short-circuits: empty `final_selection`,
  `final_execution.aggregate_fill_confidence = 1.0` (trivially
  fillable), `escalated = False`.
- The M1.10 composer's `illiquidity_penalty` stays at `0.0` (no leg
  to be illiquid).
- The final `confidence` equals the tentative `recommendation.confidence`
  exactly (no execution feedback applied).

This is by design: the user shouldn't see a confidence drop for
"close my existing put" just because the chain's PUT side is thinly
quoted.

---

## 4. Two-stage `compose()` — rule selection vs. execution feasibility

### 4.1 The chicken-and-egg problem

The M1.10 Confidence Composer takes an `illiquidity_penalty` as one
of its six inputs. The M1.11 Execution Feasibility module produces
that value from a `StrikeSelection`. But the strike selection depends
on the matched rule's `Action`, which the M1.9 rule pipeline picks
using its `confidence_lte:` clause on `hold_no_op`. And `hold_no_op`'s
threshold (0.30) is checked against… the confidence number that
depends on `illiquidity_penalty`. Circular.

Resolutions:

1. **Iterate to fixed point.** Run `recommend()` → `downgrade()` →
   `recommend()` again with the new penalty, repeat until the matched
   rule stabilizes. Theoretically rigorous; in practice oscillates
   when the chain is right at the boundary.
2. **Run `recommend()` once with `illiquidity_penalty=0`.** Rule
   selection sees the pre-execution view; final confidence reflects
   the post-execution view. Two stages; no iteration.
3. **Remove `confidence_lte:` from the rule pipeline.** Surfaces fill
   confidence elsewhere (e.g. as a hard filter on the action list).
   Reduces the rule pipeline's expressive power.

M1.13 picks **option 2**. The two-stage pattern is explicit and
finite. The rule pipeline sees a slightly optimistic confidence (no
fill cost yet); the final number is honest.

### 4.2 What the user sees

`DailyDecision.confidence` is the final post-execution number, in
`[0, 1]`. `DailyDecision.recommendation.confidence` is the
pre-execution number that the rule pipeline used.

For a healthy chain (good fill), they're approximately equal —
fill is high → `illiquidity_penalty` near 0 → composer's
`penalty_multiplier` near 1.

For an illiquid chain, the final drops below the tentative — fill is
low → `illiquidity_penalty` near 1 → composer applies the v2.0
`weights.yaml` `liquidity` cap (0.25) multiplicatively → confidence
drops by up to 25%.

For an `escalated` case (no ladder rung rescued the action), the
final drops even more — same penalty math, but `liquidity_penalty`
is at its worst.

### 4.3 The aggregate penalty

When `recommendation.actions` has more than one action (e.g.
`ROLL_UP_AND_OUT` has 2 legs — close old + open new, both with their
own fill characteristics), the orchestrator takes the **max** over
per-action `liquidity_penalty(execution)`:

```python
aggregate_penalty = 0.0
for action in tentative_rec.actions:
    dr = downgrade_if_needed(action=action, chain_snapshot=chain_snapshot)
    penalty = liquidity_penalty(dr.final_execution)
    if penalty > aggregate_penalty:
        aggregate_penalty = penalty
```

Why max (not mean)? Because the user pays for the *worst-fill* leg —
if you have to cross the spread on one leg, you've already incurred
the slippage. The composer's `illiquidity_penalty` is meant to
discount the strategy's overall confidence by the worst-link cost.

---

## 5. `inputs_hash` — canonical JSON and cross-environment determinism

### 5.1 What goes in the hash

```python
inputs_hash = compute_inputs_hash(
    as_of=...,
    ticker=...,
    chain_snapshot=...,
    positions=...,
    profile=...,
    market_state=...,
    flow_score=...,
)
```

Seven inputs cover everything the decision can depend on:

- `as_of` and `ticker` — the request identity
- `chain_snapshot` — the option chain projection (underlying + spot +
  contracts tuple)
- `positions` — current short calls / long puts / shares
- `profile` — the user's strategy profile snapshot
- `market_state` — the M1.4 classify result
- `flow_score` — the M1.5b compute result

Notably **excluded**:

- `engine_version` — already a separate pin
- `weights_version` — already a separate pin
- `data_freshness` and `disclaimers` — operational metadata, not
  logical inputs

The three pins together (`engine_version`, `weights_version`,
`inputs_hash`) define a unique replay coordinate.

### 5.2 Canonical JSON conventions

The hash is `"sha256:" + hexdigest(canonical_json.encode("utf-8"))`.
Canonical JSON means:

- **Keys sorted alphabetically** (`json.dumps(..., sort_keys=True)`)
- **No whitespace** (`separators=(",", ":")`)
- **UTF-8 encoded** (Python default)
- **Dates → ISO-8601** (`YYYY-MM-DD` for `date`, RFC 3339 for `datetime`)
- **Naive datetimes assumed UTC** (`.isoformat() + "Z"`)
- **Floats with full precision** (no rounding — `repr` semantics)
- **Tuples → lists** (JSON has no tuple)
- **Frozen dataclasses → dict of fields** (recursive via `dataclasses.fields()`)
- **Pydantic models → `model_dump(mode="json")`** (recursive, JSON-clean)
- **Enums → `.value`** (or the str content for StrEnum)
- **Frozensets → sorted lists** (stable order via `sorted(…, key=repr)`)
- **Unknown types → `repr(value)`** (defensive fallback)

These rules ensure that:

```python
compute_inputs_hash(...)  # on Python 3.14 (CI)
==
compute_inputs_hash(...)  # on Python 3.11
==
compute_inputs_hash(...)  # on Python 3.9 (sandbox)
```

for the same logical inputs. Cross-environment determinism matters
because the same `inputs_hash` may be computed in different processes
(API service, retrainer, debugger) and the database query must
match the row regardless.

### 5.3 Why naive datetimes are UTC-normalized

A naive datetime (no `tzinfo`) is ambiguous — is it local? UTC?
Some other zone? Without a convention, two callers could produce
different ISO strings for what they thought was the same instant.

`_canonical()` normalizes naive datetimes by appending `"Z"`:

```python
if isinstance(value, datetime):
    if value.tzinfo is None:
        return value.isoformat() + "Z"   # assume UTC
    return value.isoformat()              # already aware
```

This makes "naive = UTC" the engine-wide convention. The API layer
(which knows the user's timezone) should pass aware datetimes when
they care; the engine treats naive as UTC for replay safety.

### 5.4 Why the `"sha256:"` prefix

The 64-character hex digest is visually indistinguishable from a git
SHA. The `"sha256:"` prefix:

- Makes the algorithm explicit (future-proof if we ever migrate to
  BLAKE3 or similar)
- Survives JSON round-trips (it's just a string)
- Makes "is this an inputs hash?" trivially greppable

Length: 7 ("sha256:") + 64 = 71 characters.

---

## 6. `decision_id` — deterministic IDs and idempotent persistence

### 6.1 The construction

```python
decision_id = f"dd_{inputs_hash.split(':', 1)[1][:12]}_{int(as_of.timestamp())}"
```

`dd_` prefix + first 12 hex chars of the inputs hash + as_of unix
timestamp. Example:

```
dd_cfc2bd03288c_1779312600
```

The 12-hex prefix (48 bits of entropy) is enough to make collisions
astronomically unlikely (probability ~10⁻¹³ at 10K decisions/day for
a century).

### 6.2 Why deterministic IDs?

Most databases give you a random UUID4 per row. That works fine
unless you want **idempotent persistence** — two API calls with
identical inputs should produce the same row, not two.

Plan §7 specifies that `/engine/daily-plan` uses
`INSERT ... ON CONFLICT (user_id, inputs_hash) DO RETURNING`. If the
client retries on a network blip, it gets the same `decision_id`
back. The UI's "Today screen" can cache by `decision_id` and never
double-render.

If the `decision_id` were random, retries would either:
- Create duplicate rows (bad)
- Race against the UNIQUE constraint and return 409 (annoying for
  clients to handle)

Deterministic IDs make the idempotent-write story clean.

### 6.3 Why include `as_of` in the ID?

The `inputs_hash` alone could be used, but it doesn't carry a
timestamp. If a user pulls a decision at 10am and then re-pulls at
2pm with identical inputs (chain still cached), we want two rows —
one per decision-time — not a single row that overwrites the
earlier one.

`as_of.timestamp()` distinguishes them. Same inputs at the same
instant → same id (idempotent). Same inputs at different instants →
different ids (one row per logical decision).

---

## 7. The `escalated` flag — UI signal for low-liquidity decisions

`DailyDecision.escalated: bool` is set by the orchestrator:

```python
escalated = any(dr.escalated for dr in downgrades)
```

It propagates the M1.12 ladder-exhausted signal up to the decision
level. The UI uses it to:

- Show a "low liquidity warning" badge on the Today screen
- Suggest the user verify the limit-price band before submitting
- (Phase 2+) Hide the one-click "submit to broker" button when
  `escalated=True` until the user explicitly acknowledges

The flag is `True` when at least one per-action ladder couldn't
rescue the fill. The action is still emitted (the rule pipeline
matched it; downgrade tried its best); the user just needs to know
that the engine's confidence already discounted the strategy by the
full liquidity cap.

For a 0-action recommendation (NO_OP, REDUCE_COVERAGE without legs),
`escalated` is always `False` — there's nothing to be illiquid.

---

## 8. Replay safety — the three-pin lock

### 8.1 The three pins

Every `DailyDecision` carries three version stamps:

| Pin | Source | What it covers |
|---|---|---|
| `engine_version` | `packages/engine/engine/version.py` | Code in `engine/` |
| `weights_version` | `packages/engine/config/weights.yaml` | Confidence weights |
| `inputs_hash` | `compute_inputs_hash(...)` | All logical inputs |

A `(engine_version, weights_version, inputs_hash)` triple identifies
a decision exactly. Given the same triple, `produce_daily_decision()`
returns byte-identical output on any Python ≥ 3.9 with the engine
package installed.

### 8.2 Why the three are separate columns

The persisted `daily_decisions` row carries each pin as its own
Postgres column (per §6 schema), not buried in the JSONB payload:

```sql
CREATE TABLE daily_decisions (
  ...
  payload          jsonb NOT NULL,
  weights_version  text NOT NULL,
  engine_version   text NOT NULL,
  inputs_hash      text NOT NULL,
  UNIQUE (user_id, inputs_hash)
);
```

This lets the DB:

- Index on `inputs_hash` for instant cache lookups
- Run "show me every decision from before the weights v2.1 bump"
  queries without parsing JSONB
- Enforce the per-user idempotency UNIQUE constraint

### 8.3 What replay looks like in practice

```python
# Original decision (Oct 2026)
decision = produce_daily_decision(...)
db.persist(decision)  # daily_decisions row

# Replay in Phase 4 ML training (May 2027)
row = db.query("SELECT * FROM daily_decisions WHERE id = ...").one()
historical_inputs = db.query_inputs_for(row.inputs_hash, row.as_of)

# To re-run with the OLD engine and weights:
old_engine_image = docker.pull(f"engine:{row.engine_version}")
replayed_decision = old_engine_image.produce_daily_decision(**historical_inputs)
assert replayed_decision.inputs_hash == row.inputs_hash
assert replayed_decision.confidence == row.confidence

# To re-run with the CURRENT engine (1.4.0) and weights (v2.0):
current_decision = produce_daily_decision(**historical_inputs)
# current_decision.inputs_hash == row.inputs_hash  (inputs unchanged)
# current_decision.confidence may differ           (weights/code changed)
```

The pin triple is what makes "what would we have recommended last
month under the new calibration?" trivially answerable.

---

## 9. End-to-end worked example

Let's walk through a single `produce_daily_decision()` call from top
to bottom.

### 9.1 The inputs

A HIGH_IV_PIN regime with a clean chain, two weeks before earnings,
held 100 shares with no existing options:

```python
chain = ChainSnapshot(
    underlying="MSFT",
    spot=415.0,
    as_of=date(2026, 5, 20),
    contracts=(
        OptionContract(strike=415.0, option_type=OptionType.CALL,
                       bid=4.25, ask=4.30, mid=4.275,
                       iv=0.28, open_interest=3000, volume=200, ...),
        # ... more contracts ...
    ),
)

positions = PositionState(underlying_shares=100)

profile = UserStrategyProfile(
    risk_tolerance=RiskTolerance.MODERATE,
    style=ProfileStyle.BALANCED,
    drawdown_tolerance=0.15,
    # ...
)

market_state = MarketStateResult(
    regime=Regime.HIGH_IV_PIN, regime_score=0.75,
    iv_rank=0.65, trend_strength=0.30, ...,
    days_to_next_event=14, next_event_kind="earnings",
)

flow_score = FlowScore(
    score=40.0, bias=Bias.BULLISH,
    confidence=0.70,
    # ...
)
```

### 9.2 Stage 1 — Tentative recommendation

`recommend()` runs with `illiquidity_penalty=0.0`. The M1.9 rule
pipeline:

1. Computes confidence via M1.10 compose (penalty=0):
   - `flow_alignment` ≈ 0.55
   - `structure_alignment` ≈ 0.30
   - `regime_match` = 0.75
   - `signal_alignment` ≈ 0.725
   - `event_risk_penalty` ≈ 0.53 (14 days to earnings)
   - `illiquidity_penalty` = 0.0
   - positive ≈ 0.57; penalty_mult ≈ 0.84
   - confidence ≈ 0.48
2. Evaluates rules in YAML order. `high_iv_sell_call`:
   - `regime ∈ [HIGH_IV_EVENT, HIGH_IV_PIN, LOW_IV_RANGE]` ✓
   - `iv_rank_gte: 50` → 0.65 ≥ 0.50 ✓
   - `has_short_call: false` ✓
   - MATCH → emits `SELL_COVERED_CALL_PARTIAL`
3. Returns `RecommendationResult(actions=(Action(emit=SELL_COVERED_CALL_PARTIAL,
   parameters={"target_dte":30, "target_delta":0.35, ...}),),
   matched_rule=MatchedRule("high_iv_sell_call", ...),
   confidence=0.48, ...)`.

### 9.3 Stage 2 — Per-action downgrade

For the single `SELL_COVERED_CALL_PARTIAL` action,
`downgrade_if_needed()` runs:

1. Calls `select_strikes()` → picks the 415 ATM call as the
   nearest-delta-0.35 strike.
2. Calls `assess()` → on (bid=4.25, ask=4.30, mid=4.275, OI=3000,
   vol=200): `spread_bps=117`, `liquidity_score≈0.88`,
   `fill_confidence≈0.66`. Per-leg `fill_confidence > 0.50` →
   no downgrade needed.
3. Returns `DowngradeResult(iterations=0, escalated=False,
   final_selection=..., final_execution=...,)`.

The aggregate `illiquidity_penalty` is then
`1.0 - 0.66 = 0.34`.

### 9.4 Stage 3 — Final compose

```python
inputs = compute_confidence_inputs(
    market_state=ms,
    flow_score=fs,
    profile=profile,
    illiquidity_penalty=0.34,
)
# inputs.illiquidity_penalty = 0.34 (was 0.0 in stage 1)

(final_confidence, breakdown) = compose(inputs, DEFAULT_WEIGHTS)
# penalty_mult = (1 - 0.30*0.53) * (1 - 0.25*0.34) = 0.841 * 0.915 = 0.770
# final_confidence = clip01(0.57 * 0.770) ≈ 0.44
```

So the final confidence (0.44) is lower than the tentative (0.48) by
about 4 percentage points — the illiquidity penalty bit into the
multiplier.

### 9.5 Stage 4 — Assembly

```python
inputs_hash = compute_inputs_hash(as_of=..., ticker="MSFT",
                                  chain_snapshot=chain, positions=positions,
                                  profile=profile, market_state=ms,
                                  flow_score=fs)
# inputs_hash = "sha256:cfc2bd03288cd18f...d4d7788acc4"

decision_id = "dd_cfc2bd03288c_1779312600"

decision = DailyDecision(
    decision_id=decision_id,
    as_of=as_of,
    ticker="MSFT",
    spot=415.0,
    user_profile_snapshot=profile,
    market_state=ms,
    flow_score=fs,
    recommendation=tentative_rec,      # confidence=0.48 here
    strike_selections=(...,),
    downgrades=(dr,),
    executions=(dr.final_execution,),
    confidence=0.44,                   # FINAL (post-downgrade)
    confidence_breakdown=breakdown,
    inputs_hash="sha256:cfc2bd03288c...",
    engine_version="1.4.0",
    weights_version="v2.0",
    data_freshness=(),
    disclaimers=DEFAULT_DISCLAIMERS,
    escalated=False,
)
```

The Today screen renders:

> **Recommendation: SELL COVERED CALL (partial)**
> Sell 1 short call at strike $415, 30 DTE, target delta 0.35.
> Limit price band $4.27 – $4.28. Liquidity score 0.88.
> **Confidence: 44%** — driven by HIGH_IV_PIN regime + bullish flow,
> reduced by earnings in 14 days and a 117-bps spread.
> *Educational only. Not financial advice. Verify with broker.*

---

## 10. Plan deviations

M1.13 implements §9.6 with three documented deviations:

### 10.1 Two-stage `compose()`

Plan §9.6 pseudocode calls `compose()` once with `liquidity_penalty(exe)`.
M1.13 calls it twice (once inside `recommend()` with penalty=0, once
externally with the real penalty). Necessary because the rule pipeline
needs a confidence number to evaluate `confidence_lte:`, but the
penalty depends on the action that the rule emits. Two-stage is the
finite, deterministic resolution.

### 10.2 `recommend()` before `select_strikes()`

Plan §9.6 calls `select_strikes()` before `recommend()`. M1.13 reverses
this. The M1.9 rule pipeline emits the `EmittedAction` codes that
drive leg structure (single short call? collar with put? roll up
and out?) — without the matched rule, the Strike Selector has no
`Action` to consume. Modern engine flow is recommend-first.

### 10.3 `market_state` + `flow_score` as inputs (not computed inline)

Plan §9.6 calls `classify()` and `compute()` inside the orchestrator.
M1.13 takes pre-computed `MarketStateResult` + `FlowScore` instead.
Reason: `classify()` has 18 inputs (per §22.3), `compute()` has 5;
the API layer already hydrates these from Postgres rows. Threading
25+ arguments through the orchestrator adds nothing the API doesn't
already track. The API layer composes upstream engines; M1.13
stitches their results.

All three deviations are recorded in CHANGELOG `[1.4.0]` and were
green-lit during M1.13 design review.

---

## 11. Hands-on exercises

These exercises assume the repo is cloned and the engine package is
installed (`cd packages/engine && uv sync --dev`).

### Exercise 1 — Round-trip a `DailyDecision` through `compute_inputs_hash`

Build a minimal `DailyDecision` from the [§9.4 fixture](#92-stage-1--tentative-recommendation)
inputs. Confirm that:
- Two calls to `produce_daily_decision(...)` with the same arguments
  return byte-identical results (`a == b`).
- `compute_inputs_hash(...)` returns the same string both times.
- Changing `as_of` by one second changes `decision_id` but not
  `inputs_hash`.

### Exercise 2 — Where does the penalty actually bite?

Pick three call contracts at different liquidity levels:

| Strike | bid | ask | OI | volume | Expected fill |
|---|---|---|---|---|---|
| 415 (ATM) | 4.25 | 4.30 | 3000 | 200 | ≈ 0.66 |
| 420 | 2.0 | 2.5 | 200 | 30 | ≈ 0.20 |
| 425 | 1.0 | 2.5 | 50 | 3 | ≈ 0.02 |

For each chain composition (one healthy strike; one moderate strike;
one illiquid strike), run `produce_daily_decision(...)` and compare:

- `recommendation.confidence` (pre-execution)
- `decision.confidence` (post-execution)
- `decision.escalated`
- `decision.downgrades[0].iterations`

What's the relationship between `iterations` and the post-/pre-confidence
delta?

### Exercise 3 — Cross-Python-version determinism

Compute `inputs_hash` for the same logical inputs on:
- Python 3.9 with the conftest StrEnum shim (sandbox)
- Python 3.11 (CI mid-tier)
- Python 3.14 (CI)

Are they identical? If you find a discrepancy, what's the most likely
culprit? (Hint: look at `_canonical()` and how it handles datetimes
and StrEnums.)

### Exercise 4 — Two-stage compose semantics

Construct an input where the **rule selected differs** between the
single-pass and two-stage models. Specifically: find an
`(market_state, flow_score, chain_snapshot)` triple where:

- The tentative `recommend()` (penalty=0) gives a confidence above
  0.30, so `hold_no_op` doesn't fire and (say) `high_iv_sell_call`
  matches.
- The final post-downgrade confidence drops below 0.30 due to a
  catastrophically illiquid chain.

What should the engine do? Re-run the rule pipeline with the new
confidence? Accept that the rule matched and live with the low final
confidence? Discuss in light of plan §9.6 and ADR-0008's "M1.13
stitching layer is the replaceable boundary".

### Exercise 5 — Persist and replay

Pick a `DailyDecision` from your test fixtures and serialize it
manually to a JSON blob (mimicking what the API layer's Pydantic
projection would produce). Then:

1. Persist the JSON to a flat file.
2. In a separate Python process, load the JSON.
3. Reconstruct the inputs (`market_state`, `flow_score`, …) from the
   `DailyDecision` itself.
4. Re-call `produce_daily_decision(...)` with those reconstructed
   inputs.
5. Assert: the new `DailyDecision` has the same `inputs_hash` and
   the same `confidence`.

What part of the round-trip is the trickiest? (Hint: Pydantic's
`model_dump(mode="json")` projects `Decimal` to string; reading it
back requires `model_validate()` to coerce.)

---

## 12. Further reading

- **Plan v1.2** (Hyperagent thread `cmokf2twq0gsv06adlij0glqs`):
  - §7 — `DailyDecision` Pydantic schema (the wire format M1.13 mirrors as a frozen dataclass).
  - §9.6 — Master Decision Engine pseudocode (informs M1.13 with the three documented deviations).
  - §6 — `daily_decisions` Postgres schema (where the orchestrator's output lands).
  - §17 M1.13 — milestone scope and acceptance.
- **ADRs**:
  - [ADR-0001](../decisions/0001-engine-first-architecture.md) — engine-first design.
  - [ADR-0003](../decisions/0003-confidence-multiplicative.md) — multiplicative confidence (consumed by M1.13).
  - [ADR-0005](../decisions/0005-engine-pure-function-discipline.md) — pure-function discipline (M1.13 stays pure; the API layer owns I/O).
  - [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) — Phase 4 ML node-swap (M1.13 stitching layer is the replaceable boundary).
- **Sibling tutorials**:
  - [`market-state-engine.md`](./market-state-engine.md) — produces `MarketStateResult`.
  - [`flow-score-engine.md`](./flow-score-engine.md) — produces `FlowScore`.
  - [`scoring-primitives.md`](./scoring-primitives.md) — `*ScoreResult` pattern.
  - [`confidence-composer.md`](./confidence-composer.md) — the M1.10 multiplicative composer that M1.13 invokes twice.
- **Code**:
  - [`packages/engine/engine/decision/`](../../packages/engine/engine/decision/) — the M1.13 module.
  - [`packages/engine/tests/test_decision.py`](../../packages/engine/tests/test_decision.py) — 40 tests at 100% line coverage; pins pipeline integration, `compute_inputs_hash` invariants, determinism.
  - [`apps/api/app/db/migrations/versions/0001_init.py`](../../apps/api/app/db/migrations/versions/0001_init.py) — `daily_decisions` table DDL.

---

## 13. Glossary

| Term | Definition |
|---|---|
| `DailyDecision` | The frozen-dataclass output of `produce_daily_decision()`. Twenty fields; 1:1 with a `daily_decisions` Postgres row. |
| `produce_daily_decision()` | The M1.13 orchestrator entry point. Pure function per ADR-0005. |
| `inputs_hash` | `"sha256:" + 64-hex` over canonical JSON of all engine inputs. Replay-stable across environments. |
| `decision_id` | `"dd_" + inputs_hash[:12] + "_" + as_of.timestamp()`. Deterministic from inputs; enables idempotent persistence. |
| `escalated` | `True` iff at least one per-action M1.12 downgrade ladder ran out of options. Surfaced to the UI as a "low liquidity" badge. |
| Two-stage `compose()` | The deliberate decoupling of rule selection (pre-execution view) from final confidence (post-execution view). Resolves the chicken-and-egg dependency between rule pipeline and fill quality. |
| Three-pin lock | `(engine_version, weights_version, inputs_hash)` — uniquely identifies a replayable decision. Persisted as separate Postgres columns. |
| `data_freshness` | Operational metadata (engine doesn't compute; API hydrates). Tuple of `(key, value)` pairs describing input staleness. |
