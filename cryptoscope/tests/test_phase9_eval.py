"""Comprehensive Unit Tests for Phase 9: Sandbox Repository Evaluations.

Tests:
1. DuckDB analytical queries and speedup on Phase 4 Parquets.
2. QuantStats tear sheet generation and annualization discrepancy logic.
3. TA-Lib precision evaluation on real candles and Windows build capture.
4. TradingView Lightweight Charts self-hosted assets and attribution.
5. APScheduler background scheduling and dual-ID Telegram security limits.
6. Drex decision models license audit and CPU inference latency.
7. Architectural reviews for Cryptofeed, Vectorbt, Skfolio, CCXT, and Freqtrade.
"""

from pathlib import Path
import pytest

from cryptoscope.research.eval.duckdb_eval import evaluate_duckdb_parquet_queries
from cryptoscope.research.eval.quantstats_eval import run_quantstats_evaluation
from cryptoscope.research.eval.talib_eval import run_talib_evaluation
from cryptoscope.research.eval.tradingview_eval import run_tradingview_playwright_test
from cryptoscope.research.eval.apscheduler_eval import run_apscheduler_evaluation
from cryptoscope.research.eval.drex_eval import run_drex_evaluation
from cryptoscope.research.eval.reviews import get_all_repo_reviews


def test_duckdb_parquet_evaluation():
    """Verify DuckDB executes analytical queries with speedup and preserves SQLite for live state."""
    res = evaluate_duckdb_parquet_queries()
    assert res["status"] == "PASS"
    assert res["duckdb_version"] == "1.1.3"
    assert res["mean_speedup"] >= 1.2
    assert res["decision"] == "ADOPT"
    assert "RETAINED_FOR_LIVE_STATE" in res["sqlite_role"]
    assert len(res["benchmarks"]) == 3


def test_quantstats_tearsheet_evaluation():
    """Verify QuantStats computes metrics and reconciles 252 vs 365 day crypto discrepancies."""
    res = run_quantstats_evaluation()
    assert res["status"] == "PASS"
    assert res["decision"] == "ADOPT_LATER"
    assert res["tearsheet_html_path"] is not None
    assert Path(res["tearsheet_html_path"]).exists()
    assert len(res["comparisons"]) == 3

    # Check Sharpe comparison
    sharpe_comp = next(c for c in res["comparisons"] if c["metric"] == "Sharpe Ratio")
    assert sharpe_comp["quantstats_crypto_365"] > sharpe_comp["quantstats_equity_252"]


def test_talib_precision_evaluation():
    """Verify TA-Lib indicator comparison on real candles and documentation of Windows failure."""
    res = run_talib_evaluation()
    assert res["status"] == "PASS"
    assert res["symbol"] == "BTCUSDT"
    assert res["candles_analyzed"] > 1000
    assert res["decision"] == "SKIP"
    assert "BUILD_FAILED" in res["windows_install_evidence"]["result"]
    assert "ta_libc.h" in res["windows_install_evidence"]["compiler_error"]

    # Check EMA convergence post-warmup
    ema20_comp = next(c for c in res["comparisons"] if "EMA (span=20)" in c["indicator"])
    assert "exponential convergence" in ema20_comp["convergence_after_warmup"]


def test_tradingview_self_hosted_assets():
    """Verify self-hosted Lightweight Charts assets exist, contain no external CDNs, and preserve license."""
    js_path = Path("cryptoscope/dashboard/static/assets/lightweight-charts.standalone.production.js")
    lic_path = Path("cryptoscope/dashboard/static/assets/LIGHTWEIGHT_CHARTS_LICENSE.txt")
    assert js_path.exists() and js_path.stat().st_size > 50000
    assert lic_path.exists() and lic_path.stat().st_size > 500

    # Test Playwright browser execution
    res = run_tradingview_playwright_test(port=8923)
    assert res["status"] == "PASS"
    assert res["decision"] == "ADOPT"
    assert res["lightweight_charts_installed"] is True
    assert res["canvas_rendered"] is True
    assert res["tradingview_attribution_preserved"] is True
    assert res["external_cdn_script_count"] == 0
    assert res["console_errors_count"] == 0


def test_apscheduler_jobs_and_security():
    """Verify APScheduler background jobs and dual-ID Telegram security limits."""
    res = run_apscheduler_evaluation()
    assert res["status"] == "PASS"
    assert res["decision"] == "ADOPT"
    assert len(res["jobs_registered"]) == 2
    assert res["security_verification"]["both_ids_required"] is True
    assert res["security_verification"]["unauthorized_denied"] is True
    assert res["security_verification"]["no_resume_capability"] is True


def test_drex_license_and_evaluation():
    """Verify Drex v1.5 Open RAIL-M audit, DLM exclusion, and CPU latency budget."""
    res = run_drex_evaluation(quick=True)
    assert res["status"] == "PASS"
    assert res["decision"] == "SKIP"
    assert "Open RAIL-M" in res["license_audit"]["primary_license"]
    assert "strictly EXCLUDED" in res["license_audit"]["drex_dlm_compliance"]
    assert res["drex_v15_cpu_latency"]["budget_50ms_met"] is True
    assert res["drex_v15_cpu_latency"]["p95_ms"] < 50.0
    assert len(res["side_by_side_matrix"]) == 6


def test_repo_reviews_completeness():
    """Verify all 5 requested repositories are thoroughly reviewed with licenses and decisions."""
    res = get_all_repo_reviews()
    assert res["status"] == "PASS"
    assert res["repos_reviewed_count"] == 5
    assert "GPLv3" in res["license_compliance"]["gplv3_isolation"]
    assert "AST isolation" in res["license_compliance"]["ast_isolation"]

    reviewed_names = {r["repo_name"] for r in res["reviews"]}
    assert reviewed_names == {"cryptofeed", "vectorbt", "skfolio", "ccxt", "freqtrade"}
