"""Quant Pipeline Orchestrator and Portfolio Coordinator.

Unifies Stages 1-8:
- QuantPipeline: Single-asset streaming processor (Stages 1-3, 5-7).
- PortfolioCoordinator: Joint multi-asset coordinator (cross-correlations, risk parity, portfolio VaR).
- run_offline_validation: Asynchronous validator for trade history (Stages 4 & 8).
"""

import bisect
import math
from collections import deque
from typing import Any, Mapping, Sequence
from core.quant.stage1_data import (
    compute_log_returns,
    compute_annualized_vol,
    compute_ewma_vol,
    compute_atr,
    filter_bad_ticks,
)
from core.quant.stage2_signal import (
    compute_zscore,
    compute_ema,
    compute_rsi,
    compute_order_book_imbalance,
    compute_funding_carry_apr,
)
from core.quant.stage3_filter import (
    compute_tstat_returns,
    compute_half_life,
    compute_hurst_exponent,
    compute_correlation_matrix,
    is_high_vol_regime,
)
from core.quant.stage4_edge import (
    compute_expected_value,
    compute_breakeven_win_rate,
    compute_expectancy_in_r,
    compute_profit_factor,
    compute_bayesian_win_rate,
    compute_net_edge,
)
from core.quant.stage5_size import (
    compute_risk_based_size,
    compute_kelly_criterion,
    compute_volatility_target_weight,
    compute_risk_parity_weights,
    compute_liquidation_price,
)
from core.quant.stage6_execute import (
    compute_spread_cost,
    compute_microprice,
    compute_square_root_impact,
)
from core.quant.stage7_risk import (
    compute_max_drawdown,
    compute_var_95,
    compute_portfolio_volatility,
    check_kill_switch,
)
from core.quant.stage8_validate import (
    compute_sharpe_ratio,
    compute_sharpe_tstat,
    run_monte_carlo_drawdown,
)


