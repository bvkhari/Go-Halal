"""Long-only trend-following strategy on daily bars.

Halal design choices:
  - Buy shares outright with cash only: no margin, no short selling, no options.
  - Swing/position trading on daily candles. The bot runs once a day, so a
    position is never bought and sold on the same day.

Rules:
  Hold  when SMA(fast) > SMA(slow) and close > SMA(trend)
  Buy   when the hold condition is true and we don't own it
  Sell  when the hold condition breaks, or the price falls stop_loss_pct below cost
"""
from dataclasses import dataclass


@dataclass
class Params:
    fast: int = 20
    slow: int = 50
    trend: int = 200
    stop_loss_pct: float = 0.08


def sma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None


def hold_condition(closes, p: Params):
    fast, slow, trend = sma(closes, p.fast), sma(closes, p.slow), sma(closes, p.trend)
    if None in (fast, slow, trend):
        return False  # not enough history: stay out
    return fast > slow and closes[-1] > trend


def signal(closes, p: Params, cost_price=None):
    """Return 'BUY', 'SELL' or 'HOLD' for one stock. cost_price is set when we own it."""
    in_trend = hold_condition(closes, p)
    if cost_price is None:
        return "BUY" if in_trend else "HOLD"
    if closes[-1] <= cost_price * (1 - p.stop_loss_pct):
        return "SELL"
    return "HOLD" if in_trend else "SELL"


def position_size(price, equity, cash, max_position_pct, cash_buffer_pct, fractional=False, min_order=0.0):
    """Shares to buy, using cash only (never borrowed money).

    Whole shares by default; with fractional=True, down to 0.0001 share, as long
    as the order is worth at least min_order (moomoo's fractional minimum is US$5).
    """
    if price <= 0:
        return 0
    budget = min(equity * max_position_pct, cash - equity * cash_buffer_pct)
    if budget < min_order:
        return 0
    if fractional:
        return max(int(budget / price * 10_000) / 10_000, 0)
    return max(int(budget // price), 0)


def bot_capital(equity, cash, invested, budget_usd=None):
    """Equity and cash the bot may use. With a budget, it acts as if the account
    held only that much, even when the real account holds more."""
    if budget_usd is None:
        return equity, cash
    return min(equity, budget_usd), min(cash, max(budget_usd - invested, 0))


def backtest(closes, p: Params, start_cash=10_000.0):
    """Single-stock backtest. Returns (final_equity, trades, buy_and_hold_equity)."""
    cash, qty, cost, trades = start_cash, 0, None, 0
    for i in range(p.trend, len(closes)):
        window, price = closes[: i + 1], closes[i]
        action = signal(window, p, cost if qty else None)
        if action == "BUY":
            qty = int(cash // price)
            if qty:
                cash -= qty * price
                cost, trades = price, trades + 1
        elif action == "SELL" and qty:
            cash += qty * price
            qty, cost, trades = 0, None, trades + 1
    final = cash + qty * closes[-1]
    buy_hold = start_cash / closes[p.trend] * closes[-1] if len(closes) > p.trend else start_cash
    return final, trades, buy_hold


if __name__ == "__main__":
    import sys
    import warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf

    p = Params()
    for tk in sys.argv[1:] or ["AAPL", "MSFT", "SPUS"]:
        closes = yf.Ticker(tk).history(period="10y")["Close"].tolist()
        final, trades, bh = backtest(closes, p)
        print(f"{tk:<6} strategy ${final:>10,.0f}  ({trades} trades)   buy&hold ${bh:>10,.0f}   from $10,000")
