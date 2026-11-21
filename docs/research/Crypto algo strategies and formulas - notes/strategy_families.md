# Directional Strategy Families Missing From the Terminal (Long-Only Spot Crypto)

Scope: strategy families the terminal does NOT yet have, implementable on Binance spot OHLCV (15m/1h/4h/1d, taker-buy volume available), long-only. Every rule block marked "Implementable spec" is a concrete adaptation derived from the cited source. Where the source gives the rule, it says so. Where the long-only or Binance adaptation is my own, it is listed under Inferences. Evidence grades used below:
- **A**: peer-reviewed, multi-coin, some cost or out-of-sample treatment.
- **B**: peer-reviewed or serious working paper, gross of costs or single period.
- **C**: practitioner backtest (Quantpedia-style), in-sample, no costs.
- **D**: definitions, vendor blogs, or marketing only, with no credible tested result.

Research method note: about 25 tool calls. Several primary PDFs (SSRN Arefev 2026, Dobrynskaya HSE PDF, Pang-Wang arXiv 2611.01951, Springer "tea time") could not be read (403, binary-only, or paywall), so their numbers come from search snippets and are flagged.

---

## 1. Cross-sectional momentum and short-term reversal (incl. long-only top-k)

### Takeaway
Cross-sectional (CS) crypto momentum is documented at short horizons (1-4 weeks), with reversal beyond about 1 month. It loads strongly on large coins. Long-short alphas, however, come largely from short legs and shrink sharply or vanish net of costs. A long-only top-k rotation among liquid Binance coins is implementable, but its edge versus simply holding BTC or an equal-weight basket is unproven after costs. Treat it as a portfolio-construction rule, not a standalone alpha.

