"""Tests use independent governor databases; never clear production state."""
import pytest
from cryptoscope.security.halt_state import GovernorState


@pytest.fixture(autouse=True)
def isolated_governor_state(tmp_path, monkeypatch):
    path = tmp_path / 'governor.db'
    monkeypatch.setenv('GOVERNOR_STATE_DB', str(path))
    monkeypatch.delenv('TRADING_MODE', raising=False)
    GovernorState(path).resume_local_admin(admin_reauthenticated=True, actor='isolated-test-admin')


# --- Optional parquet engine guard -------------------------------------------
# Some research tests need a working pandas parquet engine (pyarrow or
# fastparquet). On machines where neither can be imported (e.g. blocked DLL or
# NumPy/pyarrow ABI mismatch) skip them with a clear reason instead of failing.
def _parquet_engine_available() -> bool:
    try:
        import io

        import pandas as pd

        pd.DataFrame({"a": [1]}).to_parquet(io.BytesIO())
        return True
    except Exception:
        return False


_PARQUET_TESTS = {
    "test_data_integrity_pass",
    "test_data_integrity_detects_gaps_and_anomalies",
    "test_duckdb_parquet_evaluation",
    "test_talib_precision_evaluation",
    "test_drex_license_and_evaluation",
}


# Tests that depend on gitignored local data (work/crypto_candles.db,
# data/parquet_klines), live exchange network access, or the Playwright browser
# cannot run on a clean CI runner. They are skipped when CI=true.
_CI_UNAVAILABLE_PREFIXES = (
    "test_binance_testnet_live_",
    "test_binance_testnet_auth_failure_semantics",
)
_CI_UNAVAILABLE_TESTS = {
    "test_01_real_market_candles_present",
    "test_03_monte_carlo_odds_simulation_with_real_candles",
    "test_04_multi_agent_deliberation_consensus",
    "test_09_listings_filter_unlisted_tokens",
    "test_10_stat_arb_and_volatility_quant_engine",
    "test_real_candle_replay_full_pipeline",
    "test_duckdb_parquet_evaluation",
    "test_talib_precision_evaluation",
    "test_drex_license_and_evaluation",
    "test_agents_deliberate_endpoint",
    "test_quant_orderflow_endpoint",
    "test_quant_pairs_endpoint",
    "test_quant_volatility_endpoint",
}


def pytest_collection_modifyitems(config, items):
    import os

    import pytest

    if os.environ.get("CI", "").lower() == "true":
        ci_skip = pytest.mark.skip(reason="Requires local market data, live exchange access or browsers unavailable on CI")
        for item in items:
            if item.name in _CI_UNAVAILABLE_TESTS or item.name.startswith(_CI_UNAVAILABLE_PREFIXES):
                item.add_marker(ci_skip)

    if not _parquet_engine_available():
        skip = pytest.mark.skip(reason="No usable parquet engine (pyarrow/fastparquet) in this environment")
        for item in items:
            if item.name in _PARQUET_TESTS:
                item.add_marker(skip)
    if not _quantstats_available():
        skip = pytest.mark.skip(reason="quantstats not installed (requires numpy<2)")
        for item in items:
            if item.name == "test_quantstats_tearsheet_evaluation":
                item.add_marker(skip)


def _quantstats_available() -> bool:
    try:
        import quantstats  # noqa: F401

        return True
    except Exception:
        return False
