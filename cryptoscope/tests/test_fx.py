"""Tests for FX rate service adhering to truthfulness rules."""
import time
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO
from cryptoscope.fx.rate_service import FxRateService


class FxRateServiceTests(unittest.TestCase):
    def test_uninitialized_returns_unavailable_without_seed_rate(self):
        svc = FxRateService()
        # auto_fetch disabled to test cold state
        res = svc.get_rate("INR", auto_fetch=False)
        self.assertEqual(res["status"], "unavailable")
        self.assertIsNone(res["rate"])
        self.assertIsNone(res["age_seconds"])

    def test_fetch_error_records_error_and_remains_unavailable(self):
        svc = FxRateService(endpoint="https://invalid.example.com/rates")
        with patch("cryptoscope.fx.rate_service.urlopen", side_effect=OSError("DNS lookup failed")):
            res = svc.get_rate("INR")
            self.assertEqual(res["status"], "unavailable")
            self.assertIsNone(res["rate"])
            self.assertIn("DNS lookup failed", str(res["error"]))

    def test_successful_fetch_provides_available_rate(self):
        svc = FxRateService()
        mock_payload = b'{"result":"success","rates":{"INR":87.123,"EUR":0.92}}'
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_payload
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch("cryptoscope.fx.rate_service.urlopen", return_value=mock_resp):
            res = svc.get_rate("INR")
            self.assertEqual(res["status"], "available")
            self.assertEqual(res["rate"], 87.123)
            self.assertIsNotNone(res["age_seconds"])
            self.assertLess(res["age_seconds"], 2.0)
            self.assertEqual(res["source"], "open_er_api")

    def test_stale_after_6_hours(self):
        svc = FxRateService()
        svc.rates = {"INR": 87.5}
        svc.source = "open_er_api"
        # 6 hours and 1 minute ago
        svc.last_fetch = time.time() - (6 * 3600 + 60)
        res = svc.get_rate("INR", auto_fetch=False)
        self.assertEqual(res["status"], "stale")
        self.assertEqual(res["rate"], 87.5)
        self.assertGreater(res["age_seconds"], 6 * 3600)


if __name__ == "__main__":
    unittest.main()
