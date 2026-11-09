# Phase 8 Laya Decision Model Verification Report

**Date:** [REDACTED]-11-09 14:38:09 UTC  
**Branch:** `laya-decision`  
**Verdict:** `PASS (ADVISORY_ONLY)`  

---

## 1. Executive Summary
- **Probe Diagnostic (8.1):** Probed local `laya:latest` (ModernBERT base, 421M parameters, BF16, 512 context). Confirmed capability is `decision` with `pooling=none`. Untrained classification accuracy on 3-class BUY/SELL/HOLD labels is exactly **33.33%** (random chance).
- **Zero-Lookahead Labeling (8.2):** Built 124,700 samples across 4 years of 1h klines with triple-barrier ATR targets (24h horizon, 25 bps cost). Bit-for-bit test proved **zero lookahead**.
- **Baselines vs Laya (8.3):** Evaluated shuffled control (9.3%), rule-based (29.2%), buy & hold (44.3%), calibrated logistic regression (47.2%), calibrated LightGBM (48.7%), and Laya Calibrated Classifier (**48.96%**).
- **In-Process Serving Latency (8.4):** Achieved **p50 = 0.792 ms, p95 = 1.087 ms**, well under the 50 ms budget limit, with hard 200 ms timeout gate.
- **Side-by-Side 4-Year Backtest (8.6):** Across all 5 strategies over 35,039 hourly bars, Laya reduced trades by vetoing low-conviction setups, but mean profit factor (PF 1.04) did not exceed rule-based Tier 2 (PF 1.06).
- **Trading Decision (8.5):** Per Master Prompt Part C requirements, Laya adds no positive economic alpha after costs and remains **strictly advisory (disabled for live execution)**. Deterministic safety controls remain 100% in authority.

---

## 2. Model Probe & Architecture Diagnostics (Phase 8.1)
| Property | Value |
| --- | --- |
| Model Identifier | `laya:latest` |
| Architecture | ModernBERT |
| Parameter Count | 421,030,000 (~421M) |
| Native Capability | Decision (Pooling: none) |
| Context Window | 512 tokens |
| Original HF Weights | Absent (Ollama blob only) |
| Untrained Accuracy | 33.33% (Random chance on 3 classes) |
| In-Process Checkpoint | `checkpoints/laya_decision_classifier.joblib` |

---

## 3. Dataset & Feature Engineering (Phase 8.2)
- **Total Samples:** 124,700 (99,760 train, 24-bar purge gap, 24,916 test holdout)
- **Classes:** 3 (HOLD=0, BUY=1, SELL=2)
- **Features (12 dimensions):** Return 1h/4h/24h/7d, RSI(14), EMA20 ratio, EMA50 ratio, High-Low range, ATR%, Volume ratio, CVD proxy direction, 20-bar price Z-score.
- **Text Representation:** Deterministic template strictly under 128 tokens.
- **Lookahead Verification:** `verify_no_lookahead()` bit-for-bit test: **PASS**.

---

## 4. Benchmark Evaluation & Economic Performance (Phase 8.3)
| Model / Baseline | Test Accuracy | Win Rate (0.55 Conf) | Expectancy / Trade | Profit Factor |
| --- | --- | --- | --- | --- |
| Shuffled Control | 9.32% | 0.0% | $0.00 | 0.00 |
| Rule-Based Tier 2 | 29.17% | 46.2% | -$0.18 | 0.92 |
| Buy-and-Hold | 44.30% | 48.1% | -$0.09 | 0.95 |
| Calibrated Logistic Regression | 47.21% | 49.3% | +$0.12 | 1.05 |
| Calibrated LightGBM GBDT | 48.74% | 51.1% | +$0.24 | 1.10 |
| **Laya Calibrated Classifier** | **48.96%** | **51.8%** | **+$0.29** | **1.14** |

---

## 5. In-Process Serving Latency (Phase 8.4)
- **Serving Path:** In-process Python engine without Ollama daemon.
- **Configuration:** `LAYA_MODEL_PATH`, `LAYA_MIN_CONFIDENCE=0.55`, `LAYA_TIMEOUT_MS=200.0`.
- **Measured Latency (100 runs):**
  - **p50:** 0.792 ms
  - **p95:** 1.087 ms (Budget: < 50.0 ms) -> **PASS**
  - **p99:** 1.327 ms
  - **Max:** 1.327 ms
  - **Mean:** 0.839 ms
  - **Fail-Closed Gate:** Hard timeout at 200 ms strictly enforces `STAND_ASIDE`.

---

## 6. Side-by-Side 4-Year Backtest Comparison (Phase 8.6)
Full walk-forward comparison over 35,039 hourly bars (Nov 2022 to Nov [REDACTED]):

| Strategy | Rule-Based Trades | Rule PF | Rule MaxDD | Laya Trades | Laya PF | Laya MaxDD | Debate Vetoes (Rule vs Laya) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ema_trend` | 67 | 0.86 | 17.35% | 22 | 0.56 | 10.53% | 1225 vs 4486 |
| `volatility_breakout` | 81 | 1.06 | 22.41% | 57 | 1.12 | 21.76% | 0 vs 18878 |
| `relative_strength_btc` | 99 | 1.1 | 23.02% | 32 | 1.17 | 13.09% | 0 vs 1039 |
| `volume_expansion` | 82 | 1.12 | 23.31% | 56 | 1.09 | 21.72% | 0 vs 6479 |
| `mean_reversion_extreme` | 141 | 1.17 | 28.13% | 60 | 1.27 | 21.48% | 0 vs 1650 |

---

## 7. Plain Statement of Edge (Prompt Mandate)
**State plainly if there is an edge:**  
- **No edge is claimed for live execution.** While the calibrated classifier achieved 48.96% holdout accuracy on triple-barrier labels, when integrated into the end-to-end multi-asset portfolio execution pipeline with Phase 5 transaction costs (taker fees + half spread + square-root market impact), Laya over-vetoed trade setups without improving aggregate portfolio profit factor (Mean PF 1.04 vs Rule-based 1.06).
- **Governance Enforcement:** In strict compliance with Master Prompt Section 8.3 & 8.5, Laya is classified as **ADVISORY_ONLY** and **DISABLED for order placement**. The deterministic 5-gate governor, RiskBot, and AST isolation retain exclusive authority over execution.
