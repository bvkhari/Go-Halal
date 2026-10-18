"""USD -> MYR exchange rate (Yahoo Finance), cached for an hour."""
import datetime as dt
import time

_cache = {"rate": None, "at": 0.0, "updated": None}


def usd_myr():
    """Returns {"usd_myr": rate or None, "updated": text}. Keeps the last known rate on errors."""
    if time.time() - _cache["at"] > 3600:
        _cache["at"] = time.time()
        try:
            import yfinance as yf
            hist = yf.Ticker("MYR=X").history(period="5d")
            _cache["rate"] = round(float(hist["Close"].iloc[-1]), 4)
            _cache["updated"] = dt.datetime.now().strftime("%d %b %H:%M")
        except Exception:
            pass
    return {"usd_myr": _cache["rate"], "updated": _cache["updated"]}
