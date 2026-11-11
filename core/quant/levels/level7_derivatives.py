"""Level 7: Derivatives Pricing & Greeks Engine (Formulas 7.1 - 7.5).

Formulas:
7.1 Black-Scholes Pricing: Call C = S*N(d1) - K*exp(-rT)*N(d2), Put P = K*exp(-rT)*N(-d2) - S*N(-d1)
7.2 Put-Call Parity: C - P = S - K * exp(-rT)
7.3 Option Greeks: Delta, Gamma, Theta, Vega, Rho
7.4 Implied Volatility Solver: Inverts C_mkt = C_BS(sigma) via Newton-Raphson / Brent
7.5 Gamma P&L: P&L_gamma = 0.5 * Gamma * (Delta S)^2 + Theta * Delta t
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal
from scipy.optimize import brentq


# Helper normal distribution functions
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function N'(x)."""
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function N(x)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class OptionGreeks:
    """Analytical option Greeks."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


# ---------------------------------------------------------------------------
# Formula 7.1: Black-Scholes Pricing
# ---------------------------------------------------------------------------

def _d1_d2(s: float, k: float, t: float, r: float, sigma: float) -> tuple[float, float]:
    """Calculate d1 and d2 for Black-Scholes."""
    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def black_scholes_call(s: float, k: float, t: float, r: float, sigma: float) -> float:
    """Price a European Call Option under Black-Scholes model:

    C = S * N(d1) - K * exp(-r*T) * N(d2)

    Boundary handling:
    - T <= 0: intrinsic payoff max(0.0, S - K)
    - sigma <= 0: discounted intrinsic payoff max(0.0, S - K * exp(-r*T))
    - S <= 0 or K <= 0: raises ValueError
    """
    if s <= 0.0 or k <= 0.0:
        raise ValueError(f"Underlying price s and strike k must be strictly positive: {s=}, {k=}")

    if t <= 0.0:
        return max(0.0, s - k)

    if sigma <= 1e-12:
        return max(0.0, s - k * math.exp(-r * t))

    d1, d2 = _d1_d2(s, k, t, r, sigma)
    return s * _norm_cdf(d1) - k * math.exp(-r * t) * _norm_cdf(d2)


def black_scholes_put(s: float, k: float, t: float, r: float, sigma: float) -> float:
    """Price a European Put Option under Black-Scholes model:

    P = K * exp(-r*T) * N(-d2) - S * N(-d1)

    Boundary handling:
    - T <= 0: intrinsic payoff max(0.0, K - S)
    - sigma <= 0: discounted intrinsic payoff max(0.0, K * exp(-r*T) - S)
    - S <= 0 or K <= 0: raises ValueError
    """
    if s <= 0.0 or k <= 0.0:
        raise ValueError(f"Underlying price s and strike k must be strictly positive: {s=}, {k=}")

    if t <= 0.0:
        return max(0.0, k - s)

    if sigma <= 1e-12:
        return max(0.0, k * math.exp(-r * t) - s)

    d1, d2 = _d1_d2(s, k, t, r, sigma)
    return k * math.exp(-r * t) * _norm_cdf(-d2) - s * _norm_cdf(-d1)


def black_scholes_price(
    option_type: Literal["call", "put"] | str,
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
) -> float:
    """Universal Black-Scholes pricer for European call or put."""
    opt_lower = option_type.lower()
    if opt_lower == "call":
        return black_scholes_call(s, k, t, r, sigma)
    elif opt_lower == "put":
        return black_scholes_put(s, k, t, r, sigma)
    else:
        raise ValueError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")


# ---------------------------------------------------------------------------
# Formula 7.2: Put-Call Parity
# ---------------------------------------------------------------------------

def verify_put_call_parity(
    call_price: float,
    put_price: float,
    s: float,
    k: float,
    t: float,
    r: float,
) -> tuple[float, float, float]:
    """Verify Put-Call Parity: C - P = S - K * exp(-r*T).

    Returns:
        (discrepancy, lhs_c_minus_p, rhs_s_minus_discounted_k)
    """
    lhs = call_price - put_price
    rhs = s - k * math.exp(-r * t)
    discrepancy = abs(lhs - rhs)
    return discrepancy, lhs, rhs


def compute_synthetic_price(
    target_type: Literal["call", "put"] | str,
    counterpart_price: float,
    s: float,
    k: float,
    t: float,
    r: float,
) -> float:
    """Synthesize European option price using Put-Call Parity:

    Synthetic Call: C = P + S - K * exp(-r*T)
    Synthetic Put:  P = C - S + K * exp(-r*T)
    """
    discounted_k = k * math.exp(-r * t)
    opt_lower = target_type.lower()
    if opt_lower == "call":
        return counterpart_price + s - discounted_k
    elif opt_lower == "put":
        return counterpart_price - s + discounted_k
    else:
        raise ValueError(f"Invalid target_type: {target_type}. Must be 'call' or 'put'.")


# ---------------------------------------------------------------------------
# Formula 7.3: Option Greeks
# ---------------------------------------------------------------------------

def compute_option_greeks(
    option_type: Literal["call", "put"] | str,
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
) -> OptionGreeks:
    """Compute the 5 primary analytical Black-Scholes Greeks:

    Delta: dC/dS = N(d1), dP/dS = N(d1) - 1
    Gamma: d^2V/dS^2 = N'(d1) / (S * sigma * sqrt(T))  (identical for call/put)
    Theta: dV/dt (annualized time decay)
    Vega:  dV/d(sigma) = S * sqrt(T) * N'(d1)         (identical for call/put)
    Rho:   dV/dr
    """
    if s <= 0.0 or k <= 0.0:
        raise ValueError(f"Underlying price s and strike k must be strictly positive: {s=}, {k=}")

    opt_lower = option_type.lower()
    if opt_lower not in ("call", "put"):
        raise ValueError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")

    # Boundary handling for expired option
    if t <= 0.0:
        if opt_lower == "call":
            if s > k:
                delta = 1.0
            elif s < k:
                delta = 0.0
            else:
                delta = 0.5
        else:
            if s < k:
                delta = -1.0
            elif s > k:
                delta = 0.0
            else:
                delta = -0.5
        return OptionGreeks(delta=delta, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)

    # Boundary handling for zero volatility
    if sigma <= 1e-12:
        discounted_k = k * math.exp(-r * t)
        if opt_lower == "call":
            delta = 1.0 if s > discounted_k else 0.0
            rho = t * discounted_k if s > discounted_k else 0.0
        else:
            delta = -1.0 if s < discounted_k else 0.0
            rho = -t * discounted_k if s < discounted_k else 0.0
        return OptionGreeks(delta=delta, gamma=0.0, theta=0.0, vega=0.0, rho=rho)

    sqrt_t = math.sqrt(t)
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    n_prime_d1 = _norm_pdf(d1)
    discount_factor = math.exp(-r * t)

    # Gamma and Vega are identical for European Call and Put
    gamma = n_prime_d1 / (s * sigma * sqrt_t)
    vega = s * sqrt_t * n_prime_d1

    if opt_lower == "call":
        delta = _norm_cdf(d1)
        theta = -(s * n_prime_d1 * sigma) / (2.0 * sqrt_t) - r * k * discount_factor * _norm_cdf(d2)
        rho = k * t * discount_factor * _norm_cdf(d2)
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = -(s * n_prime_d1 * sigma) / (2.0 * sqrt_t) + r * k * discount_factor * _norm_cdf(-d2)
        rho = -k * t * discount_factor * _norm_cdf(-d2)

    return OptionGreeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


# ---------------------------------------------------------------------------
# Formula 7.4: Implied Volatility Solver
# ---------------------------------------------------------------------------

def compute_implied_volatility(
    price: float,
    option_type: Literal["call", "put"] | str,
    s: float,
    k: float,
    t: float,
    r: float,
    initial_guess: float = 0.20,
    max_iter: int = 100,
    tol: float = 1e-7,
) -> float:
    """Solve for implied volatility sigma such that Black-Scholes price == market price.

    Uses high-speed Newton-Raphson iteration with robust Brent method fallback.
    """
    if t <= 0.0:
        raise ValueError(f"Cannot invert implied volatility for expired option: {t=}")
    if s <= 0.0 or k <= 0.0:
        raise ValueError(f"Prices must be strictly positive: {s=}, {k=}")

    opt_lower = option_type.lower()
    if opt_lower not in ("call", "put"):
        raise ValueError(f"Invalid option_type: {option_type}")

    # No-arbitrage bound check
    discounted_k = k * math.exp(-r * t)
    if opt_lower == "call":
        intrinsic = max(0.0, s - discounted_k)
        max_price = s
    else:
        intrinsic = max(0.0, discounted_k - s)
        max_price = discounted_k

    if price < intrinsic or price > max_price:
        raise ValueError(
            f"Market price {price} violates theoretical no-arbitrage bounds [{intrinsic}, {max_price}]"
        )

    # Newton-Raphson iteration
    sigma = initial_guess
    for _ in range(max_iter):
        bs_p = black_scholes_price(opt_lower, s, k, t, r, sigma)
        diff = bs_p - price
        if abs(diff) < tol:
            return sigma

        greeks = compute_option_greeks(opt_lower, s, k, t, r, sigma)
        vega = greeks.vega
        if vega < 1e-8:
            break

        step = diff / vega
        sigma_next = sigma - step
        if sigma_next <= 1e-5 or sigma_next > 10.0:
            break
        sigma = sigma_next

    # Brent fallback if Newton did not converge
    def objective(sig: float) -> float:
        return black_scholes_price(opt_lower, s, k, t, r, sig) - price

    try:
        return float(brentq(objective, 1e-4, 10.0, xtol=tol))
    except Exception as exc:
        raise ValueError(f"Failed to converge on implied volatility: {exc}") from exc


# ---------------------------------------------------------------------------
# Formula 7.5: Gamma P&L
# ---------------------------------------------------------------------------

def compute_gamma_pnl(
    gamma: float,
    delta_s: float,
    theta: float,
    delta_t: float,
) -> float:
    """Compute second-order option P&L under Delta-neutral hedging (Taylor approximation):

    P&L_gamma = 0.5 * Gamma * (Delta S)^2 + Theta * Delta t
    """
    return 0.5 * gamma * (delta_s ** 2) + theta * delta_t


def compute_gamma_vol_arbitrage_pnl(
    gamma: float,
    s: float,
    realized_vol: float,
    implied_vol: float,
    delta_t: float,
) -> float:
    """Compute realized vs implied volatility arbitrage payoff for a delta-hedged position:

    P&L = 0.5 * Gamma * S^2 * (sigma_realized^2 - sigma_implied^2) * Delta t
    """
    return 0.5 * gamma * (s ** 2) * (realized_vol ** 2 - implied_vol ** 2) * delta_t
