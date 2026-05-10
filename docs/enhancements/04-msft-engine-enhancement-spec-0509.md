# MSFT Option Engine — Enhancement Specification
**Base**: `00-02-02-long-msft-dev-plan.md` (MSFT Decision Engine v1.1)
**Reference analytics**: `00-01-02-option-strategy-os-phased-plan.md` (Options Trading OS)
**Author**: Claude Sonnet 4.6
**Date**: 2026-05-09
**Status**: Specification — awaiting approval before implementation

> **Educational disclaimer**: All analytics, signals, and outputs described in this document are for educational and research purposes only. They are not investment advice, not a recommendation to buy or sell any security or derivative, and not an automated trading system. Options trading involves substantial risk and is not suitable for all investors. Historical results do not guarantee future performance.

---

## 0. Executive Summary

The MSFT Decision Engine (v1.1) is an excellent foundation: engine-first, pure-function, decomposable confidence, outcome-tracked. However, compared to the analytics surface described in the Options Trading OS plan, it has significant analytical gaps that reduce its quality as a decision-support tool.

This document specifies **nine enhancement modules** in priority order. Each is self-contained, has a clear integration point with the existing engine, and is implementable in isolation without breaking the Phase 1 contract.

| # | Enhancement | Priority | Phase Fit | Effort |
|---|---|---|---|---|
| E1 | **GEX Module** — gamma exposure, gamma flip, call/put walls | P1 | Phase 1.5 | L |
| E2 | **Vol Surface & Skew Analytics** — term structure, 25d skew, IV smile | P1 | Phase 2 | M |
| E3 | **PnL Surface & Greeks Engine** — full visualization module | P1 | Phase 2 | L |
| E4 | **Earnings Expectation Gap Score** — overpricing score for MSFT | P2 | Phase 2 | M |
| E5 | **Realized vs. Implied Vol Premium** — HV/IV edge quantification | P2 | Phase 2 | S |
| E6 | **Multi-Expiry Strategy View** — term structure decision support | P2 | Phase 2-3 | M |
| E7 | **Historical Earnings Backtest** — strategy simulation across events | P2 | Phase 3 | XL |
| E8 | **Dividend-Aware Pricing** — correct American put treatment | P3 | Phase 3 | M |
| E9 | **Assignment Risk Module** — early assignment probability for short calls | P3 | Phase 3 | S |

**What is NOT in this document**: ML upgrades (Phase 4 in the base plan), brokerage integration, multi-ticker UI. Those are addressed by the base plan.

---

## 1. Enhancement E1 — GEX Module (Gamma Exposure)

### 1.1 Why the MSFT Engine Needs This

The base plan's Flow Score Engine uses a `dealer_gamma_proxy` (signed sum of gamma × OI × distance from spot) and a `gamma_score` (normalized 0-1 magnitude). These are **proxies**, not GEX. They produce a directional bias signal but cannot answer:
- "At what price level does dealer hedging behavior flip from stabilizing to amplifying?"
- "Which specific strikes have the largest OI-weighted gamma concentration?"
- "Is the resistance wall at $425 a meaningful GEX wall or just an OI spike?"

Without proper GEX, the Collar Builder and Recommendation Engine are making strike selections without gamma-aware context. A collar short call placed inside a call GEX wall will face systematic selling pressure from dealer delta-hedging on the way up — exactly what a long-term holder wants to avoid.

### 1.2 Core Formulas

**GEX per contract** (standard convention):
```
GEX_i = gamma_i × OI_i × 100 × spot²
```
- Calls: `GEX_i` is **positive** (dealers are long gamma; they sell into rallies, stabilizing)
- Puts: `GEX_i` is **negative** (dealers are short gamma; they buy into rallies, amplifying)

**Net GEX by strike**:
```
net_GEX(K) = GEX_call(K) + GEX_put(K)
```

**Total GEX** (aggregate dealer gamma exposure):
```
total_GEX = Σ_K net_GEX(K)
```

**Gamma Flip** (the spot level where total GEX crosses zero):
```
gamma_flip = interpolate zero-crossing of cumulative_GEX(K) over strikes K
```
If the market is below `gamma_flip`, dealer flows are amplifying (negative GEX). Above `gamma_flip`, flows are stabilizing (positive GEX).

**Call Wall** (dominant resistance zone):
```
call_wall = argmax_K [gamma_call(K)]   (among K > spot)
```

**Put Wall** (dominant support zone):
```
put_wall = argmax_K [abs(gamma_put(K))]   (among K < spot)
```

**GEX-to-EM Ratio** (how significant is the flip vs. expected move):
```
gex_em_ratio = |spot - gamma_flip| / expected_move
```
- < 0.5: flip is within half an expected move — high relevance to current trade
- 0.5–1.5: flip is within the expected range — moderate relevance
- > 1.5: flip is well beyond expected move — low immediate relevance

### 1.3 Module Specification

**Location**: `packages/engine/engine/gex/`

```python
# packages/engine/engine/gex/__init__.py

from decimal import Decimal
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class GexByStrike:
    strike: Decimal
    call_gex: float        # positive
    put_gex: float         # negative
    net_gex: float         # call_gex + put_gex
    call_oi: int
    put_oi: int
    call_gamma: float      # per-contract gamma from chain (or BS-computed)
    put_gamma: float

@dataclass(frozen=True)
class GexResult:
    gex_by_strike: list[GexByStrike]    # sorted ascending by strike
    total_gex: float                     # signed sum across all strikes
    gamma_flip: Decimal | None           # None if GEX never crosses zero
    gamma_flip_confidence: float         # 0..1; based on OI depth near flip
    call_wall: Decimal                   # strike with max call gamma (above spot)
    put_wall: Decimal                    # strike with max |put gamma| (below spot)
    call_wall_gex: float                 # magnitude at call wall
    put_wall_gex: float                  # magnitude at put wall
    gex_em_ratio: float                  # |spot - flip| / expected_move
    regime_tag: Literal[
        "positive_gex_stable",      # total_gex > 0; spot above flip; stabilizing
        "negative_gex_amplifying",  # total_gex < 0; spot below flip; amplifying
        "near_flip",                # spot within 0.5 × expected_move of flip
        "no_flip_detected",         # GEX never crosses zero in observed chain
    ]
    interpretation: str                  # 1-3 sentence educational explanation


def compute_gex(
    *,
    chain_snapshot: ChainSnapshot,
    spot: Decimal,
    expiry_focus: list[date],          # typically 1-2 nearest expiries with OI
    expected_move: float,              # as decimal fraction (e.g. 0.042 = 4.2%)
    gamma_source: Literal["chain", "bs_computed"] = "chain",
    # Use chain-provided gamma if available (Tradier/Polygon);
    # fall back to BS-computed gamma from chain IV when not available.
) -> GexResult:
    ...
```

**Algorithm**:

1. **Filter chain**: include only contracts in `expiry_focus` with `OI >= 50` and `bid > 0`.

2. **Gamma sourcing**:
   - If `gamma_source == "chain"` and `chain_row.gamma is not None`: use it directly.
   - Else: compute via `bs_greeks(spot, strike, dte_years, iv, r, q, kind)["gamma"]`.
   - Flag `gamma_source_quality: Literal["chain_provided", "bs_estimated"]` in `GexByStrike`.

3. **GEX computation per strike**:
   ```python
   for k in sorted_strikes:
       call_row = chain.lookup(expiry, k, "CALL")
       put_row  = chain.lookup(expiry, k, "PUT")
       call_gamma = resolve_gamma(call_row, spot, dte)
       put_gamma  = resolve_gamma(put_row, spot, dte)
       call_gex = call_gamma * call_row.oi * 100 * float(spot)**2
       put_gex  = -(put_gamma * put_row.oi * 100 * float(spot)**2)  # sign flip
       net_gex  = call_gex + put_gex
   ```

