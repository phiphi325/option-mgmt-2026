# Tutorial: Confidence Composer (`compose()` + the §22.13 multiplicative formula)

> **Audience.** First-year master's students in financial engineering; quant-developer onboarding; anyone consuming `confidence` or `confidence_breakdown` downstream (Recommendation Engine, Today screen UI, persisted `DailyDecision`).
> **Prerequisites.** Read the [Market State Engine tutorial](./market-state-engine.md), the [Scoring Primitives tutorial](./scoring-primitives.md), and the [Flow Score Engine tutorial](./flow-score-engine.md) first. You should be comfortable with `clip01`, with the `*ScoreResult` pattern, with `FlowScore` (especially `confidence` and the signed `score`), and with `MarketStateResult.regime_score` / `trend_strength` / `breakout_signal` / `oi_concentration_at_max_pain`.
> **Reading time.** ~55 min careful read with the exercises; ~20 min skim.
> **Engine version covered.** `1.1.0` (M1.10) onward. The composer + components + YAML loader live in [`packages/engine/engine/confidence/`](../../packages/engine/engine/confidence); the on-disk weights config lives in [`packages/engine/config/weights.yaml`](../../packages/engine/config/weights.yaml).
>
> **Disclaimer.** This tutorial is **educational material**. The Confidence Composer is a decision-support component, not investment advice. See [`docs/disclaimers.md`](../disclaimers.md).

---

## Table of contents

