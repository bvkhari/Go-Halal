"""Explains the bot's decisions for the dashboard.

Recomputes, for every watchlist stock (plus anything held), exactly what the
bot would decide right now and why: Shariah screen, moving averages, signal.
Runs in a background thread so the dashboard stays fast.
"""
import datetime as dt
import threading
import time

import moomoo as mm

import screener
from strategy import Params, sma, signal

REFRESH_SECONDS = 15 * 60
SCREEN_TTL = 12 * 3600
CHART_DAYS = 260  # about one trading year


class Insights:
    def __init__(self, cfg):
        self.cfg = cfg
        self.params = Params(**cfg["strategy"])
        self.data = {"status": "loading", "stocks": []}
        self._screens = {}
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                self.data = self._compute()
            except Exception as exc:
                self.data = {**self.data, "status": f"error: {exc}"}
            time.sleep(REFRESH_SECONDS)

    def _screen(self, code):
        hit = self._screens.get(code)
        if hit and time.time() - hit[0] < SCREEN_TTL:
            return hit[1]
        result = screener.screen(code)
        self._screens[code] = (time.time(), result)
        return result

    def _history(self, quote, code):
        start = (dt.date.today() - dt.timedelta(days=(CHART_DAYS + self.params.trend) * 1.6)).isoformat()
        end = dt.date.today().isoformat()  # without end, moomoo stops one year after start
        ret, data, _ = quote.request_history_kline(code, start=start, end=end, ktype=mm.KLType.K_DAY, max_count=1000)
        if ret == mm.RET_OK and len(data) > self.params.trend:
            return [t[:10] for t in data["time_key"]], data["close"].tolist()
        import yfinance as yf
        hist = yf.Ticker(code.split(".", 1)[1]).history(period="2y")
        return [d.strftime("%Y-%m-%d") for d in hist.index], hist["Close"].tolist()

    def _held(self, env):
        trade = mm.OpenSecTradeContext(
            filter_trdmarket=getattr(mm.TrdMarket, self.cfg["market"]),
            host=self.cfg["opend_host"], port=self.cfg["opend_port"],
            security_firm=getattr(mm.SecurityFirm, self.cfg["security_firm"]),
        )
        try:
            ret, pos = trade.position_list_query(trd_env=env, refresh_cache=True)
            if ret != mm.RET_OK:
                return {}
            return {r.code: float(r.cost_price) for r in pos.itertuples() if r.qty > 0}
        finally:
            trade.close()

    def _compute(self):
        p = self.params
        env = mm.TrdEnv.REAL if self.cfg["mode"] == "live" else mm.TrdEnv.SIMULATE
        held = self._held(env)
        market = self.cfg["market"]
        codes = [t if "." in t else f"{market}.{t}" for t in self.cfg["watchlist"]]
        codes += [c for c in held if c not in codes]

        quote = mm.OpenQuoteContext(host=self.cfg["opend_host"], port=self.cfg["opend_port"])
        stocks = []
        try:
            for code in codes:
                dates, closes = self._history(quote, code)
                check = self._screen(code)
                fast, slow, trend = sma(closes, p.fast), sma(closes, p.slow), sma(closes, p.trend)
                cost = held.get(code)
                action = signal(closes, p, cost_price=cost)
                if not check.compliant:
                    action = "SELL" if cost else "BLOCKED"

                def series(n):
                    out = [None] * len(closes)
                    for i in range(n - 1, len(closes)):
                        out[i] = round(sum(closes[i - n + 1:i + 1]) / n, 4)
                    return out[-CHART_DAYS:]

                stocks.append({
                    "code": code,
                    "ticker": code.split(".", 1)[1],
                    "held": cost is not None,
                    "cost": cost,
                    "action": action,
                    "compliant": check.compliant,
                    "screen_reasons": check.reasons,
                    "ratios": {"debt": check.debt_ratio, "cash": check.cash_ratio,
                               "interest": check.impermissible_income_ratio},
                    "price": closes[-1],
                    "checks": {
                        "fast_above_slow": fast is not None and slow is not None and fast > slow,
                        "price_above_trend": trend is not None and closes[-1] > trend,
                        "stop_hit": cost is not None and closes[-1] <= cost * (1 - p.stop_loss_pct),
                    },
                    "sma": {"fast": fast, "slow": slow, "trend": trend},
                    "dates": dates[-CHART_DAYS:],
                    "close": [round(c, 4) for c in closes[-CHART_DAYS:]],
                    "fast": series(p.fast), "slow": series(p.slow), "trend": series(p.trend),
                })
        finally:
            quote.close()

        return {
            "status": "ok",
            "updated": dt.datetime.now().strftime("%H:%M"),
            "params": {"fast": p.fast, "slow": p.slow, "trend": p.trend, "stop_loss_pct": p.stop_loss_pct},
            "stocks": stocks,
        }
