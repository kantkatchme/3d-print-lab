#!/usr/bin/env python3
"""Announces print finished / paused / error. Run every minute via launchd or cron."""
import json
import sys

from common import ERROR_SENSOR, PREFIX, STATE_DIR, STATUS_SENSOR, guest, notify, say, state

ST = STATE_DIR / "status-watch.json"
IDLE = ("none", "unknown", "unavailable")

try:
    now = state(f"sensor.{PREFIX}_{STATUS_SENSOR}")
    err = state(f"sensor.{PREFIX}_{ERROR_SENSOR}")
    name = state(f"sensor.{PREFIX}_file_name")
except Exception as ex:
    print("Home Assistant not reachable:", ex)
    sys.exit(0)

old = json.loads(ST.read_text()) if ST.exists() else {}
msg = None
if old.get("status") == "printing" and now not in ("printing", "unknown", "unavailable"):
    if err not in IDLE:
        msg = ("red", "Print error", f"{name}: {err}")
    elif now in ("paused", "pause", "pausing"):
        msg = ("yellow", "Print paused", name)
    else:
        msg = ("info", "Print finished", f"{name} ({now})")
elif err not in IDLE and err != old.get("err"):
    msg = ("red", "Print error", f"{name}: {err}")

if msg:
    notify(*msg)
    if msg[1] == "Print finished":
        say("The print is finished.")
        guest("Printer", "The print is finished.")
    elif msg[1] == "Print error":
        say("Attention, the printer reports an error.")
        guest("Printer error", "The printer reports an error. The admin has been notified.")

if now not in ("unknown", "unavailable"):
    ST.write_text(json.dumps({"status": now, "err": err}))
