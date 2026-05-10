"""Gamma-exposure scoring primitive.

Per plan v1.2 §9.11 (Scoring Functions Module) and §17 M1.5a.

`gamma_score()` answers: **"How constrained or amplified is spot's
near-term path by the options-dealer community's net gamma exposure?"**

The composite has two pieces:

  proxy_magnitude  Magnitude of the dealer-gamma proxy
                   (`engine.flow_score.compute_dealer_gamma_proxy()`), normalized
                   to `[0, 1]` by a spot-scaled calibration constant.
  walls_magnitude  Average absolute gamma exposure across the supplied
                   `GammaWall` set, normalized the same way. When no walls
                   are supplied (V1 / pre-GEX-module), this component is
                   zero and the proxy carries the score alone.

The result's **sign** field is the sign of the dealer-gamma proxy:

  +1   dealers net long gamma  → vol *dampener* (spot mean-reverts as
                                  dealers hedge by selling rallies / buying dips).
   0   neutral / no signal.
  −1   dealers net short gamma → vol *amplifier* (spot chases as dealers
                                  buy rallies / sell dips to delta-hedge).

The headline `score` in `[0, 1]` is the magnitude; the sign tells the
direction. This split mirrors plan §9.11's spec: *"0..1 magnitude + sign
in result; positive=stabilizing, negative=amplifying."*

Per the §9.11 wiring matrix, `gamma_score` is consumed by the Flow Score
Engine (M1.5b) — feeding `gamma_risk` and `gamma_context` on the V1
`FlowScore` contract.

## V1 calibration caveat

The V1 proxy normalization uses a `_PROXY_NORMALIZATION_SCALE` constant
calibrated against typical MSFT-style chain magnitudes. The Phase 1.5 E1
GEX module (per [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md))
replaces this V1 proxy with proper signed-gamma-weighted-by-OI and
introduces the real `GammaWall` producer. V1 callers can pass
`gamma_walls=[]` and the function degrades gracefully.

Pure function (per ADR-0005). No I/O.

Edge cases:

  - `spot <= 0` → `ValueError`.
  - `gamma_walls` empty → `walls_magnitude = 0`; `score = proxy_magnitude`
    (no weight redistribution — V1 trusts the proxy fully when no walls
    are present).
  - `dealer_gamma_proxy == 0` → `sign = 0`, `score` may still be small
    but non-negative from any wall component (rare; mostly degenerate).
  - `GammaWall.gamma_exposure` may be signed; only the magnitude
    contributes to `walls_magnitude`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine._utils import clip01

# Component weights — apply ONLY when gamma_walls is non-empty. With an
# empty walls list, `proxy_magnitude` is the whole score (no
# renormalization). The split matches plan §9.11's "proxy + walls" pair.
_W_PROXY = 0.7
_W_WALLS = 0.3

# Normalization scale for the dealer-gamma proxy. The proxy itself is
# `Σ sign(c) · OI(c) · (K - S)` (see `engine.flow_score.compute_dealer_gamma_proxy`),
# which has units of (contracts · dollars). Dividing by
# `spot · _PROXY_NORMALIZATION_SCALE` gives a dimensionless quantity that
# we expect to sit in `[0, ~1]` for a typical mega-cap chain.
#
# Calibration: with MSFT-style chains (spot ~$400, typical net OI · distance
# of order 4_000_000), `proxy / (400 · 10_000) ≈ 1.0`, saturating the
# magnitude at "high gamma exposure." Smaller / less-active chains land
# lower. The Phase 1.5 E1 GEX module recalibrates this against real GEX
# values per ADR-0008.
_PROXY_NORMALIZATION_SCALE = 10_000.0


@dataclass(frozen=True)
class GammaWall:
    """A strike with concentrated dealer gamma exposure.

    Produced by the Phase 1.5 E1 GEX module (per ADR-0008). V1 callers
    have no GEX module yet and pass `gamma_walls=[]` to `gamma_score`.

    `gamma_exposure` is signed: positive = dealers long gamma here
    (stabilizing); negative = dealers short gamma (amplifying). Only the
    magnitude contributes to `gamma_score`'s `walls_magnitude` component —
    the directional information is captured by the proxy's sign.
    """

    strike: float
    gamma_exposure: float


@dataclass(frozen=True)
class GammaScoreResult:
    """Result of `gamma_score()`.

    `score` is the headline magnitude in `[0, 1]`; `sign` separately
    carries direction (`+1`/`0`/`-1`). Consumers that only care about
    magnitude (e.g. Confidence Composer's signal_alignment input) read
    `score`; consumers that care about direction (e.g. Flow Score
    Engine's `gamma_risk` field, downstream recommendation rules) read
    both.

    `breakdown` keys: `proxy_magnitude`, `walls_magnitude`. Together with
    `sign` they fully reproduce `score` for explainability.
    """

    score: float
    sign: int
    breakdown: dict[str, float] = field(default_factory=dict)


def gamma_score(
    *,
    dealer_gamma_proxy: float,
    spot: float,
    gamma_walls: list[GammaWall],
) -> GammaScoreResult:
    """Composite dealer-gamma-exposure score.

    Args:
        dealer_gamma_proxy: Signed proxy from
                            `engine.flow_score.compute_dealer_gamma_proxy()`.
                            Sign convention: negative = net short gamma
                            (amplifier); positive = net long gamma
                            (dampener); 0 = neutral.
        spot: Current underlying spot. Must be > 0 (used in the
              proxy normalization to keep `score` ticker-agnostic).
        gamma_walls: Optional list of `GammaWall` records, produced by the
                     Phase 1.5 E1 GEX module. V1 callers may pass `[]`;
                     the function then bases `score` entirely on the
                     proxy magnitude.

    Returns:
        `GammaScoreResult` with `score` in `[0, 1]` (magnitude), `sign` in
        `{-1, 0, +1}` (direction), and a `breakdown` dict.

    Raises:
        ValueError: `spot` <= 0.
    """
    if spot <= 0.0:
        raise ValueError(f"gamma_score: spot must be > 0; got {spot}")

    denom = spot * _PROXY_NORMALIZATION_SCALE
    proxy_magnitude = clip01(abs(dealer_gamma_proxy) / denom)

    if not gamma_walls:
        walls_magnitude = 0.0
        score = proxy_magnitude
    else:
        total_abs_wall_exposure = sum(abs(w.gamma_exposure) for w in gamma_walls)
        avg_wall_exposure = total_abs_wall_exposure / len(gamma_walls)
        walls_magnitude = clip01(avg_wall_exposure / denom)
        score = clip01(_W_PROXY * proxy_magnitude + _W_WALLS * walls_magnitude)

    if dealer_gamma_proxy > 0.0:
        sign = +1
    elif dealer_gamma_proxy < 0.0:
        sign = -1
    else:
        sign = 0

    return GammaScoreResult(
        score=score,
        sign=sign,
        breakdown={
            "proxy_magnitude": proxy_magnitude,
            "walls_magnitude": walls_magnitude,
        },
    )
