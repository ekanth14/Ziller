"""Level 1: Probability Engine (Formulas 1.1 - 1.5).

Formulas:
1.1 Bayes' Rule: P(A|B) = P(B|A)P(A) / [P(B|A)P(A) + P(B|~A)P(~A)]
1.2 Linearity of Expectation: E[sum X_i] = sum E[X_i]
1.3 Variance: Var(X) = E[X^2] - (E[X])^2
1.4 Total Expectation: E[X] = sum_y E[X|Y=y] P(Y=y)
1.5 Key Distributions: Density & CDF for Gaussian, Student-t, Poisson, Exponential, Uniform
"""

from __future__ import annotations

import math
from typing import Optional, Sequence
import scipy.stats as stats


def compute_bayes_update(
    prior_a: float,
    prob_b_given_a: float,
    prob_b_given_not_a: float,
) -> float:
    """Calculate posterior probability using Bayes' Rule.

    Formula 1.1:
        P(A|B) = P(B|A) * P(A) / [P(B|A) * P(A) + P(B|~A) * (1 - P(A))]

    Args:
        prior_a: P(A), prior probability of hypothesis A, in [0, 1].
        prob_b_given_a: P(B|A), likelihood of evidence B given A is true, in [0, 1].
        prob_b_given_not_a: P(B|~A), false alarm rate given A is false, in [0, 1].

    Returns:
        Posterior probability P(A|B) in [0, 1].
    """
    if not (0.0 <= prior_a <= 1.0):
        raise ValueError(f"prior_a must be in [0, 1], got {prior_a}")
    if not (0.0 <= prob_b_given_a <= 1.0):
        raise ValueError(f"prob_b_given_a must be in [0, 1], got {prob_b_given_a}")
    if not (0.0 <= prob_b_given_not_a <= 1.0):
        raise ValueError(f"prob_b_given_not_a must be in [0, 1], got {prob_b_given_not_a}")

    if prior_a == 0.0:
        return 0.0
    if prior_a == 1.0:
        return 1.0

    numerator = prob_b_given_a * prior_a
    denominator = numerator + prob_b_given_not_a * (1.0 - prior_a)

    if denominator <= 1e-15:
        # Zero evidence / undefined update -> preserve prior
        return prior_a

    posterior = numerator / denominator
    return max(0.0, min(1.0, posterior))


def compute_linear_expectation(
    expectations: Sequence[float],
    weights: Optional[Sequence[float]] = None,
) -> float:
    """Calculate the expected value of a linear combination of random variables.

    Formula 1.2:
        E[sum c_i X_i] = sum c_i E[X_i]

    Args:
        expectations: Sequence of expected values E[X_i].
        weights: Optional coefficients/weights c_i. If None, all c_i = 1.0.

    Returns:
        Combined linear expectation.
    """
    if not expectations:
        return 0.0

    if weights is None:
        return float(sum(expectations))

    if len(expectations) != len(weights):
        raise ValueError(
            f"Length mismatch: {len(expectations)} expectations vs {len(weights)} weights"
        )

    return float(sum(w * e for w, e in zip(weights, expectations)))


def compute_sample_variance(
    values: Sequence[float],
    ddof: int = 1,
) -> float:
    """Calculate sample variance with zero-division safety.

    Formula 1.3:
        Var(X) = (1 / (N - ddof)) * sum (x_i - mean(X))^2

    Args:
        values: Sequence of numerical observations.
        ddof: Delta degrees of freedom (default 1 for unbiased sample variance).

    Returns:
        Sample variance (>= 0.0).
    """
    n = len(values)
    if n <= ddof:
        return 0.0

    mean_val = sum(values) / n
    var = sum((x - mean_val) ** 2 for x in values) / (n - ddof)
    return max(0.0, float(var))


def compute_variance_from_moments(
    e_x: float,
    e_x2: float,
) -> float:
    """Calculate variance directly from first and second raw moments.

    Formula 1.3:
        Var(X) = E[X^2] - (E[X])^2

    Args:
        e_x: First moment E[X].
        e_x2: Second moment E[X^2].

    Returns:
        Variance (>= 0.0).
    """
    var = e_x2 - (e_x ** 2)
    return max(0.0, float(var))


def compute_total_expectation(
    conditional_expectations: Sequence[float],
    probabilities: Sequence[float],
) -> float:
    """Calculate total expectation across disjoint partition / market regimes.

    Formula 1.4:
        E[X] = sum_y E[X|Y=y] * P(Y=y)

    Args:
        conditional_expectations: Expected values in each regime/scenario.
        probabilities: Probabilities of each regime/scenario.

    Returns:
        Weighted total expectation.
    """
    if len(conditional_expectations) != len(probabilities):
        raise ValueError(
            f"Length mismatch: {len(conditional_expectations)} cond expectations vs {len(probabilities)} probabilities"
        )
    if not conditional_expectations:
        return 0.0

    total_prob = sum(probabilities)
    if total_prob <= 1e-15:
        return 0.0

    # Auto-normalize probabilities if needed
    normalized_probs = [p / total_prob for p in probabilities]
    return float(sum(e * p for e, p in zip(conditional_expectations, normalized_probs)))


