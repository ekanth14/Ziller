"""Tests for Crypto Cost Model, Indian Tax Regime (Section 115BBH/194S), and Deflated Sharpe Ratio."""
import json
import unittest
from cryptoscope.backtesting.cost_model import (
    CryptoCostModel,
    deflated_sharpe_ratio,
    compute_monthly_return_matrix,
)


class CryptoCostModelTests(unittest.TestCase):
    def setUp(self):
        self.cost_model_standard = CryptoCostModel(
            maker_fee=0.001,
            taker_fee=0.001,
            slippage_bps_major=5.0,
            apply_indian_tax=False,
        )
        self.cost_model_indian = CryptoCostModel(
            maker_fee=0.001,
            taker_fee=0.001,
            slippage_bps_major=5.0,
            apply_indian_tax=True,
            gst_rate=0.18,
            tds_rate=0.01,
            vda_tax_rate=0.312,
        )

    def test_standard_crypto_trade_pnl(self):
        # 1 BTC buy at 50,000, sell at 55,000
        res = self.cost_model_standard.calculate_trade_pnl(
            symbol="BTCUSDT",
            buy_price=50000.0,
            sell_price=55000.0,
            quantity=1.0,
            buy_time=1700000000,
            sell_time=1700003600,
        )
        # Slippage: 5 bps = 0.05%
        # Effective buy: 50000 * 1.0005 = 50025.0
        # Effective sell: 55000 * 0.9995 = 54972.5
        self.assertEqual(res["effective_buy_price"], 50025.0)
        self.assertEqual(res["effective_sell_price"], 54972.5)
        self.assertAlmostEqual(res["exchange_fees"], (50025.0 + 54972.5) * 0.001, places=1)
        self.assertGreater(res["pre_tax_pnl"], 4800.0)
        self.assertEqual(res["post_tax_pnl"], res["pre_tax_pnl"])
        self.assertEqual(res["vda_tax_115bbh"], 0.0)

    def test_indian_tax_regime_applies_vda_tax_tds_and_gst(self):
        # Profitable trade: buy at 60,000, sell at 70,000
        gain_res = self.cost_model_indian.calculate_trade_pnl(
            symbol="BTCUSDT",
            buy_price=60000.0,
            sell_price=70000.0,
            quantity=1.0,
            buy_time=1700000000,
            sell_time=1700003600,
        )
        self.assertTrue(gain_res["indian_tax_applied"])
        # Section 194S: 1% TDS on entire gross sale consideration
        expected_tds = round(gain_res["gross_sale_value"] * 0.01, 2)
        self.assertEqual(gain_res["tds_deducted_194s"], expected_tds)

        # Section 115BBH: 31.2% flat on gain
        raw_gain = gain_res["gross_sale_value"] - gain_res["gross_buy_cost"]
        expected_vda_tax = round(raw_gain * 0.312, 2)
        self.assertEqual(gain_res["vda_tax_115bbh"], expected_vda_tax)

        # GST: 18% on exchange fees
        expected_gst = round(gain_res["exchange_fees"] * 0.18, 2)
        self.assertEqual(gain_res["gst_on_fees"], expected_gst)

        # Post-tax is lower than pre-tax due to 31.2% VDA tax + 18% GST
        self.assertLess(gain_res["post_tax_pnl"], gain_res["pre_tax_pnl"])

    def test_indian_tax_strict_no_loss_set_off(self):
        # Losing trade: buy at 70,000, sell at 65,000
        loss_res = self.cost_model_indian.calculate_trade_pnl(
            symbol="BTCUSDT",
            buy_price=70000.0,
            sell_price=65000.0,
            quantity=1.0,
            buy_time=1700000000,
            sell_time=1700003600,
        )
        # Tax on gain is 0 (losses cannot be set off and do not generate negative tax credit)
        self.assertEqual(loss_res["vda_tax_115bbh"], 0.0)
        # 1% TDS is still deducted on the sale consideration under Section 194S
        self.assertGreater(loss_res["tds_deducted_194s"], 0.0)
        # Post-tax PnL suffers the full loss plus GST on fees
        self.assertLess(loss_res["post_tax_pnl"], loss_res["pre_tax_pnl"])

    def test_schedule_vda_csv_generation(self):
        trades = [
            self.cost_model_indian.calculate_trade_pnl("BTCUSDT", 50000, 52000, 0.5, 1700000000, 1700003600),
            self.cost_model_indian.calculate_trade_pnl("ETHUSDT", 3000, 3200, 2.0, 1700004000, 1700007200),
        ]
        csv_text = self.cost_model_indian.generate_schedule_vda_csv(trades)
        self.assertIn("SCHEDULE VDA TRADE LEDGER EXPORT", csv_text)
        self.assertIn("FOR TAX ESTIMATION ONLY, NOT OFFICIAL FILING", csv_text)
        self.assertIn("Section 115BBH", csv_text)
        self.assertIn("Section 194S", csv_text)
        self.assertIn("BTCUSDT", csv_text)
        self.assertIn("ETHUSDT", csv_text)

    def test_deflated_sharpe_ratio_penalizes_multiple_trials(self):
        returns = [0.01, 0.02, -0.005, 0.015, -0.01, 0.025, 0.008, -0.002, 0.012, 0.018] * 10
        # 1 trial
        dsr_1 = deflated_sharpe_ratio(observed_sr=1.8, num_trials=1, returns=returns)
        # 50 trials (candidate overfitting)
        dsr_50 = deflated_sharpe_ratio(observed_sr=1.8, num_trials=50, returns=returns)

        self.assertIsNotNone(dsr_1["deflated_sharpe_ratio"])
        self.assertIsNotNone(dsr_50["deflated_sharpe_ratio"])
        # Deflated Sharpe score is lower when multiple trials were searched
        self.assertGreater(dsr_1["deflated_sharpe_ratio"], dsr_50["deflated_sharpe_ratio"])
        self.assertGreater(dsr_1["p_value"], dsr_50["p_value"])

    def test_monthly_return_matrix_grouping(self):
        # Create equity curve spanning 2 months
        curve = [
            {"time": 1704067200, "nav": 10000.0},  # 2024-01-01
            {"time": 1706659200, "nav": 10500.0},  # 2024-01-31 (+5%)
            {"time": 1709164800, "nav": 11025.0},  # 2024-02-29 (+5%)
        ]
        matrix = compute_monthly_return_matrix(curve)
        self.assertIn("2024", matrix)
        self.assertIn("Jan", matrix["2024"])
        self.assertIn("Feb", matrix["2024"])
        self.assertEqual(matrix["2024"]["Jan"], 5.0)
        self.assertEqual(matrix["2024"]["Feb"], 5.0)


if __name__ == "__main__":
    unittest.main()
