# Halal moomoo trading bot

A bot that trades Shariah-compliant US stocks on moomoo, on its own. It starts in **paper trading** (simulated money).

> I'm not a scholar or a financial advisor. The rules below follow mainstream AAOIFI-style screening. Ask a qualified scholar to confirm them for your own situation.

---

## 1. What makes this bot halal

| Rule | How the bot follows it |
|---|---|
| **No riba (interest)** | No margin. It buys only with cash it already has and keeps a 5% cash buffer. |
| **No selling what you don't own** | No short selling. It never sells more than the shares it holds (`can_sell_qty`). |
| **No gharar / maysir (excessive uncertainty / gambling)** | No options, futures or CFDs. It buys only shares, plus Shariah-labelled ETFs. |
| **Halal business** | It skips banks, conventional insurance and finance, alcohol, tobacco, gambling, adult content, cannabis and pork. Defense, entertainment and hotels are scholar-debated, so it blocks them by default. |
| **AAOIFI financial ratios** | Interest-bearing debt < 30% of market cap. Cash and interest-bearing securities < 30% of market cap. Interest income < 5% of revenue. |
| **Divest when a stock fails** | It re-screens every holding on every run and sells any stock that becomes non-compliant. |
| **Day trading (disputed)** | It runs once a day on daily candles and never buys and sells on the same day. This also respects the stricter view that you should own the shares before you sell them. |
| **Purification** | `screener.purification_amount(dividends, ratio)` tells you how much of your dividends to give to charity. |

The screener is a first pass, using free Yahoo Finance data. If it lacks data for a stock, the stock fails. Before you trust a stock, cross-check it with a dedicated screener such as Musaffa or Zoya, or the Securities Commission Malaysia Shariah list for Bursa stocks. Screeners use slightly different limits: AAOIFI uses 30%, while Dow Jones and S&P use about 33%.

## 2. The strategy

It is long-only trend following on daily candles (`strategy.py`):
- **Buy** when the 20-day average is above the 50-day average and the price is above the 200-day average.
- **Sell** when that trend condition breaks, or the price falls **8%** below what you paid.
- **Limits:** at most 10% of the account per stock, at most 8 stocks, and no new buys after a 5% drop in one day. It uses limit orders only.

**Honest backtest** (10 years, from $10,000, `python strategy.py`):

| Stock | Strategy | Buy & hold |
|---|---|---|
| AAPL | $29,196 | $95,240 |
| MSFT | $31,692 | $81,065 |
| NVDA | $126,614 | $522,291 |
| KO | $11,367 | $27,329 |
| SPUS | $18,727 | $26,654 |

In this bull market the strategy made money but **lost badly to simply holding**. A trend filter like this is designed to cut losses in crashes, and you pay for that by missing upside. Treat it as a safe template to improve, not a money machine.

## 3. Setup (macOS)

**a. Open the moomoo API**
1. Download **OpenD** for macOS from moomoo's OpenAPI page: <https://www.moomoo.com/download/OpenAPI>.
2. Extract the file and run the installer. Open **OpenD** and log in with your moomoo ID and password.
3. On first login, finish the **API questionnaire and agreement**.
4. Leave the API port at **11111** and keep OpenD running whenever the bot runs.
5. In the moomoo app, open the **paper trading** account (Paper Trade, US stocks).

**b. Install the bot**
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

**c. Check things work**
```bash
.venv/bin/python screener.py AAPL JPM SPUS
```
```bash
.venv/bin/python -m unittest discover -s tests -t .
```

**d. Edit `config.json`**
- `security_firm`: `FUTUMY` for moomoo Malaysia. Use `FUTUSG` for Singapore, `FUTUINC` for the US, `FUTUAU` for Australia or `FUTUCA` for Canada.
- `watchlist`: the stocks it may buy. The bot screens each one again before every buy.
- `dry_run: true` makes the bot log orders without placing them.

**e. Run in paper mode**
```bash
.venv/bin/python bot.py --loop
```
It trades once every weekday at 10:00 New York time (10 PM in Malaysia). Every order is written to `trades.csv`.

**Emergency stop:** create an empty file named `STOP` in this folder and the bot does nothing. Delete the file to resume.