def evaluate_distribution_density(
    dist_type: str,
    x: float,
    **params,
) -> float:
    """Evaluate the probability density function (or PMF) for key quant distributions.

    Formula 1.5:
        Gaussian, Student-t, Poisson, Exponential, Uniform

    Args:
        dist_type: Distribution name ('gaussian'/'normal', 'student_t'/'t', 'poisson', 'exponential', 'uniform').
        x: Point at which to evaluate density.
        **params: Distribution parameters.

    Returns:
        Density or mass value (>= 0.0).
    """
    name = dist_type.lower().strip()

    if name in ("gaussian", "normal"):
        mu = float(params.get("mu", 0.0))
        sigma = float(params.get("sigma", 1.0))
        if sigma <= 0.0:
            raise ValueError(f"sigma must be positive, got {sigma}")
        return float(stats.norm.pdf(x, loc=mu, scale=sigma))

    elif name in ("student_t", "t"):
        df = float(params.get("df", 3.0))
        loc = float(params.get("loc", params.get("mu", 0.0)))
        scale = float(params.get("scale", params.get("sigma", 1.0)))
        if df <= 0.0 or scale <= 0.0:
            raise ValueError(f"df and scale must be positive, got {df=}, {scale=}")
        return float(stats.t.pdf(x, df=df, loc=loc, scale=scale))

    elif name == "poisson":
        lam = float(params.get("lam", params.get("rate", 1.0)))
        if lam <= 0.0:
            raise ValueError(f"Poisson lambda must be positive, got {lam}")
        k = int(round(x))
        if k < 0:
            return 0.0
        return float(stats.poisson.pmf(k, mu=lam))

    elif name == "exponential":
        rate = float(params.get("rate", params.get("lam", 1.0)))
        if rate <= 0.0:
            raise ValueError(f"Exponential rate must be positive, got {rate}")
        if x < 0.0:
            return 0.0
        scale = 1.0 / rate
        return float(stats.expon.pdf(x, scale=scale))

    elif name == "uniform":
        low = float(params.get("low", 0.0))
        high = float(params.get("high", 1.0))
        if high <= low:
            raise ValueError(f"high must be greater than low, got {low=}, {high=}")
        if low <= x <= high:
            return 1.0 / (high - low)
        return 0.0

    else:
        raise ValueError(f"Unsupported distribution type: {dist_type}")


def evaluate_distribution_cdf(
    dist_type: str,
    x: float,
    **params,
) -> float:
    """Evaluate cumulative distribution function for key quant distributions.

    Formula 1.5.

    Args:
        dist_type: Distribution name ('gaussian'/'normal', 'student_t'/'t', 'poisson', 'exponential', 'uniform').
        x: Evaluation point.
        **params: Distribution parameters.

    Returns:
        Cumulative probability in [0, 1].
    """
    name = dist_type.lower().strip()

    if name in ("gaussian", "normal"):
        mu = float(params.get("mu", 0.0))
        sigma = float(params.get("sigma", 1.0))
        if sigma <= 0.0:
            raise ValueError(f"sigma must be positive, got {sigma}")
        return float(stats.norm.cdf(x, loc=mu, scale=sigma))

    elif name in ("student_t", "t"):
        df = float(params.get("df", 3.0))
        loc = float(params.get("loc", params.get("mu", 0.0)))
        scale = float(params.get("scale", params.get("sigma", 1.0)))
        if df <= 0.0 or scale <= 0.0:
            raise ValueError(f"df and scale must be positive, got {df=}, {scale=}")
        return float(stats.t.cdf(x, df=df, loc=loc, scale=scale))

    elif name == "poisson":
        lam = float(params.get("lam", params.get("rate", 1.0)))
        if lam <= 0.0:
            raise ValueError(f"Poisson lambda must be positive, got {lam}")
        k = int(math.floor(x))
        if k < 0:
            return 0.0
        return float(stats.poisson.cdf(k, mu=lam))

    elif name == "exponential":
        rate = float(params.get("rate", params.get("lam", 1.0)))
        if rate <= 0.0:
            raise ValueError(f"Exponential rate must be positive, got {rate}")
        if x <= 0.0:
            return 0.0
        scale = 1.0 / rate
        return float(stats.expon.cdf(x, scale=scale))

    elif name == "uniform":
        low = float(params.get("low", 0.0))
        high = float(params.get("high", 1.0))
        if high <= low:
            raise ValueError(f"high must be greater than low, got {low=}, {high=}")
        if x < low:
            return 0.0
        if x > high:
            return 1.0
        return (x - low) / (high - low)

    else:
        raise ValueError(f"Unsupported distribution type: {dist_type}")
