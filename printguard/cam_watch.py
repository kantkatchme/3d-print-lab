#!/usr/bin/env python3
"""Camera watchdog. Run every 2 minutes.

Checks that the printer's MJPEG stream (port 8080) delivers a frame. If the camera is dead
while a print is running (two failed checks in a row), it alerts, then again every 30 minutes.
Dead camera without a running print only goes to the state file.
"""
import json
import sys
import time

from common import PREFIX, PRINTER_IP, STATE_DIR, STATUS_SENSOR, grab_frame, notify, state

if not PRINTER_IP:
    sys.exit("PRINTER_IP is not set")

ST = STATE_DIR / "cam-watch.json"


def printing():
    try:
        return state(f"sensor.{PREFIX}_{STATUS_SENSOR}") in ("printing", "paused")
    except Exception:
        return None  # Home Assistant unreachable: don't guess


st = json.loads(ST.read_text()) if ST.exists() else {}
ok, pr, now = grab_frame() is not None, printing(), time.time()
st.update(ok=ok, printing=pr, checked=now)
st["fails"] = 0 if ok else st.get("fails", 0) + 1
if ok:
    st["last_ok"] = now
    st.pop("alarm", None)
elif st["fails"] >= 2 and pr is not None:
    if not st.get("alarm") or (pr and now - st.get("pushed", 0) > 1800):
        notify("red", "Printer camera is down",
               "Print running without a picture. Power-cycle the printer once it's done." if pr
               else "No print active. Power-cycle the printer for 10 s to bring the camera back.")
        st["pushed"], st["alarm"] = now, True
ST.write_text(json.dumps(st))
