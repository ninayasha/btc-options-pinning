import pytest
from src.options_math import (
    bs_gamma,
    calculate_gex_per_strike,
    calculate_gamma_flip,
    calculate_gex_plus_matrix,
)


def test_bs_gamma_edge_cases():
    # Safe against 0 or negative
    assert bs_gamma(0.0, 80000.0, 0.1, 0.5) == 0.0
    assert bs_gamma(80000.0, 0.0, 0.1, 0.5) == 0.0
    assert bs_gamma(80000.0, 80000.0, 0.0, 0.5) == 0.0
    assert bs_gamma(80000.0, 80000.0, 0.1, 0.0) == 0.0
    assert bs_gamma(-100.0, 80000.0, 0.1, 0.5) == 0.0

    # Normal calculation
    gamma = bs_gamma(80000.0, 80000.0, 1.0 / 365.0, 0.5)
    assert gamma > 0.0


def test_gex_calculation():
    spot = 80000.0
    t_years = 1.0 / 365.0
    strikes_data = [
        {"strike": 78000.0, "call_oi": 0.0, "put_oi": 100.0, "call_iv": 50.0, "put_iv": 50.0},
        {"strike": 82000.0, "call_oi": 100.0, "put_oi": 0.0, "call_iv": 50.0, "put_iv": 50.0},
    ]
    res_list, net_gex, call_gex, put_gex, max_strike, max_val = calculate_gex_per_strike(
        spot, strikes_data, t_years
    )
    # Dealer: long calls (positive), short puts (negative)
    assert call_gex > 0
    assert put_gex < 0
    assert round(net_gex, 2) == round(call_gex + put_gex, 2)
    assert max_strike in (78000.0, 82000.0)


def test_gamma_flip_finds_zero_crossing():
    spot = 80000.0
    t_years = 3.0 / 365.0
    # Create strike structure where puts dominate below 79000 and calls dominate above 81000
    strikes_data = [
        {"strike": 76000.0, "call_oi": 0.0, "put_oi": 1000.0, "call_iv": 40.0, "put_iv": 40.0},
        {"strike": 84000.0, "call_oi": 1000.0, "put_oi": 0.0, "call_iv": 40.0, "put_iv": 40.0},
    ]
    flip = calculate_gamma_flip(spot, strikes_data, t_years)
    assert flip is not None
    # Symmetrical so flip should be near 80000
    assert 78000.0 <= flip <= 82000.0


def test_gamma_flip_no_crossing():
    spot = 80000.0
    t_years = 1.0 / 365.0
    # Only calls -> all positive GEX everywhere
    strikes_data = [
        {"strike": 80000.0, "call_oi": 1000.0, "put_oi": 0.0, "call_iv": 50.0, "put_iv": 50.0},
    ]
    flip = calculate_gamma_flip(spot, strikes_data, t_years)
    # No crossing within +/- 15%
    assert flip is None


def test_gex_plus_matrix_computation():
    spot = 80000.0
    t_years = 5.0 / 365.0
    strikes_data = [
        {"strike": 75000.0, "call_oi": 50.0, "put_oi": 500.0, "call_iv": 45.0, "put_iv": 45.0},
        {"strike": 80000.0, "call_oi": 300.0, "put_oi": 200.0, "call_iv": 42.0, "put_iv": 42.0},
        {"strike": 85000.0, "call_oi": 600.0, "put_oi": 50.0, "call_iv": 48.0, "put_iv": 48.0},
    ]

    res = calculate_gex_plus_matrix(
        spot=spot,
        strikes_data=strikes_data,
        t_years=t_years,
        atm_iv=42.0,
        price_steps=21,
        iv_steps=15,
        price_range_pct=0.15,
        iv_range_pct=0.20,
    )

    assert len(res["prices"]) == 21
    assert len(res["ivs"]) == 15
    assert len(res["matrix"]) == 21
    assert len(res["matrix"][0]) == 15
    assert res["max_gex"] > 0
    assert res["min_gex"] < 0
    assert res["current_spot"] == spot
    assert res["current_iv"] == 42.0
    assert "max_gex_spot" in res
    assert "min_gex_spot" in res
    assert "current_net_gex" in res


def test_gex_plus_empty_data():
    res = calculate_gex_plus_matrix(0.0, [], 0.0, 0.0)
    assert res["matrix"] == []
    assert res["max_gex"] == 0.0
