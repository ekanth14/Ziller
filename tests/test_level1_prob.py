import math
import pytest
from core.quant.levels.level1_prob import (
    compute_bayes_update,
    compute_linear_expectation,
    compute_sample_variance,
    compute_variance_from_moments,
    compute_total_expectation,
    evaluate_distribution_density,
    evaluate_distribution_cdf,
)

def test_bayes_update():
    # Example: Prior P(A) = 0.01 (1% base rate of true regime).
    # Test accuracy: P(B|A) = 0.99, False alarm: P(B|~A) = 0.05
    # P(A|B) = (0.99 * 0.01) / (0.99 * 0.01 + 0.05 * 0.99) = 0.0099 / (0.0099 + 0.0495) = 0.1667 (16.7%)
    posterior = compute_bayes_update(prior_a=0.01, prob_b_given_a=0.99, prob_b_given_not_a=0.05)
    assert pytest.approx(posterior, 1e-4) == 0.166666

    # Edge cases
    assert compute_bayes_update(0.0, 0.9, 0.1) == 0.0
    assert compute_bayes_update(1.0, 0.9, 0.1) == 1.0

    # Denominator zero guard
    assert compute_bayes_update(0.5, 0.0, 0.0) == 0.5

    # Out of range priors raise ValueError
    with pytest.raises(ValueError):
        compute_bayes_update(1.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        compute_bayes_update(-0.1, 0.5, 0.5)

def test_linear_expectation():
    # E[X + Y] = E[X] + E[Y]
    # Sum of die rolls or portfolio expected returns
    asset_expectations = [0.05, 0.08, -0.02]
    weights = [0.5, 0.3, 0.2]
    total_exp = compute_linear_expectation(asset_expectations, weights)
    assert pytest.approx(total_exp, 1e-5) == (0.5 * 0.05 + 0.3 * 0.08 + 0.2 * -0.02)

    # Unweighted sum
    assert pytest.approx(compute_linear_expectation([1.0, 2.0, 3.0]), 1e-5) == 6.0

    # Empty sequence
    assert compute_linear_expectation([]) == 0.0

    # Weight length mismatch
    with pytest.raises(ValueError):
        compute_linear_expectation([1.0, 2.0], [0.5])

def test_sample_variance():
    # Fair die variance: E[X^2] - (E[X])^2 = 91/6 - (7/2)^2 = 35/12 ≈ 2.9167
    # Sample variance of [1, 2, 3, 4, 5, 6]
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    var_unbiased = compute_sample_variance(vals, ddof=1)
    # Sample variance with N-1: 3.5
    assert pytest.approx(var_unbiased, 1e-4) == 3.5
    # Population variance with N: 35/12 ≈ 2.9167
    var_pop = compute_sample_variance(vals, ddof=0)
    assert pytest.approx(var_pop, 1e-4) == 35.0 / 12.0

    # Single value returns 0.0
    assert compute_sample_variance([5.0], ddof=1) == 0.0
    assert compute_sample_variance([], ddof=1) == 0.0

    # Moment formula Var(X) = E[X^2] - (E[X])^2
    var_mom = compute_variance_from_moments(e_x=3.5, e_x2=91.0 / 6.0)
    assert pytest.approx(var_mom, 1e-4) == 35.0 / 12.0

def test_total_expectation():
    # Law of Total Expectation: Bull (60%, return 15%), Bear (40%, return -10%)
    # E[R] = 0.6 * 0.15 + 0.4 * (-0.10) = 0.09 - 0.04 = 0.05 (5%)
    cond_exp = [0.15, -0.10]
    probs = [0.60, 0.40]
    assert pytest.approx(compute_total_expectation(cond_exp, probs), 1e-5) == 0.05

    # Normalize unnormalized probabilities
    unnorm_probs = [6.0, 4.0]
    assert pytest.approx(compute_total_expectation(cond_exp, unnorm_probs), 1e-5) == 0.05

    # Mismatch length
    with pytest.raises(ValueError):
        compute_total_expectation([1.0], [0.5, 0.5])

def test_distribution_densities():
    # Normal distribution at mean has peak 1 / (sigma * sqrt(2*pi))
    norm_peak = evaluate_distribution_density("gaussian", x=0.0, mu=0.0, sigma=1.0)
    assert pytest.approx(norm_peak, 1e-4) == 1.0 / math.sqrt(2 * math.pi)

    # Student-t has fatter tails than Gaussian at 3 sigma
    t_density = evaluate_distribution_density("student_t", x=3.0, df=3)
    norm_density = evaluate_distribution_density("gaussian", x=3.0, mu=0.0, sigma=1.0)
    assert t_density > norm_density

    # Poisson distribution (trade arrival rate lambda = 4.0)
    # P(X = 4) = (4^4 * e^-4) / 4! = 256 * 0.0183156 / 24 ≈ 0.195366
    poisson_pmf = evaluate_distribution_density("poisson", x=4, lam=4.0)
    assert pytest.approx(poisson_pmf, 1e-4) == 0.195366

    # Exponential distribution (lambda = 2.0 at x = 1.0 -> 2 * e^-2 ≈ 0.27067)
    exp_pdf = evaluate_distribution_density("exponential", x=1.0, rate=2.0)
    assert pytest.approx(exp_pdf, 1e-4) == 2.0 * math.exp(-2.0)

    # Uniform distribution [0, 5] -> density = 1/5 = 0.2
    uni_pdf = evaluate_distribution_density("uniform", x=2.5, low=0.0, high=5.0)
    assert pytest.approx(uni_pdf, 1e-4) == 0.2
    assert evaluate_distribution_density("uniform", x=6.0, low=0.0, high=5.0) == 0.0

def test_distribution_cdfs():
    # Gaussian CDF at mean is 0.5
    assert pytest.approx(evaluate_distribution_cdf("gaussian", x=0.0, mu=0.0, sigma=1.0), 1e-5) == 0.5

    # Uniform CDF at midpoint is 0.5
    assert pytest.approx(evaluate_distribution_cdf("uniform", x=2.5, low=0.0, high=5.0), 1e-5) == 0.5

    # Exponential CDF at x=0 is 0.0, at inf is 1.0
    assert pytest.approx(evaluate_distribution_cdf("exponential", x=0.0, rate=1.0), 1e-5) == 0.0
    assert pytest.approx(evaluate_distribution_cdf("exponential", x=10.0, rate=1.0), 1e-4) == 1.0