4. **Gamma Flip** via linear interpolation:
   ```python
   # cumulative GEX from lowest strike to highest
   cumulative = np.cumsum([row.net_gex for row in sorted_gex_by_strike])
   # find zero crossing
   sign_changes = np.where(np.diff(np.sign(cumulative)))[0]
   if len(sign_changes) == 0:
       gamma_flip = None
   else:
       i = sign_changes[0]
       x0, y0 = sorted_strikes[i], cumulative[i]
       x1, y1 = sorted_strikes[i+1], cumulative[i+1]
       gamma_flip = Decimal(str(x0 - y0 * (x1 - x0) / (y1 - y0)))
   ```

5. **Call Wall / Put Wall**:
   ```python
   above_spot = [row for row in gex_by_strike if row.strike > spot]
   below_spot = [row for row in gex_by_strike if row.strike < spot]
   call_wall = max(above_spot, key=lambda r: r.call_gex).strike
   put_wall  = max(below_spot, key=lambda r: abs(r.put_gex)).strike
   ```

6. **Regime tag**: compare `spot` to `gamma_flip`; compute `gex_em_ratio`.

7. **Gamma flip confidence**: fraction of total OI concentrated within ±2 strikes of the flip level.

### 1.4 Integration Points with Existing Engine

**Flow Score Engine** (`flow_score/__init__.py`):
- Replace the current `dealer_gamma_proxy` computation with a full `GexResult`.
- The `gamma_risk` field (currently from `gamma_score()`) should be derived from `gex_result.gex_em_ratio` and `gex_result.regime_tag`:
  ```python
  gamma_risk = clip01(1.0 - gex_result.gex_em_ratio)  # high when flip is near
  if gex_result.regime_tag == "negative_gex_amplifying":
      gamma_risk = clip01(gamma_risk + 0.20)  # amplifying regime adds risk
  ```

**Recommendation Engine** (`recommendation/rules.yaml`) — add GEX-aware rules:
```yaml
- id: avoid_short_call_inside_call_wall
  when:
    has_proposed_short_call: true
    proposed_short_call_distance_to_wall_pct_lte: 1.0   # within 1% of call wall
  emit: ADJUST_STRIKE_ABOVE_WALL
  rationale: "Short call at {{strike}} is within 1% of the call GEX wall at {{call_wall}}; dealer flows tend to suppress upside near this level, but assignment risk increases if spot breaks above"
  risks: ["Gamma wall may fail on high-volume breakout above {{call_wall}}"]
  invalidation: ["Call wall migrates above {{call_wall}} as expiry approaches"]

- id: widen_call_side_above_gamma_flip
  when:
    spot_above_gamma_flip: true
    gex_em_ratio_lte: 1.0
  emit: SELL_COVERED_CALL_WIDE
  rationale: "Spot is above the gamma flip ({{gamma_flip}}); dealer gamma flows are stabilizing but the flip is within expected move range"
  risks: ["If spot retreats below gamma flip, amplifying flows resume", "Wide strike reduces premium income"]
```

**Strike Selector** (`strike_selector/ranking.py`) — add GEX-aware score bonus:
```python
# Bonus for short calls positioned above call_wall (natural resistance)
if intent == "sell_call" and candidate.strike > gex_context.call_wall:
    yield_score += 0.10   # S/R alignment bonus
# Penalty for short calls between spot and call_wall (gets squeezed)
if intent == "sell_call" and spot < candidate.strike < gex_context.call_wall:
    yield_score -= 0.08
```

**Collar Builder** (`collar_builder/structures.py`) — GEX-aware short call selection:
```python
# Prefer call strikes at or above call_wall for the short leg of zero_cost/income collars
# This uses natural GEX resistance to support the cap level
if gex_context and candidate.strike >= gex_context.call_wall:
    tie_break_score += 0.15
```

**Confidence Composer** — GEX provides improved `structure_alignment`:
```python
# structure_alignment now incorporates GEX wall alignment score
gex_alignment = gex_wall_alignment_score(
    gex=gex_result,
    proposed_actions=rec.actions,
    spot=spot,
)
structure_alignment = 0.6 * base_structure + 0.4 * gex_alignment
```

### 1.5 New API Endpoint

```
POST /engine/gex
```

```python
class GexRequest(BaseModel):
    ticker: str = "MSFT"
    expiry_focus: list[date]           # 1-3 expiries; default: nearest 2
    as_of: datetime | None = None

# Response: GexResult (as defined in §1.3)
```

The existing `POST /engine/daily-plan` should include a `gex_context` field in the `DailyDecision` response (currently absent):

```python
class DailyDecision(BaseModel):
    ...
    gex_context: GexResult | None = None   # None in Phase 1 CSV-only mode
    ...
```

### 1.6 UI Components

**New screen**: `apps/web/app/gex/page.tsx` (already listed as Phase 2 drill-down in base plan)

```
<GexPage>
  <GexHeader>
    <GammaFlipCard flip={gex.gamma_flip} spot={spot} em_pct={expected_move_pct} />
    <RegimeTagBadge regime_tag={gex.regime_tag} />
    <WallsCard call_wall={gex.call_wall} put_wall={gex.put_wall} />
    <GexEmRatioCard ratio={gex.gex_em_ratio} />
  </GexHeader>

  <GexByStrikeChart
    data={gex.gex_by_strike}
    spot={spot}
    gamma_flip={gex.gamma_flip}
    call_wall={gex.call_wall}
    put_wall={gex.put_wall}
    // Stacked bar: green for call GEX, red for put GEX
    // Vertical lines at spot, gamma_flip, call_wall, put_wall
  />

  <CumulativeGexChart
    // Line chart of cumulative GEX by strike; zero line is gamma flip
    data={cumulative_gex_series}
    gamma_flip={gex.gamma_flip}
  />

  <GexInterpretationPanel text={gex.interpretation} />
  <DisclaimerFooter />
</GexPage>
```

**On Today screen**: add a `GexContextStrip` between `MarketStateBadge` and `ActionList`:
```
<GexContextStrip
  flip={gex.gamma_flip}
  regime_tag={gex.regime_tag}
  call_wall={gex.call_wall}
  put_wall={gex.put_wall}
  spot={spot}
/>
```
This is a single-line strip (not a full card): "Gamma flip: $408 | Call wall: $425 | Put wall: $395 | Regime: Stabilizing"

### 1.7 Tests

```
packages/engine/tests/test_gex.py
```
- **Hand-computed example**: chain with one ATM call (OI=100, gamma=0.02) and one ATM put (OI=100, gamma=0.02) at $410, spot=$410 → `call_gex = 0.02 × 100 × 100 × 168100 = 33,620,000`, `put_gex = -33,620,000`, `net_gex = 0`. Total GEX = 0, gamma_flip = spot.
- **Flip interpolation**: chain where cumulative GEX is positive below $405 and negative above $415 → flip should be interpolated between those strikes.
- **Call wall / put wall identification**: chain with a large OI spike at $425 calls → `call_wall = 425`.
- **Property**: `total_gex == sum(row.net_gex for row in gex_by_strike)`.
- **Property**: `call_wall > spot`, `put_wall < spot` (when chain has OI on both sides).
- **BS gamma fallback**: when chain has `gamma=None`, BS-computed gamma produces a result within 10% of a chain-provided reference value.
- **Regime tag**: for each of the 4 regime tags, a fixture that produces it.
- **Integration with Flow Score**: a `FlowScore` computed with a GEX context with `negative_gex_amplifying` regime has higher `gamma_risk` than one with `positive_gex_stable`.

---

## 2. Enhancement E2 — Volatility Surface & Skew Analytics

### 2.1 Why This Matters

The base plan's Market State Engine uses a single `atm_iv_30d` value for IV rank/percentile and a single `expected_move_pct`. This flattens the vol surface to a scalar, losing:

