#!/bin/bash
# Start the bot and dashboard in background tmux sessions (skips any already running).
# OpenD must be logged in first (see opend-login.sh).
cd /opt/go-halal || exit 1
export TZ=Asia/Kuala_Lumpur
if grep -q '"mode": "live"' config.json; then
  tmux has-session -t bot 2>/dev/null || echo "Live mode: start the bot with server/go-live.sh (it asks for your trading PIN)."
else
tmux has-session -t bot 2>/dev/null || \
  tmux new -d -e TZ=Asia/Kuala_Lumpur -s bot ".venv/bin/python -u bot.py --loop 2>&1 | grep --line-buffered -v -iE 'warn|open_context_base' | tee -a bot.log"
fi
tmux has-session -t dashboard 2>/dev/null || \
  tmux new -d -e TZ=Asia/Kuala_Lumpur -s dashboard ".venv/bin/python -u dashboard.py 2>&1 | grep --line-buffered -v -iE 'warn|open_context_base'"
tmux ls
