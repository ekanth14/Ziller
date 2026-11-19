"""Level 10: Research & Machine Learning Engine (Formulas 10.1 - 10.5).

Formulas:
10.1 Backtest Biases Audit: Lookahead bias, survivorship bias, snooping FDR, zero fees
10.2 Walk-Forward Validation: Non-overlapping train [t0, t1] -> test [t1, t2] rolling windows
10.3 Deflated Sharpe Ratio (DSR): Bailey & Lopez de Prado (2014) DSR adjusting for skew, kurt, N trials
10.4 Classification Metrics: Precision = TP / (TP + FP), Recall = TP / (TP + FN), F1 = 2*P*R / (P + R)
10.5 Regime Models (HMM): Gaussian 2-state / 3-state regime classification (low vol trend vs high vol chop)
"""

import math
from typing import Sequence, Tuple
import numpy as np

from core.quant import native as _native
from scipy import stats


# ---------------------------------------------------------------------------
# Formula 10.1: Backtest Biases Audit
# ---------------------------------------------------------------------------
def audit_backtest_biases(
    signal_timestamps: Sequence[float] | None = None,
    execution_timestamps: Sequence[float] | None = None,
    fee_rate: float = 0.0,
    slippage: float = 0.0,
    universe_has_delisted: bool = True,
    num_trials: int = 1,
    alpha_threshold: float = 0.05,
) -> dict:
    """Audit quantitative backtest for standard institutional biases and flaws.

    Checks:
    - Lookahead bias: signals generated after or at execution timestamps
    - Zero fee warning: unrealistic zero exchange trading fee assumption
    - Zero slippage warning: unrealistic zero market impact/slippage assumption
    - Survivorship bias: omitting delisted/liquidated historical assets
    - Data snooping / multiple testing: false discovery rate warning for N trials
    """
    issues: list[str] = []
    lookahead_detected = False

    # Check lookahead bias
    if signal_timestamps is not None and execution_timestamps is not None:
        n = min(len(signal_timestamps), len(execution_timestamps))
        for i in range(n):
            if signal_timestamps[i] >= execution_timestamps[i]:
                lookahead_detected = True
                issues.append(
                    f"Lookahead bias detected at index {i}: signal time {signal_timestamps[i]} "
                    f">= execution time {execution_timestamps[i]}"
                )
                break

    # Check zero-fee assumption
    zero_fee = fee_rate <= 0.0
    if zero_fee:
        issues.append("Unrealistic zero-fee assumption (fee_rate <= 0.0).")

    # Check zero-slippage assumption
    zero_slippage = slippage <= 0.0
    if zero_slippage:
        issues.append("Unrealistic zero-slippage assumption (slippage <= 0.0).")

    # Check survivorship bias
    survivorship_bias = not universe_has_delisted
    if survivorship_bias:
        issues.append("Survivorship bias detected: universe omits delisted assets.")

    # Check multiple testing snooping
    snooping_warning = num_trials > 20
    alpha_clamped = max(0.0, min(1.0, alpha_threshold))
    fdr_p_value = 1.0 - ((1.0 - alpha_clamped) ** max(1, num_trials))
    if snooping_warning:
        issues.append(
            f"Data snooping warning: {num_trials} trials tested without multiple testing adjustment "
            f"(P(>=1 false discovery) = {fdr_p_value:.2%})."
        )

    passed = not (lookahead_detected or zero_fee or zero_slippage or survivorship_bias or snooping_warning)

    return {
        "passed": passed,
        "lookahead_bias": lookahead_detected,
        "zero_fee_warning": zero_fee,
        "zero_slippage_warning": zero_slippage,
        "survivorship_bias": survivorship_bias,
        "snooping_warning": snooping_warning,
        "fdr_p_value": float(fdr_p_value),
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Formula 10.2: Walk-Forward Validation
# ---------------------------------------------------------------------------
def generate_walk_forward_windows(
    total_bars: int,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    anchored: bool = False,
) -> list[Tuple[slice, slice]]:
    """Generate rolling or anchored walk-forward train and out-of-sample test window slices.

    Guarantees zero-lookahead: train_slice.stop <= test_slice.start.
    """
    if step_bars is None:
        step_bars = test_bars

    windows: list[Tuple[slice, slice]] = []
    start = 0

    while start + train_bars + test_bars <= total_bars:
        train_start = 0 if anchored else start
        train_stop = start + train_bars
        test_start = train_stop
        test_stop = test_start + test_bars

        windows.append((slice(train_start, train_stop), slice(test_start, test_stop)))
        start += step_bars

    return windows


def compute_walk_forward_efficiency(
    in_sample_metrics: Sequence[float],
    out_of_sample_metrics: Sequence[float],
) -> float:
    """Calculate Walk-Forward Efficiency: WFE = mean(OOS) / mean(IS).

    A strategy is generally considered robust if WFE >= 0.50.
    """
    if not in_sample_metrics or not out_of_sample_metrics:
        return 0.0

    mean_is = float(np.mean(in_sample_metrics))
    mean_oos = float(np.mean(out_of_sample_metrics))

    if abs(mean_is) <= 1e-12:
        return 0.0

    return mean_oos / mean_is


# ---------------------------------------------------------------------------
# Formula 10.3: Deflated Sharpe Ratio (DSR)
# ---------------------------------------------------------------------------
def compute_deflated_sharpe_ratio(
    estimated_sr: float,
    returns: Sequence[float] | None = None,
    n_trials: int = 1,
    sample_length: int | None = None,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    var_sharpe: float = 0.25,
) -> float:
    """Calculate Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    Adjusts observed Sharpe Ratio for:
    - Small sample length T
    - Non-normality (skewness and excess kurtosis)
    - Selection bias across N backtest trials (deflation)
    """
    t = sample_length
    skew = skewness
    kurt = kurtosis

    if returns is not None and len(returns) > 3:
        r = np.asarray(returns, dtype=float)
        t = len(r)
        mean_r = float(np.mean(r))
        std_r = float(np.std(r, ddof=1))
        if std_r > 1e-12 and estimated_sr == 0.0:
            estimated_sr = mean_r / std_r
        skew = float(stats.skew(r))
        kurt = float(stats.kurtosis(r, fisher=False))  # Pearson kurtosis (normal = 3)

    if t is None or t <= 2:
        return 0.0

    # 1. Expected maximum Sharpe ratio from N independent trials under null (SR=0)
    # Using Bailey-Lopez de Prado approximation
    n = max(1, n_trials)
    if n > 1:
        euler_mascheroni = 0.5772156649015328606
        z_1 = float(stats.norm.ppf(1.0 - 1.0 / n))
        z_2 = float(stats.norm.ppf(1.0 - 1.0 / (n * math.e)))
        sr_star = math.sqrt(var_sharpe) * ((1.0 - euler_mascheroni) * z_1 + euler_mascheroni * z_2)
    else:
        sr_star = 0.0

    # 2. Asymptotic variance of Sharpe Ratio under non-normality (Mertens, 2002)
    # Var(SR) = (1 - skew * SR + (kurt - 1) / 4 * SR^2) / (T - 1)
    denom_var = 1.0 - (skew * estimated_sr) + ((kurt - 1.0) / 4.0) * (estimated_sr ** 2)
    if denom_var <= 1e-12:
        denom_var = 1e-12

    sigma_sr = math.sqrt(denom_var / (t - 1))
    if sigma_sr <= 1e-12:
        return 0.0

    # 3. Z-statistic and Deflated Sharpe Ratio probability
    z_stat = (estimated_sr - sr_star) / sigma_sr
    dsr = float(stats.norm.cdf(z_stat))
    return float(np.clip(dsr, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Formula 10.4: Classification Metrics
# ---------------------------------------------------------------------------
def compute_classification_metrics(
    y_true: Sequence[int],
    y_pred: Sequence[int],
) -> dict[str, float]:
    """Calculate directional classification metrics: Precision, Recall, F1, and Accuracy."""
    n = min(len(y_true), len(y_pred))
    empty = {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "accuracy": 0.0,
        "tp": 0,
        "fp": 0,
        "tn": 0,
        "fn": 0,
    }
    if n == 0:
        return empty

    tp = sum(1 for i in range(n) if y_true[i] == 1 and y_pred[i] == 1)
    fp = sum(1 for i in range(n) if y_true[i] == 0 and y_pred[i] == 1)
    tn = sum(1 for i in range(n) if y_true[i] == 0 and y_pred[i] == 0)
    fn = sum(1 for i in range(n) if y_true[i] == 1 and y_pred[i] == 0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / n if n > 0 else 0.0

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "accuracy": float(accuracy),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


# ---------------------------------------------------------------------------
# Formula 10.5: Regime Models (Gaussian Hidden Markov Model)
# ---------------------------------------------------------------------------
class GaussianRegimeHMM:
    """Lightweight 2-state / 3-state Gaussian Hidden Markov Model for market regimes."""

    def __init__(self, n_states: int = 2, max_iter: int = 30, tol: float = 1e-4):
        self.n_states = n_states
        self.max_iter = max_iter
        self.tol = tol
        self.means: list[float] = [0.0] * n_states
        self.stds: list[float] = [0.01] * n_states
        self.transition_matrix: list[list[float]] = [
            [0.9 if i == j else 0.1 / (n_states - 1) for j in range(n_states)]
            for i in range(n_states)
        ]
        self.priors: list[float] = [1.0 / n_states] * n_states

    def fit(self, returns: Sequence[float]) -> "GaussianRegimeHMM":
        """Fit Gaussian HMM parameters via Expectation-Maximization (EM)."""
        x = np.asarray(returns, dtype=float)
        t = len(x)
        if t < self.n_states:
            return self

        # Initialize states by partitioning on volatility
        # Split data by rolling std or magnitude
        abs_x = np.abs(x - np.mean(x))
        quantiles = np.linspace(0.0, 1.0, self.n_states + 1)
        thresholds = [np.quantile(abs_x, q) for q in quantiles]

        for s in range(self.n_states):
            mask = (abs_x >= thresholds[s]) & (abs_x <= thresholds[s + 1])
            subset = x[mask]
            if len(subset) > 1:
                self.means[s] = float(np.mean(subset))
                self.stds[s] = max(1e-4, float(np.std(subset, ddof=1)))
            else:
                self.means[s] = float(np.mean(x))
                self.stds[s] = max(1e-4, float(np.std(x, ddof=1)) * (s + 1))

        # Sort states by volatility ascending (state 0 = low vol, state 1 = high vol)
        order = np.argsort(self.stds)
        self.means = [self.means[i] for i in order]
        self.stds = [self.stds[i] for i in order]

        k = self.n_states
        a = np.array(self.transition_matrix, dtype=float)
        pi = np.array(self.priors, dtype=float)
        means = np.array(self.means, dtype=float)
        stds = np.array(self.stds, dtype=float)

        fast = _native.hmm_em(x, means, stds, a, pi, self.max_iter, self.tol)
        if fast is not None:
            f_means, f_stds, f_a, f_pi = fast
            means, stds = np.array(f_means), np.array(f_stds)
            a, pi = np.array(f_a), np.array(f_pi)
        else:
            pi, a, means, stds = self._em_python(x, t, k, a, pi, means, stds)

        # Re-sort states so state 0 is lower volatility
        order = np.argsort(stds)
        self.means = [float(means[i]) for i in order]
        self.stds = [float(stds[i]) for i in order]
        self.priors = [float(pi[i]) for i in order]
        self.transition_matrix = [[float(a[i, j]) for j in order] for i in order]

        return self

    def _em_python(self, x, t, k, a, pi, means, stds):
        """Pure-Python/numpy EM loop (reference implementation and fallback)."""
        # EM loop
        for _ in range(self.max_iter):
            # Compute Gaussian emission probabilities B[t, s] = N(x_t; mu_s, sigma_s)
            b = np.zeros((t, k), dtype=float)
            for s in range(k):
                sigma = max(1e-4, stds[s])
                var = sigma ** 2
                diff = x - means[s]
                b[:, s] = np.exp(-0.5 * (diff ** 2) / var) / (math.sqrt(2.0 * math.pi) * sigma)
                b[:, s] = np.maximum(b[:, s], 1e-12)

            # Forward pass (scaled)
            alpha = np.zeros((t, k), dtype=float)
            c = np.zeros(t, dtype=float)

            alpha[0] = pi * b[0]
            c[0] = np.sum(alpha[0])
            if c[0] > 1e-12:
                alpha[0] /= c[0]

            for step in range(1, t):
                alpha[step] = (alpha[step - 1] @ a) * b[step]
                c[step] = np.sum(alpha[step])
                if c[step] > 1e-12:
                    alpha[step] /= c[step]
                else:
                    alpha[step] = 1.0 / k

            # Backward pass (scaled)
            beta = np.zeros((t, k), dtype=float)
            beta[t - 1] = 1.0

            for step in range(t - 2, -1, -1):
                beta[step] = a @ (b[step + 1] * beta[step + 1])
                if c[step + 1] > 1e-12:
                    beta[step] /= c[step + 1]

            # Posteriors gamma[t, s]
            gamma = alpha * beta
            gamma_sum = np.sum(gamma, axis=1, keepdims=True)
            gamma_sum = np.where(gamma_sum <= 1e-12, 1.0, gamma_sum)
            gamma /= gamma_sum

            # Digammas xi[t, i, j]
            xi = np.zeros((t - 1, k, k), dtype=float)
            for step in range(t - 1):
                numerator = alpha[step, :, None] * a * (b[step + 1] * beta[step + 1])[None, :]
                denom = np.sum(numerator)
                xi[step] = numerator / denom if denom > 1e-12 else 1.0 / (k * k)

            # M-step: Update parameters
            new_pi = gamma[0]
            new_a = np.sum(xi, axis=0) / np.maximum(1e-12, np.sum(gamma[:-1], axis=0)[:, None])
            # Normalize rows of a
            row_sums = np.sum(new_a, axis=1, keepdims=True)
            new_a = new_a / np.where(row_sums <= 1e-12, 1.0, row_sums)

            gamma_weights = np.sum(gamma, axis=0)
            gamma_weights_safe = np.maximum(1e-12, gamma_weights)

            new_means = np.sum(gamma * x[:, None], axis=0) / gamma_weights_safe
            new_stds = np.sqrt(
                np.sum(gamma * ((x[:, None] - new_means[None, :]) ** 2), axis=0) / gamma_weights_safe
            )
            new_stds = np.maximum(1e-4, new_stds)

            # Check convergence
            mean_shift = np.max(np.abs(new_means - means))
            std_shift = np.max(np.abs(new_stds - stds))
            pi, a, means, stds = new_pi, new_a, new_means, new_stds

            if mean_shift < self.tol and std_shift < self.tol:
                break
        return pi, a, means, stds

    def predict(self, returns: Sequence[float]) -> list[int]:
        """Decode most likely sequence of hidden states using Viterbi algorithm."""
        x = np.asarray(returns, dtype=float)
        t = len(x)
        if t == 0:
            return []
        if t < self.n_states:
            return [0] * t

        fast_path = _native.hmm_viterbi(x, self.means, self.stds, self.transition_matrix, self.priors)
        if fast_path is not None:
            return fast_path

        k = self.n_states
        a = np.array(self.transition_matrix, dtype=float)
        pi = np.array(self.priors, dtype=float)
        means = np.array(self.means, dtype=float)
        stds = np.array(self.stds, dtype=float)

        log_a = np.log(np.maximum(1e-12, a))
        log_pi = np.log(np.maximum(1e-12, pi))

        # Log emissions
        log_b = np.zeros((t, k), dtype=float)
        for s in range(k):
            sigma = max(1e-4, stds[s])
            var = sigma ** 2
            log_b[:, s] = -0.5 * np.log(2 * math.pi * var) - 0.5 * ((x - means[s]) ** 2) / var

        viterbi = np.zeros((t, k), dtype=float)
        backpointer = np.zeros((t, k), dtype=int)

        viterbi[0] = log_pi + log_b[0]

        for step in range(1, t):
            for s in range(k):
                seq_probs = viterbi[step - 1] + log_a[:, s] + log_b[step, s]
                best_prev = int(np.argmax(seq_probs))
                viterbi[step, s] = seq_probs[best_prev]
                backpointer[step, s] = best_prev

        # Backtrack
        path = [0] * t
        path[-1] = int(np.argmax(viterbi[-1]))
        for step in range(t - 2, -1, -1):
            path[step] = int(backpointer[step + 1, path[step + 1]])

        return path


def detect_regimes_hmm(
    returns: Sequence[float],
    n_states: int = 2,
    max_iter: int = 30,
) -> dict:
    """Fit Gaussian HMM on returns and detect regime states."""
    if len(returns) == 0:
        return {
            "states": [],
            "state_means": [0.0] * n_states,
            "state_stds": [0.01] * n_states,
            "transition_matrix": [[1.0 / n_states] * n_states for _ in range(n_states)],
            "current_regime": 0,
        }

    hmm = GaussianRegimeHMM(n_states=n_states, max_iter=max_iter)
    hmm.fit(returns)
    states = hmm.predict(returns)
    current_regime = states[-1] if states else 0

    return {
        "states": states,
        "state_means": hmm.means,
        "state_stds": hmm.stds,
        "transition_matrix": hmm.transition_matrix,
        "current_regime": current_regime,
    }
