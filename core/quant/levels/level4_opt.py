"""Level 4: Calculus & Optimization Engine (Formulas 4.1 - 4.5).

Formulas:
4.1 Taylor Expansion: f(x) ≈ f(x0) + f'(x0) * dx + 0.5 * f''(x0) * (dx)^2
4.2 Gradient Descent: theta_{t+1} = theta_t - eta_t * grad(L)
4.3 Lagrange Multipliers: L(x, lambda) = f(x) - lambda * g(x); KKT quadratic system
4.4 Mean-Variance Markowitz: w^* = (1 / gamma) * Sigma^(-1) * mu, normalized sum(w) = 1
4.5 Convexity & Jensen's Inequality: E[f(X)] >= f(E[X]); Volatility Drag g ≈ mu - sigma^2 / 2
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional, Sequence
import numpy as np
from scipy.optimize import minimize

from core.quant.levels.level3_linalg import safe_matrix_inverse


def compute_taylor_expansion_1d(
    f_x0: float,
    df_x0: float,
    d2f_x0: float,
    delta_x: float,
) -> float:
    """Second-order Taylor expansion approximation: f(x0 + dx) ≈ f(x0) + f'(x0)*dx + 0.5*f''(x0)*(dx)^2.

    Formula 4.1.
    """
    return float(f_x0 + df_x0 * delta_x + 0.5 * d2f_x0 * (delta_x ** 2))


def approximate_derivatives(
    f: Callable[[float], float],
    x0: float,
    h: float = 1e-5,
) -> tuple[float, float]:
    """Numerically approximate first and second derivatives via central differences.

    Formula 4.1.

    Returns:
        tuple (f'(x0), f''(x0)).
    """
    f_plus = f(x0 + h)
    f_minus = f(x0 - h)
    f_mid = f(x0)

    df = (f_plus - f_minus) / (2.0 * h)
    d2f = (f_plus - 2.0 * f_mid + f_minus) / (h ** 2)
    return float(df), float(d2f)


def taylor_pnl_approximation(
    delta: float,
    gamma: float,
    dS: float,
    theta: float = 0.0,
    dt: float = 0.0,
) -> float:
    """Approximate derivative instrument P&L using Delta-Gamma-Theta Taylor expansion.

    Formula 4.1:
        PnL ≈ Delta * dS + 0.5 * Gamma * (dS)^2 + Theta * dt
    """
    return float(delta * dS + 0.5 * gamma * (dS ** 2) + theta * dt)


def gradient_descent(
    loss_and_grad_fn: Callable[[np.ndarray], tuple[float, np.ndarray]],
    x0: Sequence[float] | np.ndarray,
    lr: float = 0.01,
    max_iters: int = 1000,
    tol: float = 1e-6,
    lr_decay: float = 1.0,
) -> dict[str, Any]:
    """Optimize parameters via Gradient Descent with learning rate decay.

    Formula 4.2:
        theta_{t+1} = theta_t - eta_t * grad(L(theta_t))

    Args:
        loss_and_grad_fn: Callable taking x (ndarray) and returning (loss, grad).
        x0: Initial parameter vector.
        lr: Initial step size / learning rate.
        max_iters: Maximum iterations.
        tol: Gradient norm convergence tolerance.
        lr_decay: Multiplicative decay factor per step (default 1.0 = constant).

    Returns:
        dict containing:
            - optimal_x: Best parameter vector found.
            - final_loss: Value of loss at optimal_x.
            - iterations: Number of iterations executed.
            - converged: Boolean flag indicating if ||grad|| < tol.
            - history: List of loss values across iterations.
    """
    x = np.asarray(x0, dtype=float).copy()
    current_lr = lr
    history: list[float] = []
    converged = False

    for it in range(max_iters):
        loss, grad = loss_and_grad_fn(x)
        history.append(float(loss))

        grad_norm = float(np.linalg.norm(grad))
        if grad_norm < tol:
            converged = True
            break

        x -= current_lr * grad
        current_lr *= lr_decay

    final_loss, _ = loss_and_grad_fn(x)

    return {
        "optimal_x": x,
        "final_loss": float(final_loss),
        "iterations": it + 1 if not converged else it,
        "converged": converged,
        "history": history,
    }


def solve_lagrange_quadratic(
    q_matrix: np.ndarray | Sequence[Sequence[float]],
    c_vector: np.ndarray | Sequence[float],
    a_eq: np.ndarray | Sequence[Sequence[float]],
    b_eq: np.ndarray | Sequence[float],
) -> tuple[np.ndarray, np.ndarray]:
    """Solve equality-constrained quadratic program analytically via Karush-Kuhn-Tucker (KKT) system.

    Formula 4.3:
        Minimize (1/2) x^T Q x + c^T x
        Subject to A_eq x = b_eq

        KKT Block System:
        [ Q    A^T ] [ x      ] = [ -c ]
        [ A     0  ] [ lambda ]   [  b ]

    Returns:
        tuple (optimal_x, optimal_lambda).
    """
    Q = np.asarray(q_matrix, dtype=float)
    c = np.asarray(c_vector, dtype=float).flatten()
    A = np.asarray(a_eq, dtype=float)
    b = np.asarray(b_eq, dtype=float).flatten()

    n = Q.shape[0]
    m = A.shape[0]

    # Build KKT system
    kkt_top = np.hstack([Q, A.T])
    kkt_bottom = np.hstack([A, np.zeros((m, m))])
    KKT = np.vstack([kkt_top, kkt_bottom])

    rhs = np.concatenate([-c, b])

    sol, residuals, rank, s = np.linalg.lstsq(KKT, rhs, rcond=1e-10)
    x_opt = sol[:n]
    lambda_opt = sol[n:]

    return x_opt, lambda_opt


def solve_minimum_variance_portfolio(
    cov_matrix: np.ndarray | Sequence[Sequence[float]],
) -> np.ndarray:
    """Find weights of the global minimum variance portfolio subject to sum(w) = 1.

    Formula 4.3:
        w^* = (Sigma^(-1) * 1) / (1^T * Sigma^(-1) * 1)

    Args:
        cov_matrix: Covariance matrix of asset returns.

    Returns:
        Optimal weight vector w^* (sum = 1.0).
    """
    cov = np.asarray(cov_matrix, dtype=float)
    p = cov.shape[0]
    ones = np.ones(p, dtype=float)

    inv_cov = safe_matrix_inverse(cov)
    inv_ones = inv_cov @ ones
    denom = float(ones @ inv_ones)

    if abs(denom) <= 1e-15:
        return np.full(p, 1.0 / p)

    weights = inv_ones / denom
    return weights


def compute_markowitz_weights(
    expected_returns: Sequence[float] | np.ndarray,
    cov_matrix: Sequence[Sequence[float]] | np.ndarray,
    risk_aversion: float = 1.0,
    allow_short: bool = True,
    target_return: Optional[float] = None,
) -> np.ndarray:
    """Compute optimal Mean-Variance Markowitz portfolio weights.

    Formula 4.4:
        Max w^T mu - (gamma / 2) * w^T Sigma w
        Subject to sum(w) = 1 and (optional) w >= 0, w^T mu = target_return

    Args:
        expected_returns: Vector of expected asset returns mu.
        cov_matrix: Asset returns covariance matrix Sigma.
        risk_aversion: gamma >= 0, risk aversion parameter (higher = more conservative).
        allow_short: If False, enforces long-only constraints (w_i >= 0).
        target_return: Optional constraint on expected portfolio return.

    Returns:
        Optimal weights array w^* of shape (n_assets,), normalized to sum 1.0.
    """
    mu = np.asarray(expected_returns, dtype=float).flatten()
    cov = np.asarray(cov_matrix, dtype=float)
    n = len(mu)

    if n == 0:
        return np.array([])
    if n == 1:
        return np.array([1.0])

    gamma = max(1e-4, float(risk_aversion))

    # If long-only or target_return is constrained, solve numerically via SLSQP
    if not allow_short or target_return is not None:
        def objective(w):
            return 0.5 * gamma * float(w @ cov @ w) - float(w @ mu)

        def grad(w):
            return gamma * (cov @ w) - mu

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        if target_return is not None:
            constraints.append({"type": "eq", "fun": lambda w: float(w @ mu) - target_return})

        bounds = [(0.0, 1.0) for _ in range(n)] if not allow_short else [(None, None) for _ in range(n)]

        w0 = np.full(n, 1.0 / n)
        res = minimize(
            objective,
            w0,
            jac=grad,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-9, "maxiter": 500},
        )
        if res.success:
            w_opt = res.x
            # Normalize to avoid floating drift
            s = np.sum(w_opt)
            return w_opt / s if s > 1e-15 else w0
        # If optimization fails, fallback to analytical or projection

    # Analytical unconstrained tangency / mean-variance weights
    inv_cov = safe_matrix_inverse(cov)
    raw_weights = (1.0 / gamma) * (inv_cov @ mu)
    total_w = float(np.sum(raw_weights))

    if abs(total_w) <= 1e-15:
        # Fallback to minimum variance portfolio
        return solve_minimum_variance_portfolio(cov)

    return raw_weights / total_w


def compute_volatility_drag(
    mean_return: float,
    volatility: float,
) -> dict[str, float]:
    """Calculate compounding volatility drag and effective geometric growth rate via Jensen's Inequality.

    Formula 4.5:
        g ≈ mu - (sigma^2 / 2)

    Args:
        mean_return: Arithmetic mean return mu.
        volatility: Standard deviation of returns sigma.

    Returns:
        dict containing:
            - drag: Volatility drag = 0.5 * sigma^2.
            - geometric_growth_rate: Effective compounded growth rate g.
    """
    drag = 0.5 * (volatility ** 2)
    g = mean_return - drag
    return {
        "drag": float(drag),
        "geometric_growth_rate": float(g),
    }


def check_jensen_inequality(
    values: Sequence[float],
    convex_fn: Callable[[float], float],
    probs: Optional[Sequence[float]] = None,
) -> dict[str, Any]:
    """Verify Jensen's inequality for a convex function: E[f(X)] >= f(E[X]).

    Formula 4.5.

    Args:
        values: Numerical outcomes X.
        convex_fn: Function guaranteed or assumed convex (e.g. exp, x^2, -log).
        probs: Probabilities of outcomes (defaults to uniform 1/N).

    Returns:
        dict containing:
            - exp_f_x: E[f(X)].
            - f_exp_x: f(E[X]).
            - jensen_gap: E[f(X)] - f(E[X]) (must be >= 0 for convex f).
            - holds: Boolean indicating whether inequality holds within numerical tolerance.
    """
    n = len(values)
    if n == 0:
        return {"exp_f_x": 0.0, "f_exp_x": 0.0, "jensen_gap": 0.0, "holds": True}

    if probs is None:
        p = np.full(n, 1.0 / n)
    else:
        p_arr = np.asarray(probs, dtype=float)
        p = p_arr / np.sum(p_arr)

    vals = np.asarray(values, dtype=float)
    e_x = float(np.sum(p * vals))

    f_vals = np.array([convex_fn(x) for x in vals], dtype=float)
    exp_f_x = float(np.sum(p * f_vals))
    f_exp_x = float(convex_fn(e_x))

    jensen_gap = exp_f_x - f_exp_x
    holds = bool(jensen_gap >= -1e-7)

    return {
        "exp_f_x": exp_f_x,
        "f_exp_x": f_exp_x,
        "jensen_gap": jensen_gap,
        "holds": holds,
    }
