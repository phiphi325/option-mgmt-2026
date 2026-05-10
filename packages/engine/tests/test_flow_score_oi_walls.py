"""OI-walls primitive tests (M1.5)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.flow_score import compute_oi_walls
from engine.scoring import OiWalls
from engine.types import OptionContract, OptionType

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


_EXPIRY = date(2026, 6, 19)
_FAR_EXPIRY = date(2026, 12, 18)


def _contract(
    *,
    strike: float,
    option_type: OptionType,
    open_interest: int,
    expiry: date = _EXPIRY,
) -> OptionContract:
    """Construct a minimal contract for OI-wall tests.

    Only `strike`, `expiry`, `option_type`, and `open_interest` matter
    for the OI-wall computation; the rest are filled with valid defaults.
    """
    return OptionContract(
        underlying="MSFT",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        open_interest=open_interest,
        volume=0,
    )


def _flat_chain(strikes: list[float], oi: int, expiry: date = _EXPIRY) -> list[OptionContract]:
    """Chain with one call + one put at each strike, identical OI."""
    out = []
    for k in strikes:
        out.append(_contract(strike=k, option_type=OptionType.CALL, open_interest=oi, expiry=expiry))
        out.append(_contract(strike=k, option_type=OptionType.PUT, open_interest=oi, expiry=expiry))
    return out


# ----------------------------------------------------------------------
# happy paths — hand-built chains
# ----------------------------------------------------------------------


def test_oi_walls_basic_support_and_resistance() -> None:
    """One large-OI peak on each side of spot → both walls present.

    With only 5 strikes the default 0.90 threshold lands at the smaller
    of the two peaks (so strict-`>` excludes it). Using
    `percentile_threshold=0.50` (median) gives both peaks room above the
    threshold. The default-0.90 behavior is exercised separately in
    `test_oi_walls_default_threshold_wide_chain`.
    """
    contracts = (
        _flat_chain([95.0, 105.0, 115.0], oi=50)
        + _flat_chain([100.0], oi=1200)
        + _flat_chain([110.0], oi=3000)
    )
    result = compute_oi_walls(
        contracts=contracts,
        spot=104.0,
        expiry_focus=[_EXPIRY],
        percentile_threshold=0.50,
    )
    assert isinstance(result, OiWalls)
    assert result.support == pytest.approx(100.0)
    assert result.resistance == pytest.approx(110.0)
    assert result.support_oi == 2400
    assert result.resistance_oi == 6000


def test_oi_walls_default_threshold_wide_chain() -> None:
    """Default 0.90 threshold on a realistic 12-strike chain.

    10 noise strikes at OI=10 each (per_strike=20) + 2 peak strikes at
    OI=2000 each (per_strike=4000). 90th percentile = 20 + 0.9·3980 ≈ 3602.
    Strict-`>` admits both 4000-OI peaks; spot=104 separates them.
    """
    noise_strikes = [80.0, 85.0, 90.0, 95.0, 102.0, 107.0, 115.0, 120.0, 125.0, 130.0]
    contracts = (
        _flat_chain(noise_strikes, oi=10)
        + _flat_chain([100.0], oi=2000)
        + _flat_chain([110.0], oi=2000)
    )
    result = compute_oi_walls(
        contracts=contracts,
        spot=104.0,
        expiry_focus=[_EXPIRY],
    )
    assert result.support == pytest.approx(100.0)
    assert result.resistance == pytest.approx(110.0)


def test_oi_walls_one_sided_resistance() -> None:
    """All large-OI strikes above spot → support is None.

    Using `percentile_threshold=0.50` so the tied 4000-OI peaks both
    clear the threshold (median = 100; both 4000s are strictly above).
    """
    contracts = (
        _flat_chain([95.0, 100.0, 105.0], oi=50)
        + _flat_chain([110.0, 120.0], oi=2000)
    )
    result = compute_oi_walls(
        contracts=contracts,
        spot=104.0,
        expiry_focus=[_EXPIRY],
        percentile_threshold=0.50,
    )
    assert result.support is None
    assert result.resistance == pytest.approx(110.0)
    assert result.support_oi == 0
    assert result.resistance_oi == 4000


def test_oi_walls_one_sided_support() -> None:
    """All large-OI strikes below spot → resistance is None."""
    contracts = (
        _flat_chain([110.0, 120.0], oi=50)
        + _flat_chain([90.0, 100.0], oi=2000)
    )
    result = compute_oi_walls(
        contracts=contracts,
        spot=104.0,
        expiry_focus=[_EXPIRY],
        percentile_threshold=0.50,
    )
    assert result.resistance is None
    assert result.support == pytest.approx(100.0)
    assert result.resistance_oi == 0
    assert result.support_oi == 4000


def test_oi_walls_flat_distribution_no_walls() -> None:
    """Every strike has identical OI → no strike exceeds the percentile threshold."""
    contracts = _flat_chain([95.0, 100.0, 105.0, 110.0, 115.0], oi=500)
    result = compute_oi_walls(contracts=contracts, spot=103.0, expiry_focus=[_EXPIRY])
    assert result.support is None
    assert result.resistance is None
    assert result.total_oi == 5 * 2 * 500


def test_oi_walls_picks_nearest_qualifying_per_side() -> None:
    """Multiple qualifying strikes per side → pick the nearer to spot.

    Four peak strikes (two below spot, two above) of identical OI sit at
    the top of the distribution; `percentile_threshold=0.25` puts the
    threshold between the noise band and the peak band so all four peaks
    qualify. The function picks the nearest qualifying strike on each
    side: support=95, resistance=110.
    """
    # Strikes 90, 95 are below spot; 110, 115 above. All have large OI.
    contracts = (
        _flat_chain([100.0, 105.0], oi=50)  # noise
        + _flat_chain([90.0, 95.0, 110.0, 115.0], oi=2000)
    )
    result = compute_oi_walls(
        contracts=contracts,
        spot=103.0,
        expiry_focus=[_EXPIRY],
        percentile_threshold=0.25,
    )
    # support is the *nearest* below = 95; resistance is the nearest above = 110.
    assert result.support == pytest.approx(95.0)
    assert result.resistance == pytest.approx(110.0)


def test_oi_walls_total_oi_aggregated_across_calls_and_puts() -> None:
    """`total_oi` sums OI across calls + puts in the focus expiries."""
    contracts = _flat_chain([95.0, 100.0, 105.0], oi=1000)
    result = compute_oi_walls(contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY])
    # 3 strikes · 2 (call+put) · 1000 OI = 6000
    assert result.total_oi == 6000


def test_oi_walls_filters_other_expiries() -> None:
    """Contracts at expiries outside `expiry_focus` are ignored."""
    contracts = (
        _flat_chain([95.0, 105.0], oi=50, expiry=_EXPIRY)
        + _flat_chain([100.0], oi=10000, expiry=_FAR_EXPIRY)  # huge OI but wrong expiry
    )
    result = compute_oi_walls(
        contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY]
    )
    # The huge-OI strike at the far expiry is ignored.
    # In the focus expiry, OI per strike is 100 (50·2) at 95 and 105 — flat.
    assert result.support is None
    assert result.resistance is None
    assert result.total_oi == 200  # 95 contributes 100, 105 contributes 100


def test_oi_walls_strike_at_spot_excluded() -> None:
    """A strike exactly on spot is neither support nor resistance."""
    contracts = (
        _flat_chain([95.0, 105.0], oi=50)
        + _flat_chain([100.0], oi=3000)  # peak right on spot
    )
    result = compute_oi_walls(contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY])
    # 100 dominates but sits on spot → not a wall on either side.
    assert result.support is None
    assert result.resistance is None


def test_oi_walls_custom_percentile_threshold() -> None:
    """Lowering the threshold lets one outsized peak qualify as a wall.

    5 strikes at OI=500 each (per_strike=1000) + 1 strike at OI=600
    (per_strike=1200). With `percentile_threshold=0.50` the median is
    1000; only 1200 is strictly above. The 120-strike sits above spot,
    so it becomes the resistance wall.
    """
    contracts = _flat_chain([95.0, 100.0, 105.0, 110.0, 115.0], oi=500) + _flat_chain(
        [120.0], oi=600
    )
    high = compute_oi_walls(
        contracts=contracts,
        spot=102.0,
        expiry_focus=[_EXPIRY],
        percentile_threshold=0.50,
    )
    assert high.resistance == pytest.approx(120.0)
    assert high.support is None  # no qualifying strike strictly below spot


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("spot", 0.0, "spot must be > 0"),
        ("spot", -1.0, "spot must be > 0"),
        ("percentile_threshold", -0.01, r"percentile_threshold must be in \[0, 1\)"),
        ("percentile_threshold", 1.0, r"percentile_threshold must be in \[0, 1\)"),
        ("percentile_threshold", 1.5, r"percentile_threshold must be in \[0, 1\)"),
    ],
)
def test_oi_walls_validation_raises(field: str, value: Any, match: str) -> None:
    contracts = _flat_chain([95.0, 100.0, 105.0], oi=100)
    kwargs: dict[str, Any] = {
        "contracts": contracts,
        "spot": 100.0,
        "expiry_focus": [_EXPIRY],
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=match):
        compute_oi_walls(**kwargs)


def test_oi_walls_empty_focus_raises() -> None:
    contracts = _flat_chain([95.0, 100.0, 105.0], oi=100)
    with pytest.raises(ValueError, match="expiry_focus must contain"):
        compute_oi_walls(contracts=contracts, spot=100.0, expiry_focus=[])


def test_oi_walls_no_contracts_at_focus_raises() -> None:
    contracts = _flat_chain([95.0, 100.0, 105.0], oi=100, expiry=_FAR_EXPIRY)
    with pytest.raises(ValueError, match="no contracts present"):
        compute_oi_walls(contracts=contracts, spot=100.0, expiry_focus=[_EXPIRY])


# ----------------------------------------------------------------------
# property tests
# ----------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    strikes_oi=st.lists(
        st.tuples(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False),
            st.integers(min_value=0, max_value=100_000),
        ),
        min_size=1,
        max_size=30,
        unique_by=lambda x: x[0],  # unique strikes
    ),
    spot=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False),
    percentile=st.floats(min_value=0.0, max_value=0.999, allow_nan=False),
)
def test_oi_walls_invariants(
    strikes_oi: list[tuple[float, int]],
    spot: float,
    percentile: float,
) -> None:
    """For any valid input, `support < spot < resistance` when both are set,
    and `support` and `resistance` (when set) are strikes from the input."""
    contracts: list[OptionContract] = []
    strike_set: set[float] = set()
    for k, oi in strikes_oi:
        contracts.append(_contract(strike=k, option_type=OptionType.CALL, open_interest=oi))
        contracts.append(_contract(strike=k, option_type=OptionType.PUT, open_interest=oi))
        strike_set.add(k)

    r = compute_oi_walls(
        contracts=contracts,
        spot=spot,
        expiry_focus=[_EXPIRY],
        percentile_threshold=percentile,
    )

    if r.support is not None:
        assert r.support < spot
        assert r.support in strike_set
    if r.resistance is not None:
        assert r.resistance > spot
        assert r.resistance in strike_set
    if r.support is not None and r.resistance is not None:
        assert r.support < r.resistance
    assert r.total_oi >= 0
