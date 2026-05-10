"""Flow Score Engine `compute()` tests (M1.5b).

Per plan v1.2 §17 M1.5b acceptance and §9.3a (V1 LOCKED contract).
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.flow_score import (
    Bias,
    FlowScore,
    RecommendedAction,
    compute,
    futures_basis,
    render_explanation,
    sigmoid_pin,
    skew_25d,
)
from engine.flow_score.compute import (
    _decide_action,
    _decide_bias,
    _dist_to_wall_norm,
    _oi_concentration_at_max_pain,
    _volume_shares,
)
from engine.scoring import GammaScoreResult, OiWalls
from engine.types import ChainSnapshot, OptionContract, OptionType

# ----------------------------------------------------------------------
# helpers — build small but realistic chains
# ----------------------------------------------------------------------


_EXPIRY = date(2026, 6, 19)


def _c(
    *,
    strike: float,
    option_type: OptionType,
    oi: int = 1000,
    volume: int = 100,
    iv: float = 0.30,
    expiry: date = _EXPIRY,
) -> OptionContract:
    return OptionContract(
        underlying="MSFT",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        open_interest=oi,
        volume=volume,
        iv=iv,
        mid=1.0,
        bid=0.95,
        ask=1.05,
    )


def _chain(contracts: list[OptionContract]) -> ChainSnapshot:
    return ChainSnapshot(
        underlying="MSFT",
        spot=100.0,
        as_of=date(2026, 5, 10),
        contracts=tuple(contracts),
    )


def _balanced_chain() -> ChainSnapshot:
    """Symmetric call+put chain centered on spot=100 with single peak at 100."""
    contracts = []
    for k in [95.0, 100.0, 105.0]:
        for ot in (OptionType.CALL, OptionType.PUT):
            contracts.append(_c(strike=k, option_type=ot, oi=1000, volume=100))
    return _chain(contracts)


# ----------------------------------------------------------------------
# component helpers
# ----------------------------------------------------------------------


def test_volume_shares_balanced() -> None:
    """Equal call/put volume → both shares = 0.5."""
    contracts = [
        _c(strike=100.0, option_type=OptionType.CALL, volume=100),
        _c(strike=100.0, option_type=OptionType.PUT, volume=100),
    ]
    cs, ps = _volume_shares(contracts=contracts, expiry_focus={_EXPIRY})
    assert cs == pytest.approx(0.5, abs=1e-12)
    assert ps == pytest.approx(0.5, abs=1e-12)


def test_volume_shares_zero_volume() -> None:
    """No volume in focus → both shares = 0.5 (neutral prior)."""
    contracts = [_c(strike=100.0, option_type=OptionType.CALL, volume=0)]
    cs, ps = _volume_shares(contracts=contracts, expiry_focus={_EXPIRY})
    assert cs == 0.5
    assert ps == 0.5


def test_volume_shares_call_heavy() -> None:
    """800 call volume + 200 put volume → 0.8 / 0.2."""
    contracts = [
        _c(strike=100.0, option_type=OptionType.CALL, volume=800),
        _c(strike=100.0, option_type=OptionType.PUT, volume=200),
    ]
    cs, ps = _volume_shares(contracts=contracts, expiry_focus={_EXPIRY})
    assert cs == pytest.approx(0.8, abs=1e-12)
    assert ps == pytest.approx(0.2, abs=1e-12)


def test_volume_shares_other_expiry_excluded() -> None:
    """Volume at expiries outside focus is ignored."""
    contracts = [
        _c(strike=100.0, option_type=OptionType.CALL, volume=100),
        _c(strike=100.0, option_type=OptionType.PUT, volume=10000, expiry=date(2027, 1, 15)),
    ]
    cs, ps = _volume_shares(contracts=contracts, expiry_focus={_EXPIRY})
    assert cs == 1.0
    assert ps == 0.0


def test_dist_to_wall_norm_on_wall() -> None:
    """spot exactly on wall → 0.0."""
    assert _dist_to_wall_norm(spot=100.0, wall=100.0) == 0.0


def test_dist_to_wall_norm_far() -> None:
    """spot 5% away → 1.0 (saturated)."""
    assert _dist_to_wall_norm(spot=100.0, wall=105.0) == 1.0
    assert _dist_to_wall_norm(spot=100.0, wall=95.0) == 1.0


def test_dist_to_wall_norm_midband() -> None:
    """spot 2.5% away → 0.5."""
    assert _dist_to_wall_norm(spot=100.0, wall=102.5) == pytest.approx(0.5, abs=1e-12)


def test_dist_to_wall_norm_missing_wall() -> None:
    """wall=None → 0.5 neutral prior."""
    assert _dist_to_wall_norm(spot=100.0, wall=None) == 0.5


def test_oi_concentration_at_max_pain_full_concentration() -> None:
    """All OI at max_pain strike → concentration = 1.0."""
    contracts = [
        _c(strike=100.0, option_type=OptionType.CALL, oi=1000),
        _c(strike=100.0, option_type=OptionType.PUT, oi=1000),
    ]
    c = _oi_concentration_at_max_pain(
        contracts=contracts, max_pain=100.0, expiry_focus={_EXPIRY}
    )
    assert c == pytest.approx(1.0, abs=1e-12)


def test_oi_concentration_at_max_pain_split() -> None:
    """Half the OI at max_pain, half elsewhere → concentration = 0.5."""
    contracts = [
        _c(strike=95.0, option_type=OptionType.CALL, oi=500),
        _c(strike=100.0, option_type=OptionType.CALL, oi=500),
    ]
    c = _oi_concentration_at_max_pain(
        contracts=contracts, max_pain=100.0, expiry_focus={_EXPIRY}
    )
    assert c == pytest.approx(0.5, abs=1e-12)


def test_oi_concentration_at_max_pain_no_oi() -> None:
    """Zero OI in focus → concentration = 0.0."""
    contracts = [_c(strike=100.0, option_type=OptionType.CALL, oi=0)]
    c = _oi_concentration_at_max_pain(
        contracts=contracts, max_pain=100.0, expiry_focus={_EXPIRY}
    )
    assert c == 0.0


# ----------------------------------------------------------------------
# bias bucketing
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "pin_prob", "expected_bias"),
    [
        (+30.0, 0.0, Bias.BULLISH),
        (-30.0, 0.0, Bias.BEARISH),
        (+5.0, 0.0, Bias.NEUTRAL),
        (-5.0, 0.0, Bias.NEUTRAL),
        (+20.0, 0.0, Bias.BULLISH),  # boundary inclusive
        (-20.0, 0.0, Bias.BEARISH),
        # PIN_RISK overrides regardless of score sign
        (+30.0, 0.7, Bias.PIN_RISK),
        (-30.0, 0.7, Bias.PIN_RISK),
        (0.0, 0.6, Bias.PIN_RISK),
    ],
)
def test_decide_bias_buckets(
    score: float, pin_prob: float, expected_bias: Bias
) -> None:
    assert _decide_bias(score=score, pin_probability=pin_prob) is expected_bias


# ----------------------------------------------------------------------
# decision tree
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "gamma_risk", "pin", "expected"),
    [
        # Aggressive: very bullish + low gamma risk
        (50.0, 0.3, 0.0, RecommendedAction.SELL_CALL_AGGRESSIVE),
        (40.0, 0.5, 0.0, RecommendedAction.SELL_CALL_AGGRESSIVE),
        # Partial: bullish but gamma > 0.5 OR score < 40
        (50.0, 0.7, 0.0, RecommendedAction.SELL_CALL_PARTIAL),
        (20.0, 0.0, 0.0, RecommendedAction.SELL_CALL_PARTIAL),
        # Wait: small |score| with high pin
        (5.0, 0.0, 0.7, RecommendedAction.WAIT),
        (-5.0, 0.0, 0.8, RecommendedAction.WAIT),
        # Protection: bearish + high gamma risk
        (-30.0, 0.7, 0.0, RecommendedAction.BUY_PROTECTION),
        (-20.0, 0.6, 0.0, RecommendedAction.BUY_PROTECTION),
        # Reduce: bearish but not aggressive enough for protection
        (-15.0, 0.3, 0.0, RecommendedAction.REDUCE_COVERAGE),
        (-25.0, 0.3, 0.0, RecommendedAction.REDUCE_COVERAGE),
        # Monitor: small |score|, no pin pressure
        (0.0, 0.5, 0.0, RecommendedAction.MONITOR),
        (-5.0, 0.5, 0.0, RecommendedAction.MONITOR),
        (5.0, 0.5, 0.0, RecommendedAction.MONITOR),
    ],
)
def test_decide_action_branches(
    score: float, gamma_risk: float, pin: float, expected: RecommendedAction
) -> None:
    assert (
        _decide_action(score=score, gamma_risk=gamma_risk, pin_probability=pin)
        is expected
    )


# ----------------------------------------------------------------------
# stubs (skew_25d, futures_basis)
# ----------------------------------------------------------------------


def test_skew_25d_returns_zero_v1() -> None:
    """V1 stub always returns 0."""
    assert skew_25d(contracts=[], expiry_focus=[]) == 0.0
    assert skew_25d(contracts=[_c(strike=100.0, option_type=OptionType.CALL)], expiry_focus=[_EXPIRY]) == 0.0


def test_futures_basis_returns_zero_v1() -> None:
    """V1 stub always returns 0 for any valid spot."""
    assert futures_basis(spot=100.0) == 0.0
    assert futures_basis(spot=1.0) == 0.0


def test_futures_basis_rejects_nonpositive_spot() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        futures_basis(spot=0.0)
    with pytest.raises(ValueError, match="spot must be > 0"):
        futures_basis(spot=-1.0)


# ----------------------------------------------------------------------
# sigmoid_pin
# ----------------------------------------------------------------------


def test_sigmoid_pin_full() -> None:
    """All three factors maxed → pin_probability = 1.0."""
    p = sigmoid_pin(
        spot=100.0,
        max_pain=100.0,
        dte_to_nearest_opex=0,
        oi_concentration_at_max_pain=1.0,
    )
    assert p == pytest.approx(1.0, abs=1e-12)


def test_sigmoid_pin_far_from_pin() -> None:
    """Spot 5% from max_pain → dist_factor = 0 → pin_probability = 0."""
    p = sigmoid_pin(
        spot=100.0,
        max_pain=95.0,
        dte_to_nearest_opex=0,
        oi_concentration_at_max_pain=1.0,
    )
    assert p == 0.0


def test_sigmoid_pin_no_opex() -> None:
    """dte_to_nearest_opex=None → 0."""
    p = sigmoid_pin(
        spot=100.0,
        max_pain=100.0,
        dte_to_nearest_opex=None,
        oi_concentration_at_max_pain=1.0,
    )
    assert p == 0.0


def test_sigmoid_pin_far_opex() -> None:
    """dte=30 → opex_factor = 0 → pin_probability = 0."""
    p = sigmoid_pin(
        spot=100.0,
        max_pain=100.0,
        dte_to_nearest_opex=30,
        oi_concentration_at_max_pain=1.0,
    )
    assert p == 0.0


def test_sigmoid_pin_negative_dte_clamps() -> None:
    """Negative dte clamps to 0 (defensive)."""
    p = sigmoid_pin(
        spot=100.0,
        max_pain=100.0,
        dte_to_nearest_opex=-2,
        oi_concentration_at_max_pain=1.0,
    )
    assert p == pytest.approx(1.0, abs=1e-12)


def test_sigmoid_pin_zero_concentration() -> None:
    """oi_concentration=0 → multiplicative gate fires → 0."""
    p = sigmoid_pin(
        spot=100.0,
        max_pain=100.0,
        dte_to_nearest_opex=0,
        oi_concentration_at_max_pain=0.0,
    )
    assert p == 0.0


def test_sigmoid_pin_validation() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        sigmoid_pin(spot=0.0, max_pain=100.0, dte_to_nearest_opex=0, oi_concentration_at_max_pain=0.5)
    with pytest.raises(ValueError, match="max_pain must be > 0"):
        sigmoid_pin(spot=100.0, max_pain=0.0, dte_to_nearest_opex=0, oi_concentration_at_max_pain=0.5)
    with pytest.raises(ValueError, match="oi_concentration"):
        sigmoid_pin(spot=100.0, max_pain=100.0, dte_to_nearest_opex=0, oi_concentration_at_max_pain=1.5)


# ----------------------------------------------------------------------
# render_explanation
# ----------------------------------------------------------------------


def test_render_explanation_full_signal() -> None:
    """Both walls + signed gamma + high pin → 4 sentences."""
    walls = OiWalls(support=95.0, resistance=105.0)
    gamma = GammaScoreResult(score=0.5, sign=-1, breakdown={})
    text = render_explanation(
        walls=walls,
        score=-25.0,
        gamma=gamma,
        pin_probability=0.75,
    )
    assert "FlowScore composite: -25.0" in text
    assert "95.00" in text  # support strike
    assert "105.00" in text  # resistance strike
    assert "amplifier" in text  # short gamma
    assert "0.75" in text  # pin_probability


def test_render_explanation_no_walls_no_gamma_low_pin() -> None:
    """Walls=None, sign=0, pin<0.6 → only composite + walls sentences."""
    walls = OiWalls(support=None, resistance=None)
    gamma = GammaScoreResult(score=0.0, sign=0, breakdown={})
    text = render_explanation(
        walls=walls,
        score=0.0,
        gamma=gamma,
        pin_probability=0.0,
    )
    # Check specific phrase presence/absence rather than period counting
    # (the score is rendered as "+0.0." which contains its own period).
    assert "FlowScore composite" in text
    assert "No significant OI walls" in text
    assert "amplifier" not in text
    assert "dampener" not in text
    assert "pin probability" not in text


def test_render_explanation_one_sided_walls() -> None:
    """Only support → say 'no clear resistance'."""
    walls = OiWalls(support=95.0, resistance=None)
    gamma = GammaScoreResult(score=0.0, sign=0, breakdown={})
    text = render_explanation(walls=walls, score=0.0, gamma=gamma, pin_probability=0.0)
    assert "no clear resistance" in text
    walls2 = OiWalls(support=None, resistance=105.0)
    text2 = render_explanation(walls=walls2, score=0.0, gamma=gamma, pin_probability=0.0)
    assert "no clear support" in text2


def test_render_explanation_long_gamma() -> None:
    """Sign +1 → dampener wording."""
    walls = OiWalls(support=None, resistance=None)
    gamma = GammaScoreResult(score=0.4, sign=+1, breakdown={})
    text = render_explanation(walls=walls, score=10.0, gamma=gamma, pin_probability=0.0)
    assert "dampener" in text
    assert "amplifier" not in text


# ----------------------------------------------------------------------
# compute() — full orchestrator
# ----------------------------------------------------------------------


def test_compute_returns_flow_score_shape() -> None:
    """compute() returns a fully populated FlowScore with bounded fields."""
    snap = _balanced_chain()
    result = compute(chain_snapshot=snap, spot=100.0, expiry_focus=[_EXPIRY])
    assert isinstance(result, FlowScore)
    # Composite bounds
    assert -100.0 <= result.score <= 100.0
    assert 0.0 <= result.bullish_score <= 100.0
    assert 0.0 <= result.bearish_score <= 100.0
    # Specific signals bounds
    assert 0.0 <= result.pin_probability <= 1.0
    assert 0.0 <= result.gamma_risk <= 1.0
    assert result.gamma_sign in {-1, 0, +1}
    assert 0.0 <= result.confidence <= 1.0
    # Categorization
    assert result.bias in set(Bias)
    assert result.recommended_action in set(RecommendedAction)
    # Explanation present and non-empty
    assert isinstance(result.explanation, str)
    assert len(result.explanation) > 0
    # Breakdown keys stable
    expected_keys = {
        "bullish_dist",
        "bullish_call_vol",
        "bullish_skew",
        "bullish_basis",
        "bullish_pcrv",
        "bearish_dist",
        "bearish_put_vol",
        "bearish_skew",
        "bearish_basis",
        "bearish_pcrv",
        "pcr_oi",
        "oi_concentration_at_max_pain",
        "max_pain",
    }
    assert set(result.breakdown.keys()) == expected_keys


def test_compute_balanced_chain_is_neutral() -> None:
    """Symmetric OI + slight call-volume tilt → score near zero → NEUTRAL.

    Note: the §9.3a PCR component is asymmetric — `bullish_pcrv = max(0, 1-PCR)`
    vs `bearish_pcrv = PCR`. A chain with PCR = 1.0 (equal call/put volume)
    produces a mild bearish tilt (~10 points) because the PCR weight (0.10)
    contributes 0 to bullish and 1.0 to bearish. To land at score ≈ 0 we
    use a slightly call-heavy chain (PCR = 0.7, which is closer to the
    typical equity-chain baseline).
    """
    # 3 strikes (95, 100, 105) × call + put. Call volume 100, put volume 70.
    # PCR = 70 / 100 = 0.7.
    contracts = []
    for k in [95.0, 100.0, 105.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, oi=1000, volume=100))
        contracts.append(_c(strike=k, option_type=OptionType.PUT, oi=1000, volume=70))
    snap = _chain(contracts)
    result = compute(chain_snapshot=snap, spot=100.0, expiry_focus=[_EXPIRY])
    # Should land within ±10 of zero (the V1 formula's "neutral band").
    assert abs(result.score) <= 10.0
    assert result.bias is Bias.NEUTRAL


def test_compute_pcr_balanced_chain_tilts_slightly_bearish() -> None:
    """PCR = 1.0 (equal call/put volume) tilts FlowScore mildly bearish.

    This documents the §9.3a formula's natural baseline: the PCR
    contribution is asymmetric. Premium-selling equities typically
    have PCR < 1.0; PCR = 1.0 is unusual and reflects elevated put
    activity relative to baseline → mild bearish tilt.
    """
    snap = _balanced_chain()  # equal call/put volume → PCR = 1.0
    result = compute(chain_snapshot=snap, spot=100.0, expiry_focus=[_EXPIRY])
    # PCR=1.0 → bullish_pcrv=0, bearish_pcrv=1.0 → score ≈ -10
    assert result.score < 0.0
    assert -15.0 <= result.score <= -5.0


def test_compute_bullish_chain_picks_bullish_bias() -> None:
    """Heavy call volume + low PCR + spot far below resistance → bullish."""
    contracts = []
    for k in [95.0, 100.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, oi=1000, volume=1000))
        contracts.append(_c(strike=k, option_type=OptionType.PUT, oi=200, volume=50))
    # Heavy resistance peak strategically far away → spot has room to run
    contracts.append(_c(strike=120.0, option_type=OptionType.CALL, oi=8000, volume=300))
    contracts.append(_c(strike=120.0, option_type=OptionType.PUT, oi=200, volume=30))
    snap = _chain(contracts)
    result = compute(chain_snapshot=snap, spot=100.0, expiry_focus=[_EXPIRY])
    # Heavy call activity should produce a bullish tilt.
    assert result.score > 0.0
    assert result.bullish_score > result.bearish_score


def test_compute_bearish_chain_picks_bearish_bias() -> None:
    """Heavy put volume + high PCR + spot above support → bearish."""
    contracts = []
    for k in [100.0, 105.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, oi=200, volume=50))
        contracts.append(_c(strike=k, option_type=OptionType.PUT, oi=1000, volume=1000))
    contracts.append(_c(strike=80.0, option_type=OptionType.CALL, oi=200, volume=30))
    contracts.append(_c(strike=80.0, option_type=OptionType.PUT, oi=8000, volume=300))
    snap = _chain(contracts)
    result = compute(chain_snapshot=snap, spot=100.0, expiry_focus=[_EXPIRY])
    assert result.score < 0.0
    assert result.bearish_score > result.bullish_score


def test_compute_pin_risk_with_high_concentration() -> None:
    """All OI at max_pain + spot near max_pain + near opex → PIN_RISK bias."""
    contracts = []
    # All OI at one strike (max_pain candidate)
    contracts.append(_c(strike=100.0, option_type=OptionType.CALL, oi=10000, volume=100))
    contracts.append(_c(strike=100.0, option_type=OptionType.PUT, oi=10000, volume=100))
    # Tiny noise elsewhere
    for k in [95.0, 105.0]:
        contracts.append(_c(strike=k, option_type=OptionType.CALL, oi=10, volume=10))
        contracts.append(_c(strike=k, option_type=OptionType.PUT, oi=10, volume=10))
    snap = _chain(contracts)
    result = compute(
        chain_snapshot=snap,
        spot=100.0,
        expiry_focus=[_EXPIRY],
        dte_to_nearest_opex=2,
    )
    assert result.pin_probability >= 0.6
    assert result.bias is Bias.PIN_RISK


def test_compute_confidence_scales_with_oi() -> None:
    """Doubling OI doubles confidence (linearly) until saturation."""

    def _confidence_for(oi: int) -> float:
        contracts = [
            _c(strike=100.0, option_type=OptionType.CALL, oi=oi),
            _c(strike=100.0, option_type=OptionType.PUT, oi=oi),
        ]
        return compute(
            chain_snapshot=_chain(contracts),
            spot=100.0,
            expiry_focus=[_EXPIRY],
        ).confidence

    c_low = _confidence_for(1000)
    c_mid = _confidence_for(10_000)
    c_full = _confidence_for(100_000)
    c_sat = _confidence_for(500_000)
    assert c_low < c_mid < c_full
    assert c_full == pytest.approx(1.0, abs=1e-9)
    assert c_sat == 1.0  # clipped


def test_compute_validation_zero_spot() -> None:
    with pytest.raises(ValueError, match="spot must be > 0"):
        compute(chain_snapshot=_balanced_chain(), spot=0.0, expiry_focus=[_EXPIRY])


def test_compute_validation_empty_focus() -> None:
    with pytest.raises(ValueError, match="expiry_focus must contain"):
        compute(chain_snapshot=_balanced_chain(), spot=100.0, expiry_focus=[])


# ----------------------------------------------------------------------
# property tests
# ----------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    spot=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False),
    n_strikes=st.integers(min_value=1, max_value=10),
    oi_max=st.integers(min_value=10, max_value=10_000),
    vol_max=st.integers(min_value=10, max_value=10_000),
    dte=st.one_of(st.none(), st.integers(min_value=0, max_value=40)),
)
def test_compute_bounded_outputs(
    spot: float,
    n_strikes: int,
    oi_max: int,
    vol_max: int,
    dte: int | None,
) -> None:
    """For any valid chain, FlowScore outputs respect their bounds."""
    # Synthesize a chain centered on spot with n_strikes per side
    contracts = []
    for i in range(n_strikes):
        k_above = spot * (1.0 + 0.02 * (i + 1))
        k_below = spot * (1.0 - 0.02 * (i + 1))
        for k in (k_above, k_below):
            contracts.append(
                _c(strike=k, option_type=OptionType.CALL, oi=oi_max, volume=vol_max)
            )
            contracts.append(
                _c(strike=k, option_type=OptionType.PUT, oi=oi_max, volume=vol_max)
            )
    # ATM strike too, so max_pain has something to pick
    contracts.append(_c(strike=spot, option_type=OptionType.CALL, oi=oi_max, volume=vol_max))
    contracts.append(_c(strike=spot, option_type=OptionType.PUT, oi=oi_max, volume=vol_max))
    snap = _chain(contracts)
    r = compute(
        chain_snapshot=snap,
        spot=spot,
        expiry_focus=[_EXPIRY],
        dte_to_nearest_opex=dte,
    )
    assert -100.0 <= r.score <= 100.0
    assert 0.0 <= r.bullish_score <= 100.0
    assert 0.0 <= r.bearish_score <= 100.0
    assert 0.0 <= r.pin_probability <= 1.0
    assert 0.0 <= r.gamma_risk <= 1.0
    assert r.gamma_sign in {-1, 0, +1}
    assert 0.0 <= r.confidence <= 1.0
    assert r.bias in set(Bias)
    assert r.recommended_action in set(RecommendedAction)
    # score is bullish - bearish to floating-point precision
    assert r.score == pytest.approx(r.bullish_score - r.bearish_score, abs=1e-9)
