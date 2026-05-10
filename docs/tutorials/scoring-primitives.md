# Tutorial: Scoring Primitives (`iv_score`, `structure_score`, `event_score`)

> **Audience.** First-year master's students in financial engineering; quant-developer onboarding; anyone consuming the scoring primitives downstream.
> **Prerequisites.** Read the [Market State Engine tutorial](./market-state-engine.md) first (or at least skim §2 on the input vocabulary — IV, HV, IV rank, max pain, expected move, OI walls). Comfort with Black–Scholes basics, `clip` operations, weighted means.
> **Reading time.** ~50 min careful read with the exercises; ~20 min skim.
> **Engine version covered.** `0.5.0` (post-M1.4a) onward; the primitives live in [`packages/engine/engine/scoring/`](../../packages/engine/engine/scoring) and have not changed since.
>
> **Disclaimer.** This tutorial is **educational material**. The scoring primitives are decision-support components, not investment advice. See [`docs/disclaimers.md`](../disclaimers.md).

---

## Table of contents

1. [Why scoring primitives?](#1-why-scoring-primitives)
2. [The `*ScoreResult` pattern](#2-the-scoreresult-pattern)
3. [`iv_score()` — IV-favorability](#3-iv_score--iv-favorability)
4. [`structure_score()` — options-structure signal](#4-structure_score--options-structure-signal)
5. [`event_score()` — event-uncertainty signal](#5-event_score--event-uncertainty-signal)
6. [Design philosophy & test discipline](#6-design-philosophy--test-discipline)
7. [End-to-end worked example](#7-end-to-end-worked-example)
8. [Hands-on exercises](#8-hands-on-exercises)
9. [Further reading](#9-further-reading)
10. [Glossary of symbols](#10-glossary-of-symbols)

---

## 1. Why scoring primitives?

### 1.1 The role in the architecture

The decision pipeline (per plan v1.2 §9 and the [architecture doc](../architecture.md))
flows roughly like this for any given trading day:

```
ChainSnapshot ──┐
                │
OHLC + event ──►├─► Primitives ─► Scoring fns ─► Engines ─► Decision
calendar       │   (M1.1–M1.3)   (M1.4a, M1.5a)  (M1.4, M1.5,
User profile ──┘                                  M1.7, M1.8, ...)
```

**Primitives** (`iv_rank`, `compute_hv`, `compute_max_pain`, `expected_move_pct`,
`pcr_volume`, `pcr_oi`, `compute_trend_strength`, `compute_breakout_signal`) turn
raw inputs into scalars and small dataclasses.

**Scoring functions** sit between the primitives and the engines. They answer
**single, focused questions** about the market:

- "How attractive is selling premium right now?" → `iv_score()`
- "How constrained is the underlying by options structure?" → `structure_score()`
- "How much event-driven uncertainty sits in the chain?" → `event_score()`

Each scoring function returns a frozen `*ScoreResult` dataclass that carries a
headline `score ∈ [0, 1]` plus a per-component `breakdown: dict[str, float]`.
The headline lets downstream engines do fast comparisons; the breakdown lets
them — and the UI — explain *why* the score is what it is.

### 1.2 The §9.11 wiring matrix

The plan v1.2 §9.11 wiring matrix spells out which engine consumes which
scoring function. M1.4a ships the three that surround `iv` / `structure` /
`event`; M1.5a adds `gamma`; the existing Flow Score Engine is the
orchestrator that composes them:

| Consumer | iv | structure | gamma | event | flow |
|---|:---:|:---:|:---:|:---:|:---:|
| Market State Engine (`classify`) | ✓ | ✓ |   | ✓ |   |
| Flow Score Engine (orchestrator) | ✓ |   | ✓ |   | (self) |
| Recommendation Engine |   | ✓ |   |   | ✓ |
| Confidence Composer | ✓ | ✓ |   | ✓ | ✓ |
| Collar Builder | ✓ |   |   | ✓ |   |
| Strike Selector | ✓ |   |   |   |   |

The matrix tells you immediately why these three were the M1.4a deliverable:
they are the inputs the Market State Engine (M1.4) and Collar Builder (M1.11a)
need before they can compute anything useful, and they are *consumed* by the
Confidence Composer for explainability.

### 1.3 Design objectives

The scoring primitives are deliberately:

1. **Pure functions** — no I/O, no clock, no env. Per
   [ADR-0005](../decisions/0005-engine-pure-function-discipline.md). Same
   inputs → byte-identical outputs.
2. **Composable** — each takes ≤ 5 inputs, kwargs-only, returns a result
   dataclass. You can hand-trace them in a notebook in seconds.
3. **At 100% line coverage** — per plan v1.2 §9.11 acceptance bar. CI
   enforces via `pytest --cov=engine.scoring --cov-fail-under=100`. If the
   bar starts to slip, future maintainers feel it immediately.
4. **Calibration-friendly** — every threshold/weight is a top-of-module
   constant with a comment naming the plan reference. Phase 4 ML will
   replace these with learned parameters via [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md).

---

## 2. The `*ScoreResult` pattern

Every scoring primitive returns a frozen dataclass with two fields:

```python
@dataclass(frozen=True)
class IvScoreResult:
    score: float                   # [0, 1] headline
    breakdown: dict[str, float]    # per-component
```

The pattern is identical for `StructureScoreResult` and `EventScoreResult`.

### 2.1 Why `breakdown`?

The Confidence Composer (M1.10) decomposes the final confidence into
contributions from each scoring fn, and the UI renders each contribution
as a bar in a stacked chart. Without `breakdown`, the Composer would need
to recompute components from raw inputs — duplicating logic and inviting
drift.

The breakdown is also what makes a scoring function **testable in
isolation**. A test can assert not just `score == 0.85` but
`breakdown["rank"] == 0.8 and breakdown["percentile"] == 0.7 and
breakdown["iv_hv_premium"] == 1.0`, which catches regressions where the
*total* is right but a component is wrong.

### 2.2 Why `frozen=True`?

The Phase 1 contract is that `inputs_hash` + `engine_version` +
`weights_version` uniquely determine the persisted `DailyDecision`. If a
`*ScoreResult` were mutable, downstream code could silently mutate `score`
between when it's produced and when it's hashed, breaking replay. Frozen
dataclasses give compile-time immutability without ceremony.

(The `breakdown` dict itself is technically mutable — Python's frozen
dataclass freezes the assignment to the field, not the deep object graph.
Consumers must treat the dict as read-only. The shape `tuple[tuple[str,
float], ...]` was considered and rejected as ergonomically worse.)

### 2.3 Why a flat `dict[str, float]` not nested?

Two reasons:

- The Confidence Composer's UI flat-iterates breakdowns: every key becomes
  a labeled bar segment. Nested structures would force a recursive
  flattener.
- The breakdown is for *human inspection* and downstream diagnostics. If a
  scoring fn ever needs structured output, that's a new public type, not a
  nested breakdown.

---

## 3. `iv_score()` — IV-favorability

### 3.1 What it measures

`iv_score()` answers one question: **"How favorable is the current implied-vol
environment for *selling* premium?"** Higher score = more favorable.

The intuition has three pieces:

1. **Is current IV high relative to the 252-day band?** Rich premium relative
   to recent history matters more than absolute IV — IV=30 on a bond ETF is
   a regime shift; IV=30 on a tech mega-cap is Tuesday.
2. **Is current IV high relative to count-based percentile?** A complement
   to rank that is robust to single outliers. Together they triangulate
   "where in the band are we" without overfitting to spikes.
3. **Is implied vol expensive relative to realized?** The textbook
   premium-seller edge: when implied is much higher than realized, the
   market is paying for vol that historical behavior did not justify.

### 3.2 Inputs

```python
def iv_score(
    *,
    iv_rank: float,      # [0, 1], from engine.market_state.iv_rank
    iv_percentile: float, # [0, 1], from engine.market_state.iv_percentile
    hv_30: float,         # >= 0, annualized 30d HV
    atm_iv_30d: float,    # >= 0, current ATM 30d IV
) -> IvScoreResult: ...
```

All four inputs are non-negative; `iv_rank` and `iv_percentile` are bounded
in $[0, 1]$. The engine raises `ValueError` on out-of-range inputs — these
flow from upstream primitives that already guarantee the bounds, so an
out-of-range value is a programmer error worth surfacing loudly.

### 3.3 Formula

```python
_W_RANK = 0.40
_W_PERCENTILE = 0.30
_W_PREMIUM = 0.30

_PREMIUM_RATIO_FLOOR = 0.7
_PREMIUM_RATIO_CEIL = 1.5
```

$$\text{rank\_component} = \mathrm{IV\,rank}$$
$$\text{percentile\_component} = \mathrm{IV\,percentile}$$

For the premium component, define $\rho = \sigma_{IV}/\sigma_{HV}$:

$$\text{premium\_component} = \begin{cases} 0.5 & \text{if } \sigma_{HV} \le 0 \\ \mathrm{clip}_{[0,1]}\!\left( \dfrac{\rho - 0.7}{1.5 - 0.7} \right) & \text{otherwise} \end{cases}$$

And finally,

$$s_{IV} = \mathrm{clip}_{[0,1]}\!\big( 0.40 \cdot \text{rank} + 0.30 \cdot \text{percentile} + 0.30 \cdot \text{premium} \big).$$

The weights sum to 1.0 so the composite is always in $[0, 1]$ before the
final clip; the clip is defensive against floating-point overshoot.

### 3.4 Calibration intuition

| $\rho = \sigma_{IV}/\sigma_{HV}$ | `premium_component` | Interpretation |
|:---:|:---:|---|
| ≤ 0.7 | 0.0 | IV is cheap relative to realized — unfavorable for selling |
| 1.0 | 0.375 | Parity — neutral, leaning slightly cheap |
| 1.1 | 0.5 | Mild premium |
| 1.5 | 1.0 | Strong premium — fully favorable |
| ≥ 1.5 | 1.0 (saturated) | Diminishing extra information |

Why is parity at 0.375 and not 0.5? Because the realized-vol estimator is
backward-looking and IV is forward-looking. Sustained $\sigma_{IV} =
\sigma_{HV}$ means the market expects realized to continue, with no extra
premium for risk — slightly *unfavorable* for selling premium.

### 3.5 Edge case: $\sigma_{HV} = 0$

When realized vol is zero — typically because the price series is constant
for the full lookback window — there is no well-defined ratio. The engine
falls back to `premium_component = 0.5` (the "no information" prior). This
matches the convention documented at the call site:

> Plan §9.1 hv.py docstring: *"treat 0.0 HV as 'no realized motion' and
> ignore the IV − HV signal that day."*

If `hv_30 = 0` and the only signal you have is `iv_rank = 0.85, iv_percentile = 0.80`, the score is

$$s_{IV} = 0.40 \cdot 0.85 + 0.30 \cdot 0.80 + 0.30 \cdot 0.5 = 0.34 + 0.24 + 0.15 = \mathbf{0.73}.$$

The premium fallback effectively says "the IV-vs-HV signal is mute, but the
rank/percentile signals are still telling us premium is rich."

### 3.6 Worked example

```python
result = iv_score(
    iv_rank=1.0,
    iv_percentile=1.0,
    hv_30=0.10,        # 10% annualized
    atm_iv_30d=0.30,   # 30% annualized
)
```

By hand:

- `rank_component = 1.0`
- `percentile_component = 1.0`
- $\rho = 0.30 / 0.10 = 3.0$
- `premium_component = clip01((3.0 - 0.7) / 0.8) = clip01(2.875) = 1.0`
- `score = clip01(0.40 + 0.30 + 0.30) = 1.0`

`result.score == 1.0`, `result.breakdown == {"rank": 1.0, "percentile":
1.0, "iv_hv_premium": 1.0}`. This is the
`test_iv_score_all_max_inputs` fixture in
[`packages/engine/tests/test_scoring_iv.py`](../../packages/engine/tests/test_scoring_iv.py).

### 3.7 Code reference

[`packages/engine/engine/scoring/iv.py`](../../packages/engine/engine/scoring/iv.py).

---

## 4. `structure_score()` — options-structure signal

### 4.1 What it measures

`structure_score()` answers: **"How much do option positioning and structural
levels constrain spot's near-term path?"** Higher = more constrained.

A constrained environment looks like this: spot is close to a meaningful OI
wall, the max-pain strike is roughly where spot sits, monthly opex is around
the corner, and the expected move is small. All four signals reinforce
"spot won't go far before something pushes it back."

### 4.2 Inputs

```python
def structure_score(
    *,
    oi_walls: OiWalls,                  # support / resistance levels
    max_pain: float,                    # > 0
    spot: float,                        # > 0
    expected_move_pct: float,           # >= 0, fraction of spot
    dte_to_nearest_opex: int,           # >= 0
) -> StructureScoreResult: ...
```

The `OiWalls` type is defined here (not in `engine.types`) because it's an
**intermediate computation result**, not an external input contract. Its
producer is the Flow Score Engine (M1.5); its consumer is `structure_score`.

```python
@dataclass(frozen=True)
class OiWalls:
    support: float | None       # highest large-OI strike strictly below spot
    resistance: float | None    # lowest large-OI strike strictly above spot
    support_oi: int = 0         # OI at support (0 if support is None)
    resistance_oi: int = 0      # OI at resistance
    total_oi: int = 0           # total OI in the window used for computation
```

Either side may be `None` — e.g. very illiquid expiries, or chains where
the entire large-OI mass sits above or below spot. `structure_score`
handles missing walls correctly (see §4.4).

### 4.3 Formula

```python
_W_WALL = 0.30
_W_PIN = 0.25
_W_OPEX = 0.20
_W_EM = 0.25

_OPEX_NEAR_DAYS = 2
_OPEX_FAR_DAYS = 14
_EM_TIGHT_PCT = 0.02
_EM_WIDE_PCT = 0.10
```

#### Wall proximity (weight 0.30)

Let $W \subseteq \{\text{support}, \text{resistance}\}$ be the present
walls, and for each $w \in W$ define $d_w = |S - K_w| / S$ as the relative
distance. Then

$$\text{wall\_proximity} = \begin{cases} 0 & \text{if } W = \varnothing \\ 1 & \text{if } \text{EM}_\% = 0 \text{ and } \min_w d_w = 0 \\ 0 & \text{if } \text{EM}_\% = 0 \text{ and } \min_w d_w > 0 \\ \mathrm{clip}_{[0,1]}\!\left( 1 - \dfrac{\min_w d_w}{2 \cdot \text{EM}_\%} \right) & \text{otherwise} \end{cases}$$

The normalizer `2·EM` is deliberate: a wall *one* expected-move away is
weakly relevant; a wall *two* expected-moves away is essentially noise. The
choice trades off coverage (capturing walls reasonably far away) against
selectivity (not awarding too much credit to distant walls).

#### Pin alignment (weight 0.25)

Define $d_{\text{pin}} = |S - K^\*| / S$. Then

$$\text{pin\_alignment} = \begin{cases} 1 & \text{if } \text{EM}_\% = 0 \text{ and } d_{\text{pin}} = 0 \\ 0 & \text{if } \text{EM}_\% = 0 \text{ and } d_{\text{pin}} > 0 \\ \mathrm{clip}_{[0,1]}\!\left( 1 - \dfrac{d_{\text{pin}}}{\text{EM}_\%} \right) & \text{otherwise} \end{cases}$$

The normalizer here is `1·EM` (not `2·EM`): max-pain pin is a *tight*
signal — once spot is more than one expected-move from max-pain, pin
pressure has effectively dissipated.

#### Opex proximity (weight 0.20)

Maps the band $[\text{NEAR} = 2, \text{FAR} = 14]$ trading days to $[1, 0]$:

$$\text{opex\_proximity}(d) = \begin{cases} 1 & d \le 2 \\ (14 - d)/(14 - 2) & 2 < d < 14 \\ 0 & d \ge 14 \end{cases}$$

The 14-day FAR cutoff is plan-prescribed: pin pressure is weak beyond ~3
calendar weeks. The 2-day NEAR threshold gives a small plateau at the
top where opex is so close that finer resolution is meaningless.

#### EM containment (weight 0.25)

Maps the band $[\text{TIGHT} = 2\%, \text{WIDE} = 10\%]$ to $[1, 0]$:

$$\text{em\_containment}(\text{EM}_\%) = \begin{cases} 1 & \text{EM}_\% \le 0.02 \\ (0.10 - \text{EM}_\%)/(0.10 - 0.02) & 0.02 < \text{EM}_\% < 0.10 \\ 0 & \text{EM}_\% \ge 0.10 \end{cases}$$

A 2% expected move is a tight, structurally dominated environment; a 10%
expected move means realized risk swamps structural levels.

#### Composite

$$s_{\text{struct}} = \mathrm{clip}_{[0,1]}\!\big( 0.30 \cdot \text{wall} + 0.25 \cdot \text{pin} + 0.20 \cdot \text{opex} + 0.25 \cdot \text{em} \big).$$

Weights sum to 1.0. Each component is independently in $[0, 1]$, so the
composite is bounded before the final clip.

### 4.4 Edge cases

**One-sided walls.** When only `support` (or only `resistance`) is set,
`wall_proximity` uses the one present. When both are `None`, it returns 0.

**Zero EM.** A zero expected-move (e.g. `dte = 0`) makes the normalizers
$\frac{0}{2\cdot 0}$ undefined. The function branches: if distance is also
zero, return 1; if distance is positive, return 0. No intermediate values
exist — at zero EM the geometry is degenerate.

**`dte_to_nearest_opex` out of band.** Below `NEAR=2` clamps to 1.0; above
`FAR=14` clamps to 0.0. Inside the band, linear interpolation.

### 4.5 Worked example

```python
result = structure_score(
    oi_walls=OiWalls(support=96.0, resistance=104.0),
    max_pain=100.0,
    spot=100.0,
    expected_move_pct=0.04,        # 4%
    dte_to_nearest_opex=1,
)
```

By hand:

- Distances: support at 4% below, resistance at 4% above → both $d = 0.04$.
- Nearer dist = 0.04. wall_proximity = $1 - 0.04 / (2 \cdot 0.04) = 1 - 0.5 = 0.5$.
- pin_alignment: $d_{\text{pin}} = |100 - 100|/100 = 0$. → $1 - 0/0.04 = 1.0$.
- opex_proximity: $d = 1 \le 2$ → 1.0.
- em_containment: $0.04$ between TIGHT=0.02 and WIDE=0.10 → $(0.10 - 0.04)/(0.10 - 0.02) = 0.06/0.08 = 0.75$.
- $s_{\text{struct}} = 0.30 \cdot 0.5 + 0.25 \cdot 1.0 + 0.20 \cdot 1.0 + 0.25 \cdot 0.75 = 0.15 + 0.25 + 0.20 + 0.1875 = \mathbf{0.7875}$.

This is the `test_structure_score_pinned_to_max_pain_at_opex` fixture in
[`packages/engine/tests/test_scoring_structure.py`](../../packages/engine/tests/test_scoring_structure.py).

### 4.6 Code reference

[`packages/engine/engine/scoring/structure.py`](../../packages/engine/engine/scoring/structure.py).

---

## 5. `event_score()` — event-uncertainty signal

### 5.1 What it measures

`event_score()` answers: **"How much event-driven uncertainty is sitting in
the chain?"** Higher = larger event-driven risk premium.

The intuition is multiplicative:

- If no event is scheduled, the score is **identically 0**, regardless of
  the other inputs. There is no event risk when no event is on the
  calendar.
- If an event is scheduled, the score blends *kind* (earnings move
  differently than CPI) and *magnitude* (how big are this underlying's
  historical event-day moves?). The blend is then multiplied by a
  *proximity* gate — far-future events contribute little.

### 5.2 Inputs

```python
def event_score(
    *,
    days_to_event: int | None,
    event_kind: str | None,
    event_history: EventStats,
) -> EventScoreResult: ...
```

`EventStats` carries the underlying's historical event-day statistics:

```python
@dataclass(frozen=True)
class EventStats:
    avg_abs_return_pct: float       # e.g. 0.05 = 5% avg abs return on event day
    iv_runup_pct: float = 0.0       # avg IV runup in the 5 sessions pre-event
    sample_count: int = 0           # number of prior events in history
```

Only `avg_abs_return_pct` is consumed by `event_score()` directly. The other
two are surfaced for downstream consumers (Confidence Composer breakdowns,
future M4.5 ML feature engineering). The fields default to zero so callers
without history can pass `EventStats(avg_abs_return_pct=0.0)` — the
function short-circuits to a zero score in that case anyway.

### 5.3 Formula

```python
_PROXIMITY_FAR_DAYS = 30
_MAGNITUDE_THRESHOLD = 0.05      # 5% avg → magnitude = 1.0
_W_KIND = 0.5
_W_MAGNITUDE = 0.5
_DEFAULT_KIND_WEIGHT = 0.5
```

#### Proximity

$$\text{proximity}(d) = \begin{cases} 0 & d = \text{None} \\ \mathrm{clip}_{[0,1]}\!\left( 1 - \dfrac{\max(d, 0)}{30} \right) & \text{otherwise} \end{cases}$$

Negative days (event already past) clamp to 0 defensively. The
event-calendar service is responsible for advancing past events promptly;
this clamp protects the engine if the service is slow.

#### Kind weight

A lookup from `EVENT_KIND_WEIGHTS`, with `_DEFAULT_KIND_WEIGHT = 0.5` for
unknown / `None` kinds:

| `event_kind` | weight | rationale |
|---|:---:|---|
| `earnings` | 1.0 | Largest single-name catalyst |
| `fomc` | 0.7 | Significant macro driver |
| `cpi` | 0.6 | Inflation print; less single-name impact |
| `guidance` | 0.5 | Off-cycle guidance / pre-announce |
| `ex_dividend` | 0.3 | Mechanical; small impact |
| `other` | 0.5 | Default fallback |

Adding a kind is non-breaking (extend the table, document it, add a
fixture). Renaming or removing IS breaking because downstream code may be
matching on the literal string.

#### Magnitude

$$\text{magnitude} = \mathrm{clip}_{[0,1]}\!\left( \dfrac{\overline{|r|}}{0.05} \right),$$

where $\overline{|r|}$ is the historical average absolute event-day return
(`avg_abs_return_pct`). 5%+ saturates magnitude at 1.0.

#### Composite

$$s_{\text{evt}} = \mathrm{clip}_{[0,1]}\!\big( \text{proximity} \cdot (0.5 \cdot \text{kind} + 0.5 \cdot \text{magnitude}) \big).$$

The **multiplicative proximity gate** is the key design decision. A
60-day-out earnings does not "price" the same as a 1-day-out earnings,
even if their historical magnitudes are identical. Multiplication ensures
distant events contribute nothing, regardless of how large the inner blend
gets.

### 5.4 Edge cases

| Input | Output |
|---|---|
| `days_to_event = None` | `proximity = 0` → `score = 0` |
| `days_to_event ≥ 30` | `proximity = 0` → `score = 0` |
| `days_to_event = 0` | `proximity = 1.0` |
| `days_to_event = -3` | clamped to 0 → `proximity = 1.0` |
| `event_kind = None` | `kind_weight = 0.5` (default) |
| `event_kind = "bigfoot"` | `kind_weight = 0.5` (unknown → default) |
| `avg_abs_return_pct = 0` | `magnitude = 0` |
| `avg_abs_return_pct ≥ 0.05` | `magnitude = 1.0` |

The function raises `ValueError` if any `EventStats` field is negative
(invalid by definition — absolute return, runup, count are all
non-negative).

### 5.5 Worked example

```python
result = event_score(
    days_to_event=0,
    event_kind="earnings",
    event_history=EventStats(avg_abs_return_pct=0.05),
)
```

By hand:

- `proximity = clip01(1 - 0/30) = 1.0`
- `kind_weight = EVENT_KIND_WEIGHTS["earnings"] = 1.0`
- `magnitude = clip01(0.05 / 0.05) = 1.0`
- `inner = 0.5 · 1.0 + 0.5 · 1.0 = 1.0`
- `score = clip01(1.0 · 1.0) = 1.0`

This is the `test_event_score_imminent_earnings_max` fixture in
[`packages/engine/tests/test_scoring_event.py`](../../packages/engine/tests/test_scoring_event.py).

Now try with an FOMC, same magnitude:

- `kind_weight = 0.7`
- `inner = 0.5 · 0.7 + 0.5 · 1.0 = 0.85`
- `score = 1.0 · 0.85 = 0.85`

And 15 days out instead of 0:

- `proximity = clip01(1 - 15/30) = 0.5`
- `inner` unchanged at 1.0 (earnings, max mag)
- `score = 0.5 · 1.0 = 0.5`

### 5.6 Code reference

[`packages/engine/engine/scoring/event.py`](../../packages/engine/engine/scoring/event.py).

---

## 6. Design philosophy & test discipline

### 6.1 Why composite scores with breakdowns?

Three alternatives were considered and rejected:

| Alternative | Why rejected |
|---|---|
| Single Boolean ("is this regime-favorable?") | Loses gradient info; tie-breaks become arbitrary |
| Logistic regression on a flat feature vector | Hides the financial meaning; ML upgrade harder |
| Hand-written decision tree | Cliff edges; hard to calibrate; harder to test |

The composite-score-plus-breakdown pattern:

- **Smooth gradients** — small input changes produce small score changes.
- **Auditability** — the breakdown is the audit trail.
- **ML-readiness** — Phase 4 swaps the deterministic predicate for an ML
  model; the interface (input vector → `*ScoreResult`) is unchanged.
- **UI-readiness** — the Confidence Composer renders each breakdown
  component as a stacked-bar segment.

### 6.2 Weight conventions

In every primitive, **the per-component weights sum to 1.0**. This gives
two guarantees:

1. The composite is bounded by $[0, 1]$ before the final `clip01` (the
   clip is defensive against floating-point overshoot).
2. The weights are interpretable as relative importance — `_W_RANK = 0.40`
   in `iv_score` means rank explains 40% of the composite when all
   components are equal.

### 6.3 Constants at the top of the module

Every threshold and weight lives at the top of its module with a comment
naming the plan reference. The pattern:

```python
# Weights — must sum to 1.0 so the composite stays bounded by [0, 1].
_W_WALL = 0.30
_W_PIN = 0.25
_W_OPEX = 0.20
_W_EM = 0.25

# Opex-proximity normalization. Pin force is generally weak more than
# 14 trading days from a monthly opex; ≤ 2 trading days maps to 1.0.
_OPEX_NEAR_DAYS = 2
_OPEX_FAR_DAYS = 14
```

Three benefits:

- Calibration is a one-line change. Touching a constant doesn't risk
  breaking anything else.
- The comment names *why* a value is what it is — institutional memory.
- The constants are easy to grep when ADR-0008's Phase 4 ML upgrade
  starts shipping learned weights.

### 6.4 Test discipline: 100% line coverage

Plan v1.2 §9.11 mandates **100% line coverage** on
`packages/engine/engine/scoring/`. The CI step `Coverage check (engine.scoring 100%)`
runs

```bash
uv run pytest --cov=engine.scoring --cov-fail-under=100 --cov-report=term-missing
```

after the regular pytest invocation. If a single new line slips through,
CI fails and the PR can't merge.

Why 100% specifically for `scoring/`?

- The primitives are *foundational* — every Phase 1 engine consumes at
  least one of them. A bug here cascades.
- The functions are *small enough* that 100% is genuinely reachable.
  `iv_score()` is ~30 lines, `structure_score()` is ~50 lines,
  `event_score()` is ~40 lines.
- A 100% gate is **falsifiable** — much harder to negotiate down than a
  "high coverage please" social norm.

The tests themselves are at the same files referenced above. Each scoring
function has:

- ≥ 5 named happy-path fixtures with hand-computed expected scores.
- One test per validation path (every documented bound that raises).
- Hypothesis property tests for `[0, 1]` bounds on every component, plus
  monotonicity in inputs where the function is monotonic (e.g. `iv_score`
  is non-decreasing in `iv_rank`, `iv_percentile`, and `atm_iv_30d`).

180 → 245 engine tests after M1.4a + M1.4 land (the scoring tests
contribute 59 of those).

---

## 7. End-to-end worked example

Let's combine all three scoring primitives on a realistic input. Imagine
the engine processing MSFT three days before an earnings event:

```python
from engine.scoring import (
    iv_score, structure_score, event_score,
    OiWalls, EventStats,
)

# Engine inputs flow in from the data layer hydrating ChainSnapshot + event calendar.
# For this hand-trace, the numbers come from the M1.4 worked-example fixture.

iv = iv_score(
    iv_rank=0.80,
    iv_percentile=0.78,
    hv_30=0.20,
    atm_iv_30d=0.30,         # IV is 50% above HV — premium-rich
)

structure = structure_score(
    oi_walls=OiWalls(support=97.0, resistance=103.0),
    max_pain=99.0,
    spot=100.0,
    expected_move_pct=0.05,  # 5% one-σ move (event-elevated)
    dte_to_nearest_opex=10,
)

event = event_score(
    days_to_event=3,
    event_kind="earnings",
    event_history=EventStats(
        avg_abs_return_pct=0.04,
        iv_runup_pct=0.06,
        sample_count=20,
    ),
)

print(f"iv: {iv.score:.3f}    breakdown: {dict(iv.breakdown)}")
print(f"st: {structure.score:.3f}    breakdown: {dict(structure.breakdown)}")
print(f"ev: {event.score:.3f}    breakdown: {dict(event.breakdown)}")
```

### Hand-trace

**`iv_score`:**

- `rank = 0.80`, `percentile = 0.78`
- $\rho = 0.30 / 0.20 = 1.5$ → `premium = clip01((1.5 - 0.7)/0.8) = 1.0`
- `score = 0.40 · 0.80 + 0.30 · 0.78 + 0.30 · 1.0 = 0.32 + 0.234 + 0.30 = `**`0.854`**

**`structure_score`:**

- support 3% below spot, resistance 3% above → nearer dist 0.03
- `wall_proximity = 1 - 0.03/(2 · 0.05) = 1 - 0.30 = 0.70`
- `pin_alignment = 1 - |100-99|/100 / 0.05 = 1 - 0.01/0.05 = 0.80`
- `opex_proximity`: $d = 10$ → $(14-10)/12 \approx 0.333$
- `em_containment`: $0.05$ → $(0.10-0.05)/(0.10-0.02) = 0.05/0.08 = 0.625$
- `score = 0.30 · 0.70 + 0.25 · 0.80 + 0.20 · 0.333 + 0.25 · 0.625`
  $= 0.210 + 0.200 + 0.0667 + 0.1563 = `**`0.633`** (rounded)

**`event_score`:**

- `proximity = clip01(1 - 3/30) = 0.90`
- `kind_weight = 1.0` (earnings)
- `magnitude = clip01(0.04/0.05) = 0.80`
- `inner = 0.5 · 1.0 + 0.5 · 0.80 = 0.90`
- `score = clip01(0.90 · 0.90) = `**`0.81`**

### Downstream consumption

The Market State Engine `classify()` consumes these three scores indirectly
through its per-regime predicates (the M1.4 classify wires the *raw inputs*,
not the scoring outputs, into its `_score_<regime>` helpers). But the
Confidence Composer (M1.10), when it lands, will read:

- `iv.score = 0.854` → `flow_alignment` and `signal_alignment` weighted contributions
- `structure.score = 0.633` → `structure_alignment` contribution
- `event.score = 0.81` → `event_risk_penalty` contribution

The Confidence Composer's positive_weights (per [ADR-0003](../decisions/0003-confidence-composer-multiplicative.md) and plan §22.13) and penalty_caps blend these into a final $[0, 1]$ confidence. The breakdowns are surfaced in the UI as stacked bars so the user sees not just "confidence = 0.76" but "confidence is 0.76 because flow contributed 0.30·0.85, structure contributed 0.25·0.70, ..., and event risk took 15% off the top."

---

## 8. Hands-on exercises

Solutions are at the end of this section. Try them before peeking.

### Exercise 1 — `iv_score` parity

Without computing in code, predict `iv_score` when:
- `iv_rank = 0.50`, `iv_percentile = 0.50`, `hv_30 = 0.20`, `atm_iv_30d = 0.20`

What does the score equal? Why is it not 0.5?

### Exercise 2 — `iv_score` premium fallback

Compute `iv_score` when `iv_rank = 0.90, iv_percentile = 0.90, hv_30 = 0.0, atm_iv_30d = 0.30`. Why does the engine return a meaningful score even though the IV/HV ratio is undefined?

### Exercise 3 — `structure_score` one-sided wall

Recompute the §4.5 worked example with `OiWalls(support=96.0, resistance=None)` instead of both walls. Which components change? By how much?

### Exercise 4 — `structure_score` weight check

The weights are `0.30 / 0.25 / 0.20 / 0.25`. Verify the maximum possible score is 1.0 by computing the score when every component is at its max.

### Exercise 5 — `event_score` distance halving

If `event_score = 0.85` at `days_to_event = 0` with earnings + 5% magnitude, what is the score at `days_to_event = 15` keeping everything else fixed? Compute by hand.

### Exercise 6 — `event_score` kind override

You're modeling a *forward guidance* day instead of a regular earnings day. The historical magnitude is the same but the kind is `"guidance"`. By what factor does the score change at `days_to_event = 0`?

### Exercise 7 — Cross-primitive intuition

A single name has `iv_score = 0.20, structure_score = 0.85, event_score = 0.05`. Describe in words what kind of market this is and what a long-equity holder might want to do (qualitatively — no specific trade advice).

### Exercise 8 — Designing a 4th scoring fn

The §9.11 wiring matrix lists `gamma_score` (M1.5a) but the M1.4a milestone deferred it. Sketch:
(a) Inputs (1–3 fields).
(b) The composite formula (one paragraph of pseudo-code).
(c) Which engines should consume it (matrix row).
(d) Where the V1 hand-coded weights map onto plan v1.2 §9.11 conventions.

---

### Solutions

**E1.** `rank = 0.50`, `percentile = 0.50`, $\rho = 1.0$ → `premium = (1.0 - 0.7) / 0.8 = 0.375`. `score = 0.40·0.50 + 0.30·0.50 + 0.30·0.375 = 0.20 + 0.15 + 0.1125 = 0.4625`. **Not 0.5** because parity ($\rho = 1.0$) maps the premium component to 0.375, not 0.5 — sustained IV = HV implies the market is paying no risk premium for forward vol.

**E2.** `rank = 0.90, percentile = 0.90`, $hv = 0$ → premium falls back to 0.5. `score = 0.40·0.90 + 0.30·0.90 + 0.30·0.5 = 0.36 + 0.27 + 0.15 = 0.78`. The engine returns a meaningful score by ignoring the broken IV/HV signal and weighting only the two well-defined components (rank and percentile). This is the "constant prices" prior documented in [`hv.py`](../../packages/engine/engine/market_state/hv.py)'s docstring.

**E3.** With `resistance = None`: only the support distance counts. Nearest dist = $|100 - 96|/100 = 0.04$. wall_proximity = $1 - 0.04 / (2 · 0.04) = 0.50$. **Same as before** (0.5 → 0.5) because the support distance happened to equal the original nearer-distance. The other three components are unchanged. **`score = 0.7875`** (identical). The exercise illustrates that one-sided walls are not necessarily *weaker* — what matters is the *nearest* wall, regardless of how many there are.

**E4.** All max: `score = 0.30·1.0 + 0.25·1.0 + 0.20·1.0 + 0.25·1.0 = 1.00`. Confirms the weights sum to 1.0 and the composite is bounded by $[0, 1]$ before the `clip01`. (See `test_structure_score_all_max` in the test file.)

**E5.** At $d = 0$: `proximity = 1.0` → `score = 1.0 · inner = inner`. So `inner = 0.85` and we need `proximity · 0.85` at $d = 15$. `proximity = 1 - 15/30 = 0.5`. → `score = 0.5 · 0.85 = 0.425`.

**E6.** `kind_weight_earnings = 1.0`, `kind_weight_guidance = 0.5`. At $d = 0$:
- earnings: $\text{inner} = 0.5 \cdot 1.0 + 0.5 \cdot m$
- guidance: $\text{inner} = 0.5 \cdot 0.5 + 0.5 \cdot m = 0.25 + 0.5 m$

The factor isn't a clean constant — it depends on `magnitude`. For `m = 1.0`: earnings = 1.0, guidance = 0.75 → factor **0.75**. For `m = 0`: earnings = 0.5, guidance = 0.25 → factor **0.5**. The kind weight matters more when historical magnitudes are small.

**E7.** **`iv_score = 0.20`** → IV is cheap (low rank, low percentile, or low IV/HV ratio). **`structure_score = 0.85`** → spot is tightly aligned with options structure (max pain, OI walls, near opex, tight EM). **`event_score = 0.05`** → essentially no scheduled event. This is the textbook **`LOW_IV_PIN`-adjacent** environment — low IV plus tight structure. (The Market State Engine doesn't have a LOW_IV_PIN regime; this would map to `HIGH_IV_PIN` in regime terms but with weak `iv_mid` because IV isn't high.) A long holder might buy cheap protective puts (low IV) and wait — vol-selling isn't attractive at low IV.

**E8.** Outline:

(a) Inputs: `dealer_gamma_proxy: Decimal`, `spot: Decimal`, `gamma_walls: list[GammaWall]` (per plan §9.11 signature). Maybe 3 fields.

(b) Composite: signed magnitude in $[-1, 1]$ that the consumer maps to $[0, 1]$ via either `clip01((g + 1)/2)` (linear) or `clip01(|g|)` (magnitude-only). Components: dealer-gamma-proxy normalized by spot's GEX scale; nearest gamma-wall distance normalized by EM (analogous to `structure_score`); sign captures stabilizing-vs-amplifying.

(c) Wiring (per §9.11): Flow Score Engine (orchestrator). Not consumed by Market State Engine directly (that's the iv/structure/event triple).

(d) Weights live at the top of `engine/scoring/gamma.py`, e.g. `_W_DEALER_GAMMA = 0.5`, `_W_GAMMA_WALL_DIST = 0.5`. V1 hand-coded; replaced by E1 GEX module in Phase 1.5 per [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md). At least 5 named test fixtures + 100% line coverage per plan §9.11.

---

## 9. Further reading

### Project artifacts

- Plan v1.2 §9.11 (Scoring Functions Module spec — wiring matrix + test
  bar), §22.5 (clip01 reuse), §22.13 (breakdown for Confidence Composer).
- [ADR-0003](../decisions/0003-confidence-composer-multiplicative.md) —
  multiplicative-penalty Confidence Composer that consumes these scores.
- [ADR-0005](../decisions/0005-engine-pure-function-discipline.md) —
  pure-function discipline + SemVer policy.
- [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) —
  Phase 4 ML node-swap roadmap (these scoring fns are first to swap).
- [Market State Engine tutorial](./market-state-engine.md) — sibling
  tutorial covering `classify()` which sits one layer up.

### Code

- [`packages/engine/engine/scoring/`](../../packages/engine/engine/scoring) — the three primitives + their result types.
- [`packages/engine/engine/_utils.py`](../../packages/engine/engine/_utils.py) — `clip01` (shared with the rest of the engine).
- [`packages/engine/tests/test_scoring_iv.py`](../../packages/engine/tests/test_scoring_iv.py)
  / [`test_scoring_structure.py`](../../packages/engine/tests/test_scoring_structure.py)
  / [`test_scoring_event.py`](../../packages/engine/tests/test_scoring_event.py) — 59 tests, 100% line coverage.

### External / academic

- Sinclair, *Volatility Trading* — IV rank, IV-HV premium, premium-seller
  edge (chapters 2–3).
- Carr & Wu, *Variance Risk Premiums* (Review of Financial Studies, 2009)
  — empirical foundation for the IV − HV gap as a tradable premium.
- Andersen, Fusari, & Todorov, *The Risk Premia Embedded in Index Options*
  (Journal of Financial Economics, 2015) — event risk premia decomposition.
- Bollen & Whaley, *Does Net Buying Pressure Affect the Shape of Implied
  Volatility Functions?* (Journal of Finance, 2004) — empirical work on
  dealer flow / OI walls / pinning (also referenced in the Market State
  Engine tutorial).
- Christoffersen, Heston, & Jacobs, *Capturing Option Anomalies with a
  Variance-Dependent Pricing Kernel* (RFS, 2013) — for the IV-vs-HV
  premium as a risk-premium signature.

---

## 10. Glossary of symbols

| Symbol | Meaning |
|---|---|
| $S$ | Spot price of the underlying |
| $K^\*$ | Max-pain strike |
| $K_w$ | Strike of OI wall $w$ (support or resistance) |
| $\sigma_{IV}$ | Current ATM implied volatility (annualized, decimal) |
| $\sigma_{HV}$ | Annualized 30-day historical volatility (decimal) |
| $\rho$ | IV/HV ratio = $\sigma_{IV} / \sigma_{HV}$ |
| $\text{EM}_\%$ | One-σ expected fractional move = $\sigma_{IV} \sqrt{\tau/252}$ |
| $d$ | Generic distance (in days, or in fraction of spot, by context) |
| $d_w$ | Relative distance from spot to wall $w$ = $\|S - K_w\| / S$ |
| $d_{\text{pin}}$ | Relative distance from spot to max-pain = $\|S - K^\*\| / S$ |
| $d_{\text{evt}}$ | `days_to_event` |
| $d_{\text{opex}}$ | `days_to_nearest_opex` |
| $\overline{\|r\|}$ | Average absolute event-day return = `EventStats.avg_abs_return_pct` |
| $\mathrm{clip}_{[0,1]}(x)$ | Clip to closed unit interval |
| `_W_*` | Component weight constant (sums to 1.0 per primitive) |
| `_DEFAULT_KIND_WEIGHT` | 0.5 fallback for unknown / `None` event kinds |
| `EVENT_KIND_WEIGHTS` | V1 weight prior table for recognized kinds |

---

*This tutorial is maintained alongside the engine. When any file under
`packages/engine/engine/scoring/` changes — even a constant — the same
PR updates this file. Contributions welcome via the docs PR workflow in
[`docs/README.md`](../README.md).*