- **Term structure**: Is near-term IV higher than far-term? (inverted = fear; normal = calm)
- **Skew**: Are puts pricing more fear premium than calls? (25-delta put IV minus 25-delta call IV)
- **Smile**: How does IV change across strikes? (affects whether GEX walls have true premium support)
- **Vol premium**: How much is implied vol exceeding realized (HV) — the core edge for covered call sellers

For Helen (the primary persona holding 5,000 MSFT shares), understanding whether 30d IV > 60d IV (inverted — sell near-term premium now) vs. 30d IV < 60d IV (normal — wait or sell further out) is directly actionable.

### 2.2 Module Specification

**Location**: `packages/engine/engine/vol_surface/`

```python
@dataclass(frozen=True)
class TermStructurePoint:
    expiry: date
    dte: int
    atm_iv: float           # ATM constant-maturity IV for this expiry
    iv_rank_vs_52w: float   # rank of this expiry's IV vs. its own 52-week range
    vol_premium: float      # atm_iv - hv_matched_dte (IV over realized)

@dataclass(frozen=True)
class SkewPoint:
    expiry: date
    delta_25_put_iv: float
    delta_25_call_iv: float
    skew_25d: float         # put_iv - call_iv; positive = fear skew
    risk_reversal_25d: float  # same as skew_25d by convention

@dataclass(frozen=True)
class IvSmilePoint:
    strike: Decimal
    iv: float
    delta: float

@dataclass(frozen=True)
class VolSurfaceResult:
    term_structure: list[TermStructurePoint]    # sorted by dte
    skew_by_expiry: list[SkewPoint]
    atm_iv_30d: float
    atm_iv_60d: float
    hv_30: float
    hv_60: float
    vol_premium_30d: float    # atm_iv_30d - hv_30
    vol_premium_60d: float    # atm_iv_60d - hv_60
    term_structure_slope: Literal[
        "normal",           # iv_30d < iv_60d (upward sloping)
        "flat",             # |iv_30d - iv_60d| < 0.01
        "inverted",         # iv_30d > iv_60d (near-term fear / event risk)
        "humped",           # near-term > mid > far  (sell near, carry far)
    ]
    sell_vol_recommendation: str  # educational; which expiry looks richest
    interpretation: str


def compute_vol_surface(
    *,
    chain_snapshot: ChainSnapshot,
    spot: Decimal,
    iv_history: IvHistory,
    hv_history: HvHistory,
) -> VolSurfaceResult:
    ...
```

**25-delta strike interpolation** (for skew when exact 25d option not in chain):
```python
def interpolate_25d_strike(chain_rows: list[ChainRow], target_delta: float) -> float:
    # Linear interpolation between nearest strikes by |delta - target_delta|
    sorted_by_dist = sorted(chain_rows, key=lambda r: abs(abs(r.delta) - target_delta))
    r0, r1 = sorted_by_dist[0], sorted_by_dist[1]
    w = (target_delta - abs(r0.delta)) / (abs(r1.delta) - abs(r0.delta) + 1e-9)
    return r0.iv * (1 - w) + r1.iv * w
```

### 2.3 Integration with Existing Engine

**Market State Engine** — extend `MarketStateResult` with vol surface context:
```python
@dataclass(frozen=True)
class MarketStateResult:
    ...
    vol_surface: VolSurfaceResult | None   # None in CSV-only Phase 1 (chain may lack IV)
    vol_premium_tag: Literal["rich", "fair", "cheap"] | None
```

**`iv_score()` scoring function** — currently takes `iv_rank`, `iv_percentile`, `hv_30`, `atm_iv_30d`. Enhance to accept full vol surface:
```python
def iv_score(
    *,
    iv_rank: float,
    iv_percentile: float,
    hv_30: float,
    atm_iv_30d: float,
    # New:
    vol_premium_30d: float | None = None,
    term_structure_slope: str | None = None,
) -> IvScoreResult:
    base = 0.40 * iv_rank + 0.30 * iv_percentile + 0.30 * normalize(vol_premium_30d or 0, [-0.05, 0.10])
    # Bonus for inverted term structure (near-term premium elevated — sell near-term)
    if term_structure_slope == "inverted":
        base = clip01(base + 0.05)
    ...
```

**Recommendation Engine** — add term-structure-aware DTE selection:
```python
# In rules.yaml, add:
- id: prefer_near_term_when_inverted
  when: { vol_surface.term_structure_slope: "inverted", iv_rank_gte: 45 }
  hint: "Near-term IV elevated vs. far; prefer 21-45 DTE over 45-60 DTE"
  # Adjusts profile.dte_band_days[1] downward for this decision cycle
```

### 2.4 New API Endpoint

```
POST /engine/vol-surface
```

**UI**: `apps/web/app/iv/page.tsx` (Phase 2 drill-down in base plan) — enhanced with:
- Term structure line chart (x=DTE, y=ATM IV per expiry)
- Skew chart (x=delta, y=IV per expiry — the "smile")
- Vol premium bar (ATM IV vs. HV_30 vs. HV_60)
- Slope badge with color: inverted=amber, normal=green, flat=slate, humped=violet

---

## 3. Enhancement E3 — PnL Surface & Greeks Engine

### 3.1 Why This Matters

The base plan has a payoff module (`packages/engine/engine/payoff/`) that provides `terminal_pl()` (at expiration) and `combined_greeks()` (at current DTE). But the Today screen shows **no PnL visualization at all in Phase 1** — the collar structure is presented as a text action list without any chart.

For Helen reviewing a recommended collar or roll at end of day:
- "If MSFT gaps up 6% after earnings, what does my P&L look like mid-expiry?"
- "What's my theta decay profile — am I earning theta daily or is it clustered at expiry?"
- "If IV crushes 30% after earnings, what happens to my short call value?"

These questions are answered by a PnL surface (price × IV × DTE), not just terminal P&L.

### 3.2 Module Specification

**Location**: `packages/engine/engine/payoff/surface.py` (extends existing `payoff/`)

```python
@dataclass(frozen=True)
class PnLByPriceResult:
    spot_grid: list[float]      # x-axis: spot prices
    pnl_at_expiry: list[float]  # terminal P&L at expiration
    pnl_today: list[float]      # current theoretical value vs. cost basis
    breakeven_lower: float | None
    breakeven_upper: float | None
    max_gain: float | None      # None for unlimited gain
    max_loss: float             # always defined for defined-risk structures

@dataclass(frozen=True)
class PnLSurfaceResult:
    spot_grid: list[float]    # shape: (n_spots,)
    iv_grid: list[float]      # shape: (n_ivs,); as decimal (0.25 = 25%)
    pnl_matrix: list[list[float]]  # shape: (n_spots, n_ivs); P&L at DTE_eval
    dte_eval: int              # DTE at which surface is evaluated
    current_iv: float          # reference IV for "today" slice
    breakeven_lower: float | None
    breakeven_upper: float | None

@dataclass(frozen=True)
class ScenarioTableResult:
    scenarios: list[ScenarioRow]

@dataclass(frozen=True)
class ScenarioRow:
    label: str
    spot_change_pct: float
    iv_change_pct: float
    days_forward: int
    spot_after: float
    iv_after: float
    pnl: float
    pnl_pct: float


def pnl_by_price(
    *,
    legs: list[Leg],
    spot: float,
    dte_years: float,
    iv: float,
    r: float,
    q: float,
    spot_range_pct: float = 0.20,   # ±20% around spot
    n_points: int = 100,
) -> PnLByPriceResult:
    spot_grid = np.linspace(spot * (1 - spot_range_pct), spot * (1 + spot_range_pct), n_points)
    pnl_today = [sum(theoretical_value(leg, s, dte_years, iv, r, q) - leg.cost_basis * 100
                     for leg in legs) for s in spot_grid]
    pnl_expiry = terminal_pl(legs, spot_grid, at=expiry_date).tolist()
    ...


def pnl_surface(
    *,
    legs: list[Leg],
    spot: float,
    dte_years: float,
    current_iv: float,
    r: float,
    q: float,
    spot_range_pct: float = 0.20,
    iv_range: tuple[float, float] = (0.10, 0.60),  # IV grid bounds
    n_spots: int = 50,
    n_ivs: int = 20,
    dte_eval_days: int = 1,            # evaluate at this DTE (1 = day-after for earnings)
) -> PnLSurfaceResult:
    ...


def scenario_table(
    *,
    legs: list[Leg],
    spot: float,
    dte_years: float,
    current_iv: float,
    r: float,
    q: float,
    scenarios: list[dict] | None = None,  # None → use MSFT_DEFAULT_SCENARIOS
) -> ScenarioTableResult:
    ...


MSFT_DEFAULT_SCENARIOS = [
    {"label": "IV Crush 30% (no move)",          "spot_pct": 0.00,  "iv_pct": -0.30, "days": 1},
    {"label": "Earnings beat +6% + IV crush",     "spot_pct": +0.06, "iv_pct": -0.25, "days": 1},
    {"label": "Earnings miss −6% + IV crush",     "spot_pct": -0.06, "iv_pct": -0.20, "days": 1},
    {"label": "Trend +3% over 7d",                "spot_pct": +0.03, "iv_pct": -0.05, "days": 7},
    {"label": "Trend −3% over 7d",                "spot_pct": -0.03, "iv_pct": +0.02, "days": 7},
    {"label": "Theta decay, 14d (no move)",       "spot_pct": 0.00,  "iv_pct": 0.00,  "days": 14},
    {"label": "Breakout +5% + vol expansion",     "spot_pct": +0.05, "iv_pct": +0.05, "days": 2},
]
```

