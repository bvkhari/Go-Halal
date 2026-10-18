"""Shariah (AAOIFI-style) stock screener.

Screens each ticker on two levels:
  1. Business activity  - core business must not be in a prohibited industry.
  2. Financial ratios    - AAOIFI Shari'a Standard No. 21 style limits:
       interest-bearing debt          < 30% of market cap
       cash + interest-bearing assets < 30% of market cap
       interest (impermissible) income <  5% of total revenue

Data comes from Yahoo Finance (yfinance), which is free but imperfect. Treat
this as a first-pass filter and cross-check results with a dedicated Shariah
screener (Musaffa, Zoya, or the Securities Commission Malaysia list for Bursa).

Usage:  .venv/bin/python screener.py AAPL MSFT JPM
"""
import sys
import warnings
from dataclasses import dataclass, field

warnings.filterwarnings("ignore")

DEBT_LIMIT = 0.30
CASH_LIMIT = 0.30
IMPERMISSIBLE_INCOME_LIMIT = 0.05

# Matched as lowercase substrings against Yahoo's sector/industry text.
PROHIBITED_INDUSTRIES = [
    "bank", "insurance", "mortgage", "credit services", "capital markets",
    "financial conglomerates", "asset management", "reit - mortgage",
    "brewers", "wineries", "distillers", "tobacco", "gambling", "casino",
    "adult", "cannabis", "pork",
]
# Debated among scholars: blocked by default; remove from this list if your scholar permits.
DOUBTFUL_INDUSTRIES = ["aerospace & defense", "entertainment", "broadcasting", "lodging"]


@dataclass
class ScreenResult:
    ticker: str
    compliant: bool
    reasons: list = field(default_factory=list)
    debt_ratio: float = None
    cash_ratio: float = None
    impermissible_income_ratio: float = None

    def summary(self):
        status = "PASS" if self.compliant else "FAIL"
        fmt = lambda x: "n/a" if x is None else f"{x:.1%}"
        line = (f"{self.ticker:<8} {status}  debt {fmt(self.debt_ratio):>6}  "
                f"cash {fmt(self.cash_ratio):>6}  interest-income {fmt(self.impermissible_income_ratio):>6}")
        return line + ("" if self.compliant else "  <- " + "; ".join(self.reasons))


def check_business(industry_text):
    text = industry_text.lower().replace("—", " - ")
    for word in PROHIBITED_INDUSTRIES:
        if word in text:
            return f"prohibited business ({industry_text})"
    for word in DOUBTFUL_INDUSTRIES:
        if word in text:
            return f"doubtful business ({industry_text})"
    return None


def check_ratios(market_cap, total_debt, total_cash, interest_income, total_revenue):
    """Pure ratio test. Returns (reasons, debt_ratio, cash_ratio, income_ratio).
    Missing data counts as a failure: when in doubt, leave it out."""
    reasons = []
    if not market_cap:
        return ["no market cap data"], None, None, None
    debt_ratio = (total_debt or 0) / market_cap
    cash_ratio = (total_cash or 0) / market_cap
    income_ratio = None
    if total_revenue:
        income_ratio = (interest_income or 0) / total_revenue
    else:
        reasons.append("no revenue data")
    if total_debt is None:
        reasons.append("no debt data")
    if debt_ratio >= DEBT_LIMIT:
        reasons.append(f"debt {debt_ratio:.1%} >= {DEBT_LIMIT:.0%}")
    if cash_ratio >= CASH_LIMIT:
        reasons.append(f"cash/securities {cash_ratio:.1%} >= {CASH_LIMIT:.0%}")
    if income_ratio is not None and income_ratio >= IMPERMISSIBLE_INCOME_LIMIT:
        reasons.append(f"interest income {income_ratio:.1%} >= {IMPERMISSIBLE_INCOME_LIMIT:.0%}")
    return reasons, debt_ratio, cash_ratio, income_ratio


def _row(df, *names):
    if df is None or df.empty:
        return None
    for name in names:
        if name in df.index:
            value = df.loc[name].dropna()
            if not value.empty:
                return float(value.iloc[0])  # most recent annual figure
    return None


def screen(ticker):
    import yfinance as yf

    symbol = ticker.split(".", 1)[1] if ticker.startswith(("US.", "HK.")) else ticker
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        income = t.income_stmt
    except Exception as exc:
        return ScreenResult(ticker, False, [f"data error: {exc}"])

    if info.get("quoteType") == "ETF":
        # ETFs can't be ratio-screened here; only Shariah-labelled funds pass.
        name = (info.get("longName") or "").lower()
        ok = any(w in name for w in ("shariah", "sharia", "islamic", "halal"))
        return ScreenResult(ticker, ok, [] if ok else ["ETF without Shariah mandate"])

    reasons = []
    business = check_business(f"{info.get('sector', '')} {info.get('industry', '')}")
    if business:
        reasons.append(business)

    ratio_reasons, debt, cash, income_ratio = check_ratios(
        market_cap=info.get("marketCap"),
        total_debt=info.get("totalDebt"),
        total_cash=info.get("totalCash"),
        interest_income=_row(income, "Interest Income", "Interest Income Non Operating"),
        total_revenue=_row(income, "Total Revenue") or info.get("totalRevenue"),
    )
    reasons += ratio_reasons
    return ScreenResult(ticker, not reasons, reasons, debt, cash, income_ratio)


def purification_amount(dividends_received, impermissible_income_ratio):
    """Portion of dividends to give to charity for the company's small impermissible income."""
    return round(dividends_received * (impermissible_income_ratio or 0), 2)


if __name__ == "__main__":
    tickers = sys.argv[1:] or ["AAPL", "MSFT", "NVDA", "JPM", "KO", "SPUS"]
    for tk in tickers:
        print(screen(tk).summary())
