import unittest

from screener import check_business, check_ratios, purification_amount
from strategy import Params, backtest, position_size, signal

P = Params(fast=2, slow=3, trend=5, stop_loss_pct=0.08)


class Strategy(unittest.TestCase):
    def test_buy_in_uptrend(self):
        self.assertEqual(signal([1, 2, 3, 4, 5, 6], P), "BUY")

    def test_no_buy_in_downtrend(self):
        self.assertEqual(signal([6, 5, 4, 3, 2, 1], P), "HOLD")

    def test_not_enough_history_stays_out(self):
        self.assertEqual(signal([1, 2], P), "HOLD")

    def test_sell_when_trend_breaks(self):
        self.assertEqual(signal([1, 2, 3, 4, 3, 2], P, cost_price=3), "SELL")

    def test_stop_loss(self):
        self.assertEqual(signal([1, 2, 3, 4, 5, 9, 10, 9.1], P, cost_price=10), "SELL")

    def test_position_size_uses_cash_only(self):
        # 10% of 10k = 1000 budget, but only 300 cash minus 500 buffer -> buy nothing
        self.assertEqual(position_size(50, 10_000, 300, 0.10, 0.05), 0)
        self.assertEqual(position_size(50, 10_000, 10_000, 0.10, 0.05), 20)

    def test_backtest_runs(self):
        final, trades, _ = backtest([float(x) for x in range(1, 50)], P)
        self.assertGreater(final, 10_000)
        self.assertEqual(trades, 1)


class Screening(unittest.TestCase):
    def test_prohibited_business(self):
        self.assertIsNotNone(check_business("Financial Services Banks—Diversified"))
        self.assertIsNotNone(check_business("Consumer Defensive Beverages - Brewers"))
        self.assertIsNone(check_business("Technology Consumer Electronics"))

    def test_ratios(self):
        self.assertEqual(check_ratios(1000, 100, 100, 1, 100)[0], [])
        self.assertTrue(check_ratios(1000, 400, 100, 1, 100)[0])   # debt 40%
        self.assertTrue(check_ratios(1000, 100, 100, 6, 100)[0])   # interest 6%
        self.assertTrue(check_ratios(None, 1, 1, 1, 1)[0])          # missing data fails

    def test_purification(self):
        self.assertEqual(purification_amount(200, 0.012), 2.4)


if __name__ == "__main__":
    unittest.main()
