"""Local dashboard for the Go Halal bot.

  .venv/bin/python dashboard.py      then open http://127.0.0.1:8050

Read-only view of the paper/live account through OpenD, plus the bot's own
logs. The only thing it can change is pause/resume (the STOP file).
"""
import csv
import datetime as dt
import json
import subprocess
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

import moomoo as mm

HERE = Path(__file__).parent
CFG = json.loads((HERE / "config.json").read_text())
STOP_FILE = HERE / "STOP"
NY = ZoneInfo("America/New_York")
ENV = mm.TrdEnv.REAL if CFG["mode"] == "live" else mm.TrdEnv.SIMULATE
PORT = 8050


def trade_ctx():
    return mm.OpenSecTradeContext(
        filter_trdmarket=getattr(mm.TrdMarket, CFG["market"]),
        host=CFG["opend_host"], port=CFG["opend_port"],
        security_firm=getattr(mm.SecurityFirm, CFG["security_firm"]),
    )


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # moomoo returns 'N/A' for fields a paper account doesn't track


def records(df, cols):
    return [{c: (v.item() if hasattr(v, "item") else v) for c, v in zip(cols, row)}
            for row in df[cols].itertuples(index=False)]


def broker_snapshot():
    try:
        ctx = trade_ctx()
    except Exception as exc:
        return {"error": f"Can't reach OpenD: {exc}"}
    try:
        return _snapshot(ctx)
    except Exception as exc:
        return {"error": f"OpenD query failed: {exc}"}
    finally:
        ctx.close()


def _snapshot(ctx):
    ret, acc = ctx.accinfo_query(trd_env=ENV, currency=CFG["currency"], refresh_cache=True)
    if ret != mm.RET_OK:
        return {"error": f"Account query failed: {acc}"}
    a = acc.iloc[0]
    ret, pos = ctx.position_list_query(trd_env=ENV, refresh_cache=True)
    pos = pos[pos["qty"] > 0] if ret == mm.RET_OK else pos.iloc[0:0]
    ret, orders = ctx.order_list_query(trd_env=ENV, refresh_cache=True)
    return {
        "account": {k: num(a[k]) for k in ("total_assets", "cash", "market_val", "unrealized_pl", "realized_pl")},
        "positions": records(pos, ["code", "stock_name", "qty", "cost_price", "nominal_price",
                                   "market_val", "pl_val", "pl_ratio", "today_pl_val"]) if len(pos) else [],
        "orders": records(orders, ["code", "trd_side", "order_status", "qty", "price", "dealt_qty",
                                   "dealt_avg_price", "create_time", "last_err_msg"])
                  if ret == mm.RET_OK and len(orders) else [],
    }


def bot_running():
    out = subprocess.run(["pgrep", "-f", "bot.py --loop"], capture_output=True, text=True)
    return bool(out.stdout.strip())


def next_run():
    hh, mi = map(int, CFG["run_time_new_york"].split(":"))
    now = dt.datetime.now(NY)
    t = now.replace(hour=hh, minute=mi, second=0, microsecond=0)
    if t <= now:
        t += dt.timedelta(days=1)
    while t.weekday() >= 5:
        t += dt.timedelta(days=1)
    return t.astimezone().strftime("%a %d %b, %I:%M %p")


def read_csv(name, limit):
    path = HERE / name
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))[-limit:]


def status():
    log = HERE / "bot.log"
    lines = log.read_text(errors="replace").splitlines()[-40:] if log.exists() else []
    return {
        "mode": CFG["mode"], "dry_run": CFG["dry_run"], "running": bot_running(),
        "paused": STOP_FILE.exists(), "next_run": next_run(),
        "now": dt.datetime.now().strftime("%H:%M:%S"),
        "broker": broker_snapshot(),
        "trades": read_csv("trades.csv", 50)[::-1],
        "equity": read_csv("equity.csv", 365),
        "log": lines[::-1],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype="application/json", code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/status":
            self._send(json.dumps(status(), default=str))
        elif self.path in ("/", "/index.html"):
            self._send((HERE / "dashboard.html").read_text(), "text/html; charset=utf-8")
        else:
            self._send("not found", "text/plain", 404)

    def do_POST(self):
        if self.path == "/api/pause":
            STOP_FILE.touch()
        elif self.path == "/api/resume":
            STOP_FILE.unlink(missing_ok=True)
        else:
            return self._send("not found", "text/plain", 404)
        self._send(json.dumps({"paused": STOP_FILE.exists()}))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Go Halal dashboard: http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
