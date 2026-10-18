"""Optional Supabase storage for trades, account snapshots and bot log lines.

Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from the environment or from .env
next to this file. If they're missing or Supabase is unreachable, every call
quietly does nothing: storage must never stop the bot from trading.
"""
import os
from pathlib import Path

import requests

HERE = Path(__file__).parent


def _load_env():
    env = {}
    path = HERE / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return {k: os.environ.get(k) or env.get(k) for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}


_ENV = _load_env()
ENABLED = bool(_ENV["SUPABASE_URL"] and _ENV["SUPABASE_SERVICE_KEY"])


def insert(table, row):
    """Insert one row; returns True on success. Never raises."""
    if not ENABLED:
        return False
    try:
        r = requests.post(
            f"{_ENV['SUPABASE_URL']}/rest/v1/{table}", json=row, timeout=5,
            headers={"apikey": _ENV["SUPABASE_SERVICE_KEY"],
                     "Authorization": f"Bearer {_ENV['SUPABASE_SERVICE_KEY']}",
                     "Prefer": "return=minimal"},
        )
        return r.status_code < 300
    except requests.RequestException:
        return False
