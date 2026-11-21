# Exits, Position Management, Execution Scheduling and Performance-Evaluation Formulas (items not yet in the terminal)

Scope note: the terminal already has fixed-fractional, Kelly, vol-target weight, risk parity, Markowitz, VaR/CVaR, Sharpe, Deflated Sharpe, max drawdown, profit factor, expectancy, square-root impact, TWAP/VWAP price, implementation shortfall. Those are not re-described here.

Sourcing convention used in these notes: anything in "Cited Findings" was seen in a fetched/search-returned source during this session. Formulas that are standard textbook definitions but whose primary source was NOT retrieved this session are placed under "Inferences -> Standard definitions (domain knowledge, not re-verified this session)" so the report writer can flag them. Research budget was ~22 tool calls; one primary PDF (Kaminski & Lo) was rate-limited (HTTP 429) and one (Bailey & López de Prado) was binary-compressed and unreadable, so some primary-source verification is missing (see Gaps).

Common notation used throughout:
- P_t, H_t, L_t, C_t = price / high / low / close of bar t
- TR_t = max(H_t, C_{t-1}) - min(L_t, C_{t-1}) (Wilder true range)
- ATR_t(n) = n-bar average (Wilder smoothing, or SMA/EMA depending on implementation) of TR
- r_t = per-bar simple return; N = number of observations; r_f = risk-free per bar (for crypto, usually 0 or a stablecoin lending yield)

---

## 1. Exits: ATR trailing stop, Chandelier, Kase DevStop, Parabolic, time stops, break-even stops, profit target vs trailing, and evidence on whether they improve expectancy

### Takeaway
Theory (Kaminski & Lo 2014) says a stop-loss can only add expected return if returns are serially correlated (momentum) or regime-switching; under a random walk every 0/1 stop-loss rule strictly reduces expected return. Crypto shows strong time-series momentum (mostly in bull regimes), so volatility-scaled trailing exits (Chandelier / ATR / DevStop) are theoretically justifiable for a long-only trend system, but there is no rigorous, peer-reviewed crypto study isolating trailing-stop value; practitioner evidence is mixed and whipsaw is the main failure mode.

### Cited Findings

