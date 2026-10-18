import unittest

from screener import check_business, check_ratios, purification_amount
from strategy import Params, backtest, bot_capital, position_size, signal

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

    def test_fractional_shares_for_small_budget(self):
        # RM500 ~ $122.58: 10% = $12.26 per stock, MSFT at $530 -> 0.0231 share
        self.assertEqual(position_size(530, 122.58, 122.58, 0.10, 0.05, fractional=True, min_order=5), 0.0231)
        # whole shares only: can't afford even one
        self.assertEqual(position_size(530, 122.58, 122.58, 0.10, 0.05), 0)

    def test_below_minimum_order_buys_nothing(self):
        # $40 account: 10% = $4 < $5 fractional minimum
        self.assertEqual(position_size(100, 40, 40, 0.10, 0.05, fractional=True, min_order=5), 0)

    def test_budget_caps_a_bigger_account(self):
        # paper account holds $1M but the budget is $122.58, $50 already invested
        self.assertEqual(bot_capital(1_000_000, 1_000_000, 50, 122.58), (122.58, 72.58))
        self.assertEqual(bot_capital(1_000_000, 1_000_000, 200, 122.58), (122.58, 0))
        self.assertEqual(bot_capital(1000, 500, 0, None), (1000, 500))

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
