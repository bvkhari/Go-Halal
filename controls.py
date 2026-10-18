"""Server controls for the dashboard: OpenD login and starting/stopping the bot.

Secrets typed into the dashboard (moomoo password, trading PIN) never touch the
disk or a command line: OpenD input goes through a tmux paste buffer fed on
stdin, and the PIN goes straight into the bot process's environment.
"""
import os
import re
import socket
import subprocess
import time
from pathlib import Path

import moomoo as mm

HERE = Path(__file__).parent
BOT_LOG = HERE / "bot.log"
TZ = {"TZ": "Asia/Kuala_Lumpur"}


def _tmux(*args, stdin=None):
    return subprocess.run(["tmux", *args], input=stdin, capture_output=True, text=True)


def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


# ---------- OpenD ----------
def opend_state(cfg):
    session = _tmux("has-session", "-t", "opend").returncode == 0
    state = {"session": session, "api_up": _port_open(cfg["opend_host"], cfg["opend_port"]),
             "logged_in": False, "console": []}
    if session:
        out = _tmux("capture-pane", "-p", "-t", "opend", "-S", "-40").stdout
        state["console"] = [l for l in out.splitlines() if l.strip()][-14:]
    if state["api_up"]:
        quote = mm.OpenQuoteContext(host=cfg["opend_host"], port=cfg["opend_port"])
        try:
            ret, data = quote.get_global_state()
            state["logged_in"] = ret == mm.RET_OK and bool(data.get("qot_logined")) and bool(data.get("trd_logined"))
        finally:
            quote.close()
    return state


def opend_start():
    if _tmux("has-session", "-t", "opend").returncode == 0:
        return "OpenD is already running."
    _tmux("new", "-d", "-e", f"TZ={TZ['TZ']}", "-s", "opend", str(HERE / "server" / "opend-login.sh"))
    time.sleep(4)
    return "OpenD started. Enter your moomoo ID when it asks."


def _last_console_line():
    out = _tmux("capture-pane", "-p", "-t", "opend").stdout
    lines = [l.strip() for l in out.splitlines() if l.strip() and l.strip() != ">>>"]
    return lines[-1].lower() if lines else ""


def _type_line(text):
    # Fed on stdin, so the text never appears in a command line or process list.
    _tmux("load-buffer", "-b", "gohalal", "-", stdin=text)
    _tmux("paste-buffer", "-d", "-b", "gohalal", "-t", "opend")
    _tmux("send-keys", "-t", "opend", "Enter")
    time.sleep(2)


def opend_login_step(kind, value=""):
    """The only things the dashboard can send to OpenD: a login answer while OpenD is asking
    for it, or the SMS-code commands. No free-form console commands."""
    if _tmux("has-session", "-t", "opend").returncode != 0:
        return "OpenD isn't running. Start it first."
    prompt = _last_console_line()
    if kind == "account":
        if "account" not in prompt:
            return "OpenD isn't asking for your moomoo ID right now."
        if not re.fullmatch(r"[\w.@+-]{3,64}", value):
            return "That doesn't look like a moomoo ID."
        _type_line(value)
    elif kind == "password":
        if "password" not in prompt:
            return "OpenD isn't asking for a password right now."
        if not value or len(value) > 128 or "\n" in value:
            return "Invalid password."
        _type_line(value)
    elif kind == "sms_request":
        _type_line("req_phone_verify_code")
    elif kind == "sms_code":
        if not re.fullmatch(r"\d{4,8}", value):
            return "The SMS code should be 4 to 8 digits."
        _type_line(f"input_phone_verify_code -code={value}")
    else:
        return "Unknown request."
    return "Sent."


# ---------- bot ----------
def bot_running():
    return subprocess.run(["pgrep", "-f", "bot.py --loop"], capture_output=True).returncode == 0


def bot_start(cfg, pin):
    if bot_running():
        return False, "The bot is already running."
    live = cfg["mode"] == "live"
    if live and not pin:
        return False, "Enter your trading PIN to start live trading."
    env = {**os.environ, **TZ}
    if live:
        env["MOOMOO_TRADE_PASSWORD"] = pin
    log = BOT_LOG.open("a")
    subprocess.Popen([str(HERE / ".venv/bin/python"), "-u", "bot.py", "--loop"], cwd=HERE, env=env,
                     stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    log.close()
    time.sleep(8)  # long enough to connect and unlock trading
    if bot_running():
        return True, "Bot started in LIVE mode." if live else "Bot started in paper mode."
    return False, "The bot stopped right away. Check the bot log (a wrong PIN shows as 'unlock_trade failed')."


def bot_stop():
    _tmux("kill-session", "-t", "bot")
    subprocess.run(["pkill", "-f", "bot.py --loop"])
    time.sleep(1)
    return not bot_running()