class ReferenceQuantPipeline:
    """Original full-history-recompute pipeline (O(n) per bar).

    Kept unchanged as the correctness oracle for QuantPipeline and any future native
    implementation. Not used in the live path.
    """

    def __init__(self, symbol: str, initial_equity: float = 10000.0, max_dd_limit: float = 0.15) -> None:
        self.symbol = symbol
        self.equity = initial_equity
        self.peak_equity = initial_equity
        self.max_dd_limit = max_dd_limit

        self.closes: list[float] = []
        self.highs: list[float] = []
        self.lows: list[float] = []
        self.volumes: list[float] = []
        self.equity_curve: list[float] = [initial_equity]

        self.latest_metrics: dict[str, Any] = {}

    def on_bar(
        self,
        open_p: float,
        high_p: float,
        low_p: float,
        close_p: float,
        volume: float,
        bid_p: float,
        bid_q: float,
        ask_p: float,
        ask_q: float,
        funding_rate_8h: float = 0.0001,
        daily_volume: float = 1000000.0,
        equity: float | None = None,
    ) -> dict[str, Any]:
        """Process incoming closed bar and live book tick."""
        if equity is not None:
            self.equity = equity
            if equity > self.peak_equity:
                self.peak_equity = equity
            self.equity_curve.append(equity)

        self.closes.append(close_p)
        self.highs.append(high_p)
        self.lows.append(low_p)
        self.volumes.append(volume)

        # Stage 1: Data
        log_returns = compute_log_returns(self.closes)
        ann_vol = compute_annualized_vol(log_returns, bars_per_year=365) if len(log_returns) > 1 else 0.0
        ewma_vols = compute_ewma_vol(log_returns, lambda_param=0.94) if log_returns else [0.0]
        cur_ewma_vol = ewma_vols[-1] if ewma_vols else 0.0
        atrs = compute_atr(self.highs, self.lows, self.closes, period=14)
        cur_atr = atrs[-1] if atrs else 0.0
        bad_ticks = filter_bad_ticks(log_returns)
        is_bad_tick = bad_ticks[-1] if bad_ticks else False

        # Stage 2: Signal
        z_scores = compute_zscore(self.closes, window=20)
        cur_z = z_scores[-1] if z_scores else 0.0
        emas = compute_ema(self.closes, period=20)
        cur_ema = emas[-1] if emas else close_p
        rsis = compute_rsi(self.closes, period=14)
        cur_rsi = rsis[-1] if rsis else 50.0
        book_imbalance = compute_order_book_imbalance(bid_q, ask_q)
        funding_apr = compute_funding_carry_apr(funding_rate_8h)

        # Stage 3: Filter
        t_stat = compute_tstat_returns(log_returns) if len(log_returns) >= 5 else 0.0
        half_life = compute_half_life(self.closes) if len(self.closes) >= 15 else float("inf")
        hurst = compute_hurst_exponent(self.closes) if len(self.closes) >= 50 else 0.5
        # 20-bar vol vs long-term vol
        short_vol = compute_annualized_vol(log_returns[-20:], bars_per_year=365) if len(log_returns) >= 20 else ann_vol
        is_high_vol = is_high_vol_regime(short_vol, ann_vol, threshold=1.5) if ann_vol > 0 else False

        # Stage 5: Size
        stop_price = close_p - 2.0 * cur_atr if cur_atr > 0 else close_p * 0.98
        risk_size = compute_risk_based_size(self.equity, risk_pct=0.01, entry=close_p, stop=stop_price)
        vol_scalar = compute_volatility_target_weight(target_vol=0.15, realized_vol=ann_vol, max_leverage=3.0) if ann_vol > 0 else 0.0
        liq_price = compute_liquidation_price(entry=close_p, leverage=10.0, mmr=0.005, is_long=True)

        # Stage 6: Execute
        spread, half_spread = compute_spread_cost(bid_p, ask_p)
        microprice = compute_microprice(bid_p, bid_q, ask_p, ask_q, last_price=close_p)
        impact = compute_square_root_impact(volatility=ann_vol, order_qty=risk_size, daily_volume=daily_volume)

        # Stage 7: Risk
        daily_vol_est = ann_vol / (365.0 ** 0.5) if ann_vol > 0 else 0.01
        var_95 = compute_var_95(portfolio_value=self.equity, daily_vol=daily_vol_est)
        max_dd, peak_e, trough_e = compute_max_drawdown(self.equity_curve)
        kill_switch_trip = check_kill_switch(self.equity, self.peak_equity, max_allowed_dd=self.max_dd_limit)

        metrics = {
            "symbol": self.symbol,
            "close": close_p,
            "log_return": log_returns[-1] if log_returns else 0.0,
            "annualized_vol": ann_vol,
            "ewma_vol": cur_ewma_vol,
            "atr": cur_atr,
            "is_bad_tick": is_bad_tick,
            "z_score": cur_z,
            "ema_20": cur_ema,
            "rsi_14": cur_rsi,
            "order_book_imbalance": book_imbalance,
            "funding_apr": funding_apr,
            "t_stat": t_stat,
            "half_life": half_life if half_life != float("inf") else None,
            "hurst_exponent": hurst,
            "is_high_vol": is_high_vol,
            "suggested_size": risk_size,
            "volatility_target_scalar": vol_scalar,
            "liquidation_price": liq_price,
            "spread": spread,
            "microprice": microprice,
            "estimated_impact": impact,
            "var_95": var_95,
            "max_drawdown": max_dd,
            "kill_switch_triggered": kill_switch_trip,
        }
        self.latest_metrics = metrics
        return metrics

    def get_telemetry(self) -> dict[str, Any]:
        """Return the latest calculated telemetry metrics."""
        return self.latest_metrics


