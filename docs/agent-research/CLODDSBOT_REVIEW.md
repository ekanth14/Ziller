# CloddsBot review and selected installation

Reviewed 2026-10-31. Upstream: [alsk1992/CloddsBot](https://github.com/alsk1992/CloddsBot), version **1.9.1**, revision **c930628c47a4a745f497e29035a3b64622f97cc7**, MIT license. This is a focused review of architecture, dependencies, crypto feeds, provider support, execution safety, and reusable risk modules. It is not a security audit of the entire application.

## Architecture and fit

CloddsBot is a separate Node/TypeScript trading terminal: gateway and webchat, messaging adapters, model providers, crypto/prediction-market feeds, exchange execution, wallets, risk controls, scheduled tasks, and a SQLite-backed application. It is not a Python library that can be installed into the Zien backtesting virtual environment.

The full package requires Node >=22. Its `package.json` declares many exchange, Solana/EVM, messaging, database, AI, and document packages. Its `postinstall` includes native binding fixes and a transformer embedding-model prefetch, while the repository `.npmrc` sets `ignore-scripts=true`. A blanket npm install therefore needs a deliberate policy for scripts and native components. None of those lifecycle hooks is needed by our selected risk utilities.

Evidence: [package metadata](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/package.json), [architecture](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/docs/ARCHITECTURE.md), [npm settings](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/.npmrc).

| Component | Fit for Zien | Installation decision |
| --- | --- | --- |
| Historical and parametric VaR / CVaR | Optional loss-distribution diagnostics | Installed standalone upstream source |
| Sequential volatility detector | Relative-to-baseline regime assessment | Installed standalone upstream source; fixed warmup in adapter |
| Five stress scenarios | Review long spot exposure under explicit shocks | Installed standalone upstream source; advisory only |
| Binance WebSocket crypto feed | Useful design for live prices/reconnects | Reviewed, not installed; existing Zien REST feed remains authoritative |
| Feed freshness and retry infrastructure | Useful resilience patterns | Reviewed, not installed into trading execution |
| Execution circuit breaker | Session losses, error rates, manual stop | Requires a carefully integrated Python equivalent or service boundary |
| Binance futures, Bybit, Hyperliquid | Additional execution venues | Not installed or activated; Zien is currently a spot paper simulator |
| Ollama model provider | Supports a local model endpoint | Reviewed; retain Zien's exact-model, schema-constrained Laya adapter |
| Messaging, prediction markets, wallets, DeFi, mining | Outside current BTC/ETH research scope | Not installed |

## Installed files and dependencies

Three upstream files are installed unmodified under `integrations/clodds-risk/src/risk/`:

- `var.ts`
- `volatility.ts`
- `stress.ts`

Their imports are empty, so the selected subset requires **no npm dependencies**. Your existing Node 24.19.0 can execute their erasable TypeScript syntax directly. The full app's Node >=22 requirement differs from this subset's explicit Node >=24 execution contract.

`integrations/clodds-risk/LICENSE` preserves the upstream MIT notice; `provenance.json` records the repository revision and individual Git blob hashes. `adapter.mjs` validates inputs and checks source integrity. The Python entry point `cryptoscope/risk_tools/__main__.py` invokes only this fixed local Node CLI, with input over stdin and a bounded process timeout.

No npm packages, global binaries, account credentials, model downloads, messaging bots, wallets, daemons, or trading gateways were installed. This source installation is sufficient for the three selected modules. It does not integrate risk output into the existing execution gate or dashboard automatically.

## Verified behavior

```powershell
# Offline synthetic installation check; no API key or exchange access required.
python -m cryptoscope.risk_tools --demo

# Analyze a JSON observation file (the supplied example is synthetic).
python -m cryptoscope.risk_tools --input config/risk-observations.example.json

# Verify source hashes and risk behavior directly.
node --test integrations/clodds-risk/tests/risk.test.mjs

# Convenience command for demo plus Node tests.
powershell -NoProfile -File scripts/check-clodds-risk.ps1
```

Verification passed: seven Node tests plus all 21 existing Zien Python tests. Checks cover source integrity, known loss quantiles, fixed stress values, a sequential volatility shock, malformed/non-finite input, invalid confidence levels, spot-only input, and duplicate positions. The demo's 60 synthetic P&L observations produce historical VaR=50 and CVaR=50 USD per observation; a 1,000 USD long position loses 200 USD under the fixed flash-crash scenario and 400 USD under the fixed black-swan scenario. These are fixture checks, not measurements of the real account. Output is saved to `work/clodds-risk/verification.json`.

## Findings that affect integration

1. **Keep Laya as the decision model.** The repository does support an `OllamaProvider`; it defaults to a generic model and does not send Zien's role-specific structured schemas or thinking controls. Replacing our adapter with it would lose behavior already verified for Laya. [Provider source](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/providers/index.ts).

2. **Risk validation is needed at module boundaries.** The reusable VaR functions accept unvalidated numeric arrays and confidence values. The Zien adapter refuses non-finite numbers and confidence outside `[0.5, 1)`. VaR/CVaR uses a discrete empirical tail convention; per-observation results should not be mistaken for annualized risk or combined from incompatible sample cadences. [VaR source](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/risk/var.ts).

3. **One-shot volatility calibrates on its evaluation sample.** `detectRegime()` sets the lookback to the full input length, and baseline calibration finishes on the last input; the evaluated volatility then normally equals that baseline, giving a ratio of one. The adapter instead calibrates on the first fixed 30 observations and evaluates subsequent history. Insufficient history returns `null`. `returns_pct` uses percentage points (`1` = 1%), while stress-position `pnlPct` uses decimal fractions (`0.01` = 1%). [Volatility source](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/risk/volatility.ts).

4. **Stress estimates are assumptions, not fitted market models.** Five scenarios apply fixed losses of 10–40%; shorts use heuristic gains for some crash scenarios. The spot adapter accepts long positions only. Upstream names such as “3-sigma” do not mean the code estimates a real return distribution. Raw recommendations and multipliers are advisory and do not change Zien sizing. [Stress source](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/risk/stress.ts).

5. **Retain Zien's stricter feed cutoff checks.** The Clodds crypto feed's `getOHLCV()` maps every returned candle, without rejecting the open candle. Its combined-price objects can insert zeros for assets not yet observed. The WebSocket handler expects an unwrapped ticker payload even though multi-stream URL handling should be checked against Binance's documented payload format before reuse. Cached prices are returned without a freshness check in those getters. [Crypto-feed source](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/feeds/crypto/index.ts).

6. **Do not transplant execution safety without changes.** The reviewed circuit breaker schedules automatic reset even for a manual trip. Its session P&L and reset behavior need explicit policy decisions in an always-on bot. The standalone order-size helper returns no rejection for non-finite notional, so it relies on validation elsewhere; Zien's existing finite-number validation should be retained. [Circuit breaker](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/execution/circuit-breaker.ts), [order guards](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/trading/risk.ts).

7. **Retries do not imply request cancellation.** The timeout helper rejects its wrapper promise without aborting the original operation. Retrying a timed-out mutation could submit it twice unless the venue adapter provides idempotency/reconciliation. The reviewed Binance futures client defaults to the normal endpoint unless testnet is explicitly requested and caches the client using only an API-key comparison; credentials and environment changes require careful handling. Those adapters were not installed. [Retry implementation](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/infra/retry.ts), [Binance futures](https://github.com/alsk1992/CloddsBot/blob/c930628c47a4a745f497e29035a3b64622f97cc7/src/exchanges/binance-futures/index.ts).

Next implementation work, if requested: expose advisory risk reports in the dashboard using actual, consistently sampled paper-account history. Automatic enforcement needs separate decisions on USD/USDT valuation, calibration history, and loss-reset policy.
