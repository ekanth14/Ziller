# Selected CloddsBot risk modules

Optional offline research tooling for Zien. Installed from upstream version 1.9.1, commit `c930628c47a4a745f497e29035a3b64622f97cc7`. `provenance.json` records Git blob hashes for the three unmodified source files and their MIT license. `adapter.mjs` verifies those hashes at runtime.

Required runtime: Node.js 24+ (native TypeScript stripping). There are no npm dependencies or install hooks in this selected subset. Do not run the full CloddsBot installer to use these utilities.

From the Zien project root:

```powershell
python -m cryptoscope.risk_tools --demo
node --test integrations/clodds-risk/tests/risk.test.mjs
python -m cryptoscope.risk_tools --input config/risk-observations.example.json
```

The demo writes `work/clodds-risk/verification.json`. It uses synthetic observations and opens no network connections, wallets, exchange sessions, or gateway. It does not replace Laya or alter trading limits.

Input arrays `pnl_usd` and `returns_pct` must have the same length, chronological order and fixed sampling cadence. Use percentage points for `returns_pct` (`1` = +1%). Stress positions use `value` in USD and `pnlPct` as a decimal fraction (`0.01` = +1%); only long positions are supported in this Zien spot adapter. Real USDT accounts need an explicit valuation convention before reporting these figures as USD.

The first 30 return observations calibrate the volatility baseline; subsequent observations evaluate the regime. Shorter histories return `volatility: null`, rather than presenting the upstream startup defaults as measured risk. The upstream one-shot `detectRegime` helper fits and evaluates the same full window and normally yields a volatility ratio of one. This adapter uses the sequential detector instead. VaR/CVaR uses at most the last 100 observations. Five stress outputs are fixed scenario shocks, not estimated event probabilities or a derivatives liquidation model.

The output is advisory. Upstream `shouldHalt`, size multipliers and textual recommendations are reported but do not trigger actions in Zien. Dashboard integration and automatic risk enforcement remain separate work.
