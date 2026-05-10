# Tutorial: Flow Score Engine (`compute()` orchestrator + §9.3a V1 LOCKED contract)

> **Audience.** First-year master's students in financial engineering; quant-developer onboarding; anyone consuming `FlowScore` downstream (Recommendation Engine, Today screen UI, Confidence Composer).
> **Prerequisites.** Read the [Market State Engine tutorial](./market-state-engine.md) and the [Scoring Primitives tutorial](./scoring-primitives.md) first. You should be comfortable with options vocabulary (IV, OI, max pain, expected move, PCR, OI walls), with `clip01`, with the `*ScoreResult` pattern, and with how `gamma_score` splits magnitude from direction.
> **Reading time.** ~70 min careful read with the exercises; ~30 min skim.
> **Engine version covered.** `0.9.0` (M1.5b) and `0.10.0` (M1.6) onward. The orchestrator and supporting primitives live in [`packages/engine/engine/flow_score/`](../../packages/engine/engine/flow_score); the Black-Scholes Greeks consumed by the M1.6-activated `skew_25d` live in [`packages/engine/engine/greeks.py`](../../packages/engine/engine/greeks.py).
>
> **Disclaimer.** This tutorial is **educational material**. The Flow Score Engine is a decision-support component, not investment advice. See [`docs/disclaimers.md`](../disclaimers.md).

---

## Table of contents