**Kaminski & Lo, "When do stop-loss rules stop losses?" (J. Financial Markets 18, 2014, 234-254)**
- Defines the "stopping premium" as the change in a strategy's expected return caused by the stop-loss rule. — [IDEAS/RePEc](https://ideas.repec.org/a/eee/finmar/v18y2014icp234-254.html); [MIT DSpace](https://dspace.mit.edu/handle/1721.1/114876)
- Under a random walk (i.i.d. returns) the stopping premium is always negative: simple 0/1 stop-loss rules always reduce expected return. — [IDEAS/RePEc](https://ideas.repec.org/a/eee/finmar/v18y2014icp234-254.html)
- If returns have momentum (positive serial correlation) or regime switching, the stopping premium can be positive. — [IDEAS/RePEc](https://ideas.repec.org/p/hhs/sifrwp/0063.html)
- Empirically (US equities), stop-loss rules show positive stopping premiums over longer sampling frequencies and a larger range of thresholds, attributed to conditional momentum after losses. — [IDEAS/RePEc](https://ideas.repec.org/a/eee/finmar/v18y2014icp234-254.html)

**Chandelier Exit (Chuck LeBeau; popularised by Alexander Elder, "Come Into My Trading Room", 2002)**
- Long exit: CE_long = HighestHigh(22) - 3 x ATR(22). Short exit: CE_short = LowestLow(22) + 3 x ATR(22). — [StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit); [Barchart](https://www.barchart.com/education/technical-indicators/chandelier-exit)
- 22 = approx. trading days per month; multiplier usually 2.5-3.5, raised for more volatile instruments. — [StockCharts](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit)
- Original LeBeau form hangs the stop from the highest high (or highest close) since trade entry; the fixed 22-bar lookback is a charting adaptation. A raw chandelier level can move against the trade (when ATR rises or no new high is made inside the lookback), so implementations normally ratchet it (never lower a long stop). — [LuxAlgo](https://www.luxalgo.com/library/concept/chandelier-stop.md); [Incredible Charts](https://www.incrediblecharts.com/indicators/chandelier_exits.php)

**Kase DevStop (Cynthia Kase)**
- Built on the two-bar true range (TRD); default lookback n = 30; computes mean of TRD and its standard deviation; stop lines at mean + k x SD with k = 0 (warning line), 1, 2.2, 3.6. — [ProRealCode forum quoting Kase](https://www.prorealcode.com/prorealtime-indicators/kase-dev-stop/?pnum=17); [LuxAlgo](https://www.luxalgo.com/library/concept/kase-studies.md)
- Conflict: CQG's implementation uses 1, 2, 3 SD "corrected for skew", not 2.2/3.6. — [CQG help](https://help.cqg.com/cqgic/25/Documents/devstopkdevstp.htm)
- A stop at the warning line (mean TRD) implies roughly a 50% chance that any two-bar reversal stops you out on noise. — [TradingView Trendstone DevStop](https://fr.tradingview.com/script/FnzsoHWJ-Trendstone-DevStop-v1-0)
- The 2.2 and 3.6 multipliers appear to embed a skew allowance (approx. +10% and +20% over 2 and 3 SD); one forum user replicates this manually — this is a user workaround, not Kase's published formula. — [ProRealCode](https://www.prorealcode.com/prorealtime-indicators/kase-dev-stop/?pnum=17)

**Turtle stop (volatility stop used with pyramiding)**
- Initial stop 2N from entry, N = 20-day ATR; when a unit is added, all units' stops move to 2N below the newest entry (long). — [FXOpen](https://fxopen.com/blog/en/turtle-trading-system-rules-and-strategy); [MQL5 article](https://www.mql5.com/en/articles/23448)

**Crypto-specific evidence**
- Han, Kang & Ryu (realistic-assumption crypto momentum): time-series momentum evidence is strong, cross-sectional weak; TSMOM is concentrated in bull markets; mean-return t-tests alone are insufficient to establish profitability. — [AUT/ACFR paper](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf)
- AdaptiveTrend (arXiv preprint 2602.11708): 6-hour candles, dynamic volatility-calibrated trailing stops, 150+ pairs, 2022-2024: reported Sharpe 2.41, max DD -12.7%, Calmar 3.18. Self-reported, not peer-reviewed; treat cautiously. — [arXiv 2602.11708](https://arxiv.org/html/2602.11708v1)
- Practitioner backtest (single author, crypto bot): trailing stops did ~8% worse in total profit than a fixed -3.5% stop due to whipsaw in jagged crypto moves; final setup used fixed stop + time-based exit. Anecdotal. — [DEV Community](https://dev.to/trendrider/i-tested-4-stop-loss-methods-on-my-crypto-bot-heres-what-actually-works-47i0)

### Inferences

**Standard definitions (domain knowledge, not re-verified this session) — implementable formulas**

- ATR trailing stop (long): S_t = max(S_{t-1}, C_t - m x ATR_t(n)) (ratcheting; variant uses H_t instead of C_t). Typical m = 2-4, n = 14-22. Exit when C_t < S_{t-1} (close-based) or L_t <= S_{t-1} (intrabar). The ratchet max() is what turns a volatility band into a trailing stop.
- Chandelier (ratcheted, since-entry form): S_t = max(S_{t-1}, max_{entry<=i<=t} H_i - m x ATR_t(n)), m = 3, n = 22.
- Kase DevStop (long): TRD_t = max(H_t, H_{t-1}, C_{t-2}) - min(L_t, L_{t-1}, C_{t-2}) [two-bar true range]; mu = mean(TRD, n=30); sd = stdev(TRD, 30); DevStop_k,t = (highest close or high since entry, or of recent bars) - (mu + k x sd), k in {0, 1, 2.2, 3.6}. Implementations differ on reference price (close vs high) and skew correction (see conflict above).
- Parabolic SAR (Wilder 1978) for a long: SAR_{t+1} = SAR_t + AF_t x (EP_t - SAR_t), where EP = highest high since trade start, AF starts at 0.02, increases by 0.02 each new EP, capped at 0.20; SAR_{t+1} may not exceed min(L_t, L_{t-1}). Its acceleration means the stop tightens with trade age regardless of volatility — effectively a hybrid time+price stop. Long-only: use only the "long" leg and treat a flip as flat, not short.
- Time stop: exit if bars_in_trade >= T_max, or if after T_check bars the open profit < k x ATR (i.e., "trade didn't work"). Kaufman/LeBeau style.
- Break-even stop: once open profit >= a x ATR (or a x initial risk R), set S = entry price + fees/slippage buffer. Converts losers into scratches but also truncates trades that retrace before trending — the Kaminski-Lo logic implies it helps only when there is momentum after the trigger.
- Profit target: exit at entry + b x R (R = entry - initial stop). Under positive autocorrelation, targets cap the right tail that pays for trend-following; trend systems typically depend on a small number of large winners, so fixed targets usually reduce expectancy in trend systems and are more appropriate for mean-reversion systems.
- Volatility-adjusted stop distance generally: stop = k x sigma_hat x sqrt(h) where sigma_hat = per-bar return volatility and h = expected holding horizon in bars; links stop distance to the holding period so the probability of noise stop-out is roughly constant across instruments/timeframes.

**Synthesis**
- For a long-only spot crypto trend system on 15m-1d bars, the Kaminski-Lo framework predicts: stops help if the system is momentum-based and the stop is wide enough not to fire on noise (their positive premiums appear at longer frequencies and wider thresholds). This favours wide, volatility-scaled trailing exits (Chandelier m approx. 3, DevStop k = 2.2-3.6) on 4h-1d bars, and argues against tight fixed-% stops on 15m bars where microstructure noise dominates.
- Since crypto TSMOM is concentrated in bull regimes (Han, Kang & Ryu), a trailing stop is functionally a regime-exit tool for long-only spot: it moves to cash when the uptrend ends — which is exactly the case where stopping premium can be positive.
- Profit targets are inconsistent with trend-following's payoff skew; if used, prefer partial scale-out (e.g. sell 1/3 at 2R, trail the rest).
- Recommended ablation to implement in the terminal: same entry signal, compare (a) signal-reversal exit only, (b) + ATR/Chandelier trailing, (c) + time stop, (d) + break-even, (e) + fixed target; judge by expectancy in R, PSR and Ulcer/UPI, net of fees.

### Gaps
- Could not read the Kaminski & Lo PDF (HTTP 429), so the exact stopping-premium formula, the (gamma, delta, J) rule parameters, and the empirical magnitudes (bps/month) are not captured here.
- No primary-source verification of Carver's, Clenow's, Kaufman's or Tharp's specific stop-loss evidence. From domain knowledge (unverified): Carver argues trend systems should exit via forecast change rather than separate stop-losses; Clenow's "Following the Trend" uses ~3 ATR trailing stops; Kaufman's book contains many stop comparisons generally showing wide stops beat tight stops for trend systems. These should be confirmed before being cited.
- No rigorous, peer-reviewed crypto study isolating trailing-stop vs. no-stop vs. profit-target performance was found.
- Kase's original DevStop white paper (exact skew correction, reference price) not found.

---

## 2. Position management: pyramiding, portfolio volatility targeting, CPPI, drawdown de-risking, Carver forecast scaling and position formula

### Takeaway
Volatility targeting reliably reduces tail risk and vol-of-vol and improves Sharpe mainly for "risk assets" (equities, credit) — crypto behaves like a risk asset so it is the most relevant use. Carver's chain (forecast scaled to average |10|, capped at 20; position = forecast/10 x volatility scalar) is a clean, implementable framework. CPPI and drawdown-floor rules give a hard capital-protection overlay at the cost of "cash-lock" after a crash.

### Cited Findings

**Turtle unit sizing and pyramiding**
- N = 20-day ATR (some sources: 20-day EMA of TR). Unit = (1% of equity) / (N x dollar value per point). — [FXOpen](https://fxopen.com/blog/en/turtle-trading-system-rules-and-strategy); [MQL5](https://www.mql5.com/en/articles/23448)
- Add one unit each time price moves +1/2 N from the previous entry; max 4 units per market; stops on all units moved to 2N below the latest entry. — [FXOpen](https://fxopen.com/blog/en/turtle-trading-system-rules-and-strategy); [TrendSpider](https://trendspider.com/learning-center/richard-dennis-turtle-trading-strategy/)
- Sources differ on sizing % (1% vs 2%) and stop-adjustment method (some modern scripts advance stop 0.5 ATR per add). — [TradingView script](https://www.tradingview.com/script/jbyeMkat/)

**Volatility targeting — Moreira & Muir (2017)**
- "Volatility-Managed Portfolios", Journal of Finance 72(4), 1611-1644. Scales monthly factor returns by the inverse of the previous month's realized variance. — [NBER w22208](https://www.nber.org/papers/w22208); [RePEc](https://econpapers.repec.org/RePEc:nbr:nberwo:22208)
- Managed return: f^sigma_t = (c* / sigma_hat^2_{t-1}) x f_t, where f_t = original excess return, sigma_hat^2_{t-1} = prior-month realized variance (from daily returns), c* = constant chosen so f^sigma and f have the same full-sample variance. — [Sydney/SBFC paper restating M&M](https://sbfc.sydney.edu.au/2019/papers/P057_Named.pdf); [Lehigh paper](https://www.lehigh.edu/~xuy219/research/COWY.pdf)
- Alpha of the managed portfolio is proportional to -cov(mu_t / sigma^2_t, sigma^2_t): it is positive when expected returns do not rise proportionally with variance. — [NBER PDF](https://www.nber.org/papers/w22208.pdf)

**Volatility targeting — Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & Van Hemert (2018), "The Impact of Volatility Targeting", JPM 45(1)**
- 60+ assets, daily data back to 1926 for some; vol targeting raises Sharpe for equities and credit (and balanced/risk-parity portfolios), negligible effect for bonds, FX, commodities. — [Duke PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf); [Man Institute](https://www.man.com/maninstitute/the-impact-of-volatility-targeting)
- Reduces extreme returns and vol-of-vol across assets; US equities vol-of-vol 4.6% -> 1.8%; Sharpe 0.40 -> 0.48-0.51, insensitive to the volatility estimator; reduces max drawdown for balanced/risk-parity portfolios. — [Quantpedia summary](https://quantpedia.com/the-impact-of-volatility-targeting-on-equities-bonds-commodities-and-currencies); [Alpha Architect](https://alphaarchitect.com/volatility-targeting-improves-risk-adjusted-returns/)

**CPPI (Perold 1986; Black & Jones 1987; Black & Perold 1992)**
- Cushion C_t = V_t - F_t (portfolio value minus floor); risky exposure E_t = m x C_t; remainder in safe asset. Floor F and multiplier m are exogenous (investor risk tolerance). — [Wikipedia CPPI](https://en.wikipedia.org/wiki/Constant_proportion_portfolio_insurance); [Mancinelli 2022](https://iris.uniroma1.it/retrieve/handle/11573/1645856/2057356/Mancinelli_%20Managing-cash-risk_2022.pdf)
- As C -> 0, exposure -> 0; continuous rebalancing keeps V above F; with discrete rebalancing the floor is breached if the risky asset falls more than 1/m between rebalances (gap risk). Once cushion hits zero the strategy is fully de-risked and cannot recover ("cash lock"). — [Wikipedia CPPI](https://en.wikipedia.org/wiki/Constant_proportion_portfolio_insurance); [MetricGate](https://metricgate.com/docs/constant-proportion-portfolio-insurance/)

**Carver, "Systematic Trading" — position formula (via secondary summaries)**
- Block value = value change of one block (e.g., one share/coin) for a 1% price move = 0.01 x price x contract multiplier. — [the7circles summary](https://the7circles.uk/?p=24214)
- Instrument currency volatility (ICV) = price volatility (daily % stdev) x block value. Volatility scalar = daily cash volatility target / ICV. — [the7circles](https://the7circles.uk/?p=24214)
- Subsystem position (blocks) = volatility scalar x forecast / 10; average absolute forecast = 10, so +10 = one full volatility-scaled position, +5 = half. — [the7circles](https://the7circles.uk/?p=24214)
- Position inertia: no trade if current position within 10% of target (cost control). — [the7circles part 6](https://the7circles.uk/?p=24323)

### Inferences

**Standard definitions (domain knowledge, not re-verified this session)**
- Carver forecast scaling: scaled_forecast_t = raw_forecast_t x FS, with FS = 10 / mean(|raw_forecast|) estimated over a long pooled history; then cap to [-20, +20]. Combined forecast = IDM_f x sum_j w_j x scaled_forecast_j (IDM_f = forecast diversification multiplier, approx. 1/sqrt(w' rho w)), re-capped at +/-20.
- Daily cash volatility target = capital x annual % vol target / 16 (16 approx. sqrt(256) trading days). For crypto trading 365 days, use sqrt(365) approx. 19.1 instead of 16 (inference).
- Portfolio position = subsystem position x instrument weight x instrument diversification multiplier (IDM).
- Long-only adaptation: position = max(0, forecast)/10 x vol scalar (negative forecasts -> flat).
- Portfolio-level vol targeting (practical): w_t = min(L_max, sigma_target / sigma_hat_t), sigma_hat_t = EWMA or realized vol of the portfolio (or asset) returns over a short lookback (e.g. 20-60 days); L_max = 1 for unlevered spot. Harvey et al. found the estimator choice barely matters.
- Drawdown-based de-risking (Grossman & Zhou 1993 / TIPP, Estep & Kritzman 1988): floor F_t = alpha x max_{s<=t} V_s (e.g. alpha = 0.8 for a 20% max-DD constraint); exposure E_t = m x (V_t - F_t). A simpler linear de-risk: scale = clip(1 - DD_t / DD_max, 0, 1), where DD_t = 1 - V_t / max_{s<=t} V_s.
- Turtle-style pyramiding as formula: add unit k (k = 2..4) at P_entry,1 + (k-1) x 0.5 x N; after each add, S = P_entry,k - 2N for all units.

**Synthesis / applicability to long-only spot crypto**
- Volatility targeting is likely most valuable for crypto (a high-vol, vol-clustering risk asset); Harvey et al.'s finding that benefits concentrate in risk assets supports this. With no leverage, the cap L_max = 1 means vol targeting only de-risks in high-vol regimes (it cannot lever up in calm regimes) — this asymmetry still reduces tail risk.
- CPPI on top of a crypto strategy: crypto gap moves (10-30% intraday) mean m should be <= ~1/(worst plausible inter-rebalance drop), e.g. m <= 3-5 for 15m-1h rebalancing; cash-lock should be handled by periodic floor reset (ratchet) rather than permanent stop.
- Pyramiding is compatible with long-only spot (adds only on strength). On 15m bars, 0.5N adds may trigger too frequently and inflate fees; prefer 1h-1d bars.

### Gaps
- Moreira & Muir's published numerical results (alpha, Sharpe improvements per factor) not retrieved; later literature (e.g., Cederburg et al. 2020) disputes out-of-sample gains — not verified this session.
- Carver's book itself not consulted; formulas come from secondary blog summaries.
- No crypto-specific study of CPPI or drawdown de-risking found.

---

## 3. Execution scheduling: Almgren-Chriss, VWAP volume-profile scheduling, POV, iceberg/limit placement; relevance at small retail size

### Takeaway
Almgren-Chriss gives a closed-form sinh trajectory that front-loads trading as risk aversion rises and collapses to TWAP when risk aversion is zero. At retail size on liquid crypto pairs (order << 1% of bar volume), impact is negligible, so the practically relevant execution levers are maker vs taker fees, spread, and limit-order placement; A-C/VWAP/POV matter only for illiquid altcoins or large orders.

### Cited Findings
- Continuous-time A-C holding trajectory: x(t) = X x sinh(kappa(T - t)) / sinh(kappa T), trading rate v(t) = X kappa cosh(kappa(T - t)) / sinh(kappa T), with urgency kappa = sqrt(lambda sigma^2 / eta) (lambda = risk aversion, sigma = price volatility, eta = temporary impact coefficient, X = initial shares, T = horizon). — [Wikipedia: Almgren-Chriss model](https://en.wikipedia.org/wiki/Almgren%E2%80%93Chriss_model); [mghnasiri notes](https://mghnasiri.github.io/MathematicalModeling/applications/optimal-execution.html)
- kappa -> 0 (lambda = 0) gives the linear TWAP schedule; larger kappa front-loads trading. — [mghnasiri notes](https://mghnasiri.github.io/MathematicalModeling/applications/optimal-execution.html)
- Discrete version (N trades, interval tau = T/N): x_j = sinh(kappa(T - t_j)) / sinh(kappa T) x X; trade list n_j = [2 sinh(kappa tau / 2) / sinh(kappa T)] x cosh(kappa(T - t_{j-1/2})) x X; kappa solves (2/tau^2)(cosh(kappa tau) - 1) = kappa_tilde^2, i.e. kappa = (1/tau) arccosh(tau^2 kappa_tilde^2 / 2 + 1), with kappa_tilde^2 = lambda sigma^2 / eta_tilde; reduces to continuous kappa as tau -> 0. — [arXiv 1403.2229](https://arxiv.org/pdf/1403.2229); [blotter acOptTxns docs](https://rdrr.io/github/braverock/blotter/man/acOptTxns.html)
- Original: Almgren & Chriss (2000/2001), "Optimal Execution of Portfolio Transactions", Journal of Risk 3(2), 5-40. Notation varies across sources (eta vs eta_tilde, drift terms). — [Wikipedia](https://en.wikipedia.org/wiki/Almgren%E2%80%93Chriss_model)

### Inferences

**Standard definitions (domain knowledge, not re-verified this session)**
- A-C impact model: permanent impact g(v) = gamma v (price shift per unit traded rate); temporary impact h(v) = epsilon sgn(n_k) + (eta / tau) n_k (epsilon = half-spread + fees, eta = temporary impact). eta_tilde = eta - gamma tau / 2.
- Expected cost E = (1/2) gamma X^2 + epsilon sum |n_k| + (eta_tilde / tau) sum n_k^2; variance V = sigma^2 sum_k tau x_k^2. Objective: min E + lambda V.
- Calibration heuristic from the original paper (as commonly cited): epsilon = half the bid-ask spread; eta such that trading 1% of daily volume costs ~one spread; gamma such that trading 10% of daily volume moves price ~one spread. Treat as order-of-magnitude.
- VWAP volume-profile scheduling: q_k = Q x u_k / sum_j u_j, where u_k = historical average volume fraction for intraday bucket k (e.g. median over last 20-30 days of volume in bucket k / day's volume). Crypto has a 24h profile with peaks around US/EU opens and funding/hourly boundaries.
- POV (percent of volume): in each interval, child order size q_k = rho x V_k^market (rho = participation, e.g. 5-10%), completion time is stochastic; often expressed as q_k = rho/(1 - rho) x V_k^others if counting own volume.
- Iceberg / limit placement heuristics: display size = small fraction of resting depth at the level; place passive limit at best bid (buy) to earn maker rebate/fee tier; reprice after t_wait seconds or when the mid moves > 1 tick away; fall back to marketable limit (limit at ask + x bps cap) after deadline. Fill probability falls sharply with distance from touch.

**Relevance at small retail size, long-only spot crypto**
- If order notional / bar volume << 0.1-1%, A-C kappa effects and square-root impact are dominated by spread + fees; the optimal "schedule" is a single child order. Binance-style spot maker/taker fees (~0.1% base, lower with tiers/BNB) are typically larger than impact for a retail order on BTC/ETH.
- Practical gains: (1) post-only limit at touch with timeout -> marketable limit, (2) avoid market orders on thin altcoin books, (3) execute signals at bar close + short delay rather than at the exact boundary where many bots fire, (4) model fees + half-spread as epsilon in the backtest.
- A-C and POV become relevant only for small-cap altcoins where order size is a meaningful fraction of 1-minute volume or top-of-book depth.

### Gaps
- Primary A-C paper not fetched; cost/variance expressions and calibration heuristic are from domain knowledge.
- No source found quantifying crypto intraday volume profiles or maker fill probabilities by distance from touch for retail sizes.

---

## 4. Evaluation metrics: Sortino, Calmar, MAR, Omega, Ulcer/UPI, Information ratio, PSR, MinTRL, Tail ratio, Gain-to-pain, SQN, K-ratio, Sterling/Burke, ES-based ratios

### Takeaway
PSR and MinTRL (Bailey & López de Prado 2012) are the most important additions: they convert a Sharpe ratio into a probability that the true SR exceeds a benchmark, correcting for sample length, skew and fat tails — critical for crypto's heavy-tailed, short-history returns. Drawdown-based ratios (Calmar/MAR, Ulcer/UPI, Sterling, Burke) and Omega complement them; SQN and K-ratio are trade-level / equity-curve quality checks with inconsistently documented variants.

### Cited Findings

**Probabilistic Sharpe Ratio and Minimum Track Record Length (Bailey & López de Prado 2012, "The Sharpe Ratio Efficient Frontier", Journal of Risk)**
- Paper computes the probability that an estimated SR exceeds a threshold under non-normal returns and the track-record length needed to reject SR <= threshold at a given confidence; more skew / fatter tails -> longer track records required. — [Risk.net](https://www.risk.net/journal-risk/2223785/sharpe-ratio-efficient-frontier); [IDEAS](https://ideas.repec.org/a/rsk/journ4/2223785.html)
- Mertens (2002) standard error of SR_hat: sqrt[(1/(n-1)) (1 + SR^2/2 - gamma3 SR + SR^2 (gamma4 - 3)/4)], gamma4 = raw kurtosis; algebraically equals (1/(n-1)) x (1 - gamma3 SR + ((gamma4 - 1)/4) SR^2). — [SLCG practice note](https://www.slcg.com/files/practice-notes/sharpe-ratio.pdf)
- PSR = Phi( (SR_hat - SR*) sqrt(n - 1) / sqrt(1 - gamma3 SR_hat + ((gamma4 - 1)/4) SR_hat^2) ); positive skew and longer samples raise PSR, higher kurtosis lowers it. — [QuantConnect PSR research](https://www.quantconnect.com/research/17112/probabilistic-sharpe-ratio/); [PerformanceAnalytics ProbSharpeRatio](https://rdrr.io/cran/PerformanceAnalytics/man/ProbSharpeRatio.html)
- Symbols: n = number of return observations; SR_hat = non-annualized per-period SR; SR* = benchmark SR in the same periodicity (non-annualized); gamma3 = skewness; gamma4 = raw kurtosis (normal = 3; if using excess kurtosis k_e, replace (gamma4 - 1)/4 by (k_e + 2)/4); Phi = standard normal CDF. Reference implementation default confidence p = 0.95; note PerformanceAnalytics defaults to ignore_kurtosis = TRUE. — [PerformanceAnalytics MinTrackRecord](https://rdrr.io/pkg/PerformanceAnalytics/man/MinTrackRecord.html)
- MinTRL = 1 + [1 - gamma3 SR_hat + ((gamma4 - 1)/4) SR_hat^2] x ( Phi^{-1}(1 - alpha) / (SR_hat - SR*) )^2, in observations of the same frequency as SR_hat. Worked example: SR_hat = 0.2/period, gamma3 = -1, gamma4 = 5, SR* = 0, alpha = 0.05 -> variance term 1.24, MinTRL approx. 85 obs; with n = 250, PSR approx. 0.998. (Formula provided by the fetch tool's model from literature knowledge because the PDF was unreadable; consistent with the SLCG and QuantConnect forms above.) — [Bailey & López de Prado PDF (attempted)](https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf); [SLCG](https://www.slcg.com/files/practice-notes/sharpe-ratio.pdf)

**Ulcer Index and Ulcer Performance Index (Peter Martin, 1987; Martin & McCann 1989)**
- R_i = 100 x (C_i - max(C over lookback up to i)) / max(C over lookback up to i); UI = sqrt( sum_{i=1}^{N} R_i^2 / N ); common default lookback 14 periods (as an indicator). — [Wikipedia](https://en.wikipedia.org/wiki/Ulcer_index); [StockCharts](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/ulcer-index)
- UPI (Martin ratio) = (return - risk-free return) / UI; StockCharts uses total return, TradingView uses average excess return — convention differs. Higher is better. — [StockCharts](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/ulcer-index); [TradingView](https://th.tradingview.com/support/solutions/43000773115/)
- Martin advises sampling no less often than weekly, since drawdowns and recoveries can hide inside coarse periods. — [Wikipedia](https://en.wikipedia.org/wiki/Ulcer_index)

**Omega ratio (Keating & Shadwick 2002)**
- Omega(L) = integral_L^b (1 - F(x)) dx / integral_a^L F(x) dx, F = CDF of returns, L = threshold, (a, b) = return range. Equivalent: Omega(L) = E[(R - L)+] / E[(L - R)+] = (E[R] - L)/E[(L - R)+] + 1. — [Wikipedia Omega ratio](https://en.wikipedia.org/wiki/Omega_ratio); [Keating & Shadwick intro (Duke)](https://people.duke.edu/~charvey/Teaching/BA453_2006/Keating_An_introduction_to.pdf); [arXiv 1911.10254](https://arxiv.org/pdf/1911.10254)
- Sensitive to threshold choice with no systematic way to set it; L = 0 gives the Bernardo-Ledoit gain-loss ratio. — [arXiv 2103.13806](https://arxiv.org/pdf/2103.13806)

**Van Tharp SQN**
- SQN = sqrt(N) x mean(R) / stdev(R), N = number of trades, R = trade P&L / initial risk (R-multiple); a t-statistic variant. — [NexusFi](https://nexusfi.com/a/risk-management/system-quality-number-sqn); [LuxAlgo](https://www.luxalgo.com/library/concept/sqn/)
- Commonly N capped at 100 for comparisons (attribution to Tharp disputed in secondary sources); score bands (e.g., <1.6 poor, >7 likely curve-fit) unverified against Tharp. SQN is inflated by trade frequency via sqrt(N) and ignores drawdown ordering. — [NexusFi](https://nexusfi.com/a/risk-management/system-quality-number-sqn); [Medium](https://medium.com/@niclas_hummel/system-quality-number-sqn-cb04cf7e9ecd)

**K-ratio (Lars Kestner)**
- 1996: K = slope(OLS of log cumulative equity, "log VAMI", on time) / (n x SE(slope)); 2003 revision includes number of data points in the denominator; 2013 revision (SSRN 2230949) reported as K2003 x sqrt(252)/n for daily data. Sources conflict on where sqrt(n) enters. — [Wealth-Lab forum](https://wl6.wealth-lab.com/Forum/Posts/-quot-K-Ratio-quot-Which-variation-40531); [MetricGate](https://metricgate.com/docs/kestner-k-ratio/)

### Inferences

**Standard definitions (domain knowledge, not re-verified this session)** — r_i per-period returns, N periods, T = target/MAR return, A = periods per year (crypto: 365 for daily, 365x24 for hourly, 365x96 for 15m)
- Sortino = (mean(r) - T) / DD_T, DD_T = sqrt( (1/N) sum_{i=1}^{N} min(0, r_i - T)^2 ) (divide by total N, not the count of downside observations — a common implementation bug). Annualize: x sqrt(A).
- Calmar = CAGR / |MaxDD| over trailing 36 months (Young 1991); MAR ratio = CAGR / |MaxDD| over full history (Managed Account Reports). Same formula, different window.
- Sterling = CAGR / (mean of the annual max drawdowns - 10%) in original form; common modern variant: CAGR / mean(|largest K drawdowns|).
- Burke = (CAGR - r_f) / sqrt( sum_{j=1}^{K} DD_j^2 ), DD_j = j-th drawdown depth (all drawdowns or largest K).
- Information ratio = mean(r - r_b) / stdev(r - r_b) x sqrt(A); for a crypto strategy, benchmark r_b = buy-and-hold BTC (or the traded coin).
- Tail ratio = |Q_95(r)| / |Q_05(r)| (95th percentile over absolute 5th percentile); > 1 means right tail fatter.
- Gain-to-pain (Schwager) = sum(r_i) / |sum(r_i for r_i < 0)|, usually on monthly returns; it is Omega(0) - 1 computed on sums (= profit factor on periodic returns).
- ES-based ratios: STARR / conditional Sharpe = (mean(r) - r_f) / ES_alpha(r), ES_alpha = -E[r | r <= VaR_alpha]; Rachev ratio = ES_alpha(-r) / ES_beta(r) (upside tail expectation over downside tail expectation), typically alpha = beta = 5%.
- K-ratio implementation (2003 form, commonly used): fit ln(E_t) = a + b t; K = b / (SE(b) x sqrt(n)); annualize consistently.

**Synthesis / applicability to long-only spot crypto on 15m-1d bars**
- Compute all ratios on a uniform bar frequency (resample equity to daily before Sortino/Sharpe/Omega to avoid intraday autocorrelation and the 24/7 annualization ambiguity; use A = 365).
- PSR/MinTRL are essential: crypto daily returns have strong negative skew episodes and raw kurtosis often >> 3, so the naive t-stat overstates significance; MinTRL tells you whether a 6-month crypto backtest is long enough. Use PSR(SR* = 0) and PSR vs buy-and-hold SR.
- Ulcer/UPI and Calmar are the most interpretable for a long-only spot user who experiences drawdowns directly; Ulcer penalizes depth and duration, unlike MaxDD.
- SQN is useful for per-trade R-multiple quality (fits the existing expectancy metric) but should be reported with N capped at 100 and alongside PSR because high-frequency 15m systems inflate it.
- Omega should use L = 0 (or per-period fee-adjusted hurdle) and be reported alongside its threshold.

### Gaps
- Bailey & López de Prado PDF unreadable (compressed binary) — PSR/MinTRL formulas corroborated via Mertens/SLCG, QuantConnect and PerformanceAnalytics rather than the original text.
- Primary sources for Sortino & Price (1994), Young's Calmar (1991), Sterling/Burke originals, Schwager's gain-to-pain and the tail ratio were not retrieved; definitions above are domain knowledge and variants exist.
- Kestner's 2013 K-ratio paper not retrieved; exact sqrt(n) placement unresolved.
- Tharp's original SQN cap and interpretation bands not verified against his books.
