"""Stage 4: Edge Evaluation Engine (Formulas 4.1 - 4.6).

Formulas:
4.1 Expected value: EV = p * W - (1 - p) * L
4.2 Breakeven win rate: p* = 1 / (1 + W / L)
4.3 Expectancy in R: E[R] = p * R_win - (1 - p) * 1R
4.4 Profit factor: PF = gross_wins / gross_losses
4.5 Bayesian win rate: p_hat = (alpha + wins) / (alpha + beta + n)
4.6 Net edge: net = gross - 2 * (fee + slippage)
"""


def compute_expected_value(win_prob: float, avg_win: float, avg_loss: float) -> float:
    """Calculate trade Expected Value (EV): EV = p * W - (1 - p) * L."""
    p = max(0.0, min(1.0, win_prob))
    return (p * avg_win) - ((1.0 - p) * avg_loss)


def compute_breakeven_win_rate(avg_win: float, avg_loss: float) -> float:
    """Calculate Breakeven Win Rate: p* = 1 / (1 + W / L)."""
    if avg_loss <= 1e-12:
        return 0.0
    if avg_win <= 0.0:
        return 1.0
    payoff = avg_win / avg_loss
    return 1.0 / (1.0 + payoff)


def compute_expectancy_in_r(win_prob: float, r_win: float) -> float:
    """Calculate expectancy expressed in units of Risk (R): E[R] = p * R_win - (1 - p) * 1R."""
    p = max(0.0, min(1.0, win_prob))
    return (p * r_win) - ((1.0 - p) * 1.0)


def compute_profit_factor(gross_wins: float, gross_losses: float) -> float:
    """Calculate Profit Factor: PF = gross_wins / gross_losses. Under 1.2 is thin."""
    if gross_losses <= 1e-12:
        return float("inf") if gross_wins > 0.0 else 0.0
    return gross_wins / gross_losses


def compute_bayesian_win_rate(
    wins: int,
    n: int,
    alpha: float = 1.0,
    beta: float = 1.0,
) -> float:
    """Calculate Bayesian win rate under Beta(alpha, beta) conjugate prior shrinkage."""
    denom = alpha + beta + n
    if denom <= 0.0:
        return 0.5
    return (alpha + wins) / denom


def compute_net_edge(gross_edge: float, fee_rate: float, slippage_rate: float) -> float:
    """Calculate net edge after 2-sided fees and slippage: net = gross - 2 * (fee + slippage)."""
    return gross_edge - 2.0 * (fee_rate + slippage_rate)