**Dashboard:** in a second terminal, run
```bash
.venv/bin/python dashboard.py
```
then open <http://127.0.0.1:8050>. It shows account value, holdings with profit/loss, today's orders, every bot decision and the live log, refreshing every 15 seconds. The **Pause bot** button creates the `STOP` file for you. It is only reachable from this Mac.

## Running on a server (SovernStack)

The bot can run 24/7 on a SovernStack SSH session (Ubuntu 22.04, CPU, 4 GB) instead of your Mac.
- Code lives in `/opt/go-halal` on the server, and OpenD (Linux command-line build) in `/opt/opend`.
- Each program runs in its own `tmux` session: `opend`, `bot` and `dashboard`. List them with `tmux ls`, and watch one with `tmux attach -t bot` (press Ctrl+B then D to leave it running).
- **Log in to OpenD:** `tmux new -A -s opend /opt/go-halal/server/opend-login.sh`. Type your moomoo ID and password. If it asks for an SMS code, run `req_phone_verify_code`, then `input_phone_verify_code -code=<code>`.
- **Start the bot and dashboard:** `/opt/go-halal/server/start.sh`.
- **View the dashboard from your Mac:**
  ```bash
  ssh -N -L 8050:127.0.0.1:8050 -i ~/.ssh/go-halal-bot.pem -p 8901 root@kl.sovernstack.com
  ```
  then open <http://127.0.0.1:8050>.
- If the session restarts, log in to OpenD again, then run `start.sh`.
- Never run the bot on your Mac and on the server at the same time. Both would place orders on the same account.

## Supabase storage

Trades, account snapshots and the bot's log are also saved to the Supabase project **Go Halal** (`ohncshmgjuesevhelnfg`, Singapore), in the tables `trades`, `equity_snapshots` and `bot_events`.
- **Setup:** the schema is in `supabase/migrations/`. The bot reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from `.env`, which is never committed.
- **Access:** row-level security is on with no public policies, so only that secret key can read or write.
- **If Supabase is down or not set up:** the bot keeps trading and still writes its local files.

## 4. Going live (real money)

With `"fractional": true`, the bot buys fractional US shares from US$5 per order, so it works with small accounts such as RM500. To make it ignore money above a set amount, set `"budget_myr"` to that amount. `null` means the whole account.

1. **Fund it without borrowing.** Deposit the RM, then use **Currency Exchange** in the moomoo app to turn it into **USD**. The bot only spends real USD cash, so RM left unconverted is ignored. This stops the margin account from lending USD, which would be charged interest (riba).
2. In `config.json`, set `"mode": "live"` and `"i_understand_live_trading_uses_real_money": true`.
3. **Start it from the dashboard:**
   - Under **Controls**, log in to OpenD: your moomoo ID, your password, and an SMS code if asked.
   - Enter your trading PIN and press **Start live trading**.

   The PIN goes straight to the bot process and is never saved. You can also start the bot with `server/go-live.sh` in a terminal.
4. **Stop it any time** with **Stop bot**, or **Pause bot** to skip passes. The bot can't restart itself in live mode, because it never stores your PIN.

The dashboard only accepts commands from its own page, and only through your SSH tunnel. Its OpenD box can send login answers and SMS codes, nothing else.

Costs: fractional orders (under 1 share) pay no commission and a platform fee of 0.99% of the order amount, capped at US$0.99. Malaysian stamp duty also applies. Check the current fees in the moomoo app.

## Files
- `bot.py`: connects to OpenD and runs the daily pass: sells first, then buys.
- `strategy.py`: buy/sell rules, position sizing and the backtest.
- `screener.py`: Shariah screen and purification calculator.
- `dashboard.py` + `dashboard.html`: local web dashboard.
- `db.py`: optional Supabase storage.
- `fx.py`: USD/MYR exchange rate.
- `controls.py`: dashboard controls (OpenD login, start/stop bot).
- `insights.py`: the "How the bot decides" data for the dashboard.
- `server/`: scripts for running on SovernStack (`opend-login.sh`, `start.sh`, `go-live.sh`).
- `config.json`: all settings.