### 3.3 Integration Points

**Today Screen** — add a `PayoffPreviewStrip` below `ActionList`:
```
<PayoffPreviewStrip
  pnl_by_price={...}              // lightweight version: 3 key points only
  key_scenarios={scenario_table}  // top 3 scenarios from default set
  collar_or_strategy={rec.strategy}
/>
```

The strip shows: `Max gain: +$X | Breakeven: $Y | Max loss: −$Z | Post-earnings IV crush: −$W`

Full `/payoff` drill-down page (Phase 2 in base plan) adds the 3D surface and scenario table.

**Collar Builder** — include `pnl_by_price` and `scenario_table` in `CollarStructure` response:
```python
class CollarStructure(BaseModel):
    ...
    pnl_by_price: PnLByPriceResult           # add to existing schema
    key_scenarios: ScenarioTableResult       # 7-row MSFT default table
```

**What-If endpoint** — currently returns a full `DailyDecision`. Add:
```python
class WhatIfRequest(BaseModel):
    ticker: str
    overrides: dict
    include_pnl_surface: bool = False   # opt-in; adds ~100ms compute
```

### 3.4 UI Components

```
<PayoffPage>
  <PnLByPriceChart
    pnl_expiry={...}
    pnl_today={...}
    spot={spot}
    breakeven_lower breakeven_upper
    // Two lines: terminal (solid) + current theoretical (dashed)
    // X-axis: spot price; Y-axis: P&L in dollars
    // Shaded gain region (green) / loss region (red)
  />

  <PnLSurface3D
    pnl_matrix={...}
    spot_grid={...}
    iv_grid={...}
    current_iv={current_iv}
    // Plotly Surface3D; axes: spot, IV, P&L
    // Annotation at current_iv slice
  />

  <ScenarioTable
    scenarios={scenario_table.scenarios}
    // Color-coded P&L column: green positive, red negative
  />

  <GreeksCurves
    // Four panels: delta, gamma, vega, theta vs. spot
    // Overlay at current spot with annotation
  />
</PayoffPage>
```

---

## 4. Enhancement E4 — Earnings Expectation Gap Score

### 4.1 Why This Matters

The MSFT engine has no overpricing/underpricing signal for earnings events. The Flow Score tells you directional bias. The Market State tells you regime. But neither answers: "Is the market pricing this earnings event at a premium vs. history, or is IV unusually cheap?"

This matters to Helen because:
- If IV is inflated (overpriced event), selling the call in a collar is attractive — she collects more premium
- If IV is cheap (underpriced), buying protection (long put in a collar) is cheap — but selling the call is less attractive
- If the earnings expectation gap is extreme (heavy bullish positioning, high IV, big run-up), it signals crowded consensus risk

### 4.2 Module Specification

**Location**: `packages/engine/engine/scoring/earnings_gap.py`

```python
@dataclass(frozen=True)
class EarningsGapScore:
    score: float               # 0..1; higher = potential overpricing / crowded expectations
    iv_rank_contrib: float     # component contributions (for breakdown)
    vol_premium_contrib: float
    runup_30d_contrib: float
    call_volume_contrib: float
    pcr_contrib: float
    weights_version: str
    interpretation: str        # educational; no forbidden phrases
    regime_context: Literal[
        "potential_vol_overpricing",    # score > 0.7
        "neutral_expectations",         # score 0.4–0.7
        "potential_vol_underpricing",   # score < 0.4
    ]


def earnings_gap_score(
    *,
    iv_rank: float,              # [0, 1]
    vol_premium_30d: float,      # atm_iv_30d - hv_30 (can be negative)
    runup_30d: float,            # spot / spot_30d_ago - 1 (e.g. +0.08 = +8%)
    call_volume_ratio: float,    # today's call volume / 20-day avg call volume
    put_call_ratio: float,       # total put volume / total call volume
    weights: EarningsGapWeights | None = None,
) -> EarningsGapScore:
    w = weights or DEFAULT_EARNINGS_GAP_WEIGHTS

    iv_norm           = clip01(iv_rank)
    vol_prem_norm     = clip01(normalize(vol_premium_30d, [-0.05, 0.15]))
    runup_norm        = clip01(normalize(abs(runup_30d) * sign_boost(runup_30d), [-0.20, 0.20]))
    call_vol_norm     = clip01(normalize(max(call_volume_ratio - 1.0, 0), [0, 2.0]))
    pcr_norm          = clip01(1 - normalize(put_call_ratio, [0.5, 1.5]))  # low PCR = call heavy

    score = (
        w.w_iv_rank    * iv_norm +
        w.w_vol_prem   * vol_prem_norm +
        w.w_runup      * runup_norm +
        w.w_call_vol   * call_vol_norm +
        w.w_pcr        * pcr_norm
    )
    score = clip01(score)
    ...


DEFAULT_EARNINGS_GAP_WEIGHTS = EarningsGapWeights(
    w_iv_rank  = 0.30,    # IV rank is the most direct measure of vol pricing
    w_vol_prem = 0.25,    # IV over realized = the actual premium sold
    w_runup    = 0.20,    # pre-earnings run-up = speculative positioning risk
    w_call_vol = 0.15,    # call volume surge = retail FOMO
    w_pcr      = 0.10,    # low PCR = bullish tilt
    version    = "v1.0"
)
```

**`sign_boost(runup_30d)`**: Returns 1.0 for positive run-up (bullish crowding) and 0.6 for negative run-up (the market is already pricing in the miss, less crowding risk). This prevents symmetry bias — a -8% drawdown before earnings is not the same crowding signal as a +8% run-up.

### 4.3 Integration with Existing Engine

Add `earnings_gap: EarningsGapScore | None` to `MarketState`:
- Populated only when `days_to_next_event <= 14` and `next_event_kind == "earnings"`
- Used by the Confidence Composer: `event_risk_penalty` is now `max(event_score, earnings_gap.score)` when both are available