class QuantPipeline:
    """Single-asset streaming quantitative engine with incremental (amortized O(1)) updates.

    Produces the same metrics as :class:`ReferenceQuantPipeline` (verified by
    differential tests) but keeps running state instead of recomputing the full
    history on every bar.
    """

    _HURST_LAGS = tuple(range(10, 100, 5))

    def __init__(self, symbol: str, initial_equity: float = 10000.0, max_dd_limit: float = 0.15) -> None:
        self.symbol = symbol
        self.equity = initial_equity
        self.peak_equity = initial_equity
        self.max_dd_limit = max_dd_limit

        self.closes: list[float] = []
        self.highs: list[float] = []
        self.lows: list[float] = []
        self.volumes: list[float] = []
        self.equity_curve: list[float] = [initial_equity]

        self.latest_metrics: dict[str, Any] = {}

        # Return statistics (Welford) and order statistics
        self._n_ret = 0
        self._mean = 0.0
        self._m2 = 0.0
        self._sorted_ret: list[float] = []
        self._ret_win: deque[float] = deque(maxlen=20)
        self._ewma_s2 = 0.0
        # Indicators
        self._tr_win: deque[float] = deque(maxlen=14)
        self._z_win: deque[float] = deque(maxlen=20)
        self._ema: float | None = None
        self._gain_win: deque[float] = deque(maxlen=14)
        self._loss_win: deque[float] = deque(maxlen=14)
        # Half-life regression sums (x shifted by first close to limit cancellation)
        self._hl_sx = 0.0
        self._hl_sy = 0.0
        self._hl_sxx = 0.0
        self._hl_sxy = 0.0
        # Hurst: per-lag running R/S accumulators over completed non-overlapping segments
        self._rs_sum = {lag: 0.0 for lag in self._HURST_LAGS}
        self._rs_cnt = {lag: 0 for lag in self._HURST_LAGS}
        # Drawdown state over the equity curve
        self._dd_peak = initial_equity
        self._dd_max = 0.0

    # -- helpers ---------------------------------------------------------
    def _update_equity(self, equity: float) -> None:
        self.equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        self.equity_curve.append(equity)
        if equity > self._dd_peak:
            self._dd_peak = equity
        dd = (self._dd_peak - equity) / self._dd_peak if self._dd_peak > 1e-12 else 0.0
        if dd > self._dd_max:
            self._dd_max = dd

    def _mad_robust_last_flag(self, last_ret: float) -> bool:
        n = self._n_ret
        if n < 3:
            return False
        s = self._sorted_ret
        pos = n // 2
        median_r = s[pos]
        # (n//2)-th smallest |r - median| via outward two-pointer walk from the median
        lo, hi = pos - 1, pos + 1
        mad = 0.0
        inf = float("inf")
        for _ in range(pos):
            dl = median_r - s[lo] if lo >= 0 else inf
            dh = s[hi] - median_r if hi < n else inf
            if dl <= dh:
                mad = dl
                lo -= 1
            else:
                mad = dh
                hi += 1
        robust_sigma = 1.4826 * mad
        if robust_sigma <= 1e-12:
            robust_sigma = math.sqrt(self._m2 / (n - 1))
        if robust_sigma <= 1e-12:
            return False
        return abs(last_ret - median_r) / robust_sigma > 6.0

    @staticmethod
    def _rs_segment(sub: Sequence[float], lag: int) -> float | None:
        mean_sub = sum(sub) / lag
        cur = 0.0
        cmax = -math.inf
        cmin = math.inf
        sq = 0.0
        for x in sub:
            d = x - mean_sub
            cur += d
            if cur > cmax:
                cmax = cur
            if cur < cmin:
                cmin = cur
            sq += d * d
        s_val = math.sqrt(sq / lag)
        if s_val > 1e-12:
            return (cmax - cmin) / s_val
        return None

    def _hurst(self, n: int) -> float:
        if n < 50:
            return 0.5
        lags = [lag for lag in range(10, min(n // 2, 100), 5)]
        if len(lags) < 3:
            return 0.5
        log_lags: list[float] = []
        log_rs: list[float] = []
        for lag in lags:
            cnt = self._rs_cnt[lag]
            if cnt:
                avg_rs = self._rs_sum[lag] / cnt
                if avg_rs > 0.0:
                    log_lags.append(math.log(lag))
                    log_rs.append(math.log(avg_rs))
        if len(log_lags) < 2:
            return 0.5
        mean_x = sum(log_lags) / len(log_lags)
        mean_y = sum(log_rs) / len(log_rs)
        ss_xx = sum((x - mean_x) ** 2 for x in log_lags)
        ss_xy = sum((log_lags[i] - mean_x) * (log_rs[i] - mean_y) for i in range(len(log_lags)))
        if ss_xx <= 1e-12:
            return 0.5
        return max(0.0, min(1.0, ss_xy / ss_xx))

    # -- main entry ------------------------------------------------------
    def on_bar(
        self,
        open_p: float,
        high_p: float,
        low_p: float,
        close_p: float,
        volume: float,
        bid_p: float,
        bid_q: float,
        ask_p: float,
        ask_q: float,
        funding_rate_8h: float = 0.0001,
        daily_volume: float = 1000000.0,
        equity: float | None = None,
    ) -> dict[str, Any]:
        """Process incoming closed bar and live book tick."""
        prev_close = self.closes[-1] if self.closes else None
        if prev_close is not None and (prev_close <= 0.0 or close_p <= 0.0):
            raise ValueError(f"Prices must be strictly positive: p_prev={prev_close}, p_curr={close_p}")

        if equity is not None:
            self._update_equity(equity)

        # ---- incremental state updates ----
        last_ret = 0.0
        has_ret = prev_close is not None
        if has_ret:
            last_ret = math.log(close_p / prev_close)
            self._n_ret += 1
            delta = last_ret - self._mean
            self._mean += delta / self._n_ret
            self._m2 += delta * (last_ret - self._mean)
            bisect.insort(self._sorted_ret, last_ret)
            self._ret_win.append(last_ret)
            if self._n_ret == 1:
                self._ewma_s2 = last_ret ** 2 if last_ret != 0.0 else 1e-8
            else:
                self._ewma_s2 = 0.94 * self._ewma_s2 + 0.06 * (last_ret ** 2)
            # half-life regression pair (x = previous close, y = change)
            x = prev_close - self.closes[0]
            y = close_p - prev_close
            self._hl_sx += x
            self._hl_sy += y
            self._hl_sxx += x * x
            self._hl_sxy += x * y

        if prev_close is None:
            tr = high_p - low_p
        else:
            tr = max(high_p - low_p, abs(high_p - prev_close), abs(low_p - prev_close))
        self._tr_win.append(tr)

        self._z_win.append(close_p)
        alpha = 2.0 / 21.0
        self._ema = close_p if self._ema is None else alpha * close_p + (1.0 - alpha) * self._ema

        if prev_close is None:
            cur_rsi = 50.0
        else:
            d = close_p - prev_close
            self._gain_win.append(max(0.0, d))
            self._loss_win.append(max(0.0, -d))
            avg_gain = sum(self._gain_win) / len(self._gain_win)
            avg_loss = sum(self._loss_win) / len(self._loss_win)
            if avg_loss <= 1e-12:
                cur_rsi = 100.0 if avg_gain > 0.0 else 50.0
            else:
                cur_rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

        self.closes.append(close_p)
        self.highs.append(high_p)
        self.lows.append(low_p)
        self.volumes.append(volume)
        n = len(self.closes)

        # completed non-overlapping Hurst segments
        for lag in self._HURST_LAGS:
            if n % lag == 0:
                rs = self._rs_segment(self.closes[n - lag:], lag)
                if rs is not None:
                    self._rs_sum[lag] += rs
                    self._rs_cnt[lag] += 1

        # ---- Stage 1: Data ----
        n_ret = self._n_ret
        ann_vol = math.sqrt(self._m2 / (n_ret - 1)) * math.sqrt(365) if n_ret > 1 else 0.0
        cur_ewma_vol = math.sqrt(self._ewma_s2) if n_ret >= 1 else 0.0
        cur_atr = sum(self._tr_win) / len(self._tr_win)
        is_bad_tick = self._mad_robust_last_flag(last_ret) if has_ret else False

        # ---- Stage 2: Signal ----
        m = len(self._z_win)
        if m < 2:
            cur_z = 0.0
        else:
            mean_val = sum(self._z_win) / m
            var = sum((v - mean_val) ** 2 for v in self._z_win) / (m - 1)
            std_val = math.sqrt(var)
            cur_z = 0.0 if std_val <= 1e-12 else (close_p - mean_val) / std_val
        cur_ema = self._ema
        book_imbalance = compute_order_book_imbalance(bid_q, ask_q)
        funding_apr = compute_funding_carry_apr(funding_rate_8h)

        # ---- Stage 3: Filter ----
        if n_ret >= 5:
            sigma = math.sqrt(self._m2 / (n_ret - 1))
            t_stat = 0.0 if sigma <= 1e-12 else self._mean / (sigma / math.sqrt(n_ret))
        else:
            t_stat = 0.0
        half_life = float("inf")
        if n >= 15:
            mm = n - 1
            mean_x = self._hl_sx / mm
            mean_y = self._hl_sy / mm
            ss_xx = self._hl_sxx - mm * mean_x * mean_x
            ss_xy = self._hl_sxy - mm * mean_x * mean_y
            if ss_xx > 1e-12:
                lam = ss_xy / ss_xx
                if lam < 0.0:
                    half_life = -math.log(2.0) / lam
        hurst = self._hurst(n)
        if n_ret >= 20:
            w = self._ret_win
            mw = sum(w) / len(w)
            short_vol = math.sqrt(sum((r - mw) ** 2 for r in w) / (len(w) - 1)) * math.sqrt(365)
        else:
            short_vol = ann_vol
        is_high_vol = is_high_vol_regime(short_vol, ann_vol, threshold=1.5) if ann_vol > 0 else False

        # ---- Stage 5: Size ----
        stop_price = close_p - 2.0 * cur_atr if cur_atr > 0 else close_p * 0.98
        risk_size = compute_risk_based_size(self.equity, risk_pct=0.01, entry=close_p, stop=stop_price)
        vol_scalar = compute_volatility_target_weight(target_vol=0.15, realized_vol=ann_vol, max_leverage=3.0) if ann_vol > 0 else 0.0
        liq_price = compute_liquidation_price(entry=close_p, leverage=10.0, mmr=0.005, is_long=True)

        # ---- Stage 6: Execute ----
        spread, _half_spread = compute_spread_cost(bid_p, ask_p)
        microprice = compute_microprice(bid_p, bid_q, ask_p, ask_q, last_price=close_p)
        impact = compute_square_root_impact(volatility=ann_vol, order_qty=risk_size, daily_volume=daily_volume)

        # ---- Stage 7: Risk ----
        daily_vol_est = ann_vol / (365.0 ** 0.5) if ann_vol > 0 else 0.01
        var_95 = compute_var_95(portfolio_value=self.equity, daily_vol=daily_vol_est)
        kill_switch_trip = check_kill_switch(self.equity, self.peak_equity, max_allowed_dd=self.max_dd_limit)

        metrics = {
            "symbol": self.symbol,
            "close": close_p,
            "log_return": last_ret if has_ret else 0.0,
            "annualized_vol": ann_vol,
            "ewma_vol": cur_ewma_vol,
            "atr": cur_atr,
            "is_bad_tick": is_bad_tick,
            "z_score": cur_z,
            "ema_20": cur_ema,
            "rsi_14": cur_rsi,
            "order_book_imbalance": book_imbalance,
            "funding_apr": funding_apr,
            "t_stat": t_stat,
            "half_life": half_life if half_life != float("inf") else None,
            "hurst_exponent": hurst,
            "is_high_vol": is_high_vol,
            "suggested_size": risk_size,
            "volatility_target_scalar": vol_scalar,
            "liquidation_price": liq_price,
            "spread": spread,
            "microprice": microprice,
            "estimated_impact": impact,
            "var_95": var_95,
            "max_drawdown": self._dd_max,
            "kill_switch_triggered": kill_switch_trip,
        }
        self.latest_metrics = metrics
        return metrics

    def get_telemetry(self) -> dict[str, Any]:
        """Return the latest calculated telemetry metrics."""
        return self.latest_metrics


class PortfolioCoordinator:
    """Multi-asset portfolio coordinator computing joint risks and allocations."""

    def __init__(self, symbols: Sequence[str]) -> None:
        self.symbols = list(symbols)
        self.prices: dict[str, list[float]] = {s: [] for s in self.symbols}

    def update_price(self, symbol: str, price_series: Sequence[float]) -> None:
        """Update historical price series for a given symbol."""
        self.prices[symbol] = list(price_series)

    def compute_portfolio_summary(self) -> dict[str, Any]:
        """Calculate joint cross-correlation matrix, risk parity weights, and total portfolio volatility."""
        correlations = compute_correlation_matrix(self.prices)

        # Compute annualized volatility per asset
        volatilities: dict[str, float] = {}
        for s in self.symbols:
            series = self.prices.get(s, [])
            if len(series) >= 2:
                returns = compute_log_returns(series)
                volatilities[s] = compute_annualized_vol(returns, bars_per_year=365)
            else:
                volatilities[s] = 0.20  # Neutral baseline

        risk_parity = compute_risk_parity_weights(volatilities)

        # Build covariance matrix
        weights = [risk_parity.get(s, 0.0) for s in self.symbols]
        cov_matrix: list[list[float]] = []
        for i, s1 in enumerate(self.symbols):
            row: list[float] = []
            for j, s2 in enumerate(self.symbols):
                rho = correlations.get((s1, s2), 1.0 if s1 == s2 else 0.0)
                cov = rho * volatilities[s1] * volatilities[s2]
                row.append(cov)
            cov_matrix.append(row)

        port_vol = compute_portfolio_volatility(weights, cov_matrix)

        formatted_correlations = {
            f"{k[0]}:{k[1]}": v for k, v in correlations.items()
        }

        return {
            "symbols": self.symbols,
            "correlations": formatted_correlations,
            "volatilities": volatilities,
            "risk_parity_weights": risk_parity,
            "portfolio_volatility": port_vol,
        }


def run_offline_validation(
    trades: Sequence[float],
    fee_rate: float = 0.0005,
    slippage_rate: float = 0.0002,
) -> dict[str, Any]:
    """Execute asynchronous offline evaluation across Stage 4 (Edge) and Stage 8 (Validation)."""
    if not trades:
        return {}

    wins = [t for t in trades if t > 0.0]
    losses = [abs(t) for t in trades if t < 0.0]

    n_trades = len(trades)
    n_wins = len(wins)
    win_prob = n_wins / n_trades if n_trades > 0 else 0.0

    avg_win = sum(wins) / n_wins if n_wins > 0 else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    ev = compute_expected_value(win_prob, avg_win, avg_loss)
    be_win_rate = compute_breakeven_win_rate(avg_win, avg_loss)
    r_win = (avg_win / avg_loss) if avg_loss > 0 else 1.0
    exp_r = compute_expectancy_in_r(win_prob, r_win)
    pf = compute_profit_factor(sum(wins), sum(losses))
    bayesian_p = compute_bayesian_win_rate(n_wins, n_trades)
    net_edge = compute_net_edge(ev, fee_rate, slippage_rate)

    mc_dd = run_monte_carlo_drawdown(trades, iterations=1000, confidence=0.95)

    return {
        "n_trades": n_trades,
        "win_rate": win_prob,
        "bayesian_win_rate": bayesian_p,
        "expected_value": ev,
        "breakeven_win_rate": be_win_rate,
        "expectancy_in_r": exp_r,
        "profit_factor": pf,
        "net_edge": net_edge,
        "monte_carlo_95_dd": mc_dd,
    }
