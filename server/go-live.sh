#!/bin/bash
# Restart the bot in LIVE mode. Asks for your moomoo trading PIN without showing it,
# hands it only to the bot process, and never writes it to disk.
# Before running: set "mode": "live" and "i_understand_live_trading_uses_real_money": true in config.json.
cd /opt/go-halal || exit 1
grep -q '"mode": "live"' config.json || { echo 'config.json still says "mode": "paper". Change it first.'; exit 1; }
read -rsp "moomoo trading PIN: " PIN; echo
tmux kill-session -t bot 2>/dev/null
tmux new -d -e TZ=Asia/Kuala_Lumpur -e MOOMOO_TRADE_PASSWORD="$PIN" -s bot \
  ".venv/bin/python -u bot.py --loop 2>&1 | grep --line-buffered -v -iE 'warn|open_context_base' | tee -a bot.log"
unset PIN
sleep 5; tmux capture-pane -p -t bot | grep -v '^\s*$' | tail -3
