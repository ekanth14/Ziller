import math
import pytest

from core.quant.levels.level7_derivatives import (
    black_scholes_call,
    black_scholes_put,
    black_scholes_price,
    verify_put_call_parity,
    compute_synthetic_price,
    compute_option_greeks,
    compute_implied_volatility,
    compute_gamma_pnl,
    compute_gamma_vol_arbitrage_pnl,
)


# ---------------------------------------------------------------------------
# Formula 7.1: Black-Scholes Pricing
# ---------------------------------------------------------------------------

def test_black_scholes_canonical_benchmark():
    # Canonical textbook values: S=100, K=100, T=1, r=0.05, sigma=0.20
    s = 100.0
    k = 100.0
    t = 1.0
    r = 0.05
    sigma = 0.20

    c = black_scholes_call(s, k, t, r, sigma)
    p = black_scholes_put(s, k, t, r, sigma)

    # Standard analytical benchmark: Call ≈ 10.4506, Put ≈ 5.5735
    assert pytest.approx(c, 1e-4) == 10.4506
    assert pytest.approx(p, 1e-4) == 5.5735
    assert pytest.approx(black_scholes_price("call", s, k, t, r, sigma), 1e-4) == c
    assert pytest.approx(black_scholes_price("put", s, k, t, r, sigma), 1e-4) == p


def test_black_scholes_boundary_conditions():
    s = 100.0
    k = 100.0
    r = 0.05
    sigma = 0.20

    # At expiration T <= 0: return intrinsic payoff
    # ITM call (S=110, K=100) -> 10.0
    assert black_scholes_call(110.0, 100.0, 0.0, r, sigma) == 10.0
    # OTM call (S=90, K=100) -> 0.0
    assert black_scholes_call(90.0, 100.0, 0.0, r, sigma) == 0.0
    # ITM put (S=90, K=100) -> 10.0
    assert black_scholes_put(90.0, 100.0, 0.0, r, sigma) == 10.0
    # ATM call and put at T=0
    assert black_scholes_call(100.0, 100.0, 0.0, r, sigma) == 0.0
    assert black_scholes_put(100.0, 100.0, 0.0, r, sigma) == 0.0

    # Negative T treated as expired (payoff)
    assert black_scholes_call(105.0, 100.0, -0.5, r, sigma) == 5.0

    # Zero volatility (deterministic payoff discounted)
    c_zero_vol = black_scholes_call(110.0, 100.0, 1.0, 0.05, 0.0)
    expected_c_zero = max(0.0, 110.0 - 100.0 * math.exp(-0.05))
    assert pytest.approx(c_zero_vol, 1e-5) == expected_c_zero

    # Negative prices or strikes
    with pytest.raises(ValueError):
        black_scholes_call(-100.0, 100.0, 1.0, r, sigma)
    with pytest.raises(ValueError):
        black_scholes_put(100.0, -100.0, 1.0, r, sigma)


# ---------------------------------------------------------------------------
# Formula 7.2: Put-Call Parity
# ---------------------------------------------------------------------------

def test_put_call_parity_exactness():
    # C - P = S - K * exp(-rT)
    s = 105.0
    k = 100.0
    t = 0.75
    r = 0.04
    sigma = 0.25

    c = black_scholes_call(s, k, t, r, sigma)
    p = black_scholes_put(s, k, t, r, sigma)

    discrepancy, lhs, rhs = verify_put_call_parity(c, p, s, k, t, r)
    assert abs(discrepancy) < 1e-7
    assert pytest.approx(lhs, 1e-7) == rhs

    # Synthetic prices
    syn_c = compute_synthetic_price("call", p, s, k, t, r)
    syn_p = compute_synthetic_price("put", c, s, k, t, r)
    assert pytest.approx(syn_c, 1e-6) == c
    assert pytest.approx(syn_p, 1e-6) == p


# ---------------------------------------------------------------------------
# Formula 7.3: Option Greeks
# ---------------------------------------------------------------------------

