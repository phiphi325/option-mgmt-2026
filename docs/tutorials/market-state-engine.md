# Tutorial: The Market State Engine

> **Audience.** First-year master's students in financial engineering, quantitative-developer onboarding, options traders who want to understand a working classifier.
> **Prerequisites.** Black–Scholes basics, options Greeks, log-returns, sample standard deviation, sigmoid functions, basic Python.
> **Reading time.** ~75 min careful read with the exercises; ~25 min skim.
> **Engine version covered.** `0.6.0` (post-M1.4 squash). The `classify()` signature lives in [`packages/engine/engine/market_state/classify.py`](../../packages/engine/engine/market_state/classify.py).
>
> **Disclaimer.** This tutorial is **educational material**. The engine is a decision-support system, not investment advice. See [`docs/disclaimers.md`](../disclaimers.md) for the full posture.

---

## Table of contents

1. [Why a Market State Engine?](#1-why-a-market-state-engine)
2. [Foundations: the input vocabulary](#2-foundations-the-input-vocabulary)
3. [The six regimes](#3-the-six-regimes)
4. [The classification algorithm](#4-the-classification-algorithm)
5. [Engineering design choices](#5-engineering-design-choices)
6. [End-to-end worked example](#6-end-to-end-worked-example)
7. [Hands-on exercises](#7-hands-on-exercises)
8. [Further reading](#8-further-reading)
9. [Glossary of symbols](#9-glossary-of-symbols)

---

## 1. Why a Market State Engine?

### 1.1 The decision problem

A long-equity holder of a single name (here, MSFT) wakes up each morning and
asks: **"What option action, if any, should I take on this position today?"**

The action set is small in principle — sell a covered call, buy a put, build
a collar, do nothing — but the *right* action depends on the regime the
market is in:

- Selling premium (covered calls, cash-secured puts) is most attractive when
  implied vol (IV) is rich relative to recent realized vol.
- Buying protection (puts, collars) is most attractive when *event risk* is
  imminent (earnings, FOMC, CPI) and the chain is paying for it.
- Doing nothing is often correct when the market is in a calm range, the IV
  curve is flat, and there's no near-term catalyst.

The engine's job is to map a **flat record of market-state inputs** to one
of six **named regimes** plus an explainable `[0, 1]` confidence. Downstream
modules (Strike Selector, Recommendation Engine, Confidence Composer) then
turn that regime into concrete option actions.

### 1.2 Why six regimes?

The taxonomy is locked in [ADR-0002](../decisions/0002-regime-taxonomy.md).
Six regimes is a deliberate compromise: enough to give materially different
strategy whitelists, few enough that a human can build calibration intuition
and a regression-test harness can cover all of them with named fixtures.

We will derive each regime in §3. First, we need the inputs.

### 1.3 Engine-first architecture

The engine is the product. APIs and UIs exist to surface or input to it
(see [ADR-0001](../decisions/0001-engine-first-architecture.md)). The
engine is a **pure function**: no DB, no clock, no network, no env reads
(see [ADR-0005](../decisions/0005-engine-pure-function-discipline.md)).

This matters for two reasons:

1. **Testability.** Every engine function is unit-testable from typed inputs to
   typed outputs. Golden vectors catch regressions cheaply.
2. **Replay-ability.** Every persisted decision pins
   `engine_version` + `weights_version` + `inputs_hash` for byte-identical
   replay. ML upgrades to specific nodes (Phase 4) preserve the interface.

If you have used scikit-learn or written a Kalman filter, you have already
written code that fits this discipline; the engine just makes the discipline
explicit and CI-enforced.

---

## 2. Foundations: the input vocabulary

`classify()` takes 18 inputs (the §22.3 extended signature from the project's
plan). They cluster into six **input families** which we now cover one by
one. For each family we name:

- The **financial concept** (what does it measure?).
- The **estimator** the engine uses (how is it computed?).
- The **engine convention** (units, scale, edge cases).

### 2.1 Implied vs realized volatility

**Implied volatility (IV)** is the volatility parameter $\sigma_{\text{imp}}$
that, plugged into the Black–Scholes formula, recovers the market price of an
option. It is the market's *forward-looking* view: how much daily-return
variance traders are pricing in for the period until expiry.

**Realized / historical volatility (HV)** is the empirical sample standard
deviation of past log returns, annualized. Given closes
$P_0, P_1, \dots, P_n$ over $n+1$ trading days,

$$\hat\sigma_{HV} \;=\; \sqrt{252} \cdot \sqrt{ \frac{1}{n - 1} \sum_{i=1}^{n} \big( r_i - \bar{r} \big)^2 }, \qquad r_i = \ln(P_i / P_{i-1}).$$

The factor $\sqrt{252}$ annualizes from the daily-return scale to the same
unit space as IV (one trading year ≈ 252 trading days).

The **IV − HV gap** (or ratio) is the central edge for a premium seller: when
IV is materially above HV, options are paying for vol that historical realized
behavior did not justify.

> *Engine implementations:*
> - [`engine.market_state.compute_hv`](../../packages/engine/engine/market_state/hv.py) — annualized close-to-close standard deviation; raises on insufficient prices or non-positive prices.
> - The IV side flows in directly as a parameter (the data layer pulls ATM 30d IV from the chain snapshot).

### 2.2 IV rank vs IV percentile

Selling premium is more attractive when current IV is **high relative to
where it has been**, not just high in absolute terms (NVDA 30 IV is high for
a bond ETF; SPY 30 IV is moderate).

Two complementary normalizations capture this:

- **IV rank** (range-based):
  $$\text{IV rank} \;=\; \mathrm{clip}_{[0,1]}\!\left( \frac{ \mathrm{IV}_t - \min_{s\in W} \mathrm{IV}_s }{ \max_{s\in W} \mathrm{IV}_s - \min_{s\in W} \mathrm{IV}_s } \right)$$
  over a 252-day trailing window $W$. Sensitive to outliers (one IV spike pulls the max up, suppressing the rank for the rest of the series), but the rank corresponds directly to "where in the band are we" — the natural premium-selling intuition.

- **IV percentile** (count-based): the fraction of observations in $W$
  *strictly below* $\mathrm{IV}_t$. Robust to outliers but insensitive to
  magnitude (a 1% IV jump and a 30% jump can both register as the same
  percentile if the historical distribution is dense around current IV).

The engine consumes both. They are *not* redundant; the M1.4a `iv_score()`
explicitly weight-blends them (`0.40 · rank + 0.30 · percentile + 0.30 · IV/HV premium`).

> *Engine convention.* Both are in $[0, 1]$. A rank of 0.85 means current IV
> sits 85% of the way between the 252-day min and max; a percentile of 0.85
> means 85% of the historical observations are strictly below current.
>
> *Engine implementation.* [`engine.market_state.iv_rank` / `iv_percentile`](../../packages/engine/engine/market_state/iv.py).

### 2.3 Expected move

Under a lognormal-returns assumption, the **one-σ expected dollar move** of
spot $S$ over horizon $\tau$ trading days at ATM IV $\sigma$ is

$$\text{EM}_{\$} \;=\; S \cdot \sigma \cdot \sqrt{\tau / 252}, \qquad \text{EM}_{\%} \;=\; \sigma \cdot \sqrt{\tau / 252}.$$

This is a *first-order* estimator: it assumes returns are approximately
lognormal over the window and ATM IV is a reasonable proxy for the diffusion
vol. Around an event (earnings, FOMC) the lognormal assumption breaks down —
real expected moves are bimodal (gap up vs. gap down) — so the engine treats
EM as one input among many, not a probability statement.

> *Engine convention.* `expected_move_pct` is a fraction of spot
> (`0.04 = 4%`).
>
> *Engine implementation.* [`engine.market_state.expected_move`](../../packages/engine/engine/market_state/expected_move.py).

### 2.4 Max pain

**Max pain** is the strike $K^\*$ at which the **total dollar pain to option
writers** at expiration is minimized. Define per-strike pain across all open
call and put OI:

$$\text{call\_pain}(K) = \sum_{c \in \text{CALL}} \mathrm{OI}_c \cdot \max(K - K_c, 0),$$
$$\text{put\_pain}(K) = \sum_{p \in \text{PUT}} \mathrm{OI}_p \cdot \max(K_p - K, 0),$$
$$K^\* = \arg\min_{K} \; m \cdot (\text{call\_pain}(K) + \text{put\_pain}(K)),$$

where $m = 100$ is the standard equity contract multiplier. The intuition:
$K^\*$ is the strike that makes the most short-option positions expire
worthless, transferring premium from buyers to writers. In low-vol pin
regimes around monthly opex, spot can be drawn toward $K^\*$.

Max pain is a heuristic, not a forecast. The engine uses
$|S - K^\*|/S$ as a structural alignment input, scaled by EM.

> *Engine implementation.* [`engine.market_state.compute_max_pain`](../../packages/engine/engine/market_state/max_pain.py); plan v1.2 §22.9 codifies the formula.

### 2.5 PCR (put / call ratio)

Two complementary forms:

- **PCR by volume** = $\sum \text{put volume} / \sum \text{call volume}$ — a
  short-term sentiment signal; noisy intraday but reactive.
- **PCR by OI** = $\sum \text{put OI} / \sum \text{call OI}$ — a structural
  positioning signal; slower-moving, more stable.

A high PCR generally means more bearish positioning (more put activity
relative to calls). The engine takes both as inputs to flow / regime logic.

> *Engine convention.* Both are non-negative floats; degenerate cases
> (zero call total) return 0.0 and callers must treat that as "no signal,"
> not as a directional read.
>
> *Engine implementation.* [`engine.market_state.pcr_volume` / `pcr_oi`](../../packages/engine/engine/market_state/pcr.py).

### 2.6 OI walls and pinning

When a single strike accumulates open interest far above the chain median,
that strike acts as an **OI wall** — a soft support (highest large-OI strike
strictly below spot) or resistance (lowest above spot). Dealers hedging short
gamma at large-OI strikes generate flow that resists spot moves *through* the
wall.

The Market State Engine does not compute OI walls itself (that's M1.5, the
Flow Score Engine); it consumes `oi_concentration_at_max_pain` ∈ $[0, 1]$
which captures *how concentrated* OI is at the max-pain strike. Higher
concentration → stronger pin pressure.

### 2.7 Wilder ADX (trend strength)

J. Welles Wilder Jr.'s **Average Directional Index** measures trend
*strength* without committing to direction. The recursion (Wilder, 1978),
period $n = 14$:

For each bar $i \ge 1$:

$$\text{TR}_i = \max\!\left( H_i - L_i,\, |H_i - C_{i-1}|,\, |L_i - C_{i-1}| \right),$$
$$+\!\text{DM}_i = \begin{cases} H_i - H_{i-1} & \text{if } H_i - H_{i-1} > L_{i-1} - L_i \text{ and } H_i - H_{i-1} > 0 \\ 0 & \text{otherwise} \end{cases}$$
$$-\!\text{DM}_i = \begin{cases} L_{i-1} - L_i & \text{if } L_{i-1} - L_i > H_i - H_{i-1} \text{ and } L_{i-1} - L_i > 0 \\ 0 & \text{otherwise} \end{cases}$$

Wilder's smoothing (RMA) over each series with period $n$:

$$R_n = \frac{1}{n} \sum_{i=1}^{n} x_i, \qquad R_{i} = \frac{R_{i-1} (n-1) + x_i}{n}, \quad i > n.$$

Then

$$+\!\text{DI} = 100 \cdot \frac{R_n(+\!\text{DM})}{R_n(\text{TR})}, \quad -\!\text{DI} = 100 \cdot \frac{R_n(-\!\text{DM})}{R_n(\text{TR})},$$
$$\text{DX} = 100 \cdot \frac{|+\!\text{DI} - -\!\text{DI}|}{+\!\text{DI} + -\!\text{DI}}, \qquad \text{ADX} = R_n(\text{DX}).$$

The engine's `compute_trend_strength` normalizes ADX to $[0, 1]$:

$$\text{trend\_strength} = \mathrm{clip}_{[0,1]}\!\left( \frac{\text{ADX} - 20}{20} \right).$$

ADX ≤ 20 → 0.0 (no meaningful trend); ADX ≥ 40 → 1.0 (strong trend);
linear in between. Wilder's own guidance plus standard ADX interpretation
fix these thresholds.

**Insufficient history.** ADX needs ≈ $2n$ bars to seed and another $n$ for
the DX smoother. Plan §22.5 demands `2n + 10` (= 38 for $n = 14$) for stable
ADX. Below threshold the engine returns the **0.5 sentinel** (the "no
information / neutral" prior) — a deliberate non-raising path so
`classify()` keeps running on partial data.

> *Engine implementation.* [`engine.market_state.compute_trend_strength` / `wilder_adx`](../../packages/engine/engine/market_state/trend_strength.py).

### 2.8 Breakout signal

A 4-component composite (plan v1.2 §22.5):

| Component | Formula | Weight |
|---|---|---|
| Move | $\mathrm{clip}_{[0,1]}(|\Delta S_{5d} / S_{-5d}| / 0.05)$ | 0.35 |
| Vol | $\mathrm{clip}_{[0,1]}(\Delta \sigma_{ATM, 5d} / 0.10)$ (negatives clipped to 0) | 0.20 |
| OI | $\mathrm{clip}_{[0,1]}(|\Delta \mathrm{OI\,shift\,ratio}|)$ | 0.20 |
| Break | $\mathrm{clip}_{[0,1]}(\text{above\_resistance\_pct} / 0.02)$, gated on `above_resistance` | 0.25 |

$$\text{breakout\_signal} = \mathrm{clip}_{[0,1]}\!\big( 0.35 \cdot \text{move} + 0.20 \cdot \text{vol} + 0.20 \cdot \text{oi} + 0.25 \cdot \text{break} \big).$$

Weights sum to 1.0 so the composite is always in $[0, 1]$ before the final
clip. Each component is independently clipped, so the composite is bounded
even when individual inputs overshoot.

> *Engine implementation.* [`engine.market_state.compute_breakout_signal`](../../packages/engine/engine/market_state/breakout.py).

### 2.9 Event proximity, IV crush, gap

Three optional inputs feed the event-driven regimes:

- `days_to_next_event: int | None` — trading days until the next scheduled
  event (earnings, FOMC, CPI, ex-dividend). `None` when the calendar has
  nothing scheduled. Negative values (event already past) are clamped to 0
  defensively.
- `days_since_event: int | None` — symmetric: days since the most recent
  event. Drives `POST_EVENT_REPRICE`.
- `iv_rank_change_1d: float | None` — one-day delta of `iv_rank` in
  $[-1, 1]$. A 20 percentage-point IV crush is `-0.20` in our scale.
- `gap_pct: float | None` — signed fraction of spot, e.g. `0.025 = 2.5%`.

Plan v1.2 §22.3 also takes `next_event_kind: str | None` (`"earnings"`,
`"fomc"`, `"cpi"`, `"guidance"`, `"ex_dividend"`, `"other"`) — used by the
M1.4a `event_score()` for kind-weighted impact estimation, and surfaced in
the `MarketStateResult` for tagging.

> **Scale convention.** The engine uses canonical $[0, 1]$ for `iv_rank`.
> Plan §9.2 sketches assume a $[0, 100]$ scale and use thresholds 70 / 60 /
> 30 with slope 10. The engine code rescales these to 0.70 / 0.60 / 0.30
> with slope 0.10. Sigmoid arguments are unchanged because both numerator
> and denominator scale identically. A documented "scale fix" in §5.2.

---

## 3. The six regimes

The taxonomy is locked in [ADR-0002](../decisions/0002-regime-taxonomy.md).
For each regime we name:

- **What it captures** — the market behaviour.
- **Why a long-equity holder cares** — what it changes about action choice.
- **What the predicate looks for** (preview of §4).

### 3.1 `HIGH_IV_EVENT`

**What.** IV is rich relative to the 252-day band *and* a known event sits
within ~7 trading days. The chain is paying a fat premium for the upcoming
catalyst (earnings, FOMC, CPI).

**Why care.** Selling unhedged premium across the event is a high-variance
bet with uncapped tail risk. The right answer is usually a **collar** —
sell short calls *and* buy protective puts — which lets the holder collect
some pre-event premium while capping downside.

**Predicate looks for.** High `iv_rank` (sigmoid through 0.70) **and**
nearby event (`days_to_next_event ≤ 7`). Both must be present.

### 3.2 `HIGH_IV_PIN`

**What.** Mid-high IV (sigmoid through 0.60), spot tightly aligned with the
max-pain strike (within ~1% of spot), close to monthly opex (≤ 5 trading
days). Classic "pin into expiration" setup.

**Why care.** Selling out-of-the-money premium with strikes above and below
max pain becomes attractive — pin pressure plus theta decay favor the
seller. Volume often dries up into the pin, so liquidity matters.

**Predicate looks for.** Combination of `iv_rank` band ≥ 0.60, tight
spot–max-pain alignment, near opex.

### 3.3 `LOW_IV_TREND`

**What.** Low IV (sigmoid through 0.30 *from above*) plus high
`trend_strength`. The market is trending but vol-pricing is calm — i.e. the
trend is grinding, not gapping.

**Why care.** Buying tail protection is *cheap* (low IV) and *useful*
(trends correct). For a long holder, this is the regime to consider buying
inexpensive puts. Selling calls is less attractive because trend means
upside risk to the short call is real.

**Predicate looks for.** Low `iv_rank`, high `trend_strength`. Realized
vs. implied is *not* tightly aligned (otherwise → range, not trend).

### 3.4 `LOW_IV_RANGE`

**What.** Low IV (`iv_rank` ≤ 0.30 sigmoidal), low trend (`trend_strength`
near zero), realized vol close to implied. Market is in a quiet,
mean-reverting band.

**Why care.** Selling premium is the textbook play: theta decay accumulates
without the directional shock that breaks a range. Strikes can be set just
outside the range with high probability of expiring worthless.

**Predicate looks for.** Low IV, low trend, $|\text{realized}/\text{implied} - 1|$ small.

### 3.5 `BREAKOUT`

**What.** The 4-component breakout composite is high (≥ ~0.70). Spot is
moving meaningfully, IV has lifted, OI is rotating, and spot is above a
recently established resistance.

**Why care.** Existing short calls may be threatened. Roll-up intent kicks
in: close the short call, sell a higher strike to reset the trade. The
regime tags the situation; the Strike Selector / Recommendation Engine
chooses the action.

**Predicate looks for.** `clip01(breakout_signal)` directly. The Market
State Engine defers entirely to the §22.5 composite.

### 3.6 `POST_EVENT_REPRICE`

**What.** An event happened ≤ 1 trading day ago, IV has crushed (≥ 20pp
drop in `iv_rank`), and there is a meaningful price gap (|gap_pct| > 2%).
Vol has decayed, position has gapped, the chain has repriced everything.

**Why care.** New collar opportunities open up because IV is now cheap to
buy (puts for protection) and the position has a fresh anchor (the gap).
The regime explicitly suggests "consider a collar reset" as the next move.

**Predicate looks for.** `days_since_event ≤ 1` plus large IV-crush plus
large gap.

### 3.7 What does **not** appear

The locked taxonomy excludes anything we cannot identify reliably with the
M1 input vector:

- Macroeconomic regimes (rate-cutting cycle, recession, etc.) — too noisy at
  the single-name level.
- Index-correlation regimes (market breaking down) — needs cross-asset
  inputs that ship in Phase 2.
- "Anything else" — we deliberately do *not* have a default-bucket regime;
  ties resolve via the priority list, never to a fallback.

Future regimes (e.g. `MACRO_EVENT_WEEK`) would land via a new ADR, an
Alembic migration, a TS regen, *and* at least four new fixtures — see
ADR-0002 for the full coupling list.

---

## 4. The classification algorithm

### 4.1 The 18-input signature

```python
def classify(
    *,
    spot: float,
    iv_rank: float, iv_percentile: float, hv_30: float,
    expected_move_pct: float,
    max_pain: float,
    pcr_volume: float, pcr_oi: float,
    days_to_next_event: int | None, next_event_kind: str | None,
    trend_strength: float,
    realized_vs_implied: float,
    days_since_event: int | None,
    days_to_nearest_opex: int | None,
    iv_rank_change_1d: float | None,
    gap_pct: float | None,
    breakout_signal: float,
    oi_concentration_at_max_pain: float,
) -> MarketStateResult: ...
```

Three things to notice:

1. **Kwargs-only.** The leading `*` forces every caller to name every
   argument. 18 positional floats would be a pile of off-by-one bugs.
2. **No `Decimal`.** The plan §22.3 lists `Decimal` for `spot` and
   `max_pain`; the engine currently uses `float` to match the existing
   `compute_max_pain` return type and `OptionContract.strike: float`. A
   migration to `Decimal` is tracked but not blocking.
3. **`None`-aware optionals.** Five optional fields (`days_to_next_event`,
   `next_event_kind`, `days_since_event`, `days_to_nearest_opex`,
   `iv_rank_change_1d`, `gap_pct`) all accept `None`. The default is "no
   information"; the predicates handle `None` explicitly rather than relying
   on sentinel values.

### 4.2 The six per-regime predicates

Each regime has a private `_score_<regime>()` helper returning a score in
$[0, 1]$. Higher = "more this regime." All formulas use:

- `clip01(x)` — clip to $[0, 1]$.
- `sigmoid(x) = 1 / (1 + e^{-x})` — the standard logistic, with sign
  branching so `math.exp` always sees a non-positive argument (numerical
  stability).

Constants live at the top of `classify.py` and are documented at point of
use:

```python
_IV_HIGH_THRESHOLD = 0.70   # plan §9.2: 70 in 0..100, rescaled
_IV_MID_THRESHOLD = 0.60
_IV_LOW_THRESHOLD = 0.30
_IV_SIGMOID_SLOPE = 0.10

_HIGH_IV_EVENT_NEAR_DAYS = 7
_PIN_TOLERANCE_PCT = 0.01   # 1% of spot
_OPEX_HORIZON_DAYS = 5

_POST_EVENT_WINDOW_DAYS = 1
_IV_CRUSH_FULL_DROP = 0.20  # 20pp in [0,1] scale
_POST_EVENT_GAP_THRESHOLD = 0.02
```

The closed forms:

#### `HIGH_IV_EVENT`

$$s_{\text{evt}} = \mathrm{clip}_{[0,1]}\!\big( 0.5 \cdot \sigma\!\left( \tfrac{\mathrm{IV\,rank} - 0.70}{0.10} \right) + 0.5 \cdot \mathbf{1}\{d_{\text{evt}} \le 7\} \big).$$

`near_event` is binary-stepped on purpose — events are scheduled, not
fuzzy. `iv_high` is sigmoidal so the boundary is *soft* (a small change in
`iv_rank` doesn't flip the regime decision discontinuously).

#### `HIGH_IV_PIN`

$$\text{pin\_close} = \max\!\left( 0,\, 1 - \tfrac{|S - K^\*|/S}{0.01} \right), \quad \text{near\_expiry} = \max\!\left( 0,\, 1 - \tfrac{d_{\text{opex}}}{5} \right),$$
$$s_{\text{pin}} = \mathrm{clip}_{[0,1]}\!\big( 0.4 \cdot \sigma\!\left( \tfrac{\mathrm{IV\,rank} - 0.60}{0.10} \right) + 0.4 \cdot \text{pin\_close} + 0.2 \cdot \text{near\_expiry} \big).$$

`pin_close` is clipped at 0 — once spot is more than 1% away from $K^\*$ in
either direction, the pin signal is *off*. `near_expiry` defaults to 30 if
`days_to_nearest_opex is None` (which floors `near_expiry` at 0).

#### `LOW_IV_TREND`

$$s_{\text{trend}} = \mathrm{clip}_{[0,1]}\!\big( 0.5 \cdot \sigma\!\left( \tfrac{0.30 - \mathrm{IV\,rank}}{0.10} \right) + 0.5 \cdot \text{trend\_strength} \big).$$

`iv_low` reverses the sigmoid argument (`0.30 − iv_rank` instead of
`iv_rank − 0.30`) so it rises as `iv_rank` *falls*. `trend_strength` is
already in $[0, 1]$ from `compute_trend_strength`, so no transform is needed.

#### `LOW_IV_RANGE`

$$\text{not\_trending} = 1 - \text{trend\_strength}, \quad \text{realized\_match} = \max\!\left( 0,\, 1 - \big| \tfrac{\sigma_{HV}}{\sigma_{IV}} - 1 \big| \right),$$
$$s_{\text{range}} = \mathrm{clip}_{[0,1]}\!\big( 0.4 \cdot \sigma\!\left( \tfrac{0.30 - \mathrm{IV\,rank}}{0.10} \right) + 0.3 \cdot \text{not\_trending} + 0.3 \cdot \text{realized\_match} \big).$$

`realized_match` peaks at 1 when realized vol exactly equals implied; falls
off linearly toward 0 as the ratio diverges from 1.

#### `BREAKOUT`

$$s_{\text{break}} = \mathrm{clip}_{[0,1]}( \text{breakout\_signal} ).$$

The Market State Engine *defers* to the §22.5 4-component composite. There
is no separate computation. This is by design: the breakout signal is itself
a calibrated composite, and threading it through more thresholds would just
add noise.

#### `POST_EVENT_REPRICE`

$$\text{iv\_crushed} = \mathrm{clip}_{[0,1]}\!\big( -\Delta \mathrm{IV\,rank}_{1d} / 0.20 \big), \quad \text{big\_gap} = \mathbf{1}\{ |\text{gap\_pct}| > 0.02 \},$$
$$s_{\text{post}} = \mathrm{clip}_{[0,1]}\!\big( 0.6 \cdot \text{iv\_crushed} + 0.4 \cdot \text{big\_gap} \big) \quad \text{when } d_{\text{since\_evt}} \le 1, \text{ else } 0.$$

The engine **only scores this regime within 1 day** of an event. Plan §9.2's
sketched `iv_crushed = max(0, 1 - x / -20)` had a sign error — it evaluates
to 0 (not 1) on a 20pp drop. The engine implements the corrected formula and
documents the deviation at the call site.

### 4.3 Selecting the winner: max with priority tie-break

Once we have $\{ s_{\text{evt}}, s_{\text{pin}}, s_{\text{trend}}, s_{\text{range}}, s_{\text{break}}, s_{\text{post}} \}$, we pick the highest-scoring regime — *unless* the runner-up is within `_TIE_DELTA = 0.10` of the leader, in which case the higher-priority regime wins.

The priority list, top-down (most conservative first):

```python
_TIE_BREAK_PRIORITY = (
    Regime.HIGH_IV_EVENT,
    Regime.HIGH_IV_PIN,
    Regime.POST_EVENT_REPRICE,
    Regime.BREAKOUT,
    Regime.LOW_IV_TREND,
    Regime.LOW_IV_RANGE,
)
```

Plan v1.2 §9.2 phrases the rule as: **"Ties (delta < 0.10) resolve toward
the more conservative (event-aware) regime."** The implementation:

```python
def _select_regime(scores: dict[Regime, float]) -> tuple[Regime, float]:
    max_score = max(scores.values())
    for candidate in _TIE_BREAK_PRIORITY:
        if max_score - scores[candidate] < _TIE_DELTA:
            return candidate, scores[candidate]
    leader = max(scores, key=lambda r: scores[r])
    return leader, scores[leader]
```

Note: the `regime_score` returned is **the score of the chosen regime**, not
the leader's score (when they differ under tie-break). Downstream consumers
can trust `regime_score == all_scores[regime]`.

### 4.4 Tag generation

After selecting the regime, the engine emits an **advisory tag tuple**
consumed by Strike Selector / Recommendation Engine / Confidence Composer.
Tags do **not** affect regime selection (the regime score map already
encodes the decision); they enrich downstream rationale strings and
strategy filtering.

| Tag | Trigger |
|---|---|
| `sell_vol_favorable` | `iv_rank ≥ 0.70` |
| `sell_vol_unfavorable` | `iv_rank ≤ 0.30` |
| `event_in_<N>d` | `days_to_next_event ≤ 14` (N is the actual integer) |
| `post_event_window` | `days_since_event ≤ 2` |
| `pin_risk` | `|spot − max_pain| / spot ≤ 0.005` AND `dte_to_nearest_opex ≤ 5` |
| `breakout_active` | `breakout_signal ≥ 0.70` |
| `trending` | `trend_strength ≥ 0.70` |
| `ranging` | `trend_strength ≤ 0.30` |
| `concentrated_oi_at_pin` | `oi_concentration_at_max_pain ≥ 0.60` |

Adding a tag is *non-breaking*. Removing or renaming a tag IS breaking
because downstream code may be matching on the literal string.

### 4.5 The result dataclass

```python
@dataclass(frozen=True)
class MarketStateResult:
    # Engine output
    regime: Regime
    regime_score: float
    all_scores: dict[Regime, float]
    tags: tuple[str, ...]
    # Echoed inputs (full vector, for explainability + replay)
    spot: float
    iv_rank: float
    iv_percentile: float
    hv_30: float
    expected_move_pct: float
    max_pain: float
    max_pain_delta_pct: float          # computed: (max_pain − spot) / spot
    pcr_volume: float
    pcr_oi: float
    trend_strength: float
    realized_vs_implied: float
    breakout_signal: float
    oi_concentration_at_max_pain: float
    days_to_next_event: int | None
    next_event_kind: str | None
    days_since_event: int | None
    days_to_nearest_opex: int | None
    iv_rank_change_1d: float | None
    gap_pct: float | None
```

`tags: tuple[str, ...]` (not `list`) so the dataclass is immutable enough
to compare structurally. `all_scores: dict[Regime, float]` is mutable in
principle (Python dicts can be mutated), but the engine treats it as
read-only and consumers should `.copy()` before mutating.

Why echo every input? **Replay.** Persisted `DailyDecision` rows pin
`engine_version + weights_version + inputs_hash`. With the result echoing
every input, debugging a past decision becomes "load the row, eyeball the
inputs, recompute by hand if needed." Without echoing, you'd need a join
back to the snapshot table — slower, and brittle if snapshots are GC'd.

### 4.6 Data flow diagram

```
ChainSnapshot ──┬──> iv_rank, iv_percentile (252d history)
                ├──> compute_hv ──> hv_30
                ├──> compute_max_pain ──> max_pain
                ├──> expected_move_pct
                └──> pcr_volume, pcr_oi

OHLC bars ─────────> compute_trend_strength ──> trend_strength
OHLC + chain Δ ────> compute_breakout_signal ──> breakout_signal

Event calendar ────> days_to_next_event, next_event_kind,
                     days_since_event, iv_rank_change_1d, gap_pct,
                     days_to_nearest_opex

oi_concentration_at_max_pain (M1.5 Flow Score, today supplied as input)

                              ↓

                          classify(...)
                              ↓
                     ┌──────────────────┐
                     │ MarketStateResult │
                     │  regime           │
                     │  regime_score     │
                     │  all_scores       │
                     │  tags             │
                     │  + echoed inputs  │
                     └──────────────────┘
                              ↓
            consumed by Strike Selector,
            Recommendation Engine,
            Confidence Composer,
            Today screen UI
```

---

## 5. Engineering design choices

### 5.1 Why composite scores, not a decision tree?

A decision tree would write rules like

```
if iv_rank > 0.7 and days_to_event <= 7: HIGH_IV_EVENT
elif iv_rank > 0.6 and pin_close and dte <= 5: HIGH_IV_PIN
...
```

Three reasons composite scoring wins:

1. **Smooth boundaries.** A small change in `iv_rank` from 0.69 → 0.71
   shouldn't flip the regime label. Sigmoid soft thresholds give continuous
   degradation; trees give cliffs.
2. **Calibration via weights.** When a regime mis-fires in production, you
   can shift the weight or threshold and re-run fixtures. With trees, you
   re-write the rule and risk introducing a hole.
3. **`all_scores` is free.** Composite scoring naturally produces a score
   per regime. Downstream (e.g. Confidence Composer) reads the runner-up
   margin to estimate decision confidence.

The Phase 4 ML upgrade (per [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md))
trains an HMM or Transformer to *replace* the per-regime predicates while
preserving the interface — the smooth scoring shape is what makes that swap
feasible.

### 5.2 Plan §22 audit corrections

Plan §9.2 is the original predicate sketch (drafted in v1.0). The §22 audit
caught two problems implementations need to know about:

1. **Scale fix.** §9.2 thresholds (70, 60, 30, slope 10) assume `iv_rank` in
   `[0, 100]`. The engine uses `[0, 1]`. The rescaling is straightforward:
   threshold and slope both divide by 100, so the sigmoid argument is
   identical:
   $$\sigma\!\left( \tfrac{x_{[0,100]} - 70}{10} \right) = \sigma\!\left( \tfrac{x_{[0,1]} - 0.70}{0.10} \right).$$
   *Why is the engine in `[0, 1]`?* Consistency with `compute_trend_strength`
   and the M1.4a scoring functions, all of which are in $[0, 1]$. Mixing
   scales would invite bugs.

2. **Sign error.** §9.2 sketches `iv_crushed = max(0, 1 − iv_rank_change_1d / -20)`.
   On a 20pp drop (`iv_rank_change_1d = -20` in §9.2 scale, `-0.20` in
   engine scale), this evaluates to `1 − (-20) / -20 = 1 − 1 = 0`. That's
   the *opposite* of "fully crushed." The engine implements the intended
   formula:
   $$\text{iv\_crushed} = \mathrm{clip}_{[0,1]}\!\big( -\Delta \mathrm{IV\,rank}_{1d} / 0.20 \big).$$
   On a 20pp drop: `0.20 / 0.20 = 1.0`. ✔
   The deviation is documented at the call site.

These are typical "implementer corrections" — the plan is a v1.0 / v1.1
sketch, the engine is the audited v1.2 reality. The plan v1.2 §22 patch
sheet is the source of truth wherever it conflicts with §1–§21.

### 5.3 Pure-function discipline

Per [ADR-0005](../decisions/0005-engine-pure-function-discipline.md):

**Allowed.** Pure functions over typed inputs. Imports from the stdlib,
`numpy`, `pydantic`, sibling engine modules.

**Forbidden.** DB access, network calls, filesystem writes, `os.environ`
reads, `datetime.now()`, unseeded `random`. The boundary is
`apps/api/app/services/decision_service.py`, which hydrates the inputs and
calls the engine — but the engine itself doesn't know the DB exists.

Why does this matter for the Market State Engine specifically?

- The engine takes `as_of: date` only when needed (e.g. for trend windows).
  `as_of` flows in as a parameter, not a `today()` call.
- No randomness — `classify()` is fully deterministic. Same inputs → same
  bytes out. This is what makes `inputs_hash` meaningful for replay.
- Tests run as fast pure-Python tests with no fixtures, no mocks. The 65
  M1.4 tests run in ~0.7 seconds.

### 5.4 SemVer-strict version policy

Per [ADR-0005](../decisions/0005-engine-pure-function-discipline.md) and
plan §22.15 L2:

| Bump | Change kind |
|---|---|
| **patch** (`0.x.y → 0.x.y+1`) | Bug fix, no schema change |
| **minor** (`0.x.0 → 0.x+1.0`) | New engine, score, public function |
| **major** (`x.0.0 → x+1.0.0`) | Schema change, removed/renamed fields, semantic shift |

CI enforces the bump via [`scripts/check_engine_version_bump.sh`](../../scripts/check_engine_version_bump.sh).
M1.4 ships as a minor bump (`0.5.0 → 0.6.0`) because `classify()` is a new
public function. M1.5's Flow Score Engine, when it lands, will be another
minor bump.

### 5.5 Test-driven discipline

The 65 M1.4 tests cover four shapes of correctness:

1. **24 named regime fixtures** (4 per regime) — *acceptance bar* per plan §17.
   Each fixture sets the discriminating inputs to dominate that regime's
   score over the others. The fixtures double as worked examples for new
   contributors.
2. **12 tag tests** — every tag has at least one positive case, plus
   negative cases for the conditional ones (`pin_risk`, `event_in_Nd`).
3. **Tie-break test** — verifies that when `HIGH_IV_PIN` scores higher
   numerically than `HIGH_IV_EVENT` but within `_TIE_DELTA = 0.10`, the
   priority list resolves to `HIGH_IV_EVENT`.
4. **Property tests via Hypothesis** — 200 random valid input vectors
   asserting `regime ∈ Regime`, `regime_score ∈ [0, 1]`, `all_scores`
   complete, `regime_score == all_scores[regime]`, `tags` is a tuple.

Coverage on `classify.py` is 99% (148/150). The 2 uncovered lines are an
unreachable defensive fallback in `_select_regime` that triggers only if
`_TIE_BREAK_PRIORITY` is mistakenly truncated — left in for safety.

---

## 6. End-to-end worked example

Let's trace the `test_classify_high_iv_event_earnings_in_3d` fixture by hand.

### 6.1 The input vector

```python
inputs = {
    "spot": 100.0,
    "iv_rank": 0.80,
    "iv_percentile": 0.78,
    "hv_30": 0.20,
    "expected_move_pct": 0.04,
    "max_pain": 97.0,            # 3% off spot — kills HIGH_IV_PIN
    "pcr_volume": 1.0,
    "pcr_oi": 1.0,
    "days_to_next_event": 3,
    "next_event_kind": "earnings",
    "trend_strength": 0.5,
    "realized_vs_implied": 0.4,  # IV runup pre-event
    "days_since_event": None,
    "days_to_nearest_opex": 20,
    "iv_rank_change_1d": None,
    "gap_pct": None,
    "breakout_signal": 0.0,
    "oi_concentration_at_max_pain": 0.3,
}
```

### 6.2 Compute every per-regime score by hand

We'll need the sigmoid table (rounded):

| $x$ | $\sigma(x)$ |
|---|---|
| -5 | 0.0067 |
| -3 | 0.047 |
| -2 | 0.119 |
| -1 | 0.269 |
| 0 | 0.500 |
| 1 | 0.731 |
| 2 | 0.881 |

#### `HIGH_IV_EVENT`

- $\sigma\!\left( \tfrac{0.80 - 0.70}{0.10} \right) = \sigma(1) = 0.731$
- `near_event` = $\mathbf{1}\{3 \le 7\} = 1$
- $s_{\text{evt}} = 0.5 \cdot 0.731 + 0.5 \cdot 1 = \mathbf{0.866}$

#### `HIGH_IV_PIN`

- $\sigma\!\left( \tfrac{0.80 - 0.60}{0.10} \right) = \sigma(2) = 0.881$
- `pin_close` = $\max\!\left(0, 1 - \tfrac{|100 - 97|/100}{0.01}\right) = \max\!\left(0, 1 - \tfrac{0.03}{0.01}\right) = \max(0, -2) = 0$
- `near_expiry` = $\max\!\left(0, 1 - \tfrac{20}{5}\right) = \max(0, -3) = 0$
- $s_{\text{pin}} = 0.4 \cdot 0.881 + 0.4 \cdot 0 + 0.2 \cdot 0 = \mathbf{0.352}$

#### `LOW_IV_TREND`

- $\sigma\!\left( \tfrac{0.30 - 0.80}{0.10} \right) = \sigma(-5) = 0.0067$
- $s_{\text{trend}} = 0.5 \cdot 0.0067 + 0.5 \cdot 0.5 = \mathbf{0.253}$

#### `LOW_IV_RANGE`

- iv_low component as above: 0.0067
- not_trending = $1 - 0.5 = 0.5$
- realized_match = $\max(0, 1 - |0.4 - 1|) = 0.4$
- $s_{\text{range}} = 0.4 \cdot 0.0067 + 0.3 \cdot 0.5 + 0.3 \cdot 0.4 = 0.003 + 0.15 + 0.12 = \mathbf{0.273}$

#### `BREAKOUT`

- $s_{\text{break}} = \mathrm{clip}_{[0,1]}(0.0) = \mathbf{0}$

#### `POST_EVENT_REPRICE`

- `days_since_event = None` → $s_{\text{post}} = \mathbf{0}$.

### 6.3 Pick the winner

```
HIGH_IV_EVENT       0.866   ← leader
HIGH_IV_PIN         0.352
LOW_IV_TREND        0.253
LOW_IV_RANGE        0.273
BREAKOUT            0.000
POST_EVENT_REPRICE  0.000
```

Margin to runner-up = `0.866 − 0.352 = 0.514` > `_TIE_DELTA = 0.10`.
No tie-break. Winner: **`HIGH_IV_EVENT`** at score `0.866`.

### 6.4 Generate tags

- `iv_rank = 0.80 ≥ 0.70` → `sell_vol_favorable`
- `days_to_next_event = 3 ≤ 14` → `event_in_3d`
- `days_since_event = None` → no `post_event_window`
- `|spot - max_pain|/spot = 0.03 > 0.005` → no `pin_risk`
- `breakout_signal = 0 < 0.70` → no `breakout_active`
- `trend_strength = 0.5`, neither ≥ 0.70 nor ≤ 0.30 → no `trending`/`ranging`
- `oi_concentration_at_max_pain = 0.3 < 0.60` → no `concentrated_oi_at_pin`

Final tags: `("sell_vol_favorable", "event_in_3d")`.

### 6.5 The `MarketStateResult`

```python
MarketStateResult(
    regime=Regime.HIGH_IV_EVENT,
    regime_score=0.866,
    all_scores={
        Regime.HIGH_IV_EVENT: 0.866,
        Regime.HIGH_IV_PIN:   0.352,
        Regime.LOW_IV_TREND:  0.253,
        Regime.LOW_IV_RANGE:  0.273,
        Regime.BREAKOUT:      0.000,
        Regime.POST_EVENT_REPRICE: 0.000,
    },
    tags=("sell_vol_favorable", "event_in_3d"),
    spot=100.0,
    iv_rank=0.80,
    # ... all 18 inputs echoed ...
    max_pain_delta_pct=-0.03,  # (97 − 100) / 100
)
```

The Strike Selector (M1.7) reads `regime = HIGH_IV_EVENT` plus tags, looks up
the regime's allowed-strategy whitelist (collar, sell_call_protective), then
queries the chain for strikes in the right delta band. The Recommendation
Engine (M1.8) picks one strategy, the Execution Feasibility Module (M1.11)
checks liquidity, the Confidence Composer (M1.10) blends `regime_score` with
flow alignment + structure alignment + signal alignment. The pipeline is
long; `classify()` is just step one.

---

## 7. Hands-on exercises

Solutions are at the end of this section. Don't peek.

### Exercise 1 — Predicate intuition

Without computing anything, predict the winner for each scenario. Note your
reasoning (one sentence is enough).

(a) `iv_rank = 0.20`, `trend_strength = 0.85`, no event, spot far from max_pain.

(b) `iv_rank = 0.65`, `spot = 100`, `max_pain = 100.2`, `dte_to_nearest_opex = 1`, no event.

(c) `iv_rank = 0.45`, `breakout_signal = 0.95`, no event.

(d) `iv_rank = 0.30`, `trend_strength = 0.05`, `realized_vs_implied = 1.0`.

### Exercise 2 — Hand-compute a tie

Construct an input vector where `HIGH_IV_EVENT` and `HIGH_IV_PIN` are within
`_TIE_DELTA = 0.10` of each other, and `HIGH_IV_PIN` scores higher
numerically. What does the engine return? Why?

### Exercise 3 — Sign-error replay

Plan §9.2's sketched `iv_crushed = max(0, 1 - iv_rank_change_1d / -20)`,
applied with `iv_rank_change_1d = -25` (a 25pp IV crush in `[0, 100]`
scale), gives what value? What value does the corrected formula give in the
`[0, 1]` engine scale (where `iv_rank_change_1d = -0.25`)?

### Exercise 4 — Tag emission

For the input
`spot=100, max_pain=100.4, iv_rank=0.75, days_to_next_event=10, days_to_nearest_opex=4, breakout_signal=0.8, trend_strength=0.85, oi_concentration_at_max_pain=0.7`,
list every tag the engine emits.

### Exercise 5 — Calibration tradeoff

The engine fixes `_HIGH_IV_EVENT_NEAR_DAYS = 7`. Suppose you change it to
`14`. Pick *two* of the 24 regime fixtures that would flip regime under the
new threshold. Justify each.

### Exercise 6 — Designing a 7th regime

Suppose your portfolio has a positive-carry overlay you want to turn off
during VIX spikes (cross-asset). Sketch:

(a) The new inputs needed (probably one new field).

(b) The predicate formula (one paragraph of pseudo-code).

(c) Where it fits in `_TIE_BREAK_PRIORITY`.

(d) What ADR section you'd extend and how many new fixture tests you'd
    write (per ADR-0002).

### Exercise 7 — Stress-test the property

The Hypothesis property test asserts `regime_score == all_scores[regime]`
within `1e-12`. Construct an input vector where naive floating-point
arithmetic could break that by more than `1e-12`. (Hint: the engine
explicitly uses the score from the chosen regime, not the leader's score.)

---

### Solutions

**E1.** (a) `LOW_IV_TREND` — low IV plus high trend dominates. (b)
`HIGH_IV_PIN` — mid IV plus tight pin plus near opex. (c) `BREAKOUT` —
breakout_signal nearly maxed and no other regime has a clear edge. (d)
`LOW_IV_RANGE` — low IV, low trend, realized matches implied.

**E2.** Set `iv_rank=0.80, days_to_next_event=7, spot=max_pain=100,
days_to_nearest_opex=0, realized_vs_implied=0.5, oi_concentration_at_max_pain=0.6`.
HIGH_IV_EVENT ≈ 0.866; HIGH_IV_PIN ≈ 0.952. Margin = 0.086 < 0.10. The
priority list places `HIGH_IV_EVENT` above `HIGH_IV_PIN`, so the engine
returns `regime = HIGH_IV_EVENT`. (This is the actual tie-break test in
[`test_classify_ties_resolve_to_higher_priority_event_over_pin`](../../packages/engine/tests/test_market_state_classify.py).)

**E3.** Sketched: `1 - (-25) / -20 = 1 - 1.25 = -0.25`, clipped to 0. A 25pp
crush gives `iv_crushed = 0` — opposite of intent. Corrected: `−(−0.25) /
0.20 = 1.25`, clipped to 1.0. ✔

**E4.** `sell_vol_favorable` (iv_rank ≥ 0.70), `event_in_10d` (≤ 14),
`pin_risk` (`|100−100.4|/100 = 0.004 ≤ 0.005` AND `dte=4 ≤ 5`),
`breakout_active` (≥ 0.70), `trending` (≥ 0.70), `concentrated_oi_at_pin`
(≥ 0.60). `post_event_window` not triggered (`days_since_event` is `None`).

**E5.** Two candidates from the 24:

- `test_classify_high_iv_event_earnings_in_3d` (3 days to event) — already
  inside both 7-day and 14-day windows; *no flip*. Pick another.
- A LOW_IV_RANGE fixture with `days_to_next_event=10`: under the wider
  threshold this would trigger HIGH_IV_EVENT's near_event term, and if
  `iv_rank` is even moderate the regime could flip. (None of the actual 24
  fixtures set `days_to_next_event` for non-event regimes — that's a
  design choice that would expose this calibration risk if relaxed.)
- A more honest answer: with `_HIGH_IV_EVENT_NEAR_DAYS = 14` and
  `iv_rank = 0.65 / days_to_next_event = 10`, `s_evt = 0.5·sigmoid(-0.5) + 0.5·1 ≈ 0.689`,
  potentially overtaking a LOW_IV_TREND fixture sitting near 0.5. The point of
  the exercise is recognizing that broadening the event window leaks into
  non-event regimes; the V1 calibration is conservative.

**E6.** Outline:

(a) Add `vix_change_1d: float | None` (or a more general `cross_asset_stress`).

(b) Predicate: $s_{\text{macro}} = \mathrm{clip}_{[0,1]}( \text{vix\_change\_1d} / 0.20 )$,
    active when |vix_change_1d| > 0.10 (10 pts).

(c) Above `BREAKOUT`, below `POST_EVENT_REPRICE` — a macro stress is more
    conservative than a single-name breakout but less specific than a
    just-resolved single-name event.

(d) Update ADR-0002 §"Adding a regime"; new Postgres enum value via
    Alembic migration; regenerate TS types; ≥ 4 new fixture tests; UI
    color in the regime palette.

**E7.** Naive arithmetic could compute `max(scores.values())` and use *that*
value when populating `regime_score`. If `max(scores.values()) = 0.86600001`
came from `HIGH_IV_PIN` but tie-break selected `HIGH_IV_EVENT` with
`scores[HIGH_IV_EVENT] = 0.866`, then `regime_score - all_scores[regime] =
0.86600001 - 0.866 = 1e-8 > 1e-12`. The engine guards against this by
returning `(candidate, scores[candidate])` from `_select_regime`, never
`(candidate, max_score)`.

---

## 8. Further reading

### Project artifacts

- Plan v1.2 §9.2 (per-regime predicate sketches), §22.3 (extended
  `classify()` signature), §22.5 (canonical formulas + `0.5` sentinel rule),
  §22.13 (Confidence Composer breakdowns).
- [ADR-0001](../decisions/0001-engine-first-architecture.md) — engine-first product framing.
- [ADR-0002](../decisions/0002-regime-taxonomy.md) — the six locked regimes.
- [ADR-0005](../decisions/0005-engine-pure-function-discipline.md) — pure-function discipline + SemVer-strict bumps.
- [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) — Phase 1.5 + Phase 2 enhancement adoption.

### Code

- [`packages/engine/engine/market_state/classify.py`](../../packages/engine/engine/market_state/classify.py) — the classifier.
- [`packages/engine/engine/market_state/`](../../packages/engine/engine/market_state) — every input primitive.
- [`packages/engine/engine/scoring/`](../../packages/engine/engine/scoring) — M1.4a `iv_score` / `structure_score` / `event_score`.
- [`packages/engine/engine/_utils.py`](../../packages/engine/engine/_utils.py) — `clip01` + `sigmoid`.
- [`packages/engine/tests/test_market_state_classify.py`](../../packages/engine/tests/test_market_state_classify.py) — 65 tests.

### External / academic

- Hull, *Options, Futures, and Other Derivatives* (10th+ ed.) — Black–Scholes,
  greeks, expected move (chapters 13–17).
- Natenberg, *Option Volatility and Pricing* — practitioner intuition for
  IV vs HV, vol surfaces, event premia.
- Sinclair, *Volatility Trading* — IV rank / percentile, premium-selling
  edge, regime-aware portfolio overlays.
- Wilder, *New Concepts in Technical Trading Systems* (1978) — original ADX
  derivation.
- Bollen and Whaley, *Does Net Buying Pressure Affect the Shape of Implied
  Volatility Functions?* (Journal of Finance, 2004) — empirical work on
  dealer flow / OI walls / pinning.

---

## 9. Glossary of symbols

| Symbol | Meaning |
|---|---|
| $S$ | Spot price of the underlying |
| $K$ | Option strike |
| $K^\*$ | Max-pain strike |
| $\sigma_{IV}$ | At-the-money implied volatility (annualized, decimal) |
| $\sigma_{HV}$ | 30-day annualized historical volatility (decimal) |
| $\tau$ | Days to expiration |
| $\text{EM}_{\$}$ | One-σ expected dollar move = $S \cdot \sigma_{IV} \cdot \sqrt{\tau/252}$ |
| $\text{EM}_{\%}$ | One-σ expected fractional move = $\sigma_{IV} \cdot \sqrt{\tau/252}$ |
| $\sigma(x)$ | Logistic sigmoid $1/(1+e^{-x})$ |
| $\mathrm{clip}_{[0,1]}(x)$ | Clip to closed unit interval |
| $\mathrm{IV\,rank}$ | Range-based, in $[0, 1]$ |
| $\mathrm{IV\,percentile}$ | Count-based, in $[0, 1]$ |
| $d_{\text{evt}}$ | `days_to_next_event` |
| $d_{\text{since\,evt}}$ | `days_since_event` |
| $d_{\text{opex}}$ | `days_to_nearest_opex` |
| $\Delta \mathrm{IV\,rank}_{1d}$ | One-day change of `iv_rank` in $[-1, 1]$ |
| $s_{\text{regime}}$ | Score of a per-regime predicate, in $[0, 1]$ |
| `_TIE_DELTA` | 0.10 — tie-band threshold |
| `_TIE_BREAK_PRIORITY` | Priority list, most-conservative-first |

---

*This tutorial is maintained alongside the engine. When `classify.py`,
`_utils.py`, or any of the input primitives change, the same PR updates
this file. Contributions welcome via the docs PR workflow described in
[`docs/README.md`](../README.md).*
