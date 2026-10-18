"""Shariah-compliant moomoo trading bot.

  .venv/bin/python bot.py          run one trading pass now
  .venv/bin/python bot.py --loop   keep running, one pass per US trading day

Needs moomoo OpenD running and logged in (see README.md).
Create a file named STOP in this folder to make the bot do nothing.
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

import moomoo as mm

import screener
from strategy import Params, position_size, signal

HERE = Path(__file__).parent
STATE_FILE = HERE / "state.json"
TRADE_LOG = HERE / "trades.csv"
STOP_FILE = HERE / "STOP"
NY = ZoneInfo("America/New_York")
MAX_DATA_AGE_DAYS = 7
ACTIVE_ORDER_STATUSES = {"WAITING_SUBMIT", "SUBMITTING", "SUBMITTED", "FILLED_PART"}


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def record_trade(row):
    new = not TRADE_LOG.exists()
    with TRADE_LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


class Bot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.risk = cfg["risk"]
        self.params = Params(**cfg["strategy"])
        self.market = cfg["market"]
        self.live = cfg["mode"] == "live"
        self.env = mm.TrdEnv.REAL if self.live else mm.TrdEnv.SIMULATE
        self.state = load_json(STATE_FILE, {})

        if self.live and not cfg.get("i_understand_live_trading_uses_real_money"):
            sys.exit("mode is 'live' but i_understand_live_trading_uses_real_money is false. Refusing to start.")

        host, port = cfg["opend_host"], cfg["opend_port"]
        self.quote = mm.OpenQuoteContext(host=host, port=port)
        self.trade = mm.OpenSecTradeContext(
            filter_trdmarket=getattr(mm.TrdMarket, self.market), host=host, port=port,
            security_firm=getattr(mm.SecurityFirm, cfg["security_firm"]),
        )
        if self.live:
            password = os.environ.get("MOOMOO_TRADE_PASSWORD")
            if not password:
                sys.exit("Live mode needs your trading password in the MOOMOO_TRADE_PASSWORD environment variable.")
            ret, data = self.trade.unlock_trade(password)
            if ret != mm.RET_OK:
                sys.exit(f"unlock_trade failed: {data}")
        log(f"Connected to OpenD  mode={'LIVE (real money)' if self.live else 'PAPER'}  dry_run={cfg['dry_run']}")

    def close(self):
        self.quote.close()
        self.trade.close()

    def code(self, ticker):
        return ticker if "." in ticker else f"{self.market}.{ticker}"

    # ---------- market and account data ----------
    def closes(self, code):
        """Daily closes up to today, or [] if no fresh data (the stock is then skipped)."""
        today = dt.date.today()
        fresh = (today - dt.timedelta(days=MAX_DATA_AGE_DAYS)).isoformat()
        start = (today - dt.timedelta(days=self.params.trend * 2)).isoformat()
        # end= is required: without it moomoo returns one year from start, not up to today.
        ret, data, _ = self.quote.request_history_kline(code, start=start, end=today.isoformat(),
                                                        ktype=mm.KLType.K_DAY, max_count=1000)
        if ret == mm.RET_OK and len(data) > self.params.trend and data["time_key"].iloc[-1][:10] >= fresh:
            return data["close"].tolist()
        # Fallback when OpenD lacks the quote permission for this market.
        import yfinance as yf
        hist = yf.Ticker(code.split(".", 1)[1]).history(period="2y")
        if len(hist) and hist.index[-1].strftime("%Y-%m-%d") >= fresh:
            return hist["Close"].tolist()
        log(f"skip {code}: no price data from the last {MAX_DATA_AGE_DAYS} days")
        return []

    def last_prices(self, codes):
        ret, data = self.quote.get_market_snapshot(codes)
        if ret != mm.RET_OK:
            return {}
        return {r.code: float(r.last_price) for r in data.itertuples() if r.last_price > 0}

    def account(self):
        ret, data = self.trade.accinfo_query(trd_env=self.env, currency=self.cfg["currency"], refresh_cache=True)
        if ret != mm.RET_OK:
            raise RuntimeError(f"accinfo_query failed: {data}")
        row = data.iloc[0]
        return float(row["total_assets"]), float(row["cash"])

    def positions(self):
        ret, data = self.trade.position_list_query(trd_env=self.env, refresh_cache=True)
        if ret != mm.RET_OK:
            raise RuntimeError(f"position_list_query failed: {data}")
        return {r.code: r for r in data.itertuples() if r.qty > 0}

    def codes_with_open_orders(self):
        ret, data = self.trade.order_list_query(trd_env=self.env, refresh_cache=True)
        if ret != mm.RET_OK:
            return set()
        return {r.code for r in data.itertuples() if str(r.order_status) in ACTIVE_ORDER_STATUSES}

    # ---------- orders ----------
    def order(self, side, code, qty, price, reason):
        slip = self.risk["limit_price_slippage_pct"]
        limit = price * (1 + slip) if side == "BUY" else price * (1 - slip)
        limit = round(limit, 2 if limit >= 1 else 4)
        log(f"{side} {qty} {code} @ limit {limit}  ({reason})")
        status = "dry-run"
        if not self.cfg["dry_run"]:
            ret, data = self.trade.place_order(
                price=limit, qty=qty, code=code,
                trd_side=mm.TrdSide.BUY if side == "BUY" else mm.TrdSide.SELL,
                order_type=mm.OrderType.NORMAL, trd_env=self.env,
            )
            status = f"order {data['order_id'][0]}" if ret == mm.RET_OK else f"ERROR {data}"
            log(f"  -> {status}")
        record_trade({"time": dt.datetime.now().isoformat(timespec="seconds"),
                      "mode": self.cfg["mode"], "side": side, "code": code, "qty": qty,
                      "limit": limit, "reason": reason, "status": status})

    # ---------- one daily pass ----------
    def run_once(self):
        if STOP_FILE.exists():
            log("STOP file present. Doing nothing.")
            return

        equity, cash = self.account()
        today = dt.date.today().isoformat()
        equity_log = HERE / "equity.csv"
        with equity_log.open("a") as f:
            if f.tell() == 0:
                f.write("time,equity,cash\n")
            f.write(f"{dt.datetime.now().isoformat(timespec='seconds')},{equity:.2f},{cash:.2f}\n")
        if self.state.get("day") != today:
            self.state = {"day": today, "start_equity": equity}
        drop = 1 - equity / self.state["start_equity"] if self.state["start_equity"] else 0
        buying_allowed = drop < self.risk["max_daily_loss_pct"]
        if not buying_allowed:
            log(f"Account down {drop:.1%} today: daily loss limit hit, no new buys.")

        held = self.positions()
        busy = self.codes_with_open_orders()
        watch = [self.code(t) for t in self.cfg["watchlist"]]
        prices = self.last_prices(sorted(set(watch) | set(held)))
        log(f"Equity {equity:,.2f}  cash {cash:,.2f}  positions {len(held)}")

        # 1. Exits, including divesting anything that is no longer Shariah compliant.
        for code, pos in held.items():
            if code in busy:
                continue
            check = screener.screen(code)
            price = prices.get(code) or float(pos.nominal_price)
            if not check.compliant:
                reason = "no longer Shariah compliant: " + "; ".join(check.reasons)
            else:
                closes = self.closes(code)
                if not closes:
                    continue
                action = signal(closes, self.params, cost_price=float(pos.cost_price))
                if action != "SELL":
                    continue
                reason = "exit signal / stop loss"
            qty = int(pos.can_sell_qty)  # never sell more than we own: no short selling
            if qty > 0:
                self.order("SELL", code, qty, price, reason)

        STATE_FILE.write_text(json.dumps(self.state))

        # 2. Entries.
        if not buying_allowed:
            return
        open_slots = self.risk["max_open_positions"] - len(held)
        for code in watch:
            if open_slots <= 0:
                break
            if code in held or code in busy or code not in prices:
                continue
            closes = self.closes(code)
            if not closes or signal(closes, self.params) != "BUY":
                continue
            check = screener.screen(code)
            if not check.compliant:
                log(f"skip {code}: " + "; ".join(check.reasons))
                continue
            price = prices[code]
            qty = position_size(price, equity, cash, self.risk["max_position_pct"], self.risk["cash_buffer_pct"])
            if qty < 1:
                log(f"skip {code}: not enough cash")
                continue
            self.order("BUY", code, qty, price, "trend entry")
            cash -= qty * price
            open_slots -= 1


def trading_day_now(run_time):
    now = dt.datetime.now(NY)
    hh, mm_ = map(int, run_time.split(":"))
    return now.weekday() < 5 and (now.hour, now.minute) >= (hh, mm_), now.date().isoformat()


def main():
    cfg = load_json(HERE / "config.json", None)
    if cfg is None:
        sys.exit("config.json missing or invalid")
    bot = Bot(cfg)
    try:
        if "--loop" not in sys.argv:
            bot.run_once()
            return
        last_run = None
        log(f"Loop mode: one pass each weekday after {cfg['run_time_new_york']} New York time. Ctrl+C to stop.")
        while True:
            due, day = trading_day_now(cfg["run_time_new_york"])
            if due and day != last_run:
                try:
                    bot.run_once()
                except Exception as exc:  # keep the loop alive; try again tomorrow
                    log(f"pass failed: {exc}")
                last_run = day
            time.sleep(60)
    finally:
        bot.close()


if __name__ == "__main__":
    main()