**New Recommendation Rule**:
```yaml
- id: high_earnings_gap_sell_premium
  when:
    earnings_gap.score_gte: 0.70
    iv_rank_gte: 50
    days_to_next_event_lte: 14
    days_to_next_event_gte: 5
  emit: SELL_COVERED_CALL_PARTIAL
  rationale: "Earnings expectation gap score {{earnings_gap.score:.2f}} suggests elevated vol premium; near-term covered call harvests this edge before IV crush"
  risks: ["Earnings surprise beyond expected move creates assignment risk", "Score is a composite heuristic, not a probability estimate"]

- id: low_earnings_gap_buy_protection
  when:
    earnings_gap.score_lte: 0.35
    days_to_next_event_lte: 10
  emit: OPEN_COLLAR
  rationale: "Earnings expectation gap score {{earnings_gap.score:.2f}} suggests relatively inexpensive vol; long put protection is more favorably priced"
  risks: ["Low IV can remain low; the score does not predict direction"]
```

---

## 5. Enhancement E5 — Realized vs. Implied Vol Premium Tracker

### 5.1 Specification

This is a lightweight module but provides Helen with a key edge metric: the sustained differential between what she's selling (ATM IV) and the actual realized vol of her MSFT shares.

**Location**: `packages/engine/engine/scoring/vol_premium.py`

```python
@dataclass(frozen=True)
class VolPremiumResult:
    iv_atm_30d: float
    hv_30: float
    vol_premium_30d: float       # iv - hv; positive = selling edge
    iv_atm_60d: float
    hv_60: float
    vol_premium_60d: float
    trailing_12m_avg_premium: float   # average over last 252 trading days
    premium_percentile: float         # current premium vs. trailing 12m distribution
    tag: Literal[
        "rich_premium",        # premium > 75th percentile of trailing 12m
        "fair_premium",        # 25th–75th percentile
        "thin_premium",        # < 25th percentile (selling is less attractive)
        "negative_premium",    # IV < HV (unusual; market underpricing realized vol)
    ]
    interpretation: str


def compute_vol_premium(
    *,
    iv_history: IvHistory,        # 252 trading days
    hv_history: HvHistory,
) -> VolPremiumResult:
    current_premium_30d = iv_history.latest.atm_iv_30d - hv_history.latest.hv_30
    historical_premiums  = [iv.atm_iv_30d - hv.hv_30 for iv, hv in zip(iv_history.all, hv_history.all)]
    trailing_avg         = np.mean(historical_premiums)
    percentile           = np.mean([p < current_premium_30d for p in historical_premiums]) * 100
    ...
```

**Integration**: `iv_score()` scoring function incorporates `premium_percentile` as an additional weight factor. The vol premium trend (improving vs. deteriorating) is surfaced in the `MarketStateBadge` on the Today screen as a secondary tag.

---

## 6. Enhancement E6 — Multi-Expiry Strategy View

### 6.1 Why This Matters

The base plan optimizes the collar and covered call for a single "focus expiry" (from `profile.dte_band_days`). But for a long-term holder like Helen, there's a genuine multi-expiry question:

- **Stagger coverage**: sell 30d calls now for near-term premium, AND sell 60d calls for more premium — different strikes, different expirations, partial coverage each
- **Ladder rolls**: as near-term expires, roll into next expiry maintaining coverage continuity
- **Event-aware selection**: if earnings is in 3 weeks and monthly expiry is in 4 weeks, should she use the weekly (before earnings) or monthly (after earnings)?

### 6.2 Specification

**Location**: `packages/engine/engine/multi_expiry/`

```python
@dataclass(frozen=True)
class ExpiryCandidate:
    expiry: date
    dte: int
    atm_iv: float
    event_in_window: bool          # is there an earnings/FOMC between now and expiry?
    event_kind: str | None
    days_to_event: int | None
    annualized_premium_pct: float  # for the best strike in this expiry / profile
    coverage_delta: float          # coverage this expiry provides (0-1 of underlying)
    risk_tier: Literal["pre_event", "post_event", "clean"]

@dataclass(frozen=True)
class MultiExpiryPlan:
    recommended_primary: ExpiryCandidate
    recommended_secondary: ExpiryCandidate | None   # for stagger if coverage < max
    total_coverage: float
    total_annualized_premium_pct: float
    event_exposure_warning: str | None
    rationale: list[str]


def plan_multi_expiry(
    *,
    chain_snapshot: ChainSnapshot,
    spot: Decimal,
    profile: UserStrategyProfile,
    events: list[Event],
    gex_context: GexResult | None,
) -> MultiExpiryPlan:
    ...
```

**Algorithm**:
1. Enumerate available expiries from chain (those with meaningful OI).
2. For each expiry, check if any event falls within its window.
3. Score expiries by: IV richness, event alignment (pre-event IV is richer), coverage-DTE tradeoff.
4. Select primary as the richest expiry within `profile.dte_band_days` that passes liquidity filters.
5. If `coverage_after_primary < profile.max_coverage × 0.7`, propose a secondary expiry to stagger.

**Integration**: `POST /engine/multi-expiry` — new endpoint. Also surfaced in the `CollarBuilder` as an optional "staggered collar" structure type.

---

## 7. Enhancement E7 — Historical Earnings Backtest for MSFT

### 7.1 Why This Matters

The base plan defers backtesting to Phase 4+ as an ML input. But for Helen's decision-making, even a simple historical backtest answers a critical question: "Over the last 10 MSFT earnings events, did the collar/covered call strategy produce positive PnL? What were the worst-case misses?"

This is not ML. It is a straightforward simulation:
- Fetch or load MSFT earnings dates
- For each event: snapshot pre-earnings chain, apply strategy template, mark on earnings day + 1
- Aggregate realized move vs. implied move, strategy PnL, and regime classification

### 7.2 Specification

**Location**: `packages/engine/engine/backtest/`

```python
@dataclass(frozen=True)
class EarningsEventResult:
    event_date: date
    pre_spot: Decimal
    post_spot: Decimal
    realized_move_pct: float
    implied_move_pct: float           # from pre-earnings ATM straddle
    iv_before: float
    iv_after: float | None
    iv_crush_pct: float | None
    strategy: str                     # e.g. "SELL_COVERED_CALL_PARTIAL"
    strategy_pnl: float               # simulated P&L in dollars
    strategy_pnl_pct: float           # as pct of max risk
    outcome_quality: Literal["win", "breakeven", "loss"]
    regime_actual: str | None         # what regime was it in practice?
    notes: str

@dataclass(frozen=True)
class BacktestSummary:
    ticker: str
    strategy: str
    events: list[EarningsEventResult]
    n_events: int
    win_rate: float
    avg_pnl_pct: float
    worst_loss_pct: float
    best_gain_pct: float
    avg_implied_move: float
    avg_realized_move: float
    implied_vs_realized_ratio: float    # > 1 means implied typically overstates realized
    data_quality_caveat: str            # always present
    disclaimer: str                     # always present


def backtest_earnings(
    *,
    ticker: str,
    earnings_events: list[EarningsEvent],     # from CSV or provider
    strategy_template: str,                   # "SELL_COVERED_CALL_PARTIAL", "OPEN_COLLAR", etc.
    profile: UserStrategyProfile,
    chain_source: Literal["manual_csv", "yfinance", "polygon"],
    exit_rule: Literal["on_expiry", "day_after_earnings"] = "day_after_earnings",
) -> BacktestSummary:
    ...
```

**Entry timing**: Close of last session before the earnings announcement.
**Exit timing**: Close of first session after earnings (for day-after exit) or expiry (for hold-to-expiry).
**IV sourcing**: Use available chain IV; if absent, BS-impute from ATM straddle mid.
**Strike selection**: Apply the same Strike Selector algorithm used in live recommendations, parameterized for the pre-event date.

**Data quality caveat** (always injected, non-optional):
> "Simulated results use historical option prices which may be incomplete, delayed, or reconstructed. Actual fills would have differed due to bid/ask spreads, market impact, and liquidity. This backtest does not account for taxes, commissions, or early assignment risk. Historical results do not predict future performance."

