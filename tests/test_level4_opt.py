import math
import pytest
import numpy as np
from core.quant.levels.level4_opt import (
    compute_taylor_expansion_1d,
    taylor_pnl_approximation,
    approximate_derivatives,
    gradient_descent,
    solve_lagrange_quadratic,
    solve_minimum_variance_portfolio,
    compute_markowitz_weights,
    compute_volatility_drag,
    check_jensen_inequality,
)

def test_taylor_expansion_and_greeks():
    # f(x) = x^2, x0 = 3, delta_x = 0.5
    # f(3) = 9, f'(3) = 6, f''(3) = 2
    # Taylor: 9 + 6 * 0.5 + 0.5 * 2 * (0.5)^2 = 9 + 3.0 + 0.25 = 12.25 = (3.5)^2 exact!
    approx = compute_taylor_expansion_1d(f_x0=9.0, df_x0=6.0, d2f_x0=2.0, delta_x=0.5)
    assert pytest.approx(approx, 1e-6) == 12.25

    # Finite difference derivatives
    df, d2f = approximate_derivatives(lambda x: x**2, x0=3.0)
    assert pytest.approx(df, 1e-4) == 6.0
    assert pytest.approx(d2f, 1e-4) == 2.0

    # Option P&L Greek approximation: Delta * dS + 0.5 * Gamma * (dS)^2 + Theta * dt
    # Delta = 0.5, Gamma = 0.05, dS = 2.0, Theta = -0.1, dt = 1.0
    # PnL = 0.5 * 2 + 0.5 * 0.05 * 4 + (-0.1) * 1 = 1.0 + 0.1 - 0.1 = 1.0
    pnl = taylor_pnl_approximation(delta=0.5, gamma=0.05, dS=2.0, theta=-0.1, dt=1.0)
    assert pytest.approx(pnl, 1e-6) == 1.0

def test_gradient_descent():
    # Minimize f(x, y) = (x - 2)^2 + (y + 3)^2
    # Optimum at (2, -3)
    def loss_and_grad(w: np.ndarray):
        x, y = w[0], w[1]
        loss = (x - 2.0) ** 2 + (y + 3.0) ** 2
        grad = np.array([2.0 * (x - 2.0), 2.0 * (y + 3.0)])
        return loss, grad

    res = gradient_descent(loss_and_grad, x0=np.array([0.0, 0.0]), lr=0.1, max_iters=200)
    assert res["converged"] is True
    assert pytest.approx(res["optimal_x"][0], 1e-4) == 2.0
    assert pytest.approx(res["optimal_x"][1], 1e-4) == -3.0

def test_lagrange_multipliers():
    # Min 0.5 * (x1^2 + x2^2) s.t. x1 + x2 = 1
    # Q = [[1, 0], [0, 1]], c = [0, 0], A = [[1, 1]], b = [1]
    # Optimum is x1 = 0.5, x2 = 0.5
    Q = np.eye(2)
    c = np.zeros(2)
    A = np.array([[1.0, 1.0]])
    b = np.array([1.0])

    x_opt, lmbda = solve_lagrange_quadratic(Q, c, A, b)
    assert pytest.approx(x_opt[0], 1e-5) == 0.5
    assert pytest.approx(x_opt[1], 1e-5) == 0.5

    # Minimum variance portfolio
    # Cov = diag([0.04, 0.16]) -> volatilities 0.2 and 0.4
    # Weights proportional to 1/var: 1/0.04 = 25, 1/0.16 = 6.25
    # w1 = 25 / 31.25 = 0.8, w2 = 6.25 / 31.25 = 0.2
    cov = np.diag([0.04, 0.16])
    min_var_w = solve_minimum_variance_portfolio(cov)
    assert pytest.approx(min_var_w[0], 1e-5) == 0.8
    assert pytest.approx(min_var_w[1], 1e-5) == 0.2
    assert pytest.approx(np.sum(min_var_w), 1e-5) == 1.0

def test_markowitz_weights():
    # 2 assets: mu = [0.10, 0.15], diag cov = [0.04, 0.09]
    mu = np.array([0.10, 0.15])
    cov = np.diag([0.04, 0.09])

    w = compute_markowitz_weights(mu, cov, risk_aversion=1.0, allow_short=True)
    # Sum of weights should equal 1.0
    assert pytest.approx(np.sum(w), 1e-5) == 1.0
    assert len(w) == 2

    # Long-only constraint (no shorting)
    w_long = compute_markowitz_weights(np.array([-0.05, 0.20]), cov, allow_short=False)
    assert np.all(w_long >= -1e-6)
    assert pytest.approx(np.sum(w_long), 1e-5) == 1.0
    # Asset with negative return should get 0 weight in long-only
    assert pytest.approx(w_long[0], 1e-4) == 0.0
    assert pytest.approx(w_long[1], 1e-4) == 1.0

def test_convexity_and_jensen_volatility_drag():
    # Volatility drag formula: g ≈ mu - sigma^2 / 2
    # mu = 0.10, sigma = 0.20 -> drag = 0.5 * 0.04 = 0.02 -> g = 0.08 (8%)
    drag_res = compute_volatility_drag(mean_return=0.10, volatility=0.20)
    assert pytest.approx(drag_res["drag"], 1e-6) == 0.02
    assert pytest.approx(drag_res["geometric_growth_rate"], 1e-6) == 0.08

    # Jensen's inequality: E[exp(X)] >= exp(E[X])
    x_samples = [-0.10, 0.0, 0.10]
    jensen = check_jensen_inequality(x_samples, convex_fn=math.exp)
    assert jensen["jensen_gap"] >= -1e-8
    assert jensen["holds"] is True
