import json
import urllib.request
import urllib.error
import pytest

def test_quant_metrics_endpoint():
    try:
        url = "http://127.0.0.1:8900/api/quant/metrics?symbol=BTCUSDT"
        req = urllib.request.Request(url, headers={"Host": "localhost:8900"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["symbol"] == "BTCUSDT"
            assert "stage1_data" in data
            assert "stage2_signal" in data
            assert "stage7_risk" in data
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        pytest.skip(f"Dashboard server not reachable at http://127.0.0.1:8900 ({e}); skipping integration test.")

def test_berkshire_audit_endpoint():
    try:
        url = "http://127.0.0.1:8900/api/berkshire/audit"
        payload = json.dumps({"symbol": "BTCUSDT"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Host": "localhost:8900", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["symbol"] == "BTCUSDT"
            assert "duan_moat" in data
            assert "buffett_valuation" in data
            assert "munger_inversion" in data
            assert "lilu_integrity" in data
            assert "composite_conviction_score" in data
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        pytest.skip(f"Dashboard server not reachable at http://127.0.0.1:8900 ({e}); skipping integration test.")

def test_quant_levels_endpoint():
    try:
        url = "http://127.0.0.1:8900/api/quant/levels?symbol=BTCUSDT"
        req = urllib.request.Request(url, headers={"Host": "localhost:8900"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["symbol"] == "BTCUSDT"
            assert "level1_prob" in data
            assert "level5_timeseries" in data
            assert "level7_derivatives" in data
            assert "level8_risk" in data
            assert "level9_microstructure" in data
            assert "level10_research" in data
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        pytest.skip(f"Dashboard server not reachable at http://127.0.0.1:8900 ({e}); skipping integration test.")

def test_agents_committee_endpoint():
    try:
        url = "http://127.0.0.1:8900/api/agents/committee"
        payload = json.dumps({"symbol": "BTCUSDT"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Host": "localhost:8900", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["symbol"] == "BTCUSDT"
            assert "action" in data
            assert "conviction_score" in data
            assert "persona_votes" in data
            assert len(data["persona_votes"]) >= 4
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        pytest.skip(f"Dashboard server not reachable at http://127.0.0.1:8900 ({e}); skipping integration test.")