### 7.3 API Endpoint

```
POST /engine/backtest-earnings
```

This is an async endpoint (given potentially large date ranges). Response:
```json
{
  "run_id": "bt_2026_04_29_msft_collar",
  "status": "queued",       // or "completed" if fast enough
  "poll_url": "/engine/backtest-runs/bt_2026_04_29_msft_collar"
}
```

**Not Celery in Phase 1** (base plan consolidates jobs into API for Phase 1). Use `asyncio.gather` with await for the backtest — acceptable if MSFT has ~16 earnings events per 4-year lookback.

---

## 8. Enhancement E8 — Dividend-Aware Pricing

### 8.1 The Current Gap

The base plan hardcodes `q = 0.0075` (MSFT annual dividend yield) as a constant in the payoff module. MSFT's dividend schedule is:
- **Quarterly**: typically ~$0.83/share (as of early 2026), ex-dividend dates in late February, May, August, November
- The dividend yield varies with the stock price; at $400/share, $3.32/year = 0.83%
- For **short-dated options** (14-21 DTE), the proximity of the ex-dividend date significantly affects early assignment risk on short calls

Using a flat annual yield:
- Overstates option value before ex-dividend (because dividend not yet captured)
- Understates early assignment risk on short calls in the days before ex-dividend

### 8.2 Specification

**Location**: `packages/engine/engine/payoff/dividend.py`

```python
@dataclass(frozen=True)
class DividendSchedule:
    ticker: str
    quarterly_amount: Decimal        # per share
    upcoming_ex_dates: list[date]    # next 4 quarters

@dataclass(frozen=True)
class DividendContext:
    next_ex_date: date | None
    days_to_ex: int | None
    dividend_amount: Decimal | None
    within_ex_window: bool           # ex-date is within option's DTE
    yield_for_period: float          # continuous equivalent yield for this DTE


def bs_price_dividend_aware(
    spot: float,
    strike: float,
    dte_years: float,
    iv: float,
    r: float,
    dividend_schedule: DividendSchedule,
    kind: Literal["call", "put"],
) -> float:
    # Use discrete dividend model (Merton with cash dividend):
    # Reduce spot by PV of dividends within the option's lifetime
    div_context = _dividend_context(dividend_schedule, dte_years)
    if div_context.within_ex_window:
        pv_dividend = float(div_context.dividend_amount) * math.exp(-r * div_context.days_to_ex / 365)
        adjusted_spot = spot - pv_dividend
    else:
        adjusted_spot = spot
        pv_dividend = 0
    return bs_price(adjusted_spot, strike, dte_years, iv, r, q=0, kind=kind)
```

**Early assignment risk** for short calls (informational, not a hard rule):

```python
def early_assignment_risk_score(
    *,
    short_call_strike: Decimal,
    spot: Decimal,
    days_to_ex: int | None,
    dividend_amount: Decimal | None,
    bid: Decimal,
) -> float:
    """
    Returns 0..1; higher = more risk of early assignment before ex-dividend.
    Rule: assignment is rational when dividend > time value of the call.
    time_value = call_bid - max(0, spot - strike)
    assignment_incentive = dividend > time_value
    """
    if days_to_ex is None or days_to_ex > 10 or dividend_amount is None:
        return 0.0
    intrinsic = max(0, float(spot - short_call_strike))
    time_value = max(0, float(bid) - intrinsic)
    incentive = float(dividend_amount) - time_value
    return clip01(incentive / float(dividend_amount))
```

**Integration**: 
- `bs_price_dividend_aware()` replaces `bs_price()` in Strike Selector when computing delta for near-ex-date options
- `early_assignment_risk_score()` added to `Execution.size_warnings` for short calls within 10 days of an ex-dividend date

---

## 9. Enhancement E9 — Assignment Risk Module

### 9.1 The Current Gap

The base plan's Execution Feasibility Module computes fill confidence and slippage but does not model **assignment risk** for short calls. For Helen:
- She has 5,000 shares with a $400 cost basis
- If she's short 50 calls at $415 and MSFT rallies to $420, those calls may be assigned
- Assignment would deliver away 5,000 shares, triggering a large capital gain — potentially a tax disaster

### 9.2 Specification

**Location**: `packages/engine/engine/assignment/`

```python
@dataclass(frozen=True)
class AssignmentRiskResult:
    probability_of_assignment: float      # estimated [0, 1]
    delta_at_current_spot: float          # call delta ≈ P(ITM at expiry)
    days_to_expiry: int
    moneyness_pct: float                  # (spot - strike) / strike
    ltcg_lots_at_risk: list[LotAtRisk]    # which lots would be assigned
    tax_sensitivity_warning: str | None   # if profile.tax_sensitivity != "none"
    mitigation_options: list[str]         # "Roll up and out", "Buy to close", etc.


@dataclass(frozen=True)
class LotAtRisk:
    lot_id: uuid
    qty: int
    cost_basis: Decimal
    opened_at: datetime
    ltcg_eligible_at: datetime
    is_ltcg: bool                          # opened > 366 days ago
    gain_if_assigned: Decimal


def assess_assignment_risk(
    *,
    short_calls: list[OptionPosition],
    positions: list[Position],
    lots: list[Lot],
    spot: Decimal,
    profile: UserStrategyProfile,
    dividend_context: DividendContext | None,
) -> list[AssignmentRiskResult]:
    ...
```

**Lot selection heuristic** (which lots would be assigned):
- Default: FIFO (oldest lots first) — this preserves LTCG-eligible lots longest
- `ltcg_aware` profile: SHORT-LAST (deliver short-term lots first to preserve LTCG)
- Implementer note: tax lot selection is the user's broker's decision, not the engine's — the engine provides the analysis; the user decides. Always disclaim.

**Integration**:
- `AssignmentRiskResult` added to `Execution.notes` when `probability_of_assignment > 0.30`
- For `profile.tax_sensitivity in ["ltcg_aware", "wash_sale_aware"]`, assignment risk appears in the `risks[]` array on the `DailyDecision`
- A `AssignmentRiskCard` appears on the Today screen when any open short call has `probability_of_assignment > 0.40`

---

## 10. Integration Architecture: How Enhancements Connect to the Base Engine

### 10.1 Revised Engine Data Flow

```
EngineInputs
  ├── ChainSnapshot          (existing)
  ├── IvHistory              (existing)
  ├── HvHistory              (existing)
  ├── EarningsEvents         (existing)
  ├── Positions + Lots       (existing)
  ├── UserStrategyProfile    (existing)
  └── DividendSchedule       (NEW — E8)

                ↓

Layer 1: Scoring Primitives (independent, pure functions)
  ├── iv_score()             (existing + vol_premium enhancement — E5)
  ├── structure_score()      (existing + GEX alignment — E1)
  ├── gamma_score()          (existing → REPLACE with GexResult.gex_em_ratio — E1)
  ├── event_score()          (existing)
  ├── earnings_gap_score()   (NEW — E4)
  └── vol_surface_compute()  (NEW — E2)

                ↓

Layer 2: Core Engines (use Layer 1 outputs)
  ├── MarketState Engine     (enhanced: GexResult, VolSurfaceResult, EarningsGapScore)
  ├── Flow Score Engine      (enhanced: GexResult replaces dealer_gamma_proxy)
  ├── Strike Selector        (enhanced: GEX-aware ranking — E1)
  ├── Recommendation Engine  (enhanced: GEX-aware rules + earnings gap rules — E1, E4)
  ├── Collar Builder         (enhanced: GEX strike selection + staggered collars — E1, E6)
  ├── Multi-Expiry Planner   (NEW — E6)
  └── Assignment Risk        (NEW — E9)

                ↓

Layer 3: Confidence Composer (unchanged interface; GEX sharpens structure_alignment)

                ↓

Layer 4: Execution Feasibility (enhanced: dividend-aware assignment risk — E8, E9)

                ↓

Layer 5: Master Decision Engine
  DailyDecision now includes:
  ├── gex_context: GexResult           (NEW)
  ├── vol_surface: VolSurfaceResult    (NEW)
  ├── earnings_gap: EarningsGapScore   (NEW, when event_in_14d)
  ├── multi_expiry: MultiExpiryPlan    (NEW)
  └── pnl_preview: PnLByPriceResult   (NEW — lightweight terminal P&L for Today screen)
```

