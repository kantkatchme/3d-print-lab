"""Shared config and helpers for the print guard scripts.

Everything is configured through environment variables (see .env.example).
We shell out to curl instead of using urllib on purpose: on macOS, background jobs
only get "local network" access through curl, and curl lets us keep the token out of `ps`.
"""
import json
import os
import shlex
import socket
import subprocess
import time
from pathlib import Path

HOME = Path.home()
STATE_DIR = Path(os.environ.get("PRINTLAB_STATE") or HOME / ".printlab")
STATE_DIR.mkdir(parents=True, exist_ok=True)

HA_URL = (os.environ.get("HA_URL") or "http://homeassistant.local:8123/api").rstrip("/") + "/"
PRINTER_IP = os.environ.get("PRINTER_IP", "")
# Entity prefix of the Elegoo CC2 integration, e.g. sensor.<prefix>_current_layer
PREFIX = os.environ.get("PRINTER_PREFIX") or "carbon_2_combo"
# These two sensor names are localised by the integration. Default is a German Home Assistant.
STATUS_SENSOR = os.environ.get("STATUS_SENSOR") or "druckstatus"  # English HA: "print_status"
ERROR_SENSOR = os.environ.get("ERROR_SENSOR") or "druckfehler"    # English HA: "print_error"
NOTIFY_CMD = os.environ.get("NOTIFY_CMD", "")
GUEST_NOTIFY_CMD = os.environ.get("GUEST_NOTIFY_CMD", "")
TTS_ENTITIES = [e for e in os.environ.get("TTS_ENTITIES", "").split(",") if e]


def _token():
    t = os.environ.get("HA_TOKEN")
    if t:
        return t
    f = Path(os.environ.get("HA_TOKEN_FILE") or HOME / ".ha-token")
    return f.read_text().strip() if f.exists() else ""


def curl(args, timeout=15, stdin=None):
    return subprocess.run(["/usr/bin/curl", "-s", "-m", str(timeout), *args], input=stdin,
                          capture_output=True, timeout=timeout + 5).stdout


def ha(path, payload=None, timeout=15):
    """GET (or POST with a JSON payload) against the Home Assistant REST API. Returns raw bytes."""
    args = ["-H", "@-"]  # auth header goes through stdin, never through the process list
    if payload is not None:
        args += ["-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(payload)]
    return curl(args + [HA_URL + path], timeout, stdin=f"Authorization: Bearer {_token()}\n".encode())


def state(entity):
    return json.loads(ha("states/" + entity))["state"]


def sensors():
    """All sensor.<PREFIX>_* states as {name_without_prefix: state}."""
    out, p = {}, f"sensor.{PREFIX}_"
    for s in json.loads(ha("states")):
        if s["entity_id"].startswith(p):
            out[s["entity_id"][len(p):]] = s["state"]
    return out


def grab_frame(ip=None, port=8080, timeout=8):
    """Read one JPEG frame from the printer's MJPEG stream. Returns bytes or None."""
    try:
        s = socket.create_connection((ip or PRINTER_IP, port), 4)
        s.settimeout(5)
        s.sendall(b"GET /mjpeg HTTP/1.0\r\nHost: printer\r\n\r\n")
        buf, t0 = b"", time.time()
        while len(buf) < 3_000_000 and time.time() - t0 < timeout:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            a = buf.find(b"\xff\xd8")
            if a >= 0:
                b = buf.find(b"\xff\xd9", a)
                if b >= 0:
                    s.close()
                    return buf[a:b + 2]
        s.close()
    except OSError:
        pass
    return None


def notify(level, title, text):
    """Alert the admin. `level` is red/yellow/info. Falls back to stdout when NOTIFY_CMD is unset."""
    if NOTIFY_CMD:
        subprocess.run([*shlex.split(NOTIFY_CMD), level, title, text], timeout=30)
    else:
        print(f"[{level}] {title}: {text}")


def guest(title, text):
    """Optional second channel for family/housemates (never includes file names)."""
    if GUEST_NOTIFY_CMD:
        subprocess.run([*shlex.split(GUEST_NOTIFY_CMD), title, text], timeout=60)


def say(text):
    """Text-to-speech on Home Assistant notify entities, only between 06:00 and 22:00."""
    if not TTS_ENTITIES or not 6 <= time.localtime().tm_hour < 22:
        return False
    ok = False
    for e in TTS_ENTITIES:
        r = ha("services/notify/send_message", {"entity_id": e, "message": text}, timeout=8)
        ok = ok or bool(r)
    return ok