### Cited Findings
- Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency" (J. Finance 2022, 77(2):1133-1177; NBER w25882). They test 25 equity-style factors on coins with market cap above $1M, 2014-2018 (109 coins rising to 1,583). Three factors (market CMKT, size CSMB, momentum CMOM) explain the cross-section, and momentum works more strongly in larger coins. — [NBER PDF](https://www.nber.org/papers/w25882.pdf); [EconPapers](https://econpapers.repec.org/RePEc:bla:jfinan:v:77:y:2022:i:2:p:1133-1177); [Alpha Architect summary](https://alphaarchitect.com/factors-investing-in-cryptocurrency/)
- In LTW, momentum in the below-median size group gives statistically insignificant weekly excess returns (about 0.6%/week). Another study finds the reverse pattern (momentum stronger in small coins), so the size interaction is contested. — [search summary of LTW / related](https://cowles.yale.edu/sites/default/files/2022-10/LiuTsyvinskiWu2019%20COMMON%20RISK%20FACTORS.pdf)
- Dobrynskaya, "Cryptocurrency Momentum and Reversal" (J. Alternative Investments 2023). The sample is the 2,000 largest coins, 2014-2020. It finds momentum at horizons up to 2-4 weeks and significant reversal beyond 1 month, with reversal strengthening as holding periods lengthen. The returns are reportedly not explained by standard crypto factors. Results are gross of costs as far as the abstract shows. — [SSRN 3913263](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3913263); [ResearchGate](https://www.researchgate.net/publication/369536471_Cryptocurrency_Momentum_and_Reversal)
- "Cryptocurrency anomalies and economic constraints" (Int. Rev. Financial Analysis 2024). The sample is 3,956 coins, 2014-2022. Momentum is strongest in large coins, but it incurs substantial trading costs and extracts alphas largely from short positions. This matters directly for long-only. — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509)
- Grobys & Sapkota (2019), "Cryptocurrencies and momentum" (Economics Letters 180:6-10). The sources disagree on what it found. Some summaries describe the average momentum return as negative and insignificant, while another describes significant payoffs of about 3%/week. Check the original paper before relying on either. — [IDEAS](https://ideas.repec.org/a/eee/ecolet/v180y2019icp6-10.html); [Univ. Vaasa repository](https://osuva.uwasa.fi/handle/11111/2278)
- "Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets" (Int. Rev. Financial Analysis 78, 2021). It reports a strong size effect, a distinctive short-term reversal, and an illiquidity premium, and argues the reversal challenges the momentum effect. Crypto momentum may be partly a short-term reversal artifact (Cakici & Zaremba 2021 is cited for this). — [IDEAS](https://ideas.repec.org/a/eee/finana/v78y2021ics1057521921002349.html)
- Nakagawa & Sakemoto (SSRN 2025): behaviorally based CS reversal portfolios in crypto are reported as profitable under conservative transaction-cost assumptions. — [SSRN](https://doi.org/10.2139/ssrn.5001299)
- Arefev (SSRN 2026), "Cross-Sectional Momentum in Cryptocurrency: A Net-of-Costs Replication on Tradable Binance Perpetuals (2020-2026)". This is the most relevant recent test (Binance-tradable universe, net of costs). The page returned 403 and I could not verify its results. — [SSRN 7404139](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7404139)
- Trend factor (CTREND): Fieberg, Liedtke, Poddig, Walker & Zaremba (JFQA 2025). The factor aggregates price and volume technical signals across horizons into a CS trend factor, and a model including it beats competing factor models. — [Cambridge/JFQA](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178); [JFQA PDF](https://jfqa.org/wp-content/uploads/2024/09/24955-trend-factor-cross-section-crypto-returns.pdf)
- Replication of CTREND, Pang & Wang (arXiv 2611.01951, 2026). Net of the lowest assumed costs, the long-short weekly mean return falls to -0.87%. Performance "depends materially on implementation rules and the asset universe". This is from the search snippet only; the PDF was unreadable. — [arXiv](https://arxiv.org/pdf/2611.01951)
- "Cryptocurrency factor momentum" (Fieberg, Liedtke, Metko, Zaremba; Quantitative Finance 2023) documents momentum at the level of crypto factor returns. This is not directly a single-coin rule. — [IDEAS](https://ideas.repec.org/a/taf/quantf/v23y2023i12p1853-1869.html)
- MAX momentum (Li & Urquhart): coins with extreme past daily returns (max daily return) keep outperforming, which is the opposite of the equity "lottery" MAX effect. — [Reading repository PDF](https://centaur.reading.ac.uk/99101/1/MAX%20Momentum.R1.pdf)
- Non-peer-reviewed backtest (GitHub, student-style): reversal Sharpe falls from 4.41 gross to -1.73 at 20 bps costs, while momentum has a breakeven around 35 bps. This illustrates cost sensitivity; it is grade D. — [GitHub prams2104](https://github.com/prams2104/crypto-momentum-backtest)

### Inferences
- **Implementable spec: CS momentum, long-only top-k (grade B evidence, adapted)**
  - Universe: Binance spot USDT pairs, top N=20-30 by trailing 30-day median quote volume. Exclude stablecoins and leveraged tokens, and require at least 90 days of history. A large-coin universe is where LTW and the 2024 IRFA paper locate momentum, and it keeps costs low.
  - Signal: R_i = close_t / close_{t-L} - 1 on 1d bars, with L ∈ {7, 14, 21, 28} days. The literature positive zone is 1-4 weeks; use 21d as the default, or an average of the ranks over 7/14/21/28 to reduce parameter risk.
  - Optional skip: excluding the most recent 1 day guards against the short-term reversal the IRFA 2021 paper documents. This is an inference, not tested in the sources.
  - Holding/rebalance: weekly (LTW and Dobrynskaya use weekly portfolios). Hold the top k=3-5, equal weight or inverse-vol weight (1/σ_30d).
  - Buffer rule to cut turnover: only sell a holding if its rank falls below 2k.
  - Absolute filter (see section 2): hold a coin only if R_i > 0, and hold nothing if BTC < SMA(BTC,100d) or similar. Otherwise go to USDT.
  - Costs: model 10 bps taker per side plus 5-10 bps slippage. Given the reported 20-35 bps breakevens, anything above about 25 bps round-trip per weekly rebalance likely kills a pure ranking edge.
- **Implementable spec: short-term reversal, long-only (grade B/D)**
  - Buy the k biggest 1-week losers among the top 30 liquid coins, hold for 1 week. Costs destroy most reported reversal profits (see the GitHub example), and the reversal premium sits in illiquid tails. For long-only on liquid Binance coins I would rate this low priority, best used as a "don't chase the top weekly gainer" filter on the momentum strategy.
- **Implementable spec: MAX-momentum variant (grade B)**
  - Rank by max(daily return over the last 30d). Hold the top k weekly. Same filters and costs as above.
- The long legs of crypto CS strategies are largely market beta (LTW CMKT). The realistic benefit of top-k rotation is avoiding dead coins and keeping exposure in leaders. It should be benchmarked against equal-weight top-N and BTC buy-and-hold, not against cash.

### Gaps
- I could not read the Arefev (2026) net-of-cost Binance replication or the Dobrynskaya tables. Exact long-leg-only returns net of costs for a top-k liquid universe were not found in any source I could open.
- I did not verify exact LTW formation and holding parameters (weekly 1-4 week past returns, quintile sorts) from the full text in this session.
- No source tested a long-only top-k CS rule on Binance spot with costs post-2022.

---

## 2. Dual momentum (absolute + relative, Antonacci) adapted to crypto

### Takeaway
The only crypto-specific dual-momentum backtest found is Quantpedia's BTC-vs-gold rotation (weekly, 4-12 week lookbacks). It is strong in-sample but has no costs and about 44-49% max drawdown. The absolute-momentum leg is what cuts drawdowns, consistent with Antonacci. For a crypto-only terminal, the natural adaptation is "relative momentum among BTC/ETH/top alts + absolute momentum vs USDT".

### Cited Findings
- Quantpedia (Vojtko & Dujava), dual momentum between gold (GLD) and bitcoin (BITO/IBIT), Dec 2018 - Apr 2026. Weekly rebalance at Wednesday close. Hold BTC if its X-week return > gold's X-week return and > 0; hold gold under the mirror condition; otherwise cash at 0%. X ∈ {1,2,3,4,6,8,12,20,24,28} weeks; best single X = 8 weeks; composite = average of the 4/8/12-week versions. — [Quantpedia](https://quantpedia.com/dual-momentum-allocation-between-physical-gold-and-bitcoin-digital-gold/)
- Results (no costs stated): 8-week version 79.91% CAGR, Sharpe 1.64, MDD -43.94%. Composite 64.73% CAGR, Sharpe 1.47, MDD -49.40%. Vol-capped composite (weight = min(1, 20%/σ_12w·√52)) 12.01% CAGR, Sharpe 1.37, MDD -12.27%. BTC buy-and-hold over the same period 46.66% CAGR, Sharpe 0.73, MDD -77.49%. Grade C. — [Quantpedia](https://quantpedia.com/dual-momentum-allocation-between-physical-gold-and-bitcoin-digital-gold/)
- A secondary write-up of the same paper uses lookbacks of 11, 21, 32, 42, 63 and 84 trading days, and says the composite beats every single configuration on an absolute and risk-adjusted basis. — [Valuelytica Substack](https://valuelytica.substack.com/p/golden-dual-momentum-rotation)
- Antonacci's absolute-momentum component mainly reduces volatility and drawdowns (summary of the original paper). — [Papers With Backtest podcast summary](https://podcast.ausha.co/papers-with-backtest-an-algorithmic-trading-journey/dual-momentum-a-deep-dive-into-gary-antonacci-s-strategy)
- A Lithuanian journal study of TS and CS crypto momentum finds trend persistence and volatility remain the key drivers of momentum profitability. — [Business: Theory and Practice (VU)](https://www.journals.vu.lt/BATP/lt/article/download/44540/42590/138419)

### Inferences
- **Implementable spec: crypto dual momentum (grade C, adapted)**
  - Assets: {BTC, ETH, plus optionally the top-3 alt by liquidity}; cash = USDT.
  - Every week (fixed day/hour, e.g. Wednesday 00:00 UTC on 1d bars), compute R_X = close_t / close_{t-X·7d} - 1 for X ∈ {4, 8, 12} weeks and average the three into a composite score S.
  - Relative step: pick the asset with the highest S.
  - Absolute step: hold it only if S > 0. Optionally use S > a hurdle of about 0.5%/week to cover costs, which is my inference. Otherwise hold USDT.
  - Optional vol cap: weight = min(1, target_vol / (σ_daily,84d · √365)). The Quantpedia version uses 20% annual on weekly data. For crypto-only assets, a 40-60% target is more realistic, though 20% reproduces their low-DD variant.
  - Expected turnover is low (weekly, and usually no switch), so costs are less binding than in CS momentum.
- The terminal already has plain time-series momentum. Dual momentum adds the relative selection and the cash-switch combination, so it is a distinct family worth adding.

### Gaps
- No crypto-only (BTC/ETH/alts vs USDT) dual-momentum test with costs was found. The gold/BTC test also mixes in a non-crypto asset that a Binance-spot terminal cannot hold (PAXG on Binance could proxy gold; that is an inference, untested).

---

## 3. Intraday and calendar seasonality

### Takeaway
The best-documented intraday effect is Quantpedia's "21:00-23:00 UTC" BTC hourly drift, plus a cross-exchange finding that returns are weakest around 01:00-05:00 UTC and peak around 15:00-16:00 UTC (US/Europe overlap). Several academic studies find such anomalies are not persistent across time. Day-of-week evidence is weak and unstable (a BTC Monday effect pre-2018; mostly volatility rather than return effects since). Turn-of-month has peer-reviewed positive evidence (2015-2021). Halving-cycle claims rest on 3 cycles and preprints. All of these should be treated as filters or overlays with out-of-sample checks, not standalone strategies.

### Cited Findings
- Quantpedia (Padyšák & Vojtko), Gemini hourly BTC, Oct 2015 - Feb 2022. The 22:00 and 23:00 UTC hours have the largest and most significant (5% level) positive returns, and 03:00-04:00 UTC are the worst hours, though no hour is significantly negative. Strategy: buy at 21:00 UTC, sell at 23:00 UTC (hold 2 hours) gave 33% annualized return, 20.93% volatility, -22.45% MDD. There are no costs, no out-of-sample test and no multiple-testing correction across 24 hours. Grade C. — [Quantpedia](https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/); [Quantpedia strategy page](https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin)
- Same study: with NYSE hours mapped to 15:00-21:00 UTC, overnight returns dominate on NYSE-open days, while on weekends/holidays the 15:00-21:00 UTC window is stronger and more stable. — [Quantpedia](https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/)
- "The crypto world trades at tea time: intraday evidence from centralized exchanges across the globe" (Rev. Quant. Finance & Accounting 2024). Across exchanges, returns are below average 01:00-05:00 UTC and peak 15:00-16:00 UTC. This comes from the search summary; the article was paywalled. — [Springer](https://link.springer.com/article/10.1007/s11156-024-01304-1)
- "On the Intraday Behavior of Bitcoin" (7 exchanges, more than 15M observations) finds time-specific anomalies but no persistent effects across time. — [ResearchGate](https://www.researchgate.net/publication/353205654_On_the_Intraday_Behavior_of_Bitcoin)
- Baur et al. (2019, Finance Research Letters 31:78-92) find time-specific anomalies in Bitcoin returns but no persistent effects across time. — [EconPapers](https://econpapers.repec.org/RePEc:eee:finlet:v:31:y:2019:i:c:p:78-92)
- Day of week:
  - Caporale & Plastun: BTC shows higher Monday returns, with no DOW effect in LTC, XRP or DASH (2013-2017 data). — [MPRA / EconPapers](https://econpapers.repec.org/RePEc:pra:mprapa:91429)
  - Studies covering 2013-2019 find no classical DOW return effect, only lower weekend risk/volatility. — [Brunel repository](https://bura.brunel.ac.uk/bitstream/2438/17208/3/FullText.pdf); [CESifo WP 6716](https://cesifo.org/DocDL/cesifo1_wp6716.pdf)
  - A 2024 study of the top-10 coins finds DOW effects emerging in BTC and SOL during the pandemic but not in ADA or DOGE, i.e. regime-dependent. — [MDPI JRFM 17(8):351](https://mdpi.com/1911-8074/17/8/351)
- Turn of month: Kumar (2022, Managerial Finance) finds TOM returns in BTC, ETH and LTC (Aug 2015 - Aug 2021) positive and significantly higher than non-TOM returns. Vasileiou (2023) reaches a similar conclusion for BTC/ETH. Grade B, gross. — [Emerald](https://emerald.com/insight/content/doi/10.1108/MF-02-2022-0084/full/html); [Inderscience](https://www.inderscience.com/filter.php?aid=129336)
- Halving cycle: an arXiv preprint (2607.26188) reports average forward returns strongly positive from the halving to about day 520, negative from about day 520 to 900, then positive again. It has 3 completed cycles and is not peer-reviewed. — [arXiv](https://arxiv.org/pdf/2607.26188)
- Funding-time effects (around the 00:00/08:00/16:00 UTC funding prints): I found no academic test of spot returns around funding timestamps. See section 7 for the funding level.

### Inferences
- **Implementable spec: hourly seasonality overlay (grade C)**
  - On 1h bars, long BTC from the 21:00 UTC bar open to the 23:00 UTC bar close (2 bars). This is 730 round-trips/year, so at 20 bps round-trip the cost drag is about 146%/year, far above the 33% gross. As a standalone strategy on Binance spot taker fees it is almost certainly unprofitable. Use it as a timing preference only: schedule DCA or rebalance buys outside the weak 01:00-05:00 UTC window, or delay entries from other signals into the late-US session.
- **Implementable spec: turn-of-month (grade B)**
  - Long BTC/ETH from the close of the last calendar day of the month minus 1 (T-1) to the close of day +3 of the next month. Exact window conventions vary; this is the equity-style TOM window, and the Kumar paper's exact window was not verified. That is 12 round-trips a year, so costs are small. Only adopt it after an out-of-sample check on 2021-2026 Binance data, since the published sample ends in 2021.
- **Day of week**: not robust enough for a rule. At most a volatility-sizing input (weekend volatility is lower).
- **Halving cycle**: too few observations. Use only as a narrative or regime label, not a trading rule.

### Gaps
- No post-2022 out-of-sample re-test of the 21-23 UTC effect was found. The persistence question is open, and the two academic multi-exchange studies argue against persistence.
- The exact TOM window from Kumar (2022) was not verified.
- No evidence was found on returns around Binance perpetual funding timestamps for spot.

---

## 4. Session / opening-range breakouts in a 24/7 market

### Takeaway
Crabel's ORB/NR rules are well defined for exchange-session markets. I found no published, cost-aware crypto ORB backtest. The equity ORB evidence itself is fragile (one QQQ test lost money after removing one outlier day). For crypto, a "session open" must be defined synthetically: UTC 00:00 daily open, or the Asia 00:00 / London 07:00-08:00 / NY 13:30-14:30 UTC opens. The documented 15:00-16:00 UTC return peak (section 3) offers a weak rationale for a NY-session ORB.

### Cited Findings
- Crabel's ORB: the entry is a stop placed a fixed "stretch" above (long) the session open. Stretch is typically the 10-day average of min(High - Open, Open - Low). It is often combined with NR4/NR7 days. — [Oxford Strategies, narrow range](https://oxfordstrat.com/trading-strategies/narrow-range/); [Oxford Strategies NR7 verification](https://oxfordstrat.com/?p=3707)
- An Oxford Strategies price-breakout variant (no stretch, break of the prior bar high) is reported to perform similarly to the ORB entry. The figures were in unreadable images. — [Oxford Strategies](https://oxfordstrat.com/?p=15981)
- QuantInsti classic-rule ORB on QQQ lost money once a single unusually profitable day was removed (equity example). — [QuantInsti](https://www.quantinsti.com/articles/opening-range-breakout-strategy/)
- Unger Academy tests Crabel's ORB on Nasdaq (equity index futures); this is the practitioner test of the original. — [Unger Academy](https://ungeracademy.com/?p=7020)
- Crypto-specific ORB/NR4 material is limited to TradingView idea posts with no metrics (grade D). — [TradingView XRPBTC ORB NR4](https://in.tradingview.com/chart/XRPBTC/QY01nRIH-XRPBTC-1D-ORB-Nr4-Breakout-Strategy)

### Inferences
- **Implementable spec: UTC-day ORB with Crabel stretch (grade D for crypto; equity rule definitions)**
  - Day open O = open of the 00:00 UTC 1d bar (equivalently the first 15m bar).
  - Stretch S = SMA_10( min(H-O, O-L) ) over the prior 10 daily bars.
  - Entry: buy stop at O + S, evaluated on 15m bars. Only one entry per day.
  - Exit: at the 23:45 UTC bar close (same-day). Protective stop at O, or at O - S.
  - Filter: only on days following an NR4/NR7 daily bar (section 5), and only if BTC > SMA_50d (section 7).
- **Implementable spec: session ORB**
  - Opening range = high/low of the first N=4 x 15m bars (1 hour) after the session start (London 07:00 UTC or NY 13:30 UTC).
  - Long on a 15m close above the OR high. Stop at the OR low; exit at session end (NY close about 21:00 UTC) or on a trailing stop.
  - This is untested for crypto. It needs walk-forward testing with taker costs (2 x 10 bps plus slippage per trade).

### Gaps
- No peer-reviewed or audited crypto ORB study was found. No evidence exists on which UTC "open" is most informative for breakout continuation.

---

## 5. Pattern / indicator rules with published tests (NR4/NR7, inside bar, Connors CRSI and %b, z-score, %B/bandwidth, N-day high)

### Takeaway
These rules are precisely defined in the books and practitioner literature, but crypto-specific, cost-aware evidence is almost entirely missing. The strongest crypto-specific evidence in this group is for **N-day-high continuation**: Quantpedia finds that buying BTC at a 10-day high works, while buying at an N-day low has drawdowns over 80%. It also links to the cross-sectional MAX-momentum finding. George-Hwang 52-week-high momentum has not been tested in crypto in any peer-reviewed source I found.

### Cited Findings
- **N-day high/low (BTC, Quantpedia, Padyšák & Vojtko 2022)**: Gemini daily BTC, Nov 2015 - Feb 2022. MAX rule: buy when the close equals the max of the prior x days, x ∈ {10,20,30,40,50}. MIN rule: buy at the x-day min. Shorter lookbacks are better and 10 days is best. The MIN variants have drawdowns over 80%. Combined "at max or at min" gave 98.43% CAGR, 47.75% vol, -37.67% MDD, versus BTC buy-and-hold with 74.35% vol and -83.65% MDD. No costs, no out-of-sample test, and the exact holding period is not stated in the text (appears to be 1 day). Grade C. — [Quantpedia](https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/)
- **52-week-high momentum (George & Hwang 2004, equities)**: ranking by proximity to the 52-week high (P/52wHigh) outperforms past-return momentum, which the authors attribute to anchoring. No crypto replication was found in a peer-reviewed venue. — [Alpha Architect](https://alphaarchitect.com/the-secret-to-momentum-is-the-52-week-high/); [IDEAS (anchoring paper)](https://ideas.repec.org/a/eee/finlet/v46y2022ipbs1544612321004256.html)
- A University of Liège master's thesis reports a "TMAX momentum" effect in crypto. It is a thesis, grade D/B-. — [ULiège thesis](https://matheo.uliege.be/bitstream/2268.2/18637/4/MasterThesis_DAssa.pdf)
- **NR7/NR4 (Crabel)**: NR7 is a day whose range (H-L) is narrower than each of the prior 6 days, and NR4 the same versus the prior 3 days. The usual entry is an ORB/stretch or prior-bar breakout the next day. Oxford Strategies tests N from 2 to 19 with lookbacks of 20 to 50 (figures not readable). — [Oxford Strategies](https://oxfordstrat.com/trading-strategies/narrow-range/); [Oxford N-day study](https://oxfordstrat.com/?p=8148)
- An NR7 practitioner write-up (QuantifiedStrategies, equities) claims an "improved" NR7. It is marketing-style with no crypto data, grade D. — [QuantifiedStrategies Substack](https://quantifiedstrategies.substack.com/p/we-improved-the-nr7-trading-strategy)
- An inside-bar breakout on BTC futures is claimed positive in a TradingView idea with no metrics (grade D). — [TradingView](https://www.tradingview.com/chart/BTC1!/ezrFVcFZ-Inside-Day-on-Bitcoin-futures-triggered-a-long-trade/)
- **Connors RSI (CRSI)**: CRSI = [RSI_3(Close) + RSI_2(Streak) + PercentRank_100(1-bar ROC)] / 3. Streak is the signed count of consecutive up or down closes (reset to 0 on unchanged). Connors' oversold/overbought levels are about 10/90. — [LuxAlgo](https://www.luxalgo.com/library/concept/connors-rsi.md); [QuantConnect docs](https://quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/connors-relative-strength-index); [Backtrader recipe](https://backtrader.com/recipes/indicators/crsi/crsi/)
- Percent-rank implementations differ (strictly-lower versus lower-or-equal), which affects reproducibility. On crypto 1d bars, PercentRank_100 spans 100 calendar days because weekends are included. RSI(2)-only results must not be cited as CRSI results. — [LuxAlgo](https://www.luxalgo.com/library/concept/connors-rsi.md); [The Right Trader](https://therighttrader.com/learn/indicator-strategies/best-connors-rsi-settings)
- No published crypto CRSI backtest with costs was found. A dev.to post claims 13 famous strategies (RSI etc.) "all failed" on 6 years of data. It is an unreviewed blog, grade D, but a useful caution. — [dev.to](https://dev.to/tessen/we-graded-13-famous-trading-strategies-on-6-years-of-data-all-13-failed-26o4)
- Long RSI lookbacks with strict thresholds fire rarely, so small sample sizes make crypto backtests unreliable. — [CoinPaprika](https://coinpaprika.com/education/backtest-crypto-strategy)

### Inferences
- **Implementable spec: N-day-high breakout, BTC (grade C, strongest crypto evidence in this section)**
  - On 1d bars: if close_t ≥ max(close_{t-10..t-1}), hold long for the next day, then re-evaluate daily (exit when the condition fails). A trailing exit variant: exit when close < min(close over the last 5d).
  - Note: this overlaps with Donchian, which the terminal already has. The distinct element is the *1-day re-evaluation at a 10-day high* and the *very short lookback*. Implement it as a Donchian parameter preset rather than a new family, unless the CS version below is added.
- **Implementable spec: 52-week (or 26-week) high proximity, cross-sectional (grade B in equities, untested in crypto)**
  - PH_i = close_t / max(high over 365d), or 180d for younger coins.
  - Weekly, among the top 30 liquid coins, hold the top k=3-5 by PH_i, requiring PH_i ≥ 0.9.
  - Exit when the rank falls below 2k or PH_i < 0.8.
  - This is the George-Hwang analog of the CS momentum in section 1. It needs its own backtest.
- **Implementable spec: NR7 + inside bar breakout (grade D for crypto)**
  - Daily NR7: (H-L)_t < min((H-L)_{t-6..t-1}). Inside bar: H_t < H_{t-1} and L_t > L_{t-1}. An "NR7-ID" day is both.
  - Entry next day on a buy stop at H_t + 1 tick, or at Open + Crabel stretch on 15m bars.
  - Stop at L_t. Exit after N=1-5 days or on a close below the 10-day low.
  - Optional filters: trade only in an uptrend (close > SMA_200d) and only when BTC > SMA_100d.
  - Note: this overlaps conceptually with the terminal's volatility-compression breakout. Its distinct elements are the discrete NR7/ID trigger and the stretch entry.
- **Implementable spec: Connors RSI mean reversion (grade D for crypto)**
  - Indicator: CRSI(3,2,100) as defined above.
  - Long entry: close > SMA_200 (trend filter, per Connors) and CRSI < 10. Optionally enter on a limit order 2-6% below the close (Connors-style limit entries).
  - Exit: CRSI > 70, or close > SMA_5.
  - Timeframes: 1d, or 4h, where the 100-bar rank equals about 16.7 days.
  - The terminal already has RSI-2 Connors, but CRSI is a different composite, so it is a valid addition.
- **Implementable spec: z-score mean reversion (grade D for crypto)**
  - z_t = (close_t - SMA_N) / σ_N with N=20 on 4h or 1d bars.
  - Long when z < -2 and the trend filter is on (close > SMA_200). Exit when z > 0, or after a time stop of 10 bars.
  - This is nearly identical to Bollinger mean reversion, which the terminal has, so the only value would be a "%B < 0 with bandwidth filter" variant. **%B** = (C - LowerBB)/(UpperBB - LowerBB), and **Bandwidth** = (UpperBB - LowerBB)/SMA_20.
  - Connors %b rule (from his books, not verified in this session): with C > SMA_200, buy when %B < 0.2 for 3 consecutive days, and exit when %B > 0.8.
- General: every rule in this section should be tested walk-forward with costs, because no crypto evidence above grade C exists except the BTC N-day-high result.

### Gaps
- No peer-reviewed crypto test was found for NR4/NR7, inside bar, CRSI, Connors %b, or George-Hwang 52-week high.
- The Connors %b rule parameters come from my recollection of Connors' books and were not verified from a source in this session.

---

## 6. Volume / liquidity signals (OBV divergence, Chaikin, A/D, taker buy/sell imbalance)

### Takeaway
Volume signals are used in CTREND, where volume-based technicals are one input to a cross-sectional trend factor with JFQA-level evidence, though a replication found it fragile net of costs. Taker order-flow imbalance has documented *short-horizon* (minutes) predictive power in microstructure studies. A practitioner test found that smoothed taker flow on minute bars loses money because the price move has already happened. I found no credible evidence that OBV divergence, Chaikin Money Flow, or A/D lines have a standalone edge in crypto. Taker-buy ratio is best used as a confirmation filter on breakouts.

### Cited Findings
- CTREND aggregates price *and volume* technical signals across horizons into a CS factor (JFQA 2025). — [Cambridge/JFQA](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178)
- Koutmos & Wei (2023, Rev. Quant. Finance & Accounting): order-flow imbalance helps nowcast BTC crashes, and imbalances Granger-cause returns more often than the reverse. Some of the most extreme down-moves occur without significant imbalance. — [Springer](https://link.springer.com/article/10.1007/s11156-023-01148-1)
- "Fragmentation, Price Formation, and Cross-Impact in Bitcoin Markets": taker flow (the aggressive part of order-flow imbalance) has explanatory power over *contemporaneous* returns; future-return results were left to future work. — [arXiv 2108.09750](https://arxiv.org/pdf/2108.09750)
- "Explainable Patterns in Cryptocurrency Microstructure" (arXiv 2602.00776): gradient-boosted trees on tick data for 5 coins. Imbalance effects are largely monotone, and forecasts are tradable under reasonable thresholds with a conservative taker execution model. This is tick-level, not OHLCV. — [arXiv](https://arxiv.org/html/2602.00776v1)
- Negative result (practitioner working paper): trading smoothed taker flow on minute-bar BTCUSDT loses money, because by the time a smoothed signal fires, the permanent price impact has occurred. — [trading-models working paper III](https://vankyle00.github.io/trading-models/docs/models/03-order-flow-imbalance-btc.html)
- Liquidity: an illiquidity premium exists in the crypto cross-section, but it sits in hard-to-trade coins. — [IDEAS (IRFA 2021)](https://ideas.repec.org/a/eee/finana/v78y2021ics1057521921002349.html)

### Inferences
- **Binance field**: the kline includes `taker_buy_base_volume` (TBV). Taker sell volume TSV = Volume - TBV.
  - Taker buy ratio TBR = TBV / Volume (0.5 = balanced).
  - Delta = 2·TBV - Volume. Cumulative volume delta CVD = Σ Delta.
- **Implementable spec: taker-imbalance breakout confirmation (filter, grade D)**
  - On 1h/4h bars, accept a breakout signal from an existing strategy (Donchian, Keltner, ORB, etc.) only if SMA_3(TBR) > 0.55, and CVD slope over 24 bars > 0, i.e. CVD_t > CVD_{t-24}.
  - Rationale: the microstructure studies show imbalance co-moves with price, and the negative result shows it is not a standalone *lagged* predictor. Use it to filter out low-conviction breakouts. Thresholds are untested assumptions.
- **Implementable spec: CVD/price bullish divergence (grade D)**
  - Price makes a lower low over 20 bars, but CVD makes a higher low. Enter on a close back above SMA_20, with a stop under the price low.
  - No published crypto test was found; it is practitioner folklore.
- **OBV / Chaikin / A/D**
  - OBV_t = OBV_{t-1} + sign(C_t - C_{t-1})·V_t.
  - Chaikin money flow multiplier MFM = ((C-L) - (H-C))/(H-L). A/D_t = A/D_{t-1} + MFM·V. CMF_20 = Σ_20(MFM·V)/Σ_20 V. Chaikin Oscillator = EMA_3(A/D) - EMA_10(A/D).
  - Rule (classical): long when CMF_20 crosses above +0.05 with close > SMA_50, and exit when CMF_20 < -0.05.
  - No crypto evidence was found. Implement only as a filter variant and flag it as untested.

### Gaps
- No peer-reviewed or audited crypto test of OBV divergence, CMF, Chaikin Oscillator or A/D was found.
- No study tested the Binance kline taker-buy ratio at 1h-1d horizons with costs.

---

## 7. Regime-switching / filters (BTC trend filter, volatility regime) and funding / basis / open-interest filters

### Takeaway
Trend and drawdown filters are the most robust value-add for long-only crypto. Dual momentum's absolute leg, the BTC N-day-high results and the vol-capped variants all show large drawdown reduction in-sample. Parameter stability is a known problem in walk-forward tests. Funding rate has some evidence as a contrarian *short-horizon* signal (extreme positive funding predicts negative next-8h returns on BitMEX), but the cleaner edge is the carry itself, not a spot price forecast. Open interest has no out-of-sample evidence I could find.

### Cited Findings
- Volatility capping (weight = min(1, target σ / realized σ)) in BTC/gold dual momentum cut MDD from about 49% to about 12%, at the cost of CAGR falling from about 65% to about 12%. — [Quantpedia](https://quantpedia.com/dual-momentum-allocation-between-physical-gold-and-bitcoin-digital-gold/)
- BTC at a 10-day high tends to continue upward. Being in the market only under that condition reduced MDD from -83.65% (buy-and-hold) to -37.67% in-sample. — [Quantpedia](https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/)
- A Quantpedia BTC ETF article uses a regime switch on whether BITO makes a new 10-day high, and warns that in-sample Sharpe optimization is not ideal for future allocation. — [Quantpedia](https://quantpedia.com/bitcoin-etfs-in-conventional-multi-asset-portfolios/)
- Walk-forward caution (arXiv 2009.12155): it reports high crypto trend-following walk-forward returns, but its S&P 500 check found no predictable Sharpe when parameters were trained on 1 year and tested on the next. — [arXiv](https://arxiv.org/pdf/2009.12155v1.pdf)
- AdaptiveTrend (arXiv 2602.11708, 2026 preprint): out-of-sample on 150+ crypto pairs over 2022-2024 reports Sharpe 2.41. It is an unreviewed preprint; treat with caution. — [arXiv](https://arxiv.org/html/2602.11708v1)
- BitMEX research: large positive XBTUSD funding predicts a negative return over the next 8 hours (mean-reversion). This is exchange research, not peer-reviewed, on perps rather than spot. — [BitMEX blog](https://www.bitmex.com/blog/xbtusd-funding-mean-reversion-strategy)
- Independent "Crypto Carry" working paper: the funding factor's edge is the harvested funding spread, not a price forecast. The crowded-long reversal is a faint tailwind at best. A cross-sectional funding factor has about 0.4 net Sharpe out-of-sample, and the simple funding-level trade has decayed. Single author. — [Alpha Research Paper 2](https://bryanvine.github.io/alpha-research/paper2.html)
- A Jarvis Labs analysis (via Medium) reported positive returns from going long when funding turned negative since mid-2021. It is small and unrigorous, grade D. — [Medium](https://medium.com/crypto-alpha-drip/the-signal-in-bitcoins-funding-rate-e19abee4842e)
- Industry: funding does not directly predict price but indicates positioning imbalance; OI-based rules are descriptive only. A product page claiming a 67.9% win rate for a funding/OI model is marketing. — [CoinMarketCap](https://coinmarketcap.com/charts/funding-rates/); [Forklog](https://forklog.com/en/the-funding-rate-how-it-helps-anticipate-price-reversals-in-bitcoin-and-ethereum/); [DEV Community (marketing)](https://dev.to/trendrider/funding-rates-open-interest-predict-squeezes-2026-i50)
- LTW: a large share of crypto cross-sectional variation is explained by the crypto market factor, so a BTC/market regime filter governs most of the long-only P&L. — [NBER](https://www.nber.org/papers/w25882.pdf)

### Inferences
- **Implementable spec: BTC regime gate (applies to all alt strategies)**
  - risk_on = (BTC_close_1d > SMA_100d(BTC)) AND (BTC 28d return > 0). Alternatively, BTC close ≥ 0.9 × its 10-day max (the Quantpedia-inspired variant).
  - When risk_off, block new long entries on all coins and optionally flatten.
  - Parameters are my choice. Test on a grid (SMA 50/100/200; 10/20/50-day max) with walk-forward to avoid the instability flagged in arXiv 2009.12155.
- **Implementable spec: volatility regime gating and sizing**
  - σ_d = stdev of daily log returns over 30d, annualized ×√365.
  - Size each position by w = min(1, σ_target/σ_d), with σ_target = 40-60% for alts and 30-50% for BTC.
  - Gate: block breakout entries when σ_d is in the top decile of its 1-year history (crash regimes).
  - The evidence (Quantpedia vol-cap) shows large DD reduction; the threshold choice is an inference.
- **Implementable spec: funding-rate filter for spot entries (grade C/D)**
  - Source: Binance USDⓈ-M funding rate F for the same coin (8h; public endpoint, not part of spot OHLCV). Compute F_avg = mean(F, last 3 prints = 24h).
  - Block new spot longs when F_avg > the 95th percentile of its trailing 90-day distribution (crowded longs; BitMEX finding).
  - Allow or prefer pullback entries when F_avg < 0 while price is above SMA_100 (Jarvis-style, weak evidence).
  - Basis filter: annualized basis = (Perp or quarterly future / spot - 1) × (365/days_to_expiry). Block entries when the basis is above its 95th percentile.
  - Open interest: no tested rule exists. If used at all, use it only as "skip entries when OI rose more than X% in 24h while price fell" (descriptive). Flag it as untested.
- Note: funding/OI/basis data is outside Binance spot OHLCV. These filters require an extra futures-API data feed.

### Gaps
- No peer-reviewed out-of-sample study was found on funding rate, basis or OI as a *spot* entry filter.
- No crypto-specific test was found comparing BTC-trend-gated versus ungated altcoin long-only strategies with costs.
- The volatility-regime thresholds and the BTC-gate parameters above are proposals, not published rules.

---

## Cross-cutting notes for the report writer
- **Evidence ranking for the missing families (strongest first):**
  1. CS momentum (1-4 week) in large coins (peer-reviewed, JF 2022/JFQA 2025), but weak long-only and net of costs.
  2. Turn-of-month (peer-reviewed, gross, pre-2022).
  3. Dual momentum, BTC N-day-high continuation and vol-capped regime filters (Quantpedia, in-sample, no costs, large DD reduction).
  4. Intraday hour effects (Quantpedia plus a cross-exchange paper; persistence contested; cost-infeasible standalone).
  5. Funding filter (exchange research / single-author preprint).
  6. NR7/inside bar/ORB/CRSI/%b/z-score/OBV/CMF/taker-ratio rules (well defined, no credible crypto test).
- **Marketing / no-cost flags:**
  - Every Quantpedia number cited here is gross of costs and in-sample.
  - The TrendRider funding/OI win-rate claim is marketing.
  - QuantifiedStrategies' "improved NR7" is equity-only.
  - TradingView ideas provide no metrics.