### 10.2 New API Endpoints Summary

| Method | Path | Returns | Priority |
|---|---|---|---|
| POST | `/engine/gex` | `GexResult` | E1 (high) |
| POST | `/engine/vol-surface` | `VolSurfaceResult` | E2 (high) |
| POST | `/engine/pnl-surface` | `PnLSurfaceResult` | E3 (high) |
| POST | `/engine/pnl-by-price` | `PnLByPriceResult` | E3 (high) |
| POST | `/engine/scenario-table` | `ScenarioTableResult` | E3 (high) |
| POST | `/engine/earnings-gap` | `EarningsGapScore` | E4 (medium) |
| POST | `/engine/multi-expiry` | `MultiExpiryPlan` | E6 (medium) |
| POST | `/engine/backtest-earnings` | `{ run_id, status, poll_url }` | E7 (medium) |
| GET  | `/engine/backtest-runs/{id}` | `BacktestSummary` | E7 (medium) |
| POST | `/engine/assignment-risk` | `list[AssignmentRiskResult]` | E9 (medium) |

### 10.3 DB Schema Additions

```sql
-- E4: Earnings gap score (stored alongside market_states)
ALTER TABLE market_states
    ADD COLUMN earnings_gap_score   numeric(6,4),
    ADD COLUMN earnings_gap_context jsonb;

-- E7: Backtest runs
CREATE TABLE backtest_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker          text NOT NULL,
    strategy        text NOT NULL,
    start_date      date NOT NULL,
    end_date        date NOT NULL,
    exit_rule       text NOT NULL DEFAULT 'day_after_earnings',
    chain_source    text NOT NULL,
    summary         jsonb NOT NULL,    -- BacktestSummary
    events          jsonb NOT NULL,    -- list[EarningsEventResult]
    status          text NOT NULL DEFAULT 'completed',
    computed_at     timestamptz NOT NULL DEFAULT now(),
    engine_version  text NOT NULL,
    disclaimer      text NOT NULL
);
CREATE INDEX backtest_runs_user_idx ON backtest_runs(user_id, computed_at DESC);

-- E8: Dividend schedules
CREATE TABLE dividend_schedules (
    ticker              text NOT NULL,
    quarterly_amount    numeric(10,4) NOT NULL,
    ex_date             date NOT NULL,
    record_date         date,
    payment_date        date,
    source              text NOT NULL,
    PRIMARY KEY (ticker, ex_date)
);

-- E1: GEX results (optional persistence for audit/replay)
CREATE TABLE gex_snapshots (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          text NOT NULL,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    expiry_focus    date[] NOT NULL,
    result          jsonb NOT NULL,    -- GexResult
    inputs_hash     text NOT NULL,
    engine_version  text NOT NULL
);
CREATE INDEX gex_snapshots_lookup ON gex_snapshots(ticker, computed_at DESC);
```

---

## 11. Phased Implementation Roadmap

### Phase 1.5 (Immediately after Phase 1 ships — 2 weeks)

**Goal**: Ship GEX module and vol surface analytics as the highest-leverage enhancements; these are the foundation everything else builds on.

| Milestone | Deliverable | Size |
|---|---|---|
| ME1.1 | `GexResult` dataclass + `compute_gex()` pure function | M |
| ME1.2 | GEX tests: 8 fixtures, 3 property tests, flip interpolation | M |
| ME1.3 | GEX integration into Flow Score Engine (replace dealer_gamma_proxy) | S |
| ME1.4 | GEX integration into Strike Selector (ranking bonus/penalty) | S |
| ME1.5 | GEX-aware Recommendation rules (2 new rules in rules.yaml) | S |
| ME1.6 | `POST /engine/gex` endpoint | S |
| ME1.7 | `DailyDecision.gex_context` field + Today screen `GexContextStrip` | M |
| ME1.8 | `/gex` drill-down page: `GEXByStrikeChart` + `CumulativeGexChart` | M |
| ME2.1 | `VolSurfaceResult` + `compute_vol_surface()` + term structure slope | M |
| ME2.2 | 25-delta skew interpolation + `SkewPoint` | S |
| ME2.3 | Vol premium tracker (`vol_premium.py`) | S |
| ME2.4 | `iv_score()` enhancement to use vol premium and term structure slope | S |
| ME2.5 | `/engine/vol-surface` endpoint | S |
| ME2.6 | `/iv` drill-down page: term structure chart + skew chart + vol premium bar | M |

### Phase 2 (following Phase 2 of base plan — 2-3 weeks additional)

| Milestone | Deliverable | Size |
|---|---|---|
| ME3.1 | `pnl_by_price()` + `pnl_surface()` + `scenario_table()` | M |
| ME3.2 | PnL tests: BS sanity, scenario correctness | M |
| ME3.3 | `PayoffPreviewStrip` on Today screen | S |
| ME3.4 | `/engine/pnl-by-price`, `/engine/pnl-surface`, `/engine/scenario-table` | S |
| ME3.5 | Full `/payoff` page: PnLByPriceChart + PnLSurface3D + ScenarioTable + GreeksCurves | L |
| ME3.6 | Collar Builder enhanced with `pnl_by_price` + `key_scenarios` fields | S |
| ME4.1 | `earnings_gap_score()` pure function + weights YAML | M |
| ME4.2 | Integration: `DailyDecision.earnings_gap` field; new recommendation rules | M |
| ME4.3 | `EarningsGapCard` on Today screen (visible when event_in_14d) | S |
| ME5.1 | Vol premium percentile computation | S |
| ME6.1 | `MultiExpiryPlan` + `plan_multi_expiry()` | M |
| ME6.2 | `/engine/multi-expiry` endpoint + phase-2 drill-down UI | M |

### Phase 3 (following base Phase 3 — 3-4 weeks additional)

| Milestone | Deliverable | Size |
|---|---|---|
| ME7.1 | Earnings calendar ingestion (CSV + yfinance fallback) | M |
| ME7.2 | `backtest_earnings()` engine + `BacktestSummary` | L |
| ME7.3 | `/engine/backtest-earnings` async endpoint + `/engine/backtest-runs/{id}` | M |
| ME7.4 | `/backtest` page: event table + summary metrics + disclaimer block | L |
| ME7.5 | Backtest tests: determinism, single-event correctness, data quality caveat presence | M |
| ME8.1 | `DividendSchedule` + `DividendContext` + `bs_price_dividend_aware()` | M |
| ME8.2 | `early_assignment_risk_score()` added to Execution Module | S |
| ME8.3 | Dividend schedule CSV seeding for MSFT (quarterly, next 4 quarters) | S |
| ME9.1 | `AssignmentRiskResult` + `assess_assignment_risk()` | M |
| ME9.2 | `AssignmentRiskCard` on Today screen + integration with Execution.notes | M |
| ME9.3 | Lot-level LTCG analysis integration | M |

---

## 12. Testing Specifications for Enhancement Modules

### E1 GEX Tests