1. [Why a Flow Score Engine?](#1-why-a-flow-score-engine)
2. [The V1 LOCKED `FlowScore` contract (§22.2)](#2-the-v1-locked-flowscore-contract-222)
3. [`compute()` — the orchestrator in twelve steps](#3-compute--the-orchestrator-in-twelve-steps)
4. [The five-component bullish + bearish formulas (§9.3a)](#4-the-five-component-bullish--bearish-formulas-93a)
5. [`sigmoid_pin()` — pin probability](#5-sigmoid_pin--pin-probability)
6. [Bias bucketing — `BULLISH / NEUTRAL / BEARISH / PIN_RISK`](#6-bias-bucketing--bullish--neutral--bearish--pin_risk)
7. [The §9.3a decision tree — `recommended_action`](#7-the-93a-decision-tree--recommended_action)
8. [Confidence and the explanation builder](#8-confidence-and-the-explanation-builder)
9. [V1 stubs and forward compatibility](#9-v1-stubs-and-forward-compatibility)
10. [End-to-end worked example](#10-end-to-end-worked-example)
11. [Hands-on exercises](#11-hands-on-exercises)
12. [Further reading](#12-further-reading)
13. [Glossary of symbols](#13-glossary-of-symbols)

---

## 1. Why a Flow Score Engine?

### 1.1 The role in the architecture

By the time the decision pipeline reaches the Flow Score Engine, the data layer
has already hydrated a `ChainSnapshot`, the M1.1–M1.3 primitives have rendered
the raw inputs into scalars, and the M1.4a / M1.5a scoring primitives have
distilled four single-question signals. What's still missing is one composite
that answers a different kind of question — not "is IV cheap?" or "where are
the gamma walls?" but:

> **Given everything visible in the chain, what is the dealer-flow regime
> right now, and what should a holder of MSFT covered-call positions do
> about it?**

That is the Flow Score Engine's job. It synthesizes OI walls, volume
imbalances, IV skew, futures basis, put–call ratios, dealer gamma exposure,
and pin pressure into a single bounded signed score and recommends one of
six concrete actions.

```
ChainSnapshot ──┐
                │
Spot + opex ────┼──► Flow Score Engine ──► FlowScore ──► Recommendation Engine
calendar        │     (compute())           contract       Today screen UI
Focus expiries──┘                                          Confidence Composer
                                                           DailyDecision (replay)
```

`compute()` is the **only public entry point**: pure, deterministic, fully
keyword-only. Same `ChainSnapshot` + spot + expiry-focus + opex distance →
byte-identical `FlowScore`. That property is the contract that the daily
`DailyDecision` replay system relies on (per [ADR-0005](../decisions/0005-engine-pure-function-discipline.md)).

### 1.2 Where it sits in the §9.11 wiring matrix

The plan v1.2 §9.11 wiring matrix tells us which engines consume which
upstream functions. The Flow Score Engine straddles three rows:

| Consumer | iv | structure | gamma | event | flow |
|---|:---:|:---:|:---:|:---:|:---:|
| Market State Engine (`classify`) | ✓ | ✓ |   | ✓ |   |
| **Flow Score Engine (orchestrator)** | ✓ |   | ✓ |   | (self) |
| Recommendation Engine |   | ✓ |   |   | ✓ |
| Confidence Composer | ✓ | ✓ |   | ✓ | ✓ |
| Collar Builder | ✓ |   |   | ✓ |   |
| Strike Selector | ✓ |   |   |   |   |

Two interpretations are worth noting:

- **Producer.** The Flow Score Engine is the producer of `FlowScore`, the
  `(score, bullish_score, bearish_score, bias, recommended_action, pin_probability,
  gamma_risk, gamma_sign, confidence, explanation, breakdown)` contract that
  the Recommendation Engine and Confidence Composer read.
- **Consumer.** Internally, `compute()` consumes `gamma_score()` (for the
  `gamma_risk` magnitude and `gamma_sign` direction) and the M1.5 / M1.2
  primitives (`compute_oi_walls`, `compute_dealer_gamma_proxy`,
  `compute_max_pain`, `pcr_volume`, `pcr_oi`). The matrix shows
  `iv` as a Flow Score Engine input too — but in V1 the IV signal flows
  in upstream through the Market State Engine's regime, not directly into
  `compute()`. The §9.3a formula leaves the door open for richer iv
  consumption in Phase 2 (see [§9](#9-v1-stubs-and-forward-compatibility)).

### 1.3 Design objectives

The Flow Score Engine inherits the engine-wide objectives from
[ADR-0005](../decisions/0005-engine-pure-function-discipline.md), plus three
of its own:

1. **One composite, six actions.** Downstream UI and the Recommendation
   Engine should never have to interpret signed scores against thresholds
   themselves. `compute()` does the bucketing.
2. **Schema-locked.** Per plan §22.2 the eleven `FlowScore` field names and
   semantics are V1 LOCKED. The Phase 4 ML node-swap
   ([ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md)) replaces
   the body of `compute()` with a learned classifier while keeping the
   contract byte-stable.
3. **Forward-compatible.** One of the five §9.3a components
   (`futures_basis`) remains a V1 stub returning 0; the previous stub
   for `skew_25d` was replaced with a real Black-Scholes-driven
   implementation in M1.6 (engine `0.10.0`). The math is intentionally
   sum-and-clip — the full 5-component formula activates **without
   recalibration** as each stub is replaced. Phase 2's futures service
   completes the picture.

---

## 2. The V1 LOCKED `FlowScore` contract (§22.2)

The plan calls this out explicitly: any change to the field names or
semantics of `FlowScore` is a **major** version bump. The Postgres column
names in `daily_decisions`, the TypeScript types in `packages/shared-types`,
the Today screen UI bindings, and the Recommendation Engine `rules.yaml` all
key off this exact shape.

```python
@dataclass(frozen=True)
class FlowScore:
    # Composite scores
    score: float              # signed, in [-100, 100]
    bullish_score: float      # [0, 100]
    bearish_score: float      # [0, 100]

    # Categorization
    bias: Bias                # BULLISH / NEUTRAL / BEARISH / PIN_RISK
    recommended_action: RecommendedAction  # one of 6 (see §7)

    # Specific signals
    pin_probability: float    # [0, 1]
    gamma_risk: float         # [0, 1]; magnitude only (sign separate)
    gamma_sign: int           # {-1, 0, +1}; dealer direction
    confidence: float         # [0, 1]; function of total OI in focus

    # Explainability
    explanation: str          # human-readable 2-4 sentence summary
    breakdown: dict[str, float]  # 13 per-component keys (stable names)
```

### 2.1 Composite scores

`bullish_score` and `bearish_score` are **independently weighted sums** of
the same five components, each side reading the opposing tail of every
input. They are NOT a softmax: both can be high (active two-sided flow),
both can be low (a sleepy chain).

`score = bullish_score − bearish_score`. This signed composite is what the
downstream UI plots on a "bias gauge" running from -100 (extreme bearish)
to +100 (extreme bullish). When the V1 stubs are active (skew = basis = 0),
`bullish_score` and `bearish_score` each cap at $0.30 + 0.25 + 0.10 = 65$,
so `score` can range only over $[-65, +65]$ in practice. When the stubs
are replaced the natural range opens up to the full $[-100, +100]$.

### 2.2 `Bias` enum

```python
class Bias(StrEnum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    PIN_RISK = "PIN_RISK"
```

`PIN_RISK` is a **first-class fourth state**, not a modifier on the other
three. The plan §9.3a bias mapping treats high pin probability as its own
regime because the appropriate response is qualitatively different: in
`PIN_RISK` the strategy whitelist shifts toward waiting and avoiding short
gamma until past opex, not toward bullish or bearish positioning.

The enum is a `StrEnum` so its string value is wire-stable. Adding a new
bias requires coordinated changes in the Postgres `bias` enum, the
TypeScript codegen, and any UI components that switch on it.

### 2.3 `RecommendedAction` enum

```python
class RecommendedAction(StrEnum):
    SELL_CALL_AGGRESSIVE = "SELL_CALL_AGGRESSIVE"
    SELL_CALL_PARTIAL = "SELL_CALL_PARTIAL"
    WAIT = "WAIT"
    BUY_PROTECTION = "BUY_PROTECTION"
    REDUCE_COVERAGE = "REDUCE_COVERAGE"
    MONITOR = "MONITOR"
```

Six actions — five concrete plus a fallback. The §9.3a decision tree
([§7](#7-the-93a-decision-tree--recommended_action)) maps from
`(score, gamma_risk, pin_probability)` to exactly one. The Recommendation
Engine and Strike Selector then translate the action into concrete strikes,
sizes, and roll dates per the user's profile.

### 2.4 Why three numbers for gamma?

The contract carries three gamma-related fields: `gamma_risk` (magnitude),
`gamma_sign` (direction), and indirectly the `_decide_action()` reads
`gamma_risk` to gate `SELL_CALL_AGGRESSIVE` vs `BUY_PROTECTION`. Why split?

The Scoring Primitives tutorial covers this in detail ([§8 Ex. 8](./scoring-primitives.md#exercise-8--gamma_score-sign-vs-magnitude)), but the punch line is:

- **Magnitude** (`gamma_risk`) is what gates aggressive premium selling.
  Selling calls when dealers are heavily long gamma (`gamma_risk ≥ 0.6`) is
  fine in absolute terms but the position carries little signal advantage.
- **Direction** (`gamma_sign`) is what gates buying protection. Buying puts
  when dealers are net short gamma above spot is qualitatively different
  from buying puts when they're net long — the first is leaning *with* a
  vol-amplifying flow, the second is leaning *against* it.
- The Confidence Composer's positive-weight math (§22.13) reads only the
  magnitude. Folding sign into the score would either lose direction (via
  `abs`) or break the positive-weight math (via clip).

### 2.5 `breakdown` keys

`breakdown` is a stable `dict[str, float]` with thirteen keys. Five
`bullish_*` keys, five `bearish_*` keys (symmetric), plus three
diagnostics:

| Key | Source | Use |
|---|---|---|
| `bullish_dist` / `bearish_dist` | wall distance, normalized | UI bar |
| `bullish_call_vol` / `bearish_put_vol` | volume share | UI bar |
| `bullish_skew` / `bearish_skew` | $\max(0, -\text{skew}) / \max(0, +\text{skew})$ | UI bar (0 in V1) |
| `bullish_basis` / `bearish_basis` | $\max(0, +\text{basis}) / \max(0, -\text{basis})$ | UI bar (0 in V1) |
| `bullish_pcrv` / `bearish_pcrv` | derived from PCR_v | UI bar |
| `pcr_oi` | put–call ratio on OI | diagnostic |
| `oi_concentration_at_max_pain` | OI at max-pain / total OI | diagnostic |
| `max_pain` | the strike | diagnostic |

The breakdown is stable across patch bumps — UI snapshot tests and
Recommendation Engine rationale templates anchor on these keys.

---

## 3. `compute()` — the orchestrator in twelve steps

`compute()` is intentionally a straight-line orchestration. Each step calls a
small, individually testable function. The full pipeline:

```python
def compute(
    *,
    chain_snapshot: ChainSnapshot,
    spot: float,
    expiry_focus: Sequence[date],
    dte_to_nearest_opex: int | None = None,
) -> FlowScore: ...
```

The twelve steps, in order:

1. **OI walls** — `compute_oi_walls(contracts, spot, expiry_focus)`
   ([M1.5 primitive](../../packages/engine/engine/flow_score/oi_walls.py)).
   Yields `(support, resistance)`, each `float | None`.

2. **Max pain** — `compute_max_pain(contracts, expiry=focus_list[0])`
   ([M1.2 primitive](../../packages/engine/engine/market_state/max_pain.py)).
   The primitive raises if no contracts exist at the chosen expiry — that
   error is propagated rather than swallowed, because hiding it would mask
   data-layer bugs.

3. **PCR** — `pcr_volume(contracts)` and `pcr_oi(contracts)`, restricted
   to focus contracts ([M1.2 primitives](../../packages/engine/engine/market_state/pcr.py)).
   PCR_v feeds the bullish/bearish formulas; PCR_oi is a diagnostic.

4. **Skew (active, M1.6) + basis stub** — `skew_25d(...)` computes real
   25-delta IV skew via [`engine.greeks`](../../packages/engine/engine/greeks.py)
   (delta-with-each-strike's-own-IV); `futures_basis(spot=spot)` remains
   a V1 stub returning 0. See [§9](#9-v1-stubs-and-forward-compatibility).

5. **Dealer-gamma proxy** — `compute_dealer_gamma_proxy(contracts, spot,
   expiry_focus)` ([M1.5 primitive](../../packages/engine/engine/flow_score/dealer_gamma.py)).
   Signed sum of $\text{sign}(c) \cdot \text{OI}(c) \cdot (K_c - S)$
   where sign is $-1$ for calls and $+1$ for puts.

6. **Gamma score** — `gamma_score(dealer_gamma_proxy=..., spot=spot,
   gamma_walls=[])`. Yields `score ∈ [0, 1]` magnitude and `sign ∈ {-1, 0, +1}`.

7. **5-component bullish + bearish scores** (the heart of the §9.3a
   formula — see [§4](#4-the-five-component-bullish--bearish-formulas-93a)).

8. **Pin probability** — `sigmoid_pin()` with the OI concentration at
   max pain ([§5](#5-sigmoid_pin--pin-probability)).

9. **Bias bucketing** — `_decide_bias(score, pin_probability)`. Four
   buckets, first match wins ([§6](#6-bias-bucketing--bullish--neutral--bearish--pin_risk)).

10. **Decision tree** — `_decide_action(score, gamma_risk, pin_probability)`.
    First match over six rules ([§7](#7-the-93a-decision-tree--recommended_action)).

11. **Confidence** — `_confidence_from_oi_total(contracts, expiry_focus)`.
    Linear in total focus-expiry OI, clipped at 1 with a
    100,000-OI saturation point.

12. **Explanation** — `render_explanation(walls, score, gamma,
    pin_probability)`. 2-4 sentences of human-readable rationale.

### 3.1 Why this order?

Two reasons drive the sequence:

- **Dependencies.** Walls feed dist; max pain feeds OI concentration which
  feeds pin probability; dealer gamma proxy feeds gamma score; bias depends
  on score AND pin probability; action depends on score AND gamma risk AND
  pin probability. The DAG is straight-line, so a list of steps suffices.
- **Failure surface.** Steps 1–3 are the data-layer-trust boundary: an
  empty chain, a non-existent focus expiry, or a degenerate PCR
  (no volume) all raise here, before any composite score is built.

### 3.2 Why kwargs-only?

Three positional arguments would risk argument-order bugs that the type
checker can't catch (swap `spot` and `dte_to_nearest_opex` and both are
`float | int` — the call still type-checks). Kwargs-only is the engine
convention from [ADR-0005](../decisions/0005-engine-pure-function-discipline.md);
the cost is one extra `*=` in the call site, the benefit is a class of bug
that simply cannot occur.

### 3.3 Input validation

`compute()` validates two preconditions itself; the rest delegates to
primitives:

```python
if spot <= 0.0:
    raise ValueError(f"compute: spot must be > 0; got {spot}")
focus = set(expiry_focus)
if not focus:
    raise ValueError("compute: expiry_focus must contain at least one expiry")
```

These two checks catch the most common caller mistakes. Everything else
(no contracts at focus expiry, bad OI value, etc.) propagates up from the
delegated primitives with their own clear error messages.

---

## 4. The five-component bullish + bearish formulas (§9.3a)

The plan §9.3a specifies the headline formula. Each side reads opposite
tails of the same five inputs:

$$
\text{bullish\_raw} = 0.30 \cdot \text{dist}_R + 0.25 \cdot \text{call\_share} + 0.20 \cdot \max(0, -\text{skew}) + 0.15 \cdot \max(0, +\text{basis}) + 0.10 \cdot \max(0, 1 - \text{PCR}_v)
$$

$$
\text{bearish\_raw} = 0.30 \cdot \text{dist}_S + 0.25 \cdot \text{put\_share} + 0.20 \cdot \max(0, +\text{skew}) + 0.15 \cdot \max(0, -\text{basis}) + 0.10 \cdot \text{PCR}_v
$$

then

$$
\text{bullish\_score} = 100 \cdot \mathrm{clip}_{[0,1]}(\text{bullish\_raw}); \quad \text{bearish\_score} = 100 \cdot \mathrm{clip}_{[0,1]}(\text{bearish\_raw}); \quad \text{score} = \text{bullish\_score} - \text{bearish\_score}
$$

Five components × two sides = ten breakdown entries. The weights sum to 1.0,
so each side caps at 100. The composite signed score caps at $\pm 100$.

### 4.1 Component 1 — wall distance (weight 0.30)

```python
_W_DIST = 0.30
_WALL_FAR_PCT = 0.05
_WALL_MISSING_PRIOR = 0.5

def _dist_to_wall_norm(*, spot: float, wall: float | None) -> float:
    if wall is None:
        return _WALL_MISSING_PRIOR
    dist_pct = abs(wall - spot) / spot
    return clip01(dist_pct / _WALL_FAR_PCT)
```

The bullish side reads `walls.resistance` — *room to run upward*. The
bearish side reads `walls.support` — *room to fall*. The wall is a peak in
OI: it acts as a magnet for dealer hedging activity, so distance from spot
to wall correlates with how unobstructed flow in that direction is.

The normalization choices:

- **Linear in `dist_pct / 0.05`, clipped at 1.0.** A wall ≥ 5% away
  contributes maximum (1.0); a wall on top of spot contributes 0; everything
  in between is linear. The 5% threshold is a V1 calibration — it
  approximates "two trading days' worth of MSFT volatility," which is the
  scale at which dealer hedging activity decays. Phase 4 ML may learn this.
- **`None` → 0.5 (neutral prior).** The conservative choice when no wall
  has been identified. Treating it as 0 (close-wall) or 1 (far-wall) would
  arbitrarily tilt the score — 0.5 is a "no information" prior consistent
  with the rest of the engine.

### 4.2 Component 2 — volume share (weight 0.25)

```python
def _volume_shares(
    *,
    contracts: Sequence[OptionContract],
    expiry_focus: set[date],
) -> tuple[float, float]:
    # ...
    total = call_vol + put_vol
    if total == 0:
        return 0.5, 0.5
    return call_vol / total, put_vol / total
```

The bullish side reads `call_share` and the bearish side reads `put_share`.
Together they sum to 1.0 (when total volume > 0). A chain with 80% call
volume contributes $0.25 \cdot 0.8 = 0.20$ to bullish and $0.25 \cdot 0.2 = 0.05$
to bearish — a $+15$ net point swing from a single component.

Volume (not OI) goes here because volume is the *flow* signal and OI is the
*stock* signal. The engine reads both in different roles:

- `volume_share` (here) feeds the directional formula.
- `total_oi` (later) feeds confidence (§8).
- `oi_concentration` (later still) feeds pin probability (§5).

### 4.3 Component 3 — IV skew (weight 0.20, **active from M1.6**)

The plan formula:

$$
\text{bullish}\!: 0.20 \cdot \max(0, -\text{skew}); \quad \text{bearish}\!: 0.20 \cdot \max(0, +\text{skew})
$$

Negative skew means call IV trades richer than put IV — call-side demand
exceeds put-side, bullish. Positive skew is the put-side fear premium —
bearish.

M1.6 shipped the [`engine.greeks`](../../packages/engine/engine/greeks.py)
Black-Scholes module and replaced the M1.5b `skew_25d` stub with a real
implementation. The procedure (per `engine/flow_score/skew.py`):

1. For each expiry in `expiry_focus`, compute
   $\tau = (\text{expiry} - \text{as\_of}) / 365$.
2. Filter contracts at that expiry with valid IV (`iv != None`, `iv > 0`).
3. Among calls, pick the strike whose BS delta is closest to $+0.25$ —
   using each contract's *own* IV (so the empirical smile is honored).
4. Among puts, pick the strike whose BS delta is closest to $-0.25$.
5. Per-expiry skew $= \text{IV}_\text{put}(25\Delta) - \text{IV}_\text{call}(25\Delta)$.
6. Final skew is the average across qualifying expiries.

The function signature is

```python
skew_25d(
    *,
    contracts: Sequence[OptionContract],
    expiry_focus: Sequence[date],
    spot: float,
    as_of: date,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> float
```

`compute()` threads `chain_snapshot.as_of`, `spot`, plus optional
`risk_free_rate` and `dividend_yield` overrides through to `skew_25d`.
Defaults match the V1 priors: `r = 0.05` (early-2026 SOFR baseline),
`q = 0.0` (sensible for MSFT-class names; broad-index callers
should override).

**Smile-aware vs flat-vol naive.** The implementation evaluates each
strike's BS delta with that strike's *own* implied vol, not a single
chain-average vol. This matters: at the 25-Δ wings, IV typically
differs from ATM by several volatility points, and using ATM vol to
find the wings would mis-identify the strike. The trade-off is
extra compute (one BS delta call per qualifying contract); the upside
is the skew the function reports is the genuine wing-to-wing IV gap.

### 4.4 Component 4 — futures basis (weight 0.15, **stub in V1**)

The plan formula:

$$
\text{bullish}\!: 0.15 \cdot \max(0, +\text{basis}); \quad \text{bearish}\!: 0.15 \cdot \max(0, -\text{basis})
$$

Positive basis (futures trading above spot) reflects bullish flow at the
front of the curve. Phase 1 of option-mgmt-2026 doesn't provision a
futures-data service — `futures_basis()` returns 0.0 in V1. The §9.3a
formula explicitly contemplates this: "0 if futures unavailable."

### 4.5 Component 5 — put–call ratio (weight 0.10)

The bullish side reads $\max(0, 1 - \text{PCR}_v)$. The bearish side reads
$\text{PCR}_v$ directly. Why asymmetric?

- A typical premium-selling equity has PCR_v ≈ 0.5 (more call volume than
  put). The bullish weight on $1 - 0.5 = 0.5$ contributes $0.10 \cdot 0.5 = 0.05$.
  The bearish weight on $0.5$ contributes the same. Roughly balanced.
- PCR_v = 1.0 (equal volume) → bullish contributes 0, bearish contributes
  $0.10 \cdot 1.0 = 0.10$ — a $-10$ point tilt that documents the engine's
  view that PCR_v = 1.0 is mildly bearish *relative to the equity baseline*.
- PCR_v ≫ 1.0 (more put volume than call) is clamped: the bullish term is
  `max(0, 1 - PCR_v)` → 0, and the bearish term is clamped at 1.0 inside
  the formula (see the `pcrv if pcrv <= 1.0 else 1.0` ternary).

This asymmetry is real and intentional — the engine's V1 baseline of "calls
slightly outweigh puts" matches the historical premium-selling equity
universe MSFT belongs to.

### 4.6 The clip and the scale

The unweighted sum of all five bullish components, each at max, is
$0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.0$. After scaling by 100, the
bullish score caps at 100. The `clip01` defends against numerical noise
(a sum of 1.0000000001 from float arithmetic) and against future weight
edits that don't quite sum to 1.

With the V1 stubs, $\text{skew} = \text{basis} = 0$, so the three active
components have weights summing to $0.65$. Both bullish and bearish each
cap at $65$, and the signed `score` ranges over $[-65, +65]$ in practice.

---

## 5. `sigmoid_pin()` — pin probability

```python
def sigmoid_pin(
    *,
    spot: float,
    max_pain: float,
    dte_to_nearest_opex: int | None,
    oi_concentration_at_max_pain: float,
) -> float: ...
```

The name is historical — the actual implementation is a **multiplicative
blend** of three factors, each in $[0, 1]$:

$$
\text{pin\_probability} = \mathrm{clip}_{[0,1]}\left(\underbrace{f_{\text{dist}}}_{\text{spot near max pain?}} \cdot \underbrace{f_{\text{opex}}}_{\text{opex near?}} \cdot \underbrace{f_{\text{oi}}}_{\text{OI at max pain?}}\right)
$$

### 5.1 Distance factor

```python
_PIN_TIGHT_PCT = 0.02
_PIN_LOOSE_PCT = 0.05

if dist_pct <= _PIN_TIGHT_PCT:
    dist_factor = 1.0
elif dist_pct >= _PIN_LOOSE_PCT:
    dist_factor = 0.0
else:
    dist_factor = (_PIN_LOOSE_PCT - dist_pct) / (_PIN_LOOSE_PCT - _PIN_TIGHT_PCT)
```

A piecewise-linear "saturate near max pain, decay past it" function. Within
2% of max pain → 1.0; past 5% → 0; linear in between. The 2/5 split is a
V1 prior matching practitioner observation that a max-pain pin meaningfully
binds spot only when spot is *within a fraction of the expected move* of
the pinning strike.

### 5.2 Opex factor

```python
_OPEX_HORIZON_DAYS = 14
_OPEX_FAR_DAYS = 30

if dte_to_nearest_opex is None or dte_to_nearest_opex >= _OPEX_FAR_DAYS:
    return 0.0   # short-circuit out of compute() entirely
dte = max(dte_to_nearest_opex, 0)
opex_factor = clip01(1.0 - dte / _OPEX_HORIZON_DAYS)
```

Two thresholds:

- $\geq 30$ days or `None` → pin probability is **identically 0**. No
  monthly-opex hedging unwind in the relevant horizon means no pinning.
- $\leq 14$ days → `opex_factor` ramps linearly to 1.0 at $d = 0$.

The 14-day horizon ($\approx 3$ trading weeks) is the practitioner
heuristic for when dealer delta-hedging starts compressing toward the
high-OI strike at the monthly opex.

### 5.3 OI factor

This is the *only* factor the caller supplies — the rest is computed in
`compute()` from the snapshot. The caller passes:

$$
\text{oi\_concentration\_at\_max\_pain} = \frac{\sum_{c : K_c = K^*} \text{OI}_c}{\sum_{c} \text{OI}_c}
$$

over focus-expiry contracts. The function validates $\in [0, 1]$.

### 5.4 Why multiplicative?

Two reasons multiplicative beats additive:

- **Mutual reinforcement.** A pin is real only if *all three* signals
  agree. Spot at max pain with 30-day opex and 5% OI concentration is not
  a pin; nor is spot 4% away with same-day opex and 80% OI concentration.
  Multiplication enforces "all three must be present."
- **Conservative.** Multiplicative blends saturate at the minimum factor.
  No single elevated signal can manufacture a pin. The Phase 4 ML upgrade
  can learn an arbitrary nonlinear function; the V1 deterministic prior is
  deliberately conservative.

### 5.5 The `_PIN_EXPLAIN_THRESHOLD` shared with bias

Both the bias bucketer ([§6](#6-bias-bucketing--bullish--neutral--bearish--pin_risk))
and the explanation builder ([§8](#8-confidence-and-the-explanation-builder))
use the same 0.6 threshold. Below 0.6 the explanation omits the pin
sentence and the bias does not bucket to `PIN_RISK`. Sharing one threshold
means: if the bias says `PIN_RISK`, the explanation *will* mention pin; if
the bias does not say `PIN_RISK`, the explanation will *not* mention pin.

This invariance is documented in
[`engine/flow_score/explanation.py`](../../packages/engine/engine/flow_score/explanation.py)
and asserted in the test suite.

---

## 6. Bias bucketing — `BULLISH / NEUTRAL / BEARISH / PIN_RISK`

The bucketer is six lines of code:

```python
_BIAS_BULLISH_THRESHOLD = 20.0
_BIAS_BEARISH_THRESHOLD = -20.0
_BIAS_PIN_THRESHOLD = 0.6

def _decide_bias(*, score: float, pin_probability: float) -> Bias:
    if pin_probability >= _BIAS_PIN_THRESHOLD:
        return Bias.PIN_RISK
    if score >= _BIAS_BULLISH_THRESHOLD:
        return Bias.BULLISH
    if score <= _BIAS_BEARISH_THRESHOLD:
        return Bias.BEARISH
    return Bias.NEUTRAL
```

Three design decisions are worth unpacking.

### 6.1 Pin precedence

Pin is checked **first**, so a chain that looks bullish ($\text{score} = +30$)
but has high pin probability ($p = 0.7$) buckets to `PIN_RISK`, not
`BULLISH`. Why? Because the Recommendation Engine's strategy whitelist for
the two regimes is different:

- `BULLISH` → consider partial / aggressive call selling.
- `PIN_RISK` → consider waiting; calls sold above max pain are likely to
  expire worthless, but calls sold *at* max pain face short-gamma roll
  risk into the pin.

The "obvious wrong thing" would be to pick the regime by score alone and
then layer a pin warning — that leaves the strategy whitelist incorrect.
The bucketer's job is to give the Recommendation Engine the right whitelist
key directly.

### 6.2 ±20-point dead zone

The bullish/bearish thresholds are $\pm 20$, not 0. The thresholds carve
out a "neutral band" of width 40 points around zero. Reasons:

- **Noise tolerance.** The 5-component formula uses heuristic weights and
  V1 stubs. A score of $+5$ vs $-5$ is well within the calibration
  uncertainty.
- **Decision stability.** A user looking at their portfolio doesn't want
  `BULLISH` flipping to `BEARISH` from one trading day to the next based
  on a 2-point swing. The neutral band provides hysteresis without
  state.
- **Phase 4 ML compatibility.** When ADR-0008's ML node-swap learns the
  bias classifier, the learned thresholds may differ from $\pm 20$ but the
  enum and the bucketing structure remain the contract.

### 6.3 Why a `NEUTRAL` enum, not `None`?

`Bias` is a `StrEnum` with `NEUTRAL` as a first-class value. The contract
is "every chain produces exactly one of four biases." `None` would mean
"refused to classify" — but the engine never refuses; in the worst case
(empty chain, no volume, no walls) it returns `NEUTRAL` with score = 0
and confidence near 0. Downstream code can read the `confidence` field if
it cares about classification quality.

---

## 7. The §9.3a decision tree — `recommended_action`

The plan §9.3a specifies a five-line decision tree, taken verbatim into
code:

```python
def _decide_action(
    *,
    score: float,
    gamma_risk: float,
    pin_probability: float,
) -> RecommendedAction:
    if score >= _ACTION_AGGRESSIVE_SCORE and gamma_risk <= _ACTION_AGGRESSIVE_GAMMA:
        return RecommendedAction.SELL_CALL_AGGRESSIVE
    if score >= _ACTION_PARTIAL_SCORE:
        return RecommendedAction.SELL_CALL_PARTIAL
    if (
        abs(score) < _ACTION_WAIT_SCORE_BAND
        and pin_probability >= _ACTION_WAIT_PIN
    ):
        return RecommendedAction.WAIT
    if score <= _ACTION_PROTECTION_SCORE and gamma_risk >= _ACTION_PROTECTION_GAMMA:
        return RecommendedAction.BUY_PROTECTION
    if score <= _ACTION_REDUCE_SCORE:
        return RecommendedAction.REDUCE_COVERAGE
    return RecommendedAction.MONITOR
```

First match wins. Six possible outputs. The thresholds:

| Rule | Score | Gamma risk | Pin | Action |
|---|---|---|---|---|
| 1 | ≥ +40 | ≤ 0.5 | — | `SELL_CALL_AGGRESSIVE` |
| 2 | ≥ +10 | — | — | `SELL_CALL_PARTIAL` |
| 3 | $\|s\| < 10$ | — | ≥ 0.6 | `WAIT` |
| 4 | ≤ −20 | ≥ 0.6 | — | `BUY_PROTECTION` |
| 5 | ≤ −10 | — | — | `REDUCE_COVERAGE` |
| 6 | otherwise | — | — | `MONITOR` |

### 7.1 The two gamma-gates

Two of the six rules read `gamma_risk`. The pattern is symmetric:

- **`SELL_CALL_AGGRESSIVE`** requires `gamma_risk ≤ 0.5`. Aggressive call
  selling when dealers are heavily long gamma is unattractive — dealers
  dampen vol, premium is rich, but the upside risk is muted and so are
  the realized vol moves that make short calls profitable.
- **`BUY_PROTECTION`** requires `gamma_risk ≥ 0.6`. Buying puts when
  dealers are heavily short gamma (vol amplifier) means leaning *with* a
  vol-expanding flow — the puts are likely to outpace their theta.

The gates use only the magnitude (`gamma_risk`), not the sign. The sign
enters in V1.5+ via richer rules (e.g. ADR-0008's Phase 1.5 rules in
`apps/api/app/config/rules.yaml`); V1 keeps the decision tree small.

### 7.2 The `WAIT` rule and the dead zone

`WAIT` fires when $|s| < 10$ AND $p \geq 0.6$ — a *narrow* condition. The
small dead zone (width 20) is intentional: most pinned chains have either
mild bullish or mild bearish tilt within the $\pm 20$ neutral band, and
the right action is `WAIT` regardless. A wider window (say $\pm 20$) would
risk recommending `WAIT` when the chain genuinely tilts and a partial sell
or partial reduction is the better answer.

### 7.3 Why no `BUY_CALL_PARTIAL` or `BUY_CALL_AGGRESSIVE`?

By design. The Phase 1 product MSFT covered-call risk management — the
user holds the underlying and writes calls against it. The action set is
restricted to actions the engine can recommend within that holding pattern:

- Sell more calls (aggressive or partial).
- Buy protection (puts).
- Reduce existing call coverage.
- Wait or monitor.

Buying calls is out of scope for V1; it falls under "open new directional
positions," a Phase 2 feature.

### 7.4 Why `MONITOR` as the fallback?

The decision tree has a `MONITOR` floor — when no rule matches, the
recommendation is *do nothing yet, but keep watching*. This is
qualitatively different from "no recommendation" or "error." The
Recommendation Engine reads `MONITOR` and renders a calm UI state ("we
saw the chain; nothing actionable today") rather than treating it as a
failure.

---

## 8. Confidence and the explanation builder

Two more outputs round out the `FlowScore` contract: a numeric confidence
in $[0, 1]$ and a human-readable explanation string.

### 8.1 Confidence

```python
_CONFIDENCE_OI_SCALE = 100_000

def _confidence_from_oi_total(
    *,
    contracts: Sequence[OptionContract],
    expiry_focus: set[date],
) -> float:
    total_oi = sum(c.open_interest for c in contracts if c.expiry in expiry_focus)
    return clip01(total_oi / _CONFIDENCE_OI_SCALE)
```

A chain with 100,000 OI at the focus expiries saturates to 1.0. Sparser
chains scale linearly. The 100,000 saturation point is a V1 calibration
covering "a liquid mega-cap weekly + monthly expiry" for MSFT-class
symbols; less liquid symbols hit smaller absolute OI and bring less
confidence per chain.

The downstream consumer is the Confidence Composer (M1.10): it multiplies
the per-engine confidence into the final per-decision confidence. Per
[ADR-0003](../decisions/0003-confidence-composer-multiplicative.md) the
Composer is **multiplicative**, so a Flow Score confidence of 0.3 is a
genuine downweighting — not a clamp, not a floor.

### 8.2 Why OI, not volume?

OI is the *stock* of open positions and is robust to single-day volume
spikes. A chain that suddenly traded 100,000 contracts in one session but
has minimal OI is a thin chain with a transient event; the Flow Score
Engine should not pretend high confidence about it.

### 8.3 Why a saturation point, not a sigmoid?

A linear scale with `clip01` is monotonic, computationally cheap, and
easy to explain. A sigmoid would slightly soften the saturation but at
the cost of a calibration choice nobody can defend on first principles.
Phase 4 ML may learn a richer mapping; until then linear-with-clip is the
conservative prior.

### 8.4 The explanation builder

```python
def render_explanation(
    *,
    walls: OiWalls,
    score: float,
    gamma: GammaScoreResult,
    pin_probability: float,
) -> str: ...
```

Two-to-four sentences, space-joined:

1. **Always present:** "FlowScore composite: $\pm S.S$."
2. **Always present:** one of four wall sentences, depending on which
   walls are populated.
3. **Conditional on `gamma.sign != 0`:** "Dealer gamma net short
   (magnitude $g$) — vol amplifier." or "Dealer gamma net long (magnitude
   $g$) — vol dampener."
4. **Conditional on `pin_probability >= 0.6`:** "High pin probability
   ($p$) near max pain."

Two design rules govern the string:

- **Stable across patch bumps.** UI snapshot tests and downstream NLP /
  disclosure templates may anchor on phrases like "Dealer gamma net
  short" or "near max pain." Adding sentences is a minor bump; rewording
  existing ones is a minor bump too (with a CHANGELOG note); restructuring
  the order is a breaking change.
- **No floats with more than 2 decimal places.** Readers see a stable
  precision that doesn't reveal the FP noise from upstream calculations.

### 8.5 The pin-threshold invariant

As mentioned in [§5.5](#55-the-_pin_explain_threshold-shared-with-bias):
the same 0.6 threshold gates the `PIN_RISK` bias and the explanation's
pin sentence. The test
`test_pin_threshold_invariant_bias_matches_explanation` asserts this
across a range of synthetic inputs.

---

## 9. V1 stubs and forward compatibility

One of the five §9.3a components — `futures_basis` — remains a V1 stub
returning 0.0. The `skew_25d` component was a stub in M1.5b; M1.6
shipped `engine.greeks` and replaced the stub with a real implementation
(see §4.3). This section explains the rationale for both — the historic
stub for skew and the still-active stub for basis.

### 9.1 Why `skew_25d` was a stub in M1.5b (and how M1.6 resolved it)

Real 25-delta skew requires identifying the strike where $|\Delta_{BS}| = 0.25$
for each side of the chain (put and call), at each focus expiry. That
requires Black–Scholes delta, which requires `r` (risk-free rate),
`q` (dividend yield), `T` (time to expiry), and the per-strike IV smile.

All of those landed in **M1.6**. The Greeks module (`engine.greeks`)
exposes `delta`, `gamma`, `vega`, `theta`, `rho`, and
`time_to_expiry_years` as pure functions; `engine/flow_score/skew.py`
calls `delta(option_type=OptionType.CALL/PUT, ...)` per contract and
picks the strike whose delta is closest to $\pm 0.25$.

The trade-off the M1.5b stub navigated was *known-zero contribution*
vs *unknown-biased contribution*. The 0.20 skew weight contributing 0
was honest. Any approximation (e.g. "raw IV at $K = 0.95 S$ minus IV at
$K = 1.05 S$") would have been:

- Sensitive to strike-grid granularity (different chains would give
  different "skews" for the same underlying).
- Drift from the true 25-delta-skew calibration that Phase 4 ML will use.

The M1.6 implementation honors both the calibration and the
forward-compatibility promise: **no threshold recalibration was needed**
when the stub was replaced. The formula sums weighted clipped values, so
the active 0.20 component naturally raises the realized range of the
bullish and bearish scores from $[0, 65]$ to $[0, 85]$. The bias and
action thresholds were set assuming the full 5-component formula, so
they fit naturally as more components come online.

### 9.2 Why `futures_basis` remains a stub

Phase 1 of option-mgmt-2026 does not provision futures data. The data
plumbing for ES (S&P 500 futures, MSFT's correlated index) is a Phase 2
feature — `apps/api/app/services/futures_service.py`. The §9.3a formula
explicitly says "0 if futures unavailable," so the V1 stub honors the
contract.

When Phase 2 wires up the service, replacing the stub adds the 0.15-weight
basis contribution to the bullish/bearish formulas. Same arithmetic
story as the M1.6 skew activation: the range widens (from $[0, 85]$ to
$[0, 100]$), the thresholds stay.

### 9.3 The `bullish_skew` and `bearish_skew` breakdown keys

Even when `skew_25d` was stubbed (M1.5b), the breakdown carried
`bullish_skew = 0` and `bearish_skew = 0` (likewise for basis). This is
intentional: when the
stubs are replaced, the UI's stacked-bar chart of breakdown values smoothly
gains two new contributions without a schema change. The UI doesn't have
to know whether a given component is "active" — it just reads the value.

### 9.4 Validation in stubs

`futures_basis` still validates `spot > 0` even though the body returns 0:

```python
def futures_basis(*, spot: float) -> float:
    if spot <= 0.0:
        raise ValueError(f"futures_basis: spot must be > 0; got {spot}")
    return 0.0
```

This catches bad input *at the boundary* — callers can't accidentally pass
a negative spot, get 0 back, and then notice silently that their downstream
formula produced nonsense. The pattern is the same as the rest of the
engine's input-validation discipline.

`skew_25d` (post-M1.6) validates `spot > 0` at the boundary — the same
pattern as `futures_basis`. Contracts with missing or zero IV are
filtered internally (BS delta is undefined at `iv = 0`); an expiry with
no eligible contracts is simply skipped rather than raising, on the
principle that the engine should degrade gracefully when individual
expiries are illiquid.

---

## 10. End-to-end worked example

Let's run `compute()` on a realistic synthetic MSFT-like chain and hand-trace
every step. Spot $= 100$, one focus expiry, no opex in the near horizon
(so `dte_to_nearest_opex = None`):

```python
from datetime import date
from engine.flow_score import compute
from engine.types import ChainSnapshot, OptionContract, OptionType

EXPIRY = date(2026, 6, 19)
ASOF = date(2026, 5, 10)

def c(strike, ot, oi, vol):
    return OptionContract(
        underlying="MSFT", expiry=EXPIRY, strike=strike,
        option_type=ot, bid=0.5, ask=0.6, mid=0.55,
        volume=vol, open_interest=oi, iv=0.30,
    )

contracts = [
    c(95.0,  OptionType.CALL, 1000, 1000),
    c(95.0,  OptionType.PUT,   200,   50),
    c(100.0, OptionType.CALL, 1000, 1000),
    c(100.0, OptionType.PUT,   200,   50),
    c(120.0, OptionType.CALL, 8000,  300),
    c(120.0, OptionType.PUT,   200,   30),
]

snap = ChainSnapshot(underlying="MSFT", as_of=ASOF, spot=100.0,
                    contracts=tuple(contracts))
result = compute(chain_snapshot=snap, spot=100.0, expiry_focus=[EXPIRY])
```

This is a deliberately stylized "bullish chain": heavy call activity at
the money plus a giant call wall well above spot, minimal put activity.

### 10.1 Hand-trace

#### Step 1 — OI walls

Per-strike OI: $K=95: 1200$; $K=100: 1200$; $K=120: 8200$.

The 90th-percentile threshold on the three-strike OI distribution is the
top-decile cutoff. With $n=3$, linear interpolation puts the threshold at
~6,800. Only $K = 120$ exceeds the threshold (strict-`>` rule), so:
$\text{walls.support} = \text{None}; \quad \text{walls.resistance} = 120.0$.

#### Step 2 — Max pain

Compute pain at each strike (call writer pays max(K* − K_c, 0)·OI; put
writer pays max(K_p − K*, 0)·OI):

| $K^*$ | call pain | put pain | total |
|---|---|---|---|
| 95 | 0 | $5 \cdot 200 + 25 \cdot 200 = 6{,}000$ | 6,000 |
| 100 | $5 \cdot 1{,}000 = 5{,}000$ | $20 \cdot 200 = 4{,}000$ | 9,000 |
| 120 | $25 \cdot 1{,}000 + 20 \cdot 1{,}000 = 45{,}000$ | 0 | 45,000 |

Minimum at $K^* = 95$ → $\text{max\_pain} = 95.0$.

#### Step 3 — PCR

Restricted to focus contracts:
- $\sum \text{vol}_{\text{put}} = 50 + 50 + 30 = 130$
- $\sum \text{vol}_{\text{call}} = 1{,}000 + 1{,}000 + 300 = 2{,}300$
- $\text{PCR}_v = 130 / 2{,}300 \approx 0.0565$
- $\sum \text{OI}_{\text{put}} = 200 + 200 + 200 = 600$
- $\sum \text{OI}_{\text{call}} = 1{,}000 + 1{,}000 + 8{,}000 = 10{,}000$
- $\text{PCR}_{OI} = 600 / 10{,}000 = 0.06$

#### Step 4 — Skew (M1.6 real impl) + basis stub

The synthetic chain has `iv=0.30` on every contract → flat smile → the
25-Δ put and 25-Δ call both have IV=0.30 → $\text{skew} = 0.30 - 0.30 = 0$.
`futures_basis` remains a V1 stub: $\text{basis} = 0$.

If the chain had a real smile (e.g. puts at IV=0.35, calls at IV=0.25),
`skew_25d` would return $0.35 - 0.25 = 0.10$ and the bearish side of
the §9.3a formula would pick up $0.20 \cdot 0.10 = 0.02$, i.e. +2 points
on `bearish_score`. The worked example below uses flat IV precisely
because it isolates the M1.5b primitives.

#### Step 5 — Dealer-gamma proxy

$\Pi = \sum_c \text{sign}(c) \cdot \text{OI}(c) \cdot (K_c - S)$ with sign $= -1$ for calls, $+1$ for puts:

| Strike | Call contribution | Put contribution | Subtotal |
|---|---|---|---|
| 95 | $(-1)(1{,}000)(95-100) = +5{,}000$ | $(+1)(200)(95-100) = -1{,}000$ | $+4{,}000$ |
| 100 | 0 | 0 | 0 |
| 120 | $(-1)(8{,}000)(20) = -160{,}000$ | $(+1)(200)(20) = +4{,}000$ | $-156{,}000$ |

$\Pi = 4{,}000 + 0 - 156{,}000 = -152{,}000$.

#### Step 6 — Gamma score

$D = S \cdot 10{,}000 = 1{,}000{,}000$. With $\mathcal{W} = \emptyset$ (no GEX
walls in V1):
$\text{proxy\_magnitude} = |{-152{,}000}| / 1{,}000{,}000 = 0.152$
$\text{score} = \text{proxy\_magnitude} = 0.152$
$\text{sign} = -1$ (amplifier)

#### Step 7 — 5-component formulas

- $\text{call\_share} = 2{,}300 / (2{,}300 + 130) = 0.9465$
- $\text{put\_share} = 130 / 2{,}430 = 0.0535$
- $\text{dist}_R = \mathrm{clip}_{[0,1]}(|120-100|/100 / 0.05) = \mathrm{clip}_{[0,1]}(4) = 1.0$
- $\text{dist}_S = 0.5$ (no support wall → neutral prior)
- $\text{bullish\_pcrv} = \max(0, 1 - 0.0565) = 0.9435$
- $\text{bearish\_pcrv} = 0.0565$

Bullish raw:
$0.30 \cdot 1.0 + 0.25 \cdot 0.9465 + 0.20 \cdot 0 + 0.15 \cdot 0 + 0.10 \cdot 0.9435 = 0.300 + 0.2366 + 0 + 0 + 0.0944 = 0.6310$

Bearish raw:
$0.30 \cdot 0.5 + 0.25 \cdot 0.0535 + 0.20 \cdot 0 + 0.15 \cdot 0 + 0.10 \cdot 0.0565 = 0.150 + 0.0134 + 0 + 0 + 0.0057 = 0.1690$

$\text{bullish\_score} = 100 \cdot 0.6310 = 63.10$
$\text{bearish\_score} = 100 \cdot 0.1690 = 16.90$
$\text{score} = +46.20$

#### Step 8 — Pin probability

$\text{dte\_to\_nearest\_opex} = \text{None}$ → `sigmoid_pin` short-circuits to 0.
$\text{pin\_probability} = 0$.

#### Step 9 — Bias

$\text{pin\_probability} < 0.6$; $\text{score} = +46.2 \geq +20$ → $\text{bias} = \text{BULLISH}$.

#### Step 10 — Action

Rule 1 (`SELL_CALL_AGGRESSIVE`): score $\geq 40$ ✓ AND gamma_risk $\leq 0.5$
(0.152 ≤ 0.5) ✓ → match.

#### Step 11 — Confidence

Total focus-expiry OI = $1{,}200 + 1{,}200 + 8{,}200 = 10{,}600$.
$\text{confidence} = \mathrm{clip}_{[0,1]}(10{,}600 / 100{,}000) = 0.106$

#### Step 12 — Explanation

Two sentences (gamma sign $-1$ adds a third; pin probability $0 < 0.6$
omits the pin sentence):

```
FlowScore composite: +46.2. OI resistance at 120.00; no clear support.
Dealer gamma net short (magnitude 0.15) — vol amplifier.
```

### 10.2 The final `FlowScore`

Putting it all together:

```python
FlowScore(
    score=46.2,
    bullish_score=63.10,
    bearish_score=16.90,
    bias=Bias.BULLISH,
    recommended_action=RecommendedAction.SELL_CALL_AGGRESSIVE,
    pin_probability=0.0,
    gamma_risk=0.152,
    gamma_sign=-1,
    confidence=0.106,
    explanation="FlowScore composite: +46.2. OI resistance at 120.00; "
                "no clear support. Dealer gamma net short (magnitude 0.15) "
                "— vol amplifier.",
    breakdown={
        "bullish_dist": 1.0,    "bullish_call_vol": 0.9465,
        "bullish_skew": 0.0,    "bullish_basis": 0.0,
        "bullish_pcrv": 0.9435,
        "bearish_dist": 0.5,    "bearish_put_vol": 0.0535,
        "bearish_skew": 0.0,    "bearish_basis": 0.0,
        "bearish_pcrv": 0.0565,
        "pcr_oi": 0.06,         "oi_concentration_at_max_pain": 0.1132,
        "max_pain": 95.0,
    },
)
```

### 10.3 Reading the result

A skeptical reviewer should now ask: "OK, but is this *right*?" Let's
sanity-check three things:

- **Score sign.** The chain is overwhelmingly call-heavy with a wall well
  above spot. Bullish is the right answer.
- **Action.** `SELL_CALL_AGGRESSIVE` requires confidence that there's
  upside without dealer-vol-amplification headwinds. Score $+46$ is well
  inside the $\geq +40$ rule, and gamma_risk $0.15$ is well below the
  $0.5$ gate. The action is decisive.
- **Confidence.** $0.106$ is low — only ~10,600 OI in the focus expiry.
  The Confidence Composer will multiply this through and downstream
  consumers will know to weight this decision modestly. The action is
  correct given the inputs, but the inputs themselves are thin.

The explanation surfaces all three signals (composite, resistance, gamma
sign) without mentioning pin (correct: $p = 0$).

---

## 11. Hands-on exercises

Solutions are at the end. Try them before peeking.

### Exercise 1 — Symmetric chain

Predict the `FlowScore` for a chain with 3 strikes (95, 100, 105), each
with $\text{call\_OI} = \text{put\_OI} = 1000$ and $\text{call\_vol} = \text{put\_vol} = 100$.
Spot = 100; no opex in horizon.

(a) What is $\text{walls.support}$ and $\text{walls.resistance}$?
(b) What does $\text{score}$ approximately equal? Why is it not zero?
(c) What is the bias?

### Exercise 2 — Wall sensitivity

Take the §10 worked example. Move the resistance wall from $K = 120$ to
$K = 103$ (keep all other contracts and OI/volume identical, just relocate
the 8000 call OI). Hand-compute the new $\text{dist}_R$ and the new
$\text{bullish\_score}$.

What happens to the recommended action?

### Exercise 3 — Pin probability dimensions

You're given $\text{spot} = 100$, $\text{max\_pain} = 99.5$, $\text{opex
in 5 days}$, $\text{oi\_concentration} = 0.8$. Compute $\text{pin\_probability}$
by hand.

Now keep two factors but change one at a time:
- (a) Push opex to 20 days. New pin?
- (b) Push spot to 96 (4% from max pain). New pin?
- (c) Drop OI concentration to 0.1. New pin?

What does this teach you about the multiplicative structure?

### Exercise 4 — `WAIT` vs `MONITOR`

When does `_decide_action()` return `WAIT` vs `MONITOR`? Construct a tuple
$(score, gamma\_risk, pin\_probability)$ for each case that's "just
barely" the right answer (i.e. one or two units off the threshold).

### Exercise 5 — Sign-aware gating

Why does the §9.3a decision tree use `gamma_risk` (magnitude) for the
`SELL_CALL_AGGRESSIVE` and `BUY_PROTECTION` gates, but not `gamma_sign`?
Sketch a fourth rule that *would* use the sign and explain whether it
belongs in V1 or in the Phase 1.5 ADR-0008 rules.yaml.

### Exercise 6 — Confidence floor

A chain has total focus-expiry OI = 250. What's the confidence? What
fraction of the V1 saturation point is this? Why does the Confidence
Composer's multiplicative chain mean this single chain effectively
flatlines decisions?

### Exercise 7 — Skew is live (M1.6)

M1.6 shipped — `skew_25d` is now active. The §10 worked example uses a
synthetic chain where every contract has `iv=0.30`, so the put 25-Δ and
call 25-Δ strikes both have IV=0.30 and the skew computes to exactly 0
(no smile = no skew, by definition).

Now imagine an alternate chain identical to §10 except every put has
`iv=0.35` and every call still has `iv=0.30`. Hand-compute the new
`bullish_score`, `bearish_score`, signed `score`, and verify the
`recommended_action`. Does the action change from
`SELL_CALL_AGGRESSIVE`?

(Hint: the put-side richness gives a positive skew. With skew=+0.05,
`bearish_skew = max(0, +0.05) = 0.05` contributes $0.20 \cdot 0.05 = 0.01$
to `bearish_raw`, i.e. +1.0 to `bearish_score`. `bullish_skew = 0`.)

### Exercise 8 — Explanation invariants

The explanation builder has a designed invariant: the bias and the
explanation must agree on the presence of pin language. Prove (informally)
that for every input where `_decide_bias() == PIN_RISK`, the explanation
will contain the substring "High pin probability."

What's the corresponding invariant for non-`PIN_RISK` biases?

### Exercise 9 — Replay regression

You bump $\text{\_PIN\_TIGHT\_PCT}$ from 0.02 to 0.03 (loosen the tight-pin
threshold). Why is this a **minor** version bump and not a patch?
Reference [ADR-0005](../decisions/0005-engine-pure-function-discipline.md)
and explain what `inputs_hash` + `engine_version` + `weights_version`
guarantee.

---

### Solutions

**E1.** (a) All three strikes tie at OI = 2,000 each (1,000 call + 1,000
put). The 90th-percentile threshold equals 2,000 (interpolated); the
strict-`>` rule excludes ties, so neither support nor resistance qualifies:
$\text{walls.support} = \text{None}; \text{walls.resistance} = \text{None}$.

(b) Both wall distances fall back to 0.5 (the missing-wall prior). Call
share = put share = 0.5. PCR_v = 300/300 = 1.0, so bullish_pcrv = 0 and
bearish_pcrv = 1.0. Skew = basis = 0.

$\text{bullish\_raw} = 0.30 \cdot 0.5 + 0.25 \cdot 0.5 + 0 + 0 + 0.10 \cdot 0 = 0.275$
$\text{bearish\_raw} = 0.30 \cdot 0.5 + 0.25 \cdot 0.5 + 0 + 0 + 0.10 \cdot 1.0 = 0.375$
$\text{score} = 27.5 - 37.5 = -10.0$

The score is **not zero** because the PCR component is *asymmetric*:
PCR_v = 1.0 contributes 0 to bullish and 1.0 to bearish. This documents the
engine's view that PCR_v = 1.0 is mildly bearish relative to the equity
baseline (typical PCR_v $\approx 0.5$).

(c) $-10 \in (-20, +20)$ and pin_probability = 0 (no opex) → bias is
$\text{NEUTRAL}$.

**E2.** With resistance at $K = 103$: $\text{dist}_R = \mathrm{clip}_{[0,1]}(3/100 / 0.05) = \mathrm{clip}_{[0,1]}(0.6) = 0.6$.

The new bullish_raw = $0.30 \cdot 0.6 + 0.25 \cdot 0.9465 + 0 + 0 + 0.10 \cdot 0.9435 = 0.180 + 0.2366 + 0.0944 = 0.5110$
→ bullish_score = 51.10. bearish_score unchanged at 16.90. score = +34.20.

Action: $+34.20 < +40$ so rule 1 fails. $+34.20 \geq +10$ so rule 2 matches
→ `SELL_CALL_PARTIAL`. Moving the resistance wall close to spot effectively
shrinks the upside room and downgrades the recommendation from aggressive
to partial.

**E3.** Base case: $\text{dist\_pct} = |100-99.5|/100 = 0.005 \leq 0.02$
→ $f_{\text{dist}} = 1.0$. $f_{\text{opex}} = \mathrm{clip}_{[0,1]}(1 - 5/14) = 9/14 \approx 0.643$.
$f_{\text{oi}} = 0.8$. Pin $= 1.0 \cdot 0.643 \cdot 0.8 \approx 0.514$. (Just below the
0.6 PIN_RISK threshold.)

(a) opex = 20 days $\geq 14$ but $< 30$: $f_{\text{opex}} = \mathrm{clip}_{[0,1]}(1 - 20/14) = 0$. Pin = 0.

(b) spot = 96, dist_pct = 4/100 = 0.04. $f_{\text{dist}} = (0.05 - 0.04)/(0.05 - 0.02) = 1/3$.
Pin = $0.333 \cdot 0.643 \cdot 0.8 \approx 0.171$. Far below 0.6.

(c) OI conc = 0.1. Pin = $1.0 \cdot 0.643 \cdot 0.1 \approx 0.064$.

Each factor is a *necessary* condition; any one being weak kills the
joint pin signal. That's the multiplicative-structure intuition: all three
must agree.

**E4.** `WAIT`: $|s| < 10$ AND $p \geq 0.6$. e.g. $(s, g, p) = (+8, 0.2, 0.7)$.
`MONITOR`: everything else not matching rules 1–5. e.g.
$(+5, 0.2, 0.4)$ — score in WAIT band but pin too low; rules 2/5 don't fire because $|s| < 10$;
rule 4 doesn't fire because $s > -20$; rule 6 catches it as `MONITOR`.

**E5.** The V1 decision tree uses magnitude because two of the gated
rules require a *strength* condition ("dealers heavily long → don't
aggressively sell calls" / "dealers heavily short → strongly consider
buying protection"). The strength is the magnitude; the direction is
already encoded in the score's sign (bullish chains tend to have
dealers short gamma above spot — vol amplifier — and the action gate
fires regardless of sign because the score itself carries direction).

A sign-aware rule might be: *if $\text{gamma\_sign} = +1$ AND
$\text{score} \leq -10$, prefer `REDUCE_COVERAGE` over `BUY_PROTECTION`
because dealers will dampen the move and the puts will bleed theta
faster*. That rule belongs in Phase 1.5's `rules.yaml` per ADR-0008 —
V1 keeps the decision tree small and pushes refinements outside the
engine, where they can be hot-swapped without engine version bumps.

**E6.** Confidence = $250 / 100{,}000 = 0.0025$ — one-quarter of one
percent of saturation. The Composer is multiplicative
([ADR-0003](../decisions/0003-confidence-composer-multiplicative.md)),
so this factor of 0.0025 enters the composite confidence
*multiplicatively*. Even if every other engine yields 1.0 confidence, the
final composite is $\leq 0.0025$ — effectively zero. The Today screen UI
will badge the decision as "low-confidence" or suppress it. The
multiplicative chain enforces "any one weak signal kills the decision,"
which is the conservative bias the engine should have when a chain is
genuinely thin.

**E7.** Put-side rich → skew = +0.05 (positive).
$\text{bullish\_skew} = \max(0, -0.05) = 0$;
$\text{bearish\_skew} = \max(0, +0.05) = 0.05$.
New bullish_raw $= 0.6310$ (unchanged from §10 baseline).
New bearish_raw $= 0.1690 + 0.20 \cdot 0.05 = 0.1790$.
$\text{bullish\_score} = 63.10$ (unchanged); $\text{bearish\_score} = 17.90$.
$\text{score} = 63.10 - 17.90 = +45.20$ (down from +46.20).
Still $\geq +40$, gamma still $\leq 0.5$ → action
unchanged: `SELL_CALL_AGGRESSIVE`. The put-side skew nudge slightly
shrinks the bullish lead but doesn't flip the recommendation. M1.6
proves out the "no recalibration needed" property — pre-existing
thresholds keep working as the formula's range expands from [-65, +65]
to [-85, +85].

**E8.** Both the bucketer and the explanation builder use the same
constant `_PIN_EXPLAIN_THRESHOLD = _BIAS_PIN_THRESHOLD = 0.6`. The
bucketer returns `PIN_RISK` iff $p \geq 0.6$. The explanation appends the
pin sentence iff $p \geq 0.6$. Therefore: `bias == PIN_RISK` ⇔ pin
sentence present.

For non-`PIN_RISK` biases ($p < 0.6$), the explanation **never** contains
"High pin probability." This invariant is asserted by the test
`test_pin_threshold_invariant_bias_matches_explanation`.

**E9.** Loosening `_PIN_TIGHT_PCT` from 0.02 to 0.03 changes the
piecewise-linear shape of `sigmoid_pin`. The same input chain now produces
a *different* pin probability and possibly a different bias / action.
Per [ADR-0005](../decisions/0005-engine-pure-function-discipline.md), any
behavioral change that affects engine output is at least a **minor** bump
(patch is reserved for bugfixes that change *no* observable behavior).
Replay (same `inputs_hash` + `weights_version` + new `engine_version`)
will yield a different `DailyDecision` — that's exactly the reason
`engine_version` is pinned: to detect and explain such drift. CI's
`scripts/check_engine_version_bump.sh` enforces the bump on every change
under `packages/engine/engine/`.

---

## 12. Further reading

### Project artifacts

- Plan v1.2 §9.3 (Flow Score Engine spec), §9.3a (V1 LOCKED contract),
  §22.2 (FlowScore schema reconciliation), §22.13 (breakdown for the
  Confidence Composer), §17 M1.5b (size M acceptance criteria).
- [ADR-0003](../decisions/0003-confidence-composer-multiplicative.md) —
  multiplicative-penalty Confidence Composer that consumes
  `FlowScore.confidence`.
- [ADR-0005](../decisions/0005-engine-pure-function-discipline.md) —
  pure-function discipline + SemVer policy that gate `compute()`.
- [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) — Phase 4
  ML node-swap that replaces `compute()`'s body while preserving the
  contract; also the Phase 1.5 E1 GEX module that supplies real
  `GammaWall` records to `gamma_score`.
- [Market State Engine tutorial](./market-state-engine.md) — sibling
  tutorial covering the regime classifier upstream of the Flow Score
  Engine.
- [Scoring Primitives tutorial](./scoring-primitives.md) — sibling
  tutorial covering the four primitives (`iv_score`, `structure_score`,
  `event_score`, `gamma_score`) that the Flow Score Engine and Market
  State Engine consume.

### Code

- [`packages/engine/engine/flow_score/`](../../packages/engine/engine/flow_score) — the orchestrator + primitives.
  - [`compute.py`](../../packages/engine/engine/flow_score/compute.py) — the orchestrator.
  - [`types.py`](../../packages/engine/engine/flow_score/types.py) — V1 LOCKED contract.
  - [`oi_walls.py`](../../packages/engine/engine/flow_score/oi_walls.py) — support/resistance levels.
  - [`dealer_gamma.py`](../../packages/engine/engine/flow_score/dealer_gamma.py) — V1 dealer-gamma proxy.
  - [`pin_probability.py`](../../packages/engine/engine/flow_score/pin_probability.py) — sigmoid_pin estimator.
  - [`skew.py`](../../packages/engine/engine/flow_score/skew.py) — 25-Δ IV skew, active from M1.6.
  - [`futures_basis.py`](../../packages/engine/engine/flow_score/futures_basis.py) — V1 stub awaiting Phase 2 futures service.
  - [`explanation.py`](../../packages/engine/engine/flow_score/explanation.py) — human-readable rationale.
- [`packages/engine/engine/greeks.py`](../../packages/engine/engine/greeks.py) — Black-Scholes-Merton Greeks (delta, gamma, vega, theta, rho, time_to_expiry_years), introduced in M1.6 and consumed by `skew_25d`.
- [`packages/engine/tests/test_flow_score_compute.py`](../../packages/engine/tests/test_flow_score_compute.py) — 58 tests on `compute()` and its helpers, including a Hypothesis property test asserting bounded outputs across the input space.
- [`packages/engine/tests/test_flow_score_skew.py`](../../packages/engine/tests/test_flow_score_skew.py) — 13 tests on the M1.6 real `skew_25d` (flat smile, put-rich, call-rich, multi-expiry, edge cases, integration with `compute()`).
- [`packages/engine/tests/test_greeks.py`](../../packages/engine/tests/test_greeks.py) — 43 tests on the Greeks module (hand-computed references, put-call parity property test via Hypothesis, monotonicity invariants, validation surface).
- [`packages/engine/engine/_utils.py`](../../packages/engine/engine/_utils.py) — `clip01` used everywhere in this module.

### External / academic

- Sinclair, *Volatility Trading*, ch. 7–8 — pin-risk and dealer-flow
  mechanics; the operational foundation of the §9.3a formula.
- Garleanu, Pedersen, & Poteshman, *Demand-Based Option Pricing* (Review
  of Financial Studies, 2009) — empirical evidence that net option
  demand affects implied volatilities and, by extension, dealer positioning.
- Ni, Pearson, & Poteshman, *Stock Price Clustering on Option Expiration
  Dates* (Journal of Financial Economics, 2005) — the empirical paper
  that established the max-pain-pinning phenomenon at monthly opex.
- Bollen & Whaley, *Does Net Buying Pressure Affect the Shape of Implied
  Volatility Functions?* (Journal of Finance, 2004) — net-pressure
  models of skew that the M1.6 `skew_25d` is calibrated to.
- Hull, *Options, Futures, and Other Derivatives* (10e), chs. 15 + 17 —
  textbook reference for the Black-Scholes-Merton Greeks the M1.6
  module implements.
- Squeeze Metrics / SpotGamma white papers (public versions) — practitioner
  treatment of dealer GEX walls and the vol-amplifier / vol-dampener
  intuition the gamma sign captures.

---

## 13. Glossary of symbols

| Symbol | Meaning |
|---|---|
| $S$ | Spot price of the underlying |
| $K_c, K_p$ | Strike of a call / put contract |
| $K^*$ | Max-pain strike (the candidate underlying-at-expiry that minimizes total writer pain) |
| $K_R, K_S$ | Resistance / support OI-wall strikes (from `compute_oi_walls`) |
| $\text{dist}_R, \text{dist}_S$ | $\mathrm{clip}_{[0,1]}(|K_R - S| / (S \cdot 0.05))$ and analogous for support; 0.5 when wall missing |
| $\text{OI}_c$ | Open interest of contract $c$ |
| $\Pi$ | Dealer-gamma proxy = `compute_dealer_gamma_proxy()` output |
| $D$ | `gamma_score` normalizer = $S \cdot 10{,}000$ |
| $\mathcal{W}$ | Set of `GammaWall` records (empty in V1) |
| $\text{PCR}_v, \text{PCR}_{OI}$ | Put–call ratio by volume / by OI |
| $\text{skew}$ | 25-delta IV skew = avg over expiries of (IV(25-Δ put) − IV(25-Δ call)); real impl from M1.6 |
| $\text{basis}$ | Front-month futures basis = (futures − spot) / spot; V1 stub = 0 |
| $\Delta_{BS}(c)$ | BS delta of contract $c$ at its own IV (used by M1.6 `skew_25d` to find the 25-Δ strikes) |
| $\tau$ | Time-to-expiry year-fraction = $\max((\text{expiry} - \text{as\_of}).\text{days}, 1) / 365$ |
| $r, q$ | Continuous-compounding risk-free rate and dividend yield (V1 priors: 0.05, 0.0) |
| $f_{\text{dist}}, f_{\text{opex}}, f_{\text{oi}}$ | The three factors of `sigmoid_pin` |
| $p$ | Pin probability = `sigmoid_pin()` output ∈ $[0, 1]$ |
| $s$ | Signed FlowScore composite ∈ $[-100, +100]$ |
| $g$ | `gamma_score.score` magnitude ∈ $[0, 1]$, exposed as `gamma_risk` |
| `_W_DIST = 0.30`, `_W_VOL = 0.25`, `_W_SKEW = 0.20`, `_W_BASIS = 0.15`, `_W_PCR = 0.10` | The five §9.3a component weights (sum = 1.0) |
| `_WALL_FAR_PCT = 0.05`, `_WALL_MISSING_PRIOR = 0.5` | Wall-distance normalization constants |
| `_BIAS_BULLISH_THRESHOLD = +20`, `_BIAS_BEARISH_THRESHOLD = -20`, `_BIAS_PIN_THRESHOLD = 0.6` | Bias bucketing thresholds |
| `_ACTION_AGGRESSIVE_SCORE = 40`, `_ACTION_AGGRESSIVE_GAMMA = 0.5` | `SELL_CALL_AGGRESSIVE` gate |
| `_ACTION_PARTIAL_SCORE = 10` | `SELL_CALL_PARTIAL` gate |
| `_ACTION_WAIT_SCORE_BAND = 10`, `_ACTION_WAIT_PIN = 0.6` | `WAIT` gate |
| `_ACTION_PROTECTION_SCORE = -20`, `_ACTION_PROTECTION_GAMMA = 0.6` | `BUY_PROTECTION` gate |
| `_ACTION_REDUCE_SCORE = -10` | `REDUCE_COVERAGE` gate |
| `_CONFIDENCE_OI_SCALE = 100{,}000` | OI value at which confidence saturates to 1.0 |
| $\mathrm{clip}_{[0,1]}(x)$ | Clip to the closed unit interval |

---

*This tutorial is maintained alongside the engine. When any file under
`packages/engine/engine/flow_score/` changes — even a constant — the
same PR updates this file. Contributions welcome via the docs PR workflow
in [`docs/README.md`](../README.md).*
