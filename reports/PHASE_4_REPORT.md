# Phase 4 — Multi-Coin Data Ingestion and Integrity Report

Generated: [REDACTED]-11-09 13:23:09 UTC. Branch: `multi-coin`.

## 1. Candidate Universe Overview (Section 4.1)

- **Total Binance Spot USDT Pairs:** 735
- **Active Trading Symbols:** 516
- **Inactive / Delisted Symbols:** 209
- **Leveraged Tokens Flagged/Excluded:** 12 (UP/DOWN/BULL/BEAR)
- **Stablecoin Pairs Flagged:** 10
- **Universe Artifact:** `data/universe/candidate_spot_usdt.json`

## 2. Ingestion & Integrity Verification Table (Section 4.2)

| Symbol | Status | Total Bars | Completeness % | Span (Days) | Gaps (Missing) | Duplicates | Monotonic | Price Anomalies |
| --- | --- | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| `BTCUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `ETHUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `SOLUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `BNBUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `ADAUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `XRPUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `DOGEUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `AVAXUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `LINKUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `NEARUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `DOTUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `LTCUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `ATOMUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `UNIUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `LUNAUSDT` | **PASS** | 35,039 | 100.00% | 1460.0 | 1 (1) | 0 | YES | 0 |
| `FTTUSDT` | **FLAGGED (HALTED/DELISTED)** | 27,573 | 78.69% | 1460.0 | 1 (7467) | 0 | YES | 0 |
| `BUSDUSDT` | **PASS** | 9,590 | 99.99% | 399.6 | 1 (1) | 0 | YES | 0 |
| `SRMUSDT` | **PASS** | 421 | 100.00% | 17.5 | 0 (0) | 0 | YES | 0 |
| `HNTUSDT` | *DELISTED_OR_PRUNED_ON_EXCHANGE* | 0 | 0.00% | 0.0 | — | — | — | — |

## 3. Delisted Symbol Accounting

Historical delisted instruments (such as `LUNAUSDT`, `FTTUSDT`, `BUSDUSDT`, `SRMUSDT`, `HNTUSDT`) were probed against the public exchange REST interface:
- Where the exchange has retired and pruned order/kline data, symbols are explicitly classified as `DELISTED_OR_PRUNED_ON_EXCHANGE` rather than assuming zero activity or inventing synthetic prices.
- For point-in-time backtesting (Phase 5), the Universe Manager restricts historical lookups to available survivorship records.

## 4. Institutional Standards Verification

- **Lower Bound Enforcement:** Exactly 4 years of history (November 2022 to November [REDACTED]); no bars older than 4 years are accepted.
- **Storage Isolation:** All klines are stored in `data/parquet_klines/1h/*.parquet` (fastparquet engine), completely isolated from production SQLite databases (`trading.db`, `execution.db`, `crypto_candles.db`).
- **Zero Secret Leakage:** No credentials or confidential strings exist in datasets, manifests, or reports.

**Verdict: PHASE 4 PASS.**