```python
# packages/engine/tests/test_gex.py

def test_symmetric_chain_zero_total_gex():
    # Equal call and put OI+gamma at every strike → total_gex == 0
    chain = build_symmetric_chain(spot=410, strikes=[400, 405, 410, 415, 420])
    result = compute_gex(chain_snapshot=chain, spot=410, expiry_focus=[near_expiry])
    assert abs(result.total_gex) < 1e-6

def test_call_heavy_chain_positive_gex():
    # Large call OI, minimal put OI → total_gex > 0, regime_tag == "positive_gex_stable"
    ...

def test_gamma_flip_interpolation():
    # Cumulative GEX crosses zero between $407 and $409 → flip between those values
    result = compute_gex(...)
    assert 407.0 <= float(result.gamma_flip) <= 409.0

def test_call_wall_is_above_spot():
    result = compute_gex(...)
    assert result.call_wall > spot

def test_put_wall_is_below_spot():
    result = compute_gex(...)
    assert result.put_wall < spot

def test_bs_gamma_fallback_within_10pct():
    # Chain has gamma=None; BS-computed gamma within 10% of reference
    ...

def test_gex_em_ratio_near_flip_flags_near_flip():
    # gex_em_ratio < 0.5 → regime_tag == "near_flip"
    ...

@given(oi=st.integers(0, 100000), gamma=st.floats(0.001, 0.10))
def test_gex_per_leg_positive_for_calls(oi, gamma):
    call_gex = gamma * oi * 100 * 410**2
    assert call_gex >= 0
```

### E2 Vol Surface Tests

```python
def test_inverted_term_structure_detection():
    # iv_30d = 0.35, iv_60d = 0.28 → slope == "inverted"
    ...

def test_vol_premium_positive_when_iv_exceeds_hv():
    result = compute_vol_surface(iv_history=iv_30d_equals_030, hv_history=hv_30d_equals_022)
    assert result.vol_premium_30d > 0

def test_25d_skew_positive_when_put_iv_higher():
    # Standard: OTM puts price higher than OTM calls
    result = compute_vol_surface(chain=standard_skew_chain)
    assert result.skew_by_expiry[0].skew_25d > 0
```

### E3 PnL Tests

```python
def test_pnl_at_expiry_short_call_capped_gain():
    # Short covered call: gain capped at premium + (strike - spot) if assigned
    legs = [stock_leg(qty=100, cost=400), short_call_leg(strike=415, premium=3.0)]
    result = pnl_by_price(legs=legs, spot=410, ...)
    assert result.max_gain > 0
    assert result.max_loss == pytest.approx(-410 * 100 + 3.0 * 100, rel=0.01)

def test_scenario_table_has_7_rows():
    result = scenario_table(legs=..., scenarios=None)  # default MSFT scenarios
    assert len(result.scenarios) == 7

def test_breakeven_upper_for_collar():
    # Collar with long put 405, short call 425 purchased at net $0
    # Upper breakeven ≈ 425, lower breakeven ≈ 405
    result = pnl_by_price(legs=collar_legs, ...)
    assert abs(result.breakeven_upper - 425) < 2.0
    assert abs(result.breakeven_lower - 405) < 2.0
```

### E7 Backtest Tests

```python
def test_backtest_deterministic():
    result1 = backtest_earnings(ticker="MSFT", ...)
    result2 = backtest_earnings(ticker="MSFT", ...)
    assert result1.summary_metrics == result2.summary_metrics

def test_data_quality_caveat_always_present():
    result = backtest_earnings(...)
    assert "historical" in result.data_quality_caveat.lower()
    assert result.disclaimer  # non-empty

def test_single_event_pnl_correctness():
    # Manually computed: pre=$410, post=$418 (earnings beat), sold call at $415 for $3.00
    # Max gain at $415: $5.00 per share stock gain + $3.00 premium - $0 option loss = $8.00 × 100 = $800
    event = EarningsEvent(pre_spot=410, post_spot=418, ...)
    result = simulate_single_event(event, strategy="SELL_COVERED_CALL_PARTIAL", ...)
    assert abs(result.strategy_pnl - 800) < 10
```

---

## 13. Non-Functional Considerations

### Performance Targets

| Operation | Target | Notes |
|---|---|---|
| `compute_gex()` | < 200ms | Vectorized over chain; numpy-based |
| `compute_vol_surface()` | < 100ms | Per-expiry interpolation |
| `pnl_by_price()` | < 50ms | 100-point grid; BS-evaluated |
| `pnl_surface()` | < 500ms | 50×20 grid; BS-vectorized with numpy |
| `scenario_table()` | < 100ms | 7 scenarios × BS reprice |
| `backtest_earnings()` (8 events) | < 5s | Async; BS reprice per event |
| Full `DailyDecision` with all enhancements | < 8s | Up from < 5s; acceptable for full analysis mode |

**Optimization**: The enhanced `DailyDecision` adds GEX computation, vol surface, earnings gap, and PnL preview. If this exceeds 8s in practice, offer a "fast mode" (`depth: Literal["quick", "full"]`) that skips `pnl_preview` and `vol_surface` for a sub-5s response.

### Data Availability Dependencies

| Enhancement | Required data beyond Phase 1 base |
|---|---|
| E1 GEX | Chain gamma (or chain IV for BS gamma fallback) — yfinance often lacks gamma; Tradier provides it |
| E2 Vol Surface | 60-day+ IV history (yfinance IV is unreliable); consider Polygon for reliable IV history |
| E4 Earnings Gap | 30-day price history (yfinance `history(period='60d')`) — available without paid key |
| E5 Vol Premium | IV history (same as E2) |
| E7 Backtest | Historical earnings dates (Polygon or manual CSV), historical chain (yfinance OK for approx) |
| E8 Dividend | MSFT dividend schedule (yfinance `info['exDividendDate']` + manual quarterly schedule) |
| E9 Assignment | Lot-level cost basis (existing `lots` table — already designed) |

**Phasing recommendation**: E1 (GEX) and E4 (Earnings Gap) can be built on yfinance. E2 and E5 (vol surface) should wait for Tradier/Polygon integration (base plan Phase 2 data providers). E7 (backtest) can start with manual CSV earnings calendar.

### Disclaimer Enforcement

All new analytical outputs must follow the base plan's disclaimer framework:

- `EarningsGapScore.interpretation` passes through `LanguageGuardMiddleware` (no "buy", "sell", "recommend")
- `BacktestSummary.disclaimer` is non-optional and non-empty (enforced by Pydantic `@validator`)
- `AssignmentRiskResult.mitigation_options` are phrased as educational options ("Consider rolling the short call up and out to a higher strike"), not instructions
- `GexResult.interpretation` ends with the short-form disclaimer
- New API routes are added to the `DisclaimerMiddleware` route list on day 1

---

## 14. Open Questions Before Implementation

1. **GEX expiry weighting**: Should GEX contributions from different expiries be weighted equally or by OI magnitude? The nearest expiry has less time but often the most OI.

2. **Gamma flip stability**: The gamma flip level moves daily as chain OI shifts. Should the Today screen show the current flip, a 5-day moving average, or both?

3. **Vol surface IV source**: yfinance option chain IV is unreliable (sometimes stale by hours; sometimes wrong). Should the vol surface show a warning when the IV source is yfinance?

4. **Backtest exit rule**: "Day after earnings close" is correct for covered call / collar simulation (you can close on the next trading day). Should there also be a "hold to expiry" mode?

5. **Earnings gap score for non-earnings regimes**: Should the score be computed even when there's no earnings event within 14 days (using the last earnings event context for educational purposes)?

6. **Assignment risk disclosure language**: Tax lot selection is the broker's choice (and potentially the user's choice via lot selection tools). How explicit should the LTCG analysis be in the UI? A conservative approach: show which lots *might* be affected without recommending specific lot assignments.

7. **Multi-expiry stagger implementation in Phase 1**: The base plan's collar builder handles a single intent/expiry. Should stagger support be added as part of Phase 1.5 (E1) or deferred to Phase 2 (E6)?

8. **PnL surface grid size cap**: At 50×20=1,000 BS evaluations, the surface is fast. What's the maximum grid the API accepts before returning 422? Suggest 100×40=4,000 as the hard cap.