1. [Why a Confidence Composer?](#1-why-a-confidence-composer)
2. [The §22.13 redesign — why multiplicative?](#2-the-2213-redesign--why-multiplicative)
3. [The six components — what each one measures](#3-the-six-components--what-each-one-measures)
4. [`compose()` — the formula in code](#4-compose--the-formula-in-code)
5. [Per-component scoring functions (V1 priors)](#5-per-component-scoring-functions-v1-priors)
6. [`event_risk_penalty` — the drawdown-tolerance boost](#6-event_risk_penalty--the-drawdown-tolerance-boost)
7. [`illiquidity_penalty` — M1.11 plumbing](#7-illiquidity_penalty--m111-plumbing)
8. [Weights and versioning](#8-weights-and-versioning)
9. [`ConfidenceBreakdown` — explainability and UI](#9-confidencebreakdown--explainability-and-ui)
10. [Integration with `recommend()`](#10-integration-with-recommend)
11. [End-to-end worked example](#11-end-to-end-worked-example)
12. [Hands-on exercises](#12-hands-on-exercises)
13. [Further reading](#13-further-reading)
14. [Glossary of symbols](#14-glossary-of-symbols)

---

## 1. Why a Confidence Composer?

### 1.1 The role in the architecture

By the time the decision pipeline reaches the Confidence Composer, three
upstream engines have already produced opinions:

- **Market State Engine** has classified one of six `Regime`s with a
  `regime_score ∈ [0, 1]` quantifying classifier confidence.
- **Flow Score Engine** has produced a signed `score ∈ [-100, +100]`, a
  categorical `bias`, and its own `confidence ∈ [0, 1]` derived from OI
  totals in focus expiries.
- **Recommendation Engine** has run the rule pipeline against those two
  inputs plus `PositionState` and `UserStrategyProfile`, and either
  matched a rule (e.g. `high_iv_sell_call` → `SELL_COVERED_CALL_PARTIAL`)
  or fallen back to `hold_no_op`.

What's missing is a **single bounded number** that summarizes _how much
the system trusts this recommendation right now_ — one scalar that the
Today screen UI can render as a "confidence pill" and that the audit
trail can persist on `DailyDecision`. That is the Confidence Composer's
job:

```
MarketStateResult ──┐
                    │
FlowScore ──────────┤
                    │  ConfidenceInputs   compose()       ConfidenceBreakdown
UserStrategyProfile ┼───────────────────────────────────► (confidence, breakdown)
                    │
illiquidity (M1.11) ┘                       │
                                            ▼
                                    DailyDecision.confidence
                                    DailyDecision.confidence_breakdown
                                    UI "confidence pill"
                                    rules.yaml `confidence_lte:` clause
```

`compose()` is the **only public entry point** for the math itself: pure,
deterministic, fully keyword-only. Same `ConfidenceInputs` + `Weights` →
byte-identical `(confidence, breakdown)` pair. That property is what the
daily `DailyDecision` replay system relies on (per
[ADR-0005](../decisions/0005-engine-pure-function-discipline.md)) and
what makes `weights_version` a sufficient pin alongside `engine_version`
+ `inputs_hash`.

### 1.2 Where it sits in the §9.11 wiring matrix

The plan v1.2 §9.11 wiring matrix tells us which engines consume which
upstream scoring primitives. The Confidence Composer sits in the most
densely connected row:

| Consumer | iv | structure | gamma | event | flow |
|---|:---:|:---:|:---:|:---:|:---:|
| Market State Engine (`classify`) | ✓ | ✓ |   | ✓ |   |
| Flow Score Engine (orchestrator) | ✓ |   | ✓ |   | (self) |
| Recommendation Engine |   | ✓ |   |   | ✓ |
| **Confidence Composer** | ✓ | ✓ |   | ✓ | ✓ |
| Collar Builder | ✓ |   |   | ✓ |   |
| Strike Selector | ✓ |   |   |   |   |

The composer reads four out of the five scoring families. It is the
last node in the decision pipeline that touches raw market signals
before the answer is handed to the user.

### 1.3 Design objectives

The Confidence Composer inherits the engine-wide objectives from
[ADR-0005](../decisions/0005-engine-pure-function-discipline.md), plus
four of its own (per [ADR-0003](../decisions/0003-confidence-multiplicative.md)
and plan §22.13):

1. **One bounded number.** Output is always in `[0, 1]`. No ambiguity
   about scale; no need for downstream code to renormalize.
2. **Explainable.** The composer always returns a `ConfidenceBreakdown`
   alongside the scalar — the UI can show "78% confidence, weighed down
   16% by event proximity." Without the breakdown a single number is
   un-auditable.
3. **Hot-swappable weights.** `weights.yaml` is the deployable
   calibration source. ADR-0008 Phase 1.5 moves it to
   `apps/api/app/config/` for hot-swap without an engine version bump.
4. **Forward-compatible.** One of the six components
   (`illiquidity_penalty`) is a V1 stub returning `0.0` — the
   plumbing for M1.11 Execution Feasibility is in place; only the
   value source changes when M1.11 ships. No formula or schema bump.

---

## 2. The §22.13 redesign — why multiplicative?

### 2.1 The audit story

The original §9.7 formula (v1.0 of the plan) was a signed-weight
additive blend:

$$
\text{confidence}_\text{v1} = \text{clip}_{[0,1]} \Big(
    w_\text{flow} \cdot c_\text{flow} +
    w_\text{struct} \cdot c_\text{struct} +
    w_\text{regime} \cdot c_\text{regime} +
    w_\text{signal} \cdot c_\text{signal} -
    w_\text{event} \cdot p_\text{event} -
    w_\text{liq} \cdot p_\text{liq}
\Big)
$$

with hand-picked weights of $w_\text{flow} = 0.30$, $w_\text{struct} =
0.25$, $w_\text{regime} = 0.25$, $w_\text{signal} = 0.20$,
$w_\text{event} = 0.10$, $w_\text{liq} = 0.10$.

The §8 audit caught the bug: the **achievable range of this expression
is $[-0.20, +0.80]$, not $[-1, +1]$**. Even with every positive
component pegged at 1.0 and every penalty pegged at 0.0:

$$
0.30 \cdot 1 + 0.25 \cdot 1 + 0.25 \cdot 1 + 0.20 \cdot 1 - 0 - 0 = 0.80
$$

After the `clip01`, confidence v1.0 is bounded at 0.80. A user can
never see "100% confidence" no matter how clean the inputs. Worse, the
practical mid-range floats around $\text{clip}(0.50) = 0.50$ — small
variations in positive components and penalties both move the score by
similar additive amounts, so the model effectively can't differentiate
"strong signal, mild headwind" from "weak signal, no headwind."

§22.13 redesigned the math to restore a true $[0, 1]$ codomain by
splitting the formula into two stages:

$$
\begin{aligned}
\text{positive} &= \text{clip}_{[0,1]} \Big(
    w_\text{flow} c_\text{flow} +
    w_\text{struct} c_\text{struct} +
    w_\text{regime} c_\text{regime} +
    w_\text{signal} c_\text{signal}
\Big) \\
\text{penalty\_mult} &= (1 - \kappa_\text{event} \cdot p_\text{event}) \cdot (1 - \kappa_\text{liq} \cdot p_\text{liq}) \\
\text{confidence} &= \text{clip}_{[0,1]} (\text{positive} \cdot \text{penalty\_mult})
\end{aligned}
$$

where $\sum w = 1.0$ and $\kappa_\text{event}, \kappa_\text{liq} \in [0, 1]$ are
the **caps** — the maximum reduction each penalty can apply.

### 2.2 What changes in practice

| Property | v1.0 additive | v2.0 multiplicative (M1.10) |
|---|---|---|
| Achievable range | $[-0.20, +0.80]$ post-clip | $[0, 1]$ exactly |
| Perfect components, no penalties | 0.80 | **1.0** |
| Perfect components, max penalties | 0.60 | $(1 - 0.30)(1 - 0.25) = 0.525$ |
| Zero components, any penalties | 0.0 (clip floor) | 0.0 |
| Positive-only semantics | "Score" — can be negative pre-clip | "Weighted mean of positives" — always in $[0, 1]$ |
| Penalty semantics | "Subtract from score" | "Multiplicatively reduce score" |
| Interpretation of components | Mixed sign convention | Uniform: all components in $[0, 1]$, higher = more positive (or more penalty, depending on slot) |

The multiplicative form is strictly more expressive: penalties scale
the positive score down by a percentage rather than subtracting a fixed
amount, so they bite harder on already-strong signals than on weak ones
— which matches financial intuition (a tightly liquidity-constrained
strategy is no better than a wide-open one when both have weak signal).

### 2.3 ADR-0003

[ADR-0003](../decisions/0003-confidence-multiplicative.md) locks the
multiplicative discipline. The §22.13 redesign honors it; the v1.0
additive form is rejected. Future calibration changes update the
weights values (in `weights.yaml`) and bump `weights_version`; they do
**not** revisit the multiplicative structure without a new ADR.

---

## 3. The six components — what each one measures

Per §22.13 and §9.7, the composer takes a `ConfidenceInputs` bundle
with exactly six fields, all in $[0, 1]$. Construction-time validation
in `ConfidenceInputs.__post_init__` rejects any out-of-range value so
downstream code can assume bounded inputs.

```python
@dataclass(frozen=True)
class ConfidenceInputs:
    flow_alignment: float       # positive: signal alignment from FlowScore
    structure_alignment: float  # positive: signal alignment from market structure
    regime_match: float         # positive: regime classifier confidence
    signal_alignment: float     # positive: composite reliability blend
    event_risk_penalty: float   # penalty: proximity to scheduled event
    illiquidity_penalty: float  # penalty: execution feasibility
```

### 3.1 The four positive components

Each positive component answers a different question:

| Component | Question it answers | V1 source |
|---|---|---|
| `flow_alignment` | "Is the dealer-flow signal reliable _and_ decisive?" | `FlowScore.confidence` + `\|FlowScore.score\|/100` |
| `structure_alignment` | "Does market structure (trend / breakout / pin) point clearly in one direction?" | `MarketStateResult.{trend_strength, breakout_signal, oi_concentration_at_max_pain}` |
| `regime_match` | "How confident is the regime classifier in its winner?" | `MarketStateResult.regime_score` (direct passthrough) |
| `signal_alignment` | "Do the two upstream engines (regime + flow) agree on a strong reading?" | `0.5 \cdot regime_score + 0.5 \cdot FlowScore.confidence` |

The four are deliberately **not orthogonal** — `signal_alignment`
re-uses `regime_score` and `FlowScore.confidence` that
already appear in `regime_match` and `flow_alignment`. That's
intentional: each component asks a slightly different question, and the
weighting ($w_\text{regime} = 0.25$, $w_\text{signal} = 0.20$,
$w_\text{flow} = 0.30$) controls how much overlap is rewarded.

### 3.2 The two penalty components

`event_risk_penalty` and `illiquidity_penalty` are scaled in the
opposite direction: **higher penalty value → more reduction of
confidence**. Like the positives, they're in $[0, 1]$; the caps
($\kappa_\text{event} = 0.30$, $\kappa_\text{liq} = 0.25$) bound how
much they can multiplicatively reduce the final confidence.

A penalty value of `1.0` corresponds to the worst-case scenario for
that risk dimension:

- `event_risk_penalty = 1.0` → "event is today or tomorrow"
- `illiquidity_penalty = 1.0` → "the chain is essentially unfillable
  for the recommended strikes"

The cap structure makes this readable in plain English:
*"event risk can reduce confidence by at most 30%; illiquidity can
reduce it by at most 25%; the worst case is `0.70 × 0.75 = 0.525`."*

### 3.3 Why six and not seven?

§9.7 v1.0 enumerated **six** components; the user's M1.10 framing
mentioned "seven component scoring functions." The plan §22.13
redesign is explicit: six components — four positive + two
multiplicative penalties. If we counted `compose()` itself as the
seventh function in the public surface, you get seven _functions_ but
six _components_. M1.10 ships per the spec.

ADR-0008 Phase 4 ML may eventually replace one or more component
scorers with learned models; the cap structure and the six-slot
schema are the boundary that lets that node-swap happen without
breaking the rest of the engine.

---

## 4. `compose()` — the formula in code

The whole thing fits in fewer than twenty lines (per
[`engine/confidence/compose.py`](../../packages/engine/engine/confidence/compose.py)):

```python
def compose(
    inputs: ConfidenceInputs,
    weights: Weights,
) -> tuple[float, ConfidenceBreakdown]:
    positive = clip01(
        weights.positive_weights.flow   * inputs.flow_alignment
        + weights.positive_weights.struct * inputs.structure_alignment
        + weights.positive_weights.regime * inputs.regime_match
        + weights.positive_weights.signal * inputs.signal_alignment
    )
    penalty_mult = (
        (1.0 - weights.penalty_caps.event     * inputs.event_risk_penalty)
        * (1.0 - weights.penalty_caps.liquidity * inputs.illiquidity_penalty)
    )
    confidence = clip01(positive * penalty_mult)

    breakdown = ConfidenceBreakdown(
        flow_alignment=inputs.flow_alignment,
        structure_alignment=inputs.structure_alignment,
        regime_match=inputs.regime_match,
        signal_alignment=inputs.signal_alignment,
        event_risk_penalty=inputs.event_risk_penalty,
        illiquidity_penalty=inputs.illiquidity_penalty,
        positive_score=positive,
        penalty_multiplier=penalty_mult,
        weights_version=weights.version,
    )
    return confidence, breakdown
```

Three things to notice:

1. **The two `clip01` calls** are belt-and-suspenders. Because $\sum w = 1.0$
   and each $c \in [0, 1]$, the inner weighted sum is mathematically
   already in $[0, 1]$ — but floating-point rounding can land
   $0.30 \cdot 1 + 0.25 \cdot 1 + 0.25 \cdot 1 + 0.20 \cdot 1$ at
   $1.0000000000000002$. The outer clip is similarly defensive.
2. **`weights_version` is stamped on the breakdown.** This is what makes
   `DailyDecision` replay safe across calibration changes: future ML
   tuning bumps `version: "v2.0"` to `"v2.1"`, and an old decision row
   with `weights_version = "v2.0"` can be replayed against the v2.0
   weights even after `weights.yaml` has been edited.
3. **No side effects.** The function does not log, raise (under valid
   inputs), or read clock / env / filesystem. It's the canonical
   example of an ADR-0005 pure function.

### 4.1 The §22.13 worked example, byte-for-byte

The plan §22.13 walks through one example explicitly. Inputs:

$$
\begin{aligned}
c_\text{flow} &= 0.80 \\
c_\text{struct} &= 0.70 \\
c_\text{regime} &= 0.90 \\
c_\text{signal} &= 0.75 \\
p_\text{event} &= 0.10 \\
p_\text{liq} &= 0.05
\end{aligned}
$$

With V1 weights:

$$
\begin{aligned}
\text{positive} &= 0.30 \cdot 0.80 + 0.25 \cdot 0.70 + 0.25 \cdot 0.90 + 0.20 \cdot 0.75 \\
              &= 0.24 + 0.175 + 0.225 + 0.15 \\
              &= 0.79 \\
\text{penalty\_mult} &= (1 - 0.30 \cdot 0.10) \cdot (1 - 0.25 \cdot 0.05) \\
              &= 0.97 \cdot 0.9875 \\
              &= 0.957875 \\
\text{confidence} &= \text{clip}_{[0,1]} (0.79 \cdot 0.957875) \\
              &\approx 0.7567 \\
              &\approx 0.76 \quad \text{(when rounded to 2 dp for display)}
\end{aligned}
$$

`tests/test_confidence.py::test_compose_matches_plan_section_22_13_worked_example`
pins this exactly. It's the calibration anchor: any change to V1
component priors, weights, or formula structure has to either keep this
example invariant or explicitly update the test (with the corresponding
`weights_version` bump in `weights.yaml`).

### 4.2 Corner cases

| Inputs | Output | Notes |
|---|---|---|
| All positives 1.0; both penalties 0.0 | `confidence = 1.0` | The upper bound is achievable, by design |
| All positives 0.0; any penalties | `confidence = 0.0` | Penalty multiplier never matters when `positive = 0` |
| All positives 1.0; both penalties 1.0 | `confidence = 0.525` | Worst case under V1 caps |
| Only event penalty maxed (1.0) | `multiplier = 0.70` | Other factor is `(1 - 0)` = 1.0 |
| Only liquidity penalty maxed | `multiplier = 0.75` | Symmetric |

A Hypothesis property test verifies that for **any** $[0, 1]$ inputs,
`0 ≤ confidence ≤ 1`, `0 ≤ positive_score ≤ 1`, and
`0 ≤ penalty_multiplier ≤ 1`. Two more property tests verify monotonicity:
increasing a positive component cannot decrease `confidence`, and
increasing a penalty cannot increase it.

---

## 5. Per-component scoring functions (V1 priors)

The composer takes a pre-built `ConfidenceInputs`. Where do the six
component values come from? `engine/confidence/components.py` ships V1
priors — pure functions that translate upstream engine outputs into
the $[0, 1]$ slots. ADR-0008 Phase 4 ML may eventually replace any of
these with learned scorers; the contract (signature → $[0, 1]$) is
the replaceable-node boundary.

### 5.1 `flow_alignment`

```python
def compute_flow_alignment(flow_score: FlowScore) -> float:
    magnitude = abs(flow_score.score) / 100.0
    return clip01(
        _FLOW_W_CONFIDENCE * flow_score.confidence
        + _FLOW_W_MAGNITUDE * magnitude
    )
```

with $w_\text{conf} = w_\text{mag} = 0.5$. Two components:

- **Reliability** (`flow_score.confidence`, already in $[0, 1]$ from OI
  totals in the focus expiries — see the [Flow Score tutorial §8](./flow-score-engine.md#8-confidence-and-the-explanation-builder)).
- **Magnitude** ($|\text{score}|/100$ — how decisive the signed score is).
  A `NEUTRAL` flow with `score = 0` has magnitude 0 regardless of how
  much OI backs the chain; a strongly bullish flow with `score = +80`
  has magnitude 0.80.

A `BULLISH` `FlowScore` with `confidence = 0.80, score = +40` gives
$0.5 \cdot 0.80 + 0.5 \cdot 0.40 = 0.60$. A `NEUTRAL` flow with the
same `confidence` but `score = 0` gives $0.5 \cdot 0.80 + 0 = 0.40$ —
the composer treats high-confidence-but-noncommittal flow as a weaker
contribution than high-confidence-and-decisive flow, which matches
intuition.

### 5.2 `structure_alignment`

```python
def compute_structure_alignment(market_state: MarketStateResult) -> float:
    return clip01(
        _STRUCT_W_TREND * market_state.trend_strength
        + _STRUCT_W_BREAKOUT * market_state.breakout_signal
        + _STRUCT_W_OI * market_state.oi_concentration_at_max_pain
    )
```

with $w_\text{trend} = 0.50$, $w_\text{breakout} = 0.30$,
$w_\text{oi} = 0.20$. The blend favors **sustained** trend signal over
single-bar breakout, with a smaller contribution from OI concentration
(which doubles as a pin-risk indicator).

All three inputs come from the Market State Engine and are already
canonical $[0, 1]$ scalars (see the [Market State tutorial §3](./market-state-engine.md#3-the-mvp-features)).

### 5.3 `regime_match`

```python
def compute_regime_match(market_state: MarketStateResult) -> float:
    return clip01(market_state.regime_score)
```

Direct passthrough of the regime classifier's confidence. The `clip01`
is defensive — `regime_score` is already in $[0, 1]$ per the
`MarketStateResult` contract, but if a future change loosens that
contract the composer's input invariant won't silently break.

### 5.4 `signal_alignment`

```python
def compute_signal_alignment(
    market_state: MarketStateResult,
    flow_score: FlowScore,
) -> float:
    return clip01(
        _SIGNAL_W_REGIME * market_state.regime_score
        + _SIGNAL_W_FLOW * flow_score.confidence
    )
```

with $w_\text{regime} = w_\text{flow} = 0.5$. This is the
"cross-engine agreement" component — both engines confident together →
high alignment; one weak engine → mid; both weak → low.

Notice that `signal_alignment` re-uses `regime_score` and
`flow_score.confidence` that already appear in `regime_match` and
`flow_alignment`. That's not double-counting in a problematic sense:
the four components capture different questions, and the weights
control the relative emphasis. The `signal_alignment` slot specifically
rewards two-engine agreement on top of the per-engine signals.

### 5.5 `event_risk_penalty` (full treatment in §6)

```python
def compute_event_risk_penalty(
    market_state: MarketStateResult,
    profile: UserStrategyProfile,
) -> float:
    days = market_state.days_to_next_event
    if days is None:
        return 0.0
    raw = clip01(1.0 - float(days) / _EVENT_HORIZON_DAYS)
    if profile.drawdown_tolerance < _DRAWDOWN_BOOST_THRESHOLD:
        raw *= _DRAWDOWN_BOOST_FACTOR
    return clip01(raw)
```

See [§6](#6-event_risk_penalty--the-drawdown-tolerance-boost) for the
full walkthrough.

### 5.6 `illiquidity_penalty` (full treatment in §7)

```python
def compute_illiquidity_penalty() -> float:
    return 0.0  # V1 stub — M1.11 Execution Feasibility plumbs the real value
```

See [§7](#7-illiquidity_penalty--m111-plumbing) for the plumbing pattern.

### 5.7 The aggregate constructor

```python
def compute_confidence_inputs(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    profile: UserStrategyProfile,
    illiquidity_penalty: float = 0.0,
) -> ConfidenceInputs:
    return ConfidenceInputs(
        flow_alignment=compute_flow_alignment(flow_score),
        structure_alignment=compute_structure_alignment(market_state),
        regime_match=compute_regime_match(market_state),
        signal_alignment=compute_signal_alignment(market_state, flow_score),
        event_risk_penalty=compute_event_risk_penalty(market_state, profile),
        illiquidity_penalty=clip01(illiquidity_penalty),
    )
```

One call, one bundle. `recommend()` and (later) the M1.13 Master
Decision Engine both go through this constructor — keeping the
aggregation in one place means changes to the component blend ripple
through every caller automatically.

`illiquidity_penalty` is an explicit kwarg with a `0.0` default
specifically because M1.11 will plumb a real value through it; until
then every caller can use the default without code changes. The
keyword-only signature prevents accidental positional misuse as new
parameters land.

---

## 6. `event_risk_penalty` — the drawdown-tolerance boost

This component deserves its own section because it's the only one
where the user's profile bleeds into the math.

### 6.1 The linear ramp

The V1 calibration assumes a 30-day attention horizon: events more than
30 days away have negligible immediate risk; events within the window
ramp linearly to 1.0 as days-to-event approaches 0.

$$
p_\text{event}^\text{raw} =
  \begin{cases}
    0 & \text{if } d \text{ is None or } d \ge 30 \\
    \dfrac{30 - d}{30} & \text{if } 0 \le d < 30
  \end{cases}
$$

| `days_to_next_event` | `p_event^raw` |
|---:|---:|
| `None` (no scheduled event) | 0.00 |
| 60 | 0.00 (out of horizon) |
| 30 | 0.00 (horizon edge) |
| 15 | 0.50 |
| 7 | $\approx 0.77$ |
| 3 | 0.90 |
| 0 (event today) | 1.00 |

### 6.2 The drawdown-tolerance boost

Plan §9.7 line 1553 specifies that the event penalty is **up-weighted
for low-tolerance users**:

$$
p_\text{event} =
  \begin{cases}
    \text{clip}_{[0,1]}(1.5 \cdot p_\text{event}^\text{raw})
      & \text{if } \texttt{drawdown\_tolerance} < 0.10 \\
    p_\text{event}^\text{raw}
      & \text{otherwise}
  \end{cases}
$$

The motivation is operational: a user who explicitly told the engine
"I can only tolerate a 10% drawdown" should see lower confidence
near events than a more risk-tolerant user, even for the same raw
event proximity. The composer turns that profile slider into actual
penalty weight rather than asking the UI to render different
confidence numbers for the same engine output.

The boost is multiplied **before** the final clip — a raw value of
$0.80$ with low tolerance becomes $1.20$ pre-clip, which clips to
$1.0$. Combined with the cap $\kappa_\text{event} = 0.30$, this caps
the maximum reduction at 30% regardless of how aggressive the boost
was. The `1.5×` boost factor is a V1 prior; Phase 4 ML may learn a
profile-dependent function but the cap structure is invariant.

### 6.3 Why a stepped boost rather than a smooth scaler?

The V1 design uses a hard threshold (`< 0.10` → boost, else no boost)
rather than a continuous `boost = f(tolerance)` function. Two reasons:

1. **Defaults dominate.** Most users will accept the
   `drawdown_tolerance = 0.15` default. Stepping at `< 0.10` means the
   boost only fires when the user has _explicitly_ said "I'm more
   risk-averse than the default." A continuous function would
   silently nudge every confidence number for everyone, which is
   harder to explain in the UI.
2. **Calibration is hand-set.** V1 priors are deliberate; smooth
   functions hide where the cut-offs are. A reviewer reading the code
   can immediately see that 0.10 is the boundary.

Phase 4 ML may replace this with a learned smoother; the cap and the
profile coupling stay.

---

## 7. `illiquidity_penalty` — M1.11 plumbing

### 7.1 The stub

```python
def compute_illiquidity_penalty() -> float:
    return 0.0
```

In V1 (engine `1.1.0` through whatever lands before M1.11), this
returns 0.0 unconditionally. Every `recommend()` call in
the integration test suite sees `illiquidity_penalty = 0.0` — confidence
is determined entirely by the four positive components and
`event_risk_penalty`.

### 7.2 Why ship the stub instead of skipping?

The §22.13 schema requires `illiquidity_penalty` as a `ConfidenceInputs`
field. Shipping the stub now means:

- **Schema is complete on day one.** `ConfidenceInputs` has six fields
  even before M1.11. No future field-addition with `weights_version`
  bump.
- **Tests have a name to mock.** `tests/test_confidence.py` includes a
  `test_recommend_illiquidity_penalty_flows_through` test that passes
  `illiquidity_penalty=1.0` through `recommend()` and verifies the
  confidence drops by exactly 25% (the cap). The wire is in place;
  M1.11 replaces only the value source.
- **`weights.yaml` is complete.** `penalty_caps.liquidity: 0.25`
  ships with M1.10. No M1.11 weights bump required.

### 7.3 What M1.11 will plumb

M1.11 ships `engine.execution.assess(...)` returning an
`ExecutionFeasibilityResult` with a `illiquidity_score ∈ [0, 1]`. The
Master Decision Engine (M1.13) will call:

```python
execution = engine.execution.assess(
    selected_strikes=strike_selection,
    chain_snapshot=chain,
    profile=profile,
)
rec = engine.recommend(
    market_state=ms,
    flow_score=fs,
    positions=positions,
    profile=profile,
    rules=rules,
    illiquidity_penalty=execution.illiquidity_score,  # ← the only new line
)
```

`recommend()` already accepts the kwarg and forwards it through
`compute_confidence_inputs`. No `engine.confidence` change is needed
when M1.11 ships.

### 7.4 The pattern, generalized

This pattern — "ship a stub function returning the V1 default; plumb
the call site behind an explicit keyword argument with that default;
unit-test the override path; document the M1.11 hand-off" — is worth
internalizing. The engine uses it elsewhere (`futures_basis = 0` in
Flow Score before futures-service data lands, the `skew_25d` stub
before M1.6 Greeks). It's how you ship a contract-complete schema
without waiting for every upstream input to be available.

---

## 8. Weights and versioning

### 8.1 The on-disk source

[`packages/engine/config/weights.yaml`](../../packages/engine/config/weights.yaml):

```yaml
version: "v2.0"

positive_weights:
  flow:    0.30
  struct:  0.25
  regime:  0.25
  signal:  0.20

penalty_caps:
  event:     0.30
  liquidity: 0.25
```

The schema is validated at load time by
`engine.confidence.yaml_loader._parse_weights_text`. The validator
rejects:

- Missing top-level keys (`version`, `positive_weights`, `penalty_caps`)
- Missing positive keys (`flow`, `struct`, `regime`, `signal`)
- Missing penalty keys (`event`, `liquidity`)
- Non-mapping shapes (the file must be a YAML map, not a list)
- Non-numeric values (`'high'` is rejected; bools are rejected
  explicitly because Python's `bool` subclasses `int`)
- Empty `version` string
- Positive weights that don't sum to 1.0 (within `1e-6` tolerance)
- Penalty caps outside $[0, 1]$
- Negative positive weights

Forward-tolerant: unknown top-level keys (e.g. a future `metadata:`
block) are ignored. This is the same pattern as
`engine.recommendation.yaml_loader` — adding fields later doesn't
break old YAML files.

### 8.2 The in-code mirror

```python
# engine/confidence/__init__.py
DEFAULT_WEIGHTS: Final[Weights] = Weights(
    version="v2.0",
    positive_weights=PositiveWeights(
        flow=0.30, struct=0.25, regime=0.25, signal=0.20,
    ),
    penalty_caps=PenaltyCaps(event=0.30, liquidity=0.25),
)
```

`DEFAULT_WEIGHTS` is a `Final[Weights]` constant that mirrors the YAML.
Why both?

- **`weights.yaml` is the canonical deployable source.** Ops can swap
  it in a Phase 1.5 hot-deploy (per ADR-0008) without rebuilding the
  engine package.
- **`DEFAULT_WEIGHTS` keeps `recommend()` pure.** Calling
  `load_default_weights()` is filesystem I/O, which would violate
  ADR-0005 if it happened inside the engine's hot path. The constant
  lets `recommend()` have a sensible default without reaching for
  disk.

### 8.3 The drift gate

`tests/test_confidence.py::test_default_weights_matches_yaml_drift_check`:

```python
def test_default_weights_matches_yaml_drift_check() -> None:
    on_disk = load_default_weights()
    assert on_disk == DEFAULT_WEIGHTS
```

This is the M1.10 equivalent of the shared-types codegen drift check:
edit `weights.yaml` without updating `DEFAULT_WEIGHTS` (or vice versa)
and CI fails. The two representations cannot silently disagree.

### 8.4 Versioning and replay

`weights_version` flows from `Weights` → `ConfidenceBreakdown` →
(M1.13+) `DailyDecision.weights_version` (persisted as a Postgres
column alongside `engine_version` and `inputs_hash`). The three pins
together make every historical decision exactly replayable:

- Same `engine_version` → same code paths
- Same `weights_version` → same calibration constants
- Same `inputs_hash` → same `MarketStateResult` / `FlowScore` / `PositionState` / `UserStrategyProfile`

Bumping any one without persisting the new value would break replay.
The CI guards (`check_engine_version_bump.sh` for the engine; the
drift test for weights; the inputs-hash semantics established in
M0.6) jointly enforce the invariant.

### 8.5 ADR-0008 Phase 1.5 hot-swap

ADR-0008 plans to move `weights.yaml` to `apps/api/app/config/` in
Phase 1.5 so ops can hot-swap it without rebuilding the engine
package. The loader call signature already takes a `Path`:

```python
weights = load_weights_yaml(Path("/etc/option-mgmt/weights.yaml"))
rec = recommend(..., weights=weights)
```

When the move happens:
- The engine still ships its packaged `weights.yaml` at the current
  path so test fixtures keep working.
- A new API service at startup calls `load_weights_yaml` with the
  configured production path and caches the result.
- `DEFAULT_WEIGHTS` stays in `engine.confidence` as the safety net for
  any caller that doesn't override.

No engine version bump is required to move the file's preferred
location — only the API service config changes.

---

## 9. `ConfidenceBreakdown` — explainability and UI

### 9.1 The shape

```python
@dataclass(frozen=True)
class ConfidenceBreakdown:
    flow_alignment: float
    structure_alignment: float
    regime_match: float
    signal_alignment: float
    event_risk_penalty: float
    illiquidity_penalty: float
    positive_score: float          # NEW — pre-penalty weighted average
    penalty_multiplier: float      # NEW — applied multiplier
    weights_version: str
```

The first six fields echo the inputs. The last three add the
intermediates `compose()` computed:

- `positive_score` — the weighted average of the four positive
  components, before penalties. In $[0, 1]$.
- `penalty_multiplier` — the product
  $(1 - \kappa_e p_e)(1 - \kappa_l p_l)$. In $[0, 1]$.
- `weights_version` — the calibration pin for replay.

`positive_score * penalty_multiplier` equals the final `confidence`
within floating-point epsilon (the outer `clip01` is the only thing
that could change it, and only when both factors are already in
range).

### 9.2 UI rendering (§22.13 final paragraph)

The plan §22.13 final paragraph specifies the UI:

> "Stack 4 positive components as a bar; render the penalty multiplier
> as a darker overlay reducing the final width. More intuitive than
> v1.0's signed-weight chart."

Concretely (for the §22.13 worked example):

```
positive_score = 0.79  ████████████████████████████████████████████████ ↓
penalty_mult   = 0.96  shrinks the bar from 79% → 76% (3pp loss to penalties)
confidence     = 0.76  ███████████████████████████████████████████░░░░░░
```

Each segment of the positive bar is labeled with its component
contribution; the overlay tooltip shows the penalty breakdown ("3pp
lost to event risk, ~0pp to liquidity"). The UI implementation lives
in `apps/web/components/today/ConfidenceBar.tsx` (planned M1.15
when the Today screen integrates).

### 9.3 How the breakdown flows into `recommend()`

```python
@dataclass(frozen=True)
class RecommendationResult:
    actions: tuple[Action, ...]
    matched_rule: MatchedRule | None
    regime: Regime
    coverage_after: float
    confidence: float
    confidence_breakdown: ConfidenceBreakdown | None = None
    rationale: tuple[str, ...] = ()
    # ...
```

`RecommendationResult.confidence_breakdown` is `None` by default for
backwards compatibility with M1.9 test fixtures that construct
`RecommendationResult` directly. The engine itself **always** populates
it — see [§10](#10-integration-with-recommend) for the integration
point. M1.13 will persist it on `DailyDecision`; the UI on the
Today screen reads it directly without re-running the composer.

---

## 10. Integration with `recommend()`

### 10.1 The wire

[`engine/recommendation/recommend.py`](../../packages/engine/engine/recommendation/recommend.py):

```python
def recommend(
    *,
    market_state: MarketStateResult,
    flow_score: FlowScore,
    positions: PositionState,
    profile: UserStrategyProfile,
    rules: Sequence[RuleSpec],
    weights: Weights | None = None,
    illiquidity_penalty: float = 0.0,
) -> RecommendationResult:
    if not rules:
        raise ValueError("recommend: `rules` is empty. ...")

    effective_weights = weights if weights is not None else DEFAULT_WEIGHTS
    confidence, breakdown = _composite_confidence(
        flow_score=flow_score,
        market_state=market_state,
        profile=profile,
        weights=effective_weights,
        illiquidity_penalty=illiquidity_penalty,
    )
    # ... rule evaluation against `confidence` ...
    return RecommendationResult(
        actions=actions,
        matched_rule=matched,
        regime=market_state.regime,
        coverage_after=coverage,
        confidence=confidence,
        confidence_breakdown=breakdown,
        # ...
    )
```

Two integration notes:

1. **`weights` and `illiquidity_penalty` are both optional kwargs.**
   Existing M1.9 callers that called `recommend(market_state=..., ..., rules=rules)`
   continue to work; M1.10 added optional parameters with sensible
   defaults. This is why the engine version bump is minor (`1.0.0`
   → `1.1.0`) — additive public surface, backwards-compatible.
2. **Confidence is computed _before_ rule evaluation.** The rule
   pipeline uses the `confidence` value in its `confidence_lte:`
   clause (`hold_no_op` fires when `confidence ≤ 0.30`). This is
   important: the composer runs once per `recommend()` call, before
   any rule fires; rules read the final confidence, not a partial
   intermediate.

### 10.2 The order matters

Why compute confidence **before** rules? Because:

- Confidence depends on `market_state`, `flow_score`, `profile`, and
  `illiquidity_penalty` — none of which depend on the matched rule.
  So the math is well-defined before rules run.
- One rule (`hold_no_op`) reads `confidence`. If confidence depended
  on the matched rule, you'd have a circularity.
- The Phase 4 ML node-swap (per ADR-0008) replaces specific component
  scorers without changing this ordering.

V1.5+ rule scoring (per plan §9.5 step 3 drawdown tie-break) may
introduce per-candidate confidence calculations, but that's strictly
additive — the first-pass `confidence` from M1.10 remains the input
to `confidence_lte:`.

### 10.3 What the test suite verifies

`tests/test_confidence.py::test_recommend_populates_confidence_breakdown`
and friends pin the integration:

```python
def test_recommend_populates_confidence_breakdown(packaged_rules):
    rec = recommend(
        market_state=_market_state(regime_score=0.60),
        flow_score=_flow_score(confidence=0.60, score=30),
        positions=PositionState(),
        profile=_profile(),
        rules=packaged_rules,
    )
    assert rec.confidence_breakdown is not None
    assert rec.confidence_breakdown.weights_version == "v2.0"
    b = rec.confidence_breakdown
    assert rec.confidence == pytest.approx(
        b.positive_score * b.penalty_multiplier, abs=1e-12
    )
```

Plus determinism (`a.confidence_breakdown == b.confidence_breakdown`
for identical inputs), passthrough (`illiquidity_penalty=1.0` drops
confidence by exactly 25%), and weights overrides (a custom `Weights`
instance changes the output).

---

## 11. End-to-end worked example

Let's run a single `recommend()` call from top to bottom.

### 11.1 The inputs

A high-IV environment with a decisive bullish FlowScore and an event
two weeks out:

```python
market_state = MarketStateResult(
    regime=Regime.HIGH_IV_PIN,
    regime_score=0.75,
    trend_strength=0.30,
    breakout_signal=0.10,
    oi_concentration_at_max_pain=0.60,
    days_to_next_event=14,
    iv_rank=0.65,
    # ... other fields ...
)

flow_score = FlowScore(
    score=+40,
    bullish_score=55,
    bearish_score=15,
    bias=Bias.BULLISH,
    recommended_action=RecommendedAction.SELL_CALL_PARTIAL,
    confidence=0.70,
    # ... other fields ...
)

profile = UserStrategyProfile(
    drawdown_tolerance=0.15,
    # ... other fields ...
)
```

### 11.2 Component-by-component

```python
flow_alignment       = 0.5 * 0.70 + 0.5 * (40 / 100)
                     = 0.35 + 0.20 = 0.55

structure_alignment  = 0.50 * 0.30 + 0.30 * 0.10 + 0.20 * 0.60
                     = 0.15 + 0.03 + 0.12 = 0.30

regime_match         = clip01(0.75) = 0.75

signal_alignment     = 0.5 * 0.75 + 0.5 * 0.70
                     = 0.375 + 0.35 = 0.725

event_risk_penalty   raw = (30 - 14) / 30 ≈ 0.533
                     drawdown_tolerance = 0.15 ≥ 0.10 → no boost
                     final = 0.533

illiquidity_penalty  = 0.0   # V1 stub
```

### 11.3 The composer

$$
\begin{aligned}
\text{positive} &= 0.30 \cdot 0.55 + 0.25 \cdot 0.30 + 0.25 \cdot 0.75 + 0.20 \cdot 0.725 \\
              &= 0.165 + 0.075 + 0.1875 + 0.145 \\
              &= 0.5725 \\
\text{penalty\_mult} &= (1 - 0.30 \cdot 0.533) \cdot (1 - 0.25 \cdot 0.0) \\
              &= 0.84 \cdot 1.0 \\
              &= 0.84 \\
\text{confidence} &= \text{clip}_{[0,1]}(0.5725 \cdot 0.84) \\
              &\approx 0.481
\end{aligned}
$$

### 11.4 The rule pipeline

`HIGH_IV_PIN` is in the `high_iv_sell_call` rule's regime list and
`iv_rank = 0.65 ≥ 0.50`, so `high_iv_sell_call` matches and emits
`SELL_COVERED_CALL_PARTIAL`. The `confidence_lte: 0.30` clause on
`hold_no_op` does **not** match (0.481 > 0.30), so the rule pipeline
stops at `high_iv_sell_call`.

### 11.5 The output

```python
RecommendationResult(
    actions=(Action(emit=SELL_COVERED_CALL_PARTIAL, parameters={...}),),
    matched_rule=MatchedRule(rule_id="high_iv_sell_call", ...),
    regime=Regime.HIGH_IV_PIN,
    coverage_after=...,
    confidence=0.481,
    confidence_breakdown=ConfidenceBreakdown(
        flow_alignment=0.55,
        structure_alignment=0.30,
        regime_match=0.75,
        signal_alignment=0.725,
        event_risk_penalty=0.533,
        illiquidity_penalty=0.0,
        positive_score=0.5725,
        penalty_multiplier=0.84,
        weights_version="v2.0",
    ),
    # ... rationale, risks, invalidation, warnings, candidates_considered ...
)
```

The UI renders "48% confidence — IV rank 65% supports a covered call;
event in 14 days subtracts ~9pp from a stronger positive signal."

### 11.6 What changes when M1.11 ships?

Suppose the M1.11 execution module assesses the chosen strikes and
returns `illiquidity_score = 0.4` (mild but real liquidity concern).
The integration becomes:

```python
rec = recommend(
    market_state=ms,
    flow_score=fs,
    positions=positions,
    profile=profile,
    rules=rules,
    illiquidity_penalty=0.4,  # ← new
)
```

The composer re-runs with the same positives, the same event penalty,
and now `illiquidity_penalty = 0.4`:

$$
\text{penalty\_mult} = 0.84 \cdot (1 - 0.25 \cdot 0.4) = 0.84 \cdot 0.90 = 0.756
$$

$$
\text{confidence} = 0.5725 \cdot 0.756 \approx 0.433
$$

So 48% confidence drops to 43% once execution feasibility is in the
loop. The rule still matches (still > 0.30), the action is unchanged,
but the user sees a more cautious confidence number on the Today
screen.

---

## 12. Hands-on exercises

These exercises assume you have the repo cloned and the engine package
installed (`cd packages/engine && uv sync --dev`).

### Exercise 1 — `compose()` algebra

Verify by hand (then by running `compose()`) that for any
`positive_weights` that sum to 1.0 and any inputs in $[0, 1]$:

- $\text{positive} \in [0, 1]$
- $\text{penalty\_mult} \in [0, 1]$
- $\text{confidence} \in [0, 1]$

Then prove by hand that increasing `flow_alignment` by $\delta$ (with
everything else fixed and no penalties) increases `confidence` by
exactly $0.30 \cdot \delta$ — until clipping bites. At what value of
the other positives does the clip start to matter?

### Exercise 2 — Calibration sensitivity

Modify `packages/engine/config/weights.yaml` (do not commit) to set
`positive_weights.flow = 0.60` and rebalance the others to keep
$\sum w = 1.0$ (try `struct = 0.20, regime = 0.15, signal = 0.05`).
What does this do to the §22.13 worked-example confidence? Why might
this be a reasonable calibration for users who explicitly prioritize
flow over structural signals? Why might it be a bad calibration for
the default user?

Run `pytest tests/test_confidence.py::test_default_weights_matches_yaml_drift_check`
and observe the drift-gate failure. Restore the file. What does this
tell you about the design choice to mirror the YAML in code?

### Exercise 3 — `event_risk_penalty` table

For a user with `drawdown_tolerance = 0.05` (low) and another with
`drawdown_tolerance = 0.25` (high), compute `event_risk_penalty` for
`days_to_next_event ∈ {0, 5, 10, 20, 30, None}`. Plot both curves.
Where do they coincide? Where do they diverge? Discuss whether the
1.5× boost factor should also depend on `event_kind` (earnings vs.
FOMC vs. ex-dividend).

### Exercise 4 — Property test in Hypothesis

Write a Hypothesis test that, for any valid `(ConfidenceInputs, Weights)`
pair, $\text{compose()}$ output satisfies:

$$
\text{confidence} = \text{clip}_{[0,1]}(\text{positive\_score} \cdot \text{penalty\_multiplier})
$$

within floating-point epsilon. (Hint: the existing
`test_compose_output_is_bounded` is a starting point.) Are there
input combinations where the outer `clip01` is non-trivial — i.e.
the product is genuinely outside $[0, 1]$ without it? If not, what
would it take to make it non-trivial (changing weights? changing the
formula?)?

### Exercise 5 — Replay

Pick any `recommend()` call you can produce. Persist the
`ConfidenceBreakdown.weights_version` along with the `confidence`.
Now imagine `weights.yaml` is edited and `version` bumps to `"v2.1"`
(say `liquidity` cap is raised from 0.25 to 0.40). Construct the
v2.0 weights instance manually with `Weights(version="v2.0", ...)`
and re-run `compose()` with the original `ConfidenceInputs`. Does
the original confidence reproduce? Now do the same with the v2.1
weights. What does this tell you about the role of `weights_version`
on `DailyDecision`?

---

## 13. Further reading

- **Plan v1.2** (Hyperagent thread `cmokf2twq0gsv06adlij0glqs`):
  - §9.7 — Confidence Composer (superseded contract; the §22.13
    redesign is the canonical V1 form).
  - §22.13 — multiplicative-penalty redesign.
  - §22.2 — `FlowScore` V1 LOCKED contract (the upstream input).
  - §22.8 — eight V1 `rules.yaml` rules (the `confidence_lte:` user
    that consumes the composer's output).
  - §17 M1.10 — milestone scope and acceptance.
- **ADRs**:
  - [ADR-0003](../decisions/0003-confidence-multiplicative.md) — locks
    the multiplicative discipline.
  - [ADR-0005](../decisions/0005-engine-pure-function-discipline.md) —
    pure-function discipline (the boundary for YAML loaders).
  - [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) —
    enhancement adoption + Phase 1.5 hot-swap plan for `weights.yaml`.
- **Sibling tutorials**:
  - [`market-state-engine.md`](./market-state-engine.md) — produces
    `regime_score` + `trend_strength` + `breakout_signal` +
    `oi_concentration_at_max_pain` + `days_to_next_event`.
  - [`flow-score-engine.md`](./flow-score-engine.md) — produces
    `FlowScore.confidence` + `score`.
  - [`scoring-primitives.md`](./scoring-primitives.md) — explains the
    `*ScoreResult` pattern used by the M1.4a primitives that feed
    `MarketStateResult`.
- **Code**:
  - [`packages/engine/engine/confidence/`](../../packages/engine/engine/confidence) —
    the module.
  - [`packages/engine/config/weights.yaml`](../../packages/engine/config/weights.yaml) —
    the on-disk weights.
  - [`packages/engine/tests/test_confidence.py`](../../packages/engine/tests/test_confidence.py) —
    64 tests at 100% line coverage; pin §22.13 worked example, drift
    gate, Hypothesis property tests, `recommend()` integration.

---

## 14. Glossary of symbols

| Symbol | Meaning |
|---|---|
| $c_\text{flow}, c_\text{struct}, c_\text{regime}, c_\text{signal}$ | The four positive ConfidenceInputs fields |
| $p_\text{event}, p_\text{liq}$ | The two penalty ConfidenceInputs fields |
| $w_\text{flow}, w_\text{struct}, w_\text{regime}, w_\text{signal}$ | Positive component weights (sum to 1.0) |
| $\kappa_\text{event}, \kappa_\text{liq}$ | Penalty caps (each in $[0, 1]$) |
| $\text{positive}$ | The pre-penalty weighted sum (≡ `positive_score`) |
| $\text{penalty\_mult}$ | The product of penalty multipliers (≡ `penalty_multiplier`) |
| `clip01(x)` | Saturates `x` to $[0, 1]$ |
| `weights_version` | String pin (`"v2.0"`) persisted with every decision for replay |
| `engine_version` | The `packages/engine/engine/version.py` semver pin |
| `inputs_hash` | SHA-256 over the canonical JSON of all engine inputs (per plan §7) |
| `DailyDecision` | The persisted M1.13 decision row carrying all three pins |
