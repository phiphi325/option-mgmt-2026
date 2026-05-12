# Collar Builder — `engine.collar_builder.build()`

> **Disclaimer.** Educational material only. The engine described here is
> not investment advice. Read [`docs/disclaimers.md`](../disclaimers.md)
> before applying anything from this tutorial to a real position.

## Audience + prerequisites

| Field | Value |
|---|---|
| **Audience** | 1st-year MFE students, quant developers, options traders new to collars |
| **Prerequisites** | [`market-state-engine.md`](./market-state-engine.md), [`flow-score-engine.md`](./flow-score-engine.md), [`confidence-composer.md`](./confidence-composer.md). The Master Decision Engine tutorial is *not* a prerequisite — the Collar Builder is a standalone module — but reading it gives useful context. |
| **Engine version** | `1.5.0` ([§Patch v1.1 §9.10](../phased-design/msft-option-risk-management-engine-phased-plan.md)) |
| **Reading time** | ~45 min careful read · ~15 min skim |
| **Milestone** | M1.11a ([dev spec](../phased-design/phase-1/m1.11a-collar-builder-engine.md), [retrospective](../phased-design/phase-1/review/m1.11a-retrospective.md)) |

## Table of contents

1. [What a collar is, and why an engine needs one](#1-what-a-collar-is-and-why-an-engine-needs-one)
2. [The three V1 intents](#2-the-three-v1-intents)
3. [The public API: `build()`](#3-the-public-api-build)
4. [The shape: `CollarLeg`, `CollarStructure`](#4-the-shape-collarleg-collarstructure)
5. [End-to-end worked example](#5-end-to-end-worked-example)
6. [Inside the solver: grid search + intent objectives](#6-inside-the-solver-grid-search--intent-objectives)
7. [Where the Collar Builder fits in the decision pipeline](#7-where-the-collar-builder-fits-in-the-decision-pipeline)
8. [Edge cases and degradation](#8-edge-cases-and-degradation)
9. [Exercises](#9-exercises)
10. [Glossary](#10-glossary)

---

## 1. What a collar is, and why an engine needs one

A **collar** is a three-leg structure built around an existing long
stock position:

1. The long stock itself (already owned — the engine doesn't open this).
2. A long out-of-the-money **put** (downside floor).
3. A short out-of-the-money **call** (upside cap).

The put protects against a drop below its strike `K_put`; the call
caps gains above its strike `K_call`. The cost of the put is partly
or fully paid for by the premium received from selling the call. When
the call premium **exactly equals** the put premium, the structure
is a "zero-cost collar" — net premium ≈ 0.

```
                          spot  K_call
                          │     │
P&L ───────────────────╮  │  ╭──────────────────
                       │     │   (capped above K_call)
                       │     │
        protected ─────╮     │
        floor          │     │
                  ────╮│     │
              ───╮    │      │
         (long  │     │      │
          put   │     │      │
          kicks │     │      │
          in)   │     │      │
                K_put  spot   K_call
```

The collar is the **canonical structural strategy** for a long-term
holder who's worried about an event (earnings, macro print, vol
regime change) but doesn't want to sell the underlying. It's
explicitly called out in master plan §9.10 as a first-class engine
(not a sub-mode of the Recommendation Engine) because users invoke
it directly — "show me 3 collar candidates" — independent of the
Master Decision flow.

Three flavors fit three different stories.

## 2. The three V1 intents

The Collar Builder produces ranked candidates for each requested
intent. Different intents optimize different things.

| Intent | Per-share net premium | Story |
|---|---|---|
| `zero_cost` | ≈ 0 (within ±$0.10) | "Protect me at zero out-of-pocket cost. Give up just enough upside to pay for the put." |
| `income` | Negative (credit) | "I want premium income. I'll accept a closer cap on the upside and less downside protection in exchange for getting paid." |
| `defensive` | Positive (debit) | "I'm worried. Maximize my downside floor. I'm willing to pay a small net debit (≤ 0.5% of position notional) for deeper protection." |

The choice of intent is the **user's** — the engine doesn't decide
which intent to recommend. (Master Decision auto-call when integrated
in M1.11b will pin `intents=[ZERO_COST]` per §9.10's integration
contract; the standalone `POST /engine/collar-builder` endpoint, M1.16a,
will let the user request 1–3 intents side-by-side.)

## 3. The public API: `build()`

```python
from engine.collar_builder import build, CollarIntent

structures = build(
    spot=400.0,                      # MSFT spot at decision time
    underlying_qty=200,              # 200 shares held → 2 contracts
    chain=chain_snapshot,            # ChainSnapshot from engine.types
    profile=user_profile,            # UserStrategyProfile (M0.6)
    market_state=market_state,       # MarketStateResult (M1.4)
    flow_score=flow_score,           # FlowScore (M1.5b)
    intents=[CollarIntent.ZERO_COST, CollarIntent.INCOME, CollarIntent.DEFENSIVE],
    horizon_days=45,                 # default; max DTE to consider
    coverage_ratio=1.0,              # default = profile.max_coverage_pct
)
```

Signature, full:

```python
def build(
    *,
    spot: float,
    underlying_qty: int,
    chain: ChainSnapshot,
    profile: UserStrategyProfile,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    intents: list[CollarIntent] | None = None,    # default: all three
    horizon_days: int | None = None,              # default: 45
    coverage_ratio: float | None = None,          # default: profile.max_coverage_pct
    weights: Weights | None = None,               # default: confidence DEFAULT_WEIGHTS (v2.0)
) -> list[CollarStructure]:
    ...
```

### Required arguments

- **`spot`** — current MSFT price (must match `chain.spot`).
- **`underlying_qty`** — total shares the user holds. **Minimum 100**;
  the function raises `ValueError` below that (you can't collar
  fewer than 100 shares per contract).
- **`chain`** — `ChainSnapshot` (Pydantic, frozen) carrying every
  option contract for the underlying.
- **`profile`** — `UserStrategyProfile` (Pydantic, frozen). Two fields
  matter directly:
  - `drawdown_tolerance` — minimum downside protection in percent.
    Default 0.15 (15%). The protective put's strike must satisfy
    `(spot − K_put) / spot ≥ drawdown_tolerance` (halved for `income`
    intent — half the protection in exchange for credit).
  - `max_coverage_pct` — default for `coverage_ratio`.
- **`market_state`** — M1.4 output. Used to drive the confidence
  composition heuristics (regime affinity, IV signal).
- **`flow_score`** — M1.5b output. Used for the `flow_alignment`
  confidence input.

### Optional arguments

- **`intents`** — list of `CollarIntent` enum values. Default: all three.
  Order in the input is order in the output; intents with no feasible
  solution are silently skipped (so `len(output) ≤ len(input)`).
- **`horizon_days`** — max days-to-expiry to consider. Default 45.
  Expirations strictly within `(0, horizon_days]` are included.
- **`coverage_ratio`** — fraction of position to collar. Default:
  `profile.max_coverage_pct`. Resolved contracts =
  `floor(underlying_qty × coverage_ratio / 100)`. If that's 0,
  `build()` raises.
- **`weights`** — M1.10 `Weights`. Default `DEFAULT_WEIGHTS` (v2.0).

### What `build()` raises

| Error | When |
|---|---|
| `ValueError("underlying_qty must be >= 100")` | `underlying_qty < 100` |
| `ValueError("horizon_days must be positive")` | `horizon_days ≤ 0` |
| `ValueError("coverage_ratio must be in (0, 1]")` | `coverage_ratio` outside that range |
| `ValueError("... resolves to 0 contracts")` | `(qty × ratio) // 100 == 0` |

### What `build()` does *not* raise

- An intent with no feasible candidate **does not raise**. It's just
  absent from the output. This is intentional — a real chain on a
  low-vol day may not have a feasible `zero_cost` pair, and the
  caller (M1.11b's dispatcher) needs to gracefully degrade, not
  trap.

## 4. The shape: `CollarLeg`, `CollarStructure`

```python
@dataclass(frozen=True)
class CollarIntent(StrEnum):
    ZERO_COST = "zero_cost"
    INCOME    = "income"
    DEFENSIVE = "defensive"

@dataclass(frozen=True)
class CollarLeg:
    kind: Literal["PUT", "CALL"]
    side: Literal["BUY", "SELL"]
    strike: float
    expiry: date
    qty: int                     # contracts (not shares)
    delta: float                 # signed: call ∈ (0, 1], put ∈ [-1, 0)
    iv: float
    bid: float
    ask: float
    mid: float
    premium: float               # signed: +paid (debit), -received (credit)

@dataclass(frozen=True)
class CollarStructure:
    name: str                              # "Zero-cost 30d collar 380/420"
    intent: CollarIntent
    horizon_days: int                      # actual DTE of the chosen expiry
    long_put: CollarLeg
    short_call: CollarLeg
    net_debit_credit: float                # +debit / −credit; per share
    max_gain: float                        # at expiry; per share
    max_loss: float                        # at expiry; per share (negative)
    upside_breakeven: float
    downside_breakeven: float
    capped_upside_pct: float               # (K_call − spot) / spot
    protected_downside_pct: float          # (spot − K_put) / spot
    confidence: float                      # M1.10 composite, [0, 1]
    confidence_breakdown: ConfidenceBreakdown
    rationale: tuple[str, ...]             # ~3 short prose lines
    risks: tuple[str, ...]                 # ~3 short prose lines
    invalidation: tuple[str, ...]          # conditions that nullify thesis
    execution: Execution                   # M1.11 result for combined legs
    score: float = 0.0                     # internal tie-break score
```

### Sign conventions, distilled

- **`delta`**: signed by `kind`. Calls are positive (in (0, 1]); puts
  are negative (in [-1, 0)). Always.
- **`premium`**: signed by `side`. `BUY` is positive (you paid debit);
  `SELL` is negative (you received credit). Always.
- **`net_debit_credit = long_put.premium + short_call.premium`** —
  positive means net debit (you paid more for the put than the call
  paid you); negative means net credit. Per share.

All P&L fields are **per share**, not per contract. Multiply by
`long_put.qty × 100` to get position-level dollars.

## 5. End-to-end worked example

Let's build a 30-day collar against 200 shares of MSFT at spot $400,
with `drawdown_tolerance = 0.05` (the V1 test profile).

### Step 0 — Chain data

The seed chain (`tests/_collar_test_helpers.py`):

| Strike | Type | Bid | Ask | Mid | OI | Vol |
|--------|------|-----|-----|-----|-----|-----|
| 360 | PUT | 0.495 | 0.505 | 0.50 | 5,000 | 1,000 |
| 370 | PUT | 0.795 | 0.805 | 0.80 | 5,000 | 1,000 |
| 380 | PUT | 0.995 | 1.005 | 1.00 | 5,000 | 1,000 |
| 390 | PUT | 1.495 | 1.505 | 1.50 | 5,000 | 1,000 |
| 395 | PUT | 1.995 | 2.005 | 2.00 | 5,000 | 1,000 |
| 405 | CALL | 3.995 | 4.005 | 4.00 | 5,000 | 1,000 |
| 410 | CALL | 2.995 | 3.005 | 3.00 | 5,000 | 1,000 |
| 420 | CALL | 0.995 | 1.005 | 1.00 | 5,000 | 1,000 |
| 430 | CALL | 0.395 | 0.405 | 0.40 | 5,000 | 1,000 |
| 440 | CALL | 0.145 | 0.155 | 0.15 | 5,000 | 1,000 |

All contracts expire 30 days from `chain.as_of`.

### Step 1 — Filter puts by `drawdown_tolerance`

`drawdown_tolerance = 0.05` means `(spot − K_put) / spot ≥ 0.05`, i.e.
`K_put ≤ 380`. Qualifying puts: 360 (10% protection), 370 (7.5%),
380 (5%).

For `income`, the threshold halves to 0.025 (2.5%), so 390 (2.5%)
also qualifies.

### Step 2 — Filter calls by delta band

The Collar Builder uses intent-specific delta target bands (see
[`structures.py`](https://github.com/csupenn/option-mgmt-2026/blob/main/packages/engine/engine/collar_builder/structures.py)):

| Intent | Target Δ (short call) | Band (±width/2) |
|--------|----------------------|-----------------|
| `zero_cost` | 0.25 | [0.20, 0.30] |
| `income` | 0.35 | [0.30, 0.40] |
| `defensive` | 0.20 | [0.15, 0.25] |

The V1 `_approx_delta()` proxy (used when the chain doesn't publish
deltas) gives:

| Strike | Δ proxy | Bands matched |
|--------|---------|--------------|
| 405 | 0.45 | none |
| 410 | 0.40 | `income` |
| 420 | 0.30 | `zero_cost`, `income` |
| 430 | 0.20 | `zero_cost`, `defensive` |
| 440 | 0.10 | none |

### Step 3 — Grid search per intent

For each intent, evaluate every (`K_put`, `K_call`) pair that passes
filters. The solver builds a full `CollarStructure` for each pair
(includes the M1.11 Execution Feasibility call) and applies an
intent-specific objective.

**ZERO_COST** — minimize `|net_debit_credit|` within ±$0.10:

| Pair | Net | Pass? | Winner? |
|------|-----|-------|---------|
| 380P (1.00) + 420C (1.00) | 0.00 | ✓ | **WINS** (residual 0.00) |
| 360P (0.50) + 430C (0.40) | +0.10 | ✓ | runner-up |
| ...all other pairs | > 0.10 residual | filtered | — |

Output: `Zero-cost 30d collar 380/420`, net 0.00, 5% downside / 5%
capped upside.

**INCOME** — maximize net credit subject to `capped_upside_pct ≥ 4%`:

| Pair | Net | Capped % | Pass? | Winner? |
|------|-----|----------|-------|---------|
| 360P (0.50) + 420C (1.00) | −0.50 | 5.0% | ✓ | **WINS** (most credit) |
| 370P (0.80) + 420C (1.00) | −0.20 | 5.0% | ✓ | runner-up |
| ...with 410C | various | 2.5% | ✗ (capped < 4%) | filtered |

Output: `Income 30d collar 360/420`, net −0.50 credit, 10% downside /
5% capped upside.

**DEFENSIVE** — maximize `protected_downside_pct` subject to
`net_debit ≤ 0.5% × position_notional`:

| Pair | Net (per share) | Protection | Pass? | Winner? |
|------|-----------------|-----------|-------|---------|
| 360P (0.50) + 430C (0.40) | +0.10 | 10.0% | ✓ | **WINS** (max protection) |
| 370P (0.80) + 430C (0.40) | +0.40 | 7.5% | ✓ | runner-up |
| 380P (1.00) + 430C (0.40) | +0.60 | 5.0% | ✓ | runner-up |

Output: `Defensive 30d collar 360/430`, net +0.10 debit, 10% downside /
7.5% capped upside.

### Step 4 — What the caller sees

```python
results = build(spot=400.0, underlying_qty=200, chain=..., profile=...,
                market_state=..., flow_score=...)

# Three structures, intent-ordered (matching the default
# intents = [ZERO_COST, INCOME, DEFENSIVE]).
[
    CollarStructure(name="Zero-cost 30d collar 380/420", intent=ZERO_COST, ...),
    CollarStructure(name="Income 30d collar 360/420",    intent=INCOME,    ...),
    CollarStructure(name="Defensive 30d collar 360/430", intent=DEFENSIVE, ...),
]
```

## 6. Inside the solver: grid search + intent objectives

The solver lives in [`structures.py`](https://github.com/csupenn/option-mgmt-2026/blob/main/packages/engine/engine/collar_builder/structures.py).
Per master plan §9.10, the algorithm is:

```
for each requested intent:
    for each candidate expiration in (0, horizon_days]:
        calls = filter_by_delta_band(chain, intent, expiry)
        puts  = filter_by_protection(chain, intent, profile, expiry)
        for (call, put) in cross_product(calls, puts):
            structure = build_full_structure(call, put, ...)
            if structure.net_debit > intent.max_debit:  continue
            if not passes_liquidity_floor(structure):    continue
            objective = intent_specific_objective(structure)
            update best_so_far if objective wins
    yield best_so_far (or skip intent if no winner)
```

Three intent-specific pieces:

| Intent | Filter | Objective | Tie-break |
|--------|--------|-----------|-----------|
| `zero_cost` | `\|put.mid − call.mid\| ≤ $0.10` pre-screen | `min(\|net_debit_credit\|)` | higher `score` |
| `income` | `capped_upside_pct ≥ 4%` | `min(net_debit_credit)` (most negative = most credit) | higher `score` |
| `defensive` | `net_debit ≤ 0.5% × position_notional` | `max(protected_downside_pct)` | higher `score` |

### The tie-break `score`

Per §9.10:

```
score = iv_score − event_score − illiquidity_penalty
```

- `iv_score` = `iv_rank / 100` (high IV = better for short premium).
- `event_score` = 0.5 if event in ≤ 5 days, 0.2 if ≤ 14 days, else 0.
- `illiquidity_penalty` = `1 − aggregate_fill_confidence`.

Range roughly `[-1, +1]`. Used only to disambiguate when the
intent-specific objective produces a tie.

### The liquidity floor

A pair must pass two thresholds (computed by M1.11 `assess()`):

- `aggregate_liquidity_score ≥ 0.40`
- `aggregate_fill_confidence ≥ 0.40`

(M1.11's per-aggregate downgrade threshold is 0.50; we filter at
0.40 and let the M1.12 downgrade ladder handle marginal cases. See
the [M1.11a retrospective finding #1](../phased-design/phase-1/review/m1.11a-retrospective.md#1-the-liquidity-floor-was-lowered-from-050-to-040-vs-dev-spec)
for why.)

### The proxy delta (V1 fallback)

When the chain doesn't publish per-contract deltas, `_approx_delta()`
substitutes a moneyness-linear proxy:

```python
moneyness = (spot - strike) / spot           # signed
delta_call =  clip(0.5 + 4.0 * moneyness, 0.01, 0.99)
delta_put  = -clip(0.5 + 4.0 * abs(moneyness), 0.01, 0.99)
```

This is correct in **ordering** (deeper OTM → smaller |Δ|) but off
by 5–15% vs. Black-Scholes for typical IV. M1.11b will thread the
M1.6 `engine.greeks.delta()` output into the solver so production
uses real Black-Scholes deltas; the proxy is preserved purely as
a fallback for chains missing the field.

## 7. Where the Collar Builder fits in the decision pipeline

```
                  ┌──────────────────────────────────┐
                  │  Master Decision Engine (M1.13)  │
                  │  produce_daily_decision()        │
                  └──────────────────────────────────┘
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
        Market State        Flow Score      Recommendation
        Engine              Engine          Engine
        (M1.4)              (M1.5b)         (M1.8/M1.9)
                                              │
                                              ▼
                                   recommendation.actions[]
                                              │
                                              ▼
                                   for each action:
                                      ┌───────────────────────┐
                                      │  intent dispatch      │
                                      │  (M1.11b — pending)   │
                                      └───────────────────────┘
                                              │
                          ┌───────────────────┼────────────────┐
                          ▼                                    ▼
                  Strike Selector                      Collar Builder
                  (M1.7)                               (M1.11a — THIS)
                  intent ∈ {sell_call,                 intent = collar
                            buy_put,                   build(intents=[ZERO_COST])
                            sell_put}                  → CollarStructure
                  → StrikeSelection
                                              │
                                              ▼
                                   Execution Feasibility
                                   (M1.11) + Downgrade
                                   ladder (M1.12)
                                              │
                                              ▼
                                   Confidence Composer
                                   (M1.10)
                                              │
                                              ▼
                                   DailyDecision
                                   (M1.13)
```

The Collar Builder is **invoked**:

1. **By the Master Decision Engine** when `recommendation.recommend()`
   emits an action with `emit_code == OPEN_COLLAR`. M1.11b wires this
   dispatch. Per §9.10, the integration auto-call uses
   `intents=[ZERO_COST]` only.
2. **Directly via the standalone endpoint** (`POST /engine/collar-builder`)
   when a user asks for collar candidates without going through the
   full decision pipeline. M1.16a will ship this endpoint; users
   typically request all three intents.

Today (post-M1.11a, pre-M1.11b) — neither call path is wired yet. The
module exists, is fully tested, and is ready for both integrations.

## 8. Edge cases and degradation

### "No feasible structure exists"

The Collar Builder returns an **empty list** (silently — no
exception) when:

- The intent's call delta band has no qualifying strikes in the chain.
- All candidate puts fail the `drawdown_tolerance` protective floor.
- All candidate pairs fail the liquidity floor.
- All candidate pairs exceed the intent's debit/credit constraint.

This is **graceful degradation**. M1.11b's dispatcher will respond by
filling a `NO_OP`-style placeholder in the `DailyDecision.collar_structures`
parallel tuple and propagating a low `liquidity_penalty` through the
Confidence Composer, so the final `confidence` reflects the gap.

### Float boundary cases

`net_debit_credit` is computed from `(bid + ask) / 2` mid-prices,
which carry float imprecision. The `ZERO_COST_TOLERANCE = 0.10`
pre-screen uses `>` (not `≥`), so a pair landing at exactly $0.10
is **kept**. The solver then produces a structure with
`net_debit_credit ≈ 0.09999999999999998` (one ULP below the
nominal $0.10). This is documented behavior — a pair at the tolerance
boundary is admitted.

### Tiny positions

`underlying_qty = 100` works (1 contract). `coverage_ratio = 0.5`
on `underlying_qty = 100` raises because `(100 × 0.5) // 100 = 0`
contracts. Real users should set `coverage_ratio = 1.0` on small
positions or hold more shares.

### Pinning behavior

Two intents may select the **same** put or call leg in their winning
pair (e.g., `zero_cost` and `defensive` both ended up using 360P
in the worked example). That's correct — the structures are
distinct because of their other leg. The solver doesn't enforce
exclusivity across intents.

## 9. Exercises

1. **Manually compute the winning ZERO_COST pair** for a chain where
   the 380P mid is 1.20 and the 420C mid is 1.15. What's the net
   debit/credit? Does the pair pass the ±$0.10 tolerance? Does it
   beat the (360P, 430C) pair?

2. **Walk through a DEFENSIVE no-feasible-structure case.** Given
   `profile.drawdown_tolerance = 0.20` (20%) and a chain whose
   deepest put is at strike 360 (10% protection), what does the
   solver return? Why is this **not** an exception?

3. **Reason about the `score` tie-break.** Two zero-cost pairs have
   identical `net_debit_credit = 0.00`. Pair A: `iv_rank = 80`,
   no event for 30 days, `aggregate_fill_confidence = 0.7`. Pair
   B: `iv_rank = 50`, event in 3 days, `aggregate_fill_confidence
   = 0.9`. Which wins by the §9.10 tie-break? What's the
   intuition?

4. **Sketch the dispatcher fix needed in M1.11b.** Given that
   `recommendation.actions[i].emit_code == EmittedAction.OPEN_COLLAR`,
   what should `decision.produce()` call? With which `intents=[]`?
   How does the result land in `DailyDecision`?

5. **Critique the proxy delta.** At spot=400, the 420 call's proxy
   delta is exactly 0.30 (in the ZERO_COST band [0.20, 0.30]).
   But the Black-Scholes delta for a 30-day call at 5% OTM with
   IV=30% is closer to 0.43. Why doesn't this break the engine's
   correctness? When would it?

## 10. Glossary

- **Collar** — long put + short call + long stock; floors downside,
  caps upside.
- **Zero-cost collar** — net premium ≈ 0; call premium pays for put.
- **Net debit** — positive `net_debit_credit`; user pays out-of-pocket.
- **Net credit** — negative `net_debit_credit`; user receives premium.
- **Protected downside %** — `(spot − K_put) / spot`. The percentage
  drop in spot before the put kicks in.
- **Capped upside %** — `(K_call − spot) / spot`. The percentage rise
  before the short call caps gains.
- **Position notional** — `spot × contracts × 100`. Used by the
  DEFENSIVE intent to scale the max-debit constraint.
- **Aggregate fill confidence** — `min(leg.fill_confidence)`. The
  weakest-link rule — a collar can only fill as well as its hardest
  leg.
- **Tie-break score** — `iv_score − event_score − illiquidity_penalty`.
  Range ~`[-1, +1]`. Disambiguates ties in the intent's primary
  objective.
- **`OPEN_COLLAR`** — the M1.9 emit code the Recommendation Engine
  produces when the rule pipeline matches a collar-recommending rule.
  Triggers the Master Decision Engine's collar dispatch (M1.11b).

## Further reading

- Master plan §9.10 — Collar Builder algorithm (canonical reference).
- M1.11a [dev spec](../phased-design/phase-1/m1.11a-collar-builder-engine.md)
  — what shipped vs. what was promised.
- M1.11a [retrospective](../phased-design/phase-1/review/m1.11a-retrospective.md)
  — post-merge code review including the 5-commit fix saga.
- M1.11b [dev spec](../phased-design/phase-1/m1.11b-collar-builder-integration.md)
  — how the Master Decision Engine wires this in (pending).
- M1.16a (pending) — the standalone `POST /engine/collar-builder`
  endpoint that exposes this module via HTTP.
