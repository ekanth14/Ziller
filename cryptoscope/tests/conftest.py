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


def pytest_collection_modifyitems(config, items):
    import pytest

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
