"""Optional research diagnostics; never imported by the core trading runtime."""
import importlib.metadata
import math


def stationarity_windows(store):
    try:
        import numpy as np
        from statsmodels.tsa.stattools import adfuller,coint
    except ImportError:
        return dict(status='NOT RUN',reason='Optional numpy/statsmodels unavailable')
    # Frozen before replay; no test-period lag selection/tuning.
    result = dict(status='PASS diagnostics executed; no causal conclusion',
                  statsmodels_version=importlib.metadata.version('statsmodels'),
                  specification='log prices; constant; maxlag=1; autolag=None; significance=0.05',windows={})
    n = len(store['ETHUSDT'])
    split = int(n*0.70)
    train_eth = np.log([c['close'] for c in store['ETHUSDT'][:split]])
    train_btc = np.log([c['close'] for c in store['BTCUSDT'][:split]])
    alpha,beta = np.linalg.lstsq(np.column_stack([np.ones(split),train_btc]),train_eth,rcond=None)[0]

    def adf(series):
        statistic,pvalue,lags,nobs,critical = adfuller(series,maxlag=1,regression='c',autolag=None)
        return dict(statistic=float(statistic),pvalue=float(pvalue),lags=int(lags),nobs=int(nobs),
                    critical_values={k:float(v) for k,v in critical.items()},reject_unit_root_5pct=bool(pvalue<0.05))

    for name,lo,hi in [('TRAIN',0,split),('TEST',split,n)]:
        eth = np.log([c['close'] for c in store['ETHUSDT'][lo:hi]])
        btc = np.log([c['close'] for c in store['BTCUSDT'][lo:hi]])
        statistic,pvalue,critical = coint(eth,btc,trend='c',maxlag=1,autolag=None)
        if not all(math.isfinite(x) for x in (statistic,pvalue)):
            raise ValueError('Degenerate cointegration diagnostic')
        result['windows'][name] = dict(bars=hi-lo,start=store['ETHUSDT'][lo]['open_time'],
            end=store['ETHUSDT'][hi-1]['close_time'],log_ratio_adf=adf(eth-btc),
            train_fixed_residual_adf=adf(eth-alpha-beta*btc),
            engle_granger=dict(statistic=float(statistic),pvalue=float(pvalue),
                              critical_values=[float(v) for v in critical],reject_no_cointegration_5pct=bool(pvalue<0.05)))
    return result