def test_option_greeks_values_and_symmetries():
    s = 100.0
    k = 100.0
    t = 1.0
    r = 0.05
    sigma = 0.20

    call_greeks = compute_option_greeks("call", s, k, t, r, sigma)
    put_greeks = compute_option_greeks("put", s, k, t, r, sigma)

    # 1. Delta: Call Delta in (0, 1), Put Delta in (-1, 0), Call Delta - Put Delta == 1
    assert 0.0 < call_greeks.delta < 1.0
    assert -1.0 < put_greeks.delta < 0.0
    assert pytest.approx(call_greeks.delta - put_greeks.delta, 1e-7) == 1.0

    # 2. Gamma: strictly positive, identical for call and put
    assert call_greeks.gamma > 0.0
    assert pytest.approx(call_greeks.gamma, 1e-7) == put_greeks.gamma

    # 3. Vega: strictly positive, identical for call and put
    assert call_greeks.vega > 0.0
    assert pytest.approx(call_greeks.vega, 1e-7) == put_greeks.vega

    # 4. Theta: negative for standard options
    assert call_greeks.theta < 0.0

    # 5. Rho: positive for call, negative for put
    assert call_greeks.rho > 0.0
    assert put_greeks.rho < 0.0


def test_option_greeks_boundary_at_expiration():
    # At T=0, Greeks must not raise ZeroDivisionError and behave consistently
    call_greeks_exp = compute_option_greeks("call", 110.0, 100.0, 0.0, 0.05, 0.2)
    assert call_greeks_exp.delta == 1.0
    assert call_greeks_exp.gamma == 0.0
    assert call_greeks_exp.vega == 0.0

    put_greeks_exp = compute_option_greeks("put", 110.0, 100.0, 0.0, 0.05, 0.2)
    assert put_greeks_exp.delta == 0.0
    assert put_greeks_exp.gamma == 0.0


# ---------------------------------------------------------------------------
# Formula 7.4: Implied Volatility Solver
# ---------------------------------------------------------------------------

def test_implied_volatility_roundtrip():
    s = 100.0
    k = 105.0
    t = 0.5
    r = 0.03
    true_vol = 0.32

    # Call IV roundtrip
    call_mkt = black_scholes_call(s, k, t, r, true_vol)
    solved_call_iv = compute_implied_volatility(call_mkt, "call", s, k, t, r)
    assert pytest.approx(solved_call_iv, 1e-5) == true_vol

    # Put IV roundtrip
    put_mkt = black_scholes_put(s, k, t, r, true_vol)
    solved_put_iv = compute_implied_volatility(put_mkt, "put", s, k, t, r)
    assert pytest.approx(solved_put_iv, 1e-5) == true_vol


def test_implied_volatility_boundaries():
    s = 100.0
    k = 100.0
    t = 0.5
    r = 0.03

    # Price below intrinsic value raises ValueError
    with pytest.raises(ValueError):
        compute_implied_volatility(0.0001, "call", 120.0, 100.0, t, r)

    # Expired option
    with pytest.raises(ValueError, match="Cannot invert implied volatility for expired option"):
        compute_implied_volatility(5.0, "call", s, k, 0.0, r)


# ---------------------------------------------------------------------------
# Formula 7.5: Gamma P&L
# ---------------------------------------------------------------------------

def test_gamma_pnl_taylor_approximation():
    # PnL = 0.5 * Gamma * (Delta S)^2 + Theta * Delta t
    gamma = 0.035
    theta = -12.50
    delta_s = 2.0
    delta_t = 1.0 / 365.0

    pnl = compute_gamma_pnl(gamma=gamma, delta_s=delta_s, theta=theta, delta_t=delta_t)
    expected_pnl = 0.5 * gamma * (delta_s ** 2) + theta * delta_t
    assert pytest.approx(pnl, 1e-7) == expected_pnl


def test_gamma_vol_arbitrage_pnl():
    # Volatility arbitrage: PnL = 0.5 * Gamma * S^2 * (sigma_realized^2 - sigma_implied^2) * Delta t
    gamma = 0.02
    s = 100.0
    delta_t = 1.0 / 252.0

    # Realized > Implied -> long gamma profits
    pnl_win = compute_gamma_vol_arbitrage_pnl(gamma, s, realized_vol=0.30, implied_vol=0.20, delta_t=delta_t)
    assert pnl_win > 0.0

    # Realized < Implied -> long gamma bleeds
    pnl_loss = compute_gamma_vol_arbitrage_pnl(gamma, s, realized_vol=0.15, implied_vol=0.20, delta_t=delta_t)
    assert pnl_loss < 0.0

    # Realized == Implied -> break-even
    pnl_even = compute_gamma_vol_arbitrage_pnl(gamma, s, realized_vol=0.20, implied_vol=0.20, delta_t=delta_t)
    assert pytest.approx(pnl_even, 1e-9) == 0.0
