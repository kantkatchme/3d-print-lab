# 3d-print-lab

A few small tools I built so my 3D printer can look after itself a bit.

I run an **Elegoo Centauri Carbon 2** in a household where several people send prints to the same machine. After a print came loose and wrecked my toolhead, I wanted something that watches the printer when I can't. So now Claude looks at the camera, a queue keeps the peace between us, and a script tells me when we're about to run out of black PLA.

It's all plain Python and `curl`. No framework, no database, nothing to host. It talks to your printer through [Home Assistant](https://www.home-assistant.io/).

## What's in the box

| | What it does |
|---|---|
| **`printguard/guard.py`** | The AI print guard. Every couple of minutes it grabs a camera frame, adds live print data (layer, temperatures, progress) and asks Claude whether the print still looks healthy: spaghetti, a part that came loose, blobs on the nozzle, an empty bed. Verdict is **GREEN / YELLOW / RED**. A fast model does the first look, and a stronger one gives a second opinion before anyone gets woken up. |
| `printguard/cam_watch.py` | Watchdog for the camera stream. A guard that can't see is worse than none, so it tells you when the picture is gone mid-print. |
| `printguard/status_watch.py` | Announces *finished*, *paused* and *error*. Optional text-to-speech on tablets around the house. |
| **`queue/print_queue.py`** | A print queue for a shared printer. Drop G-code on a USB stick, import it, reorder, group, mark as printed. Files move to `finished prints/` on the stick as you go. It never deletes anything. |
| **`filament/filament_demand.py`** | Reads grams and material from the G-code headers of everything in the queue and compares them with your spool stock. Warns when the queue needs more than you have (plus a 10 % margin). |
| `docs/` | Notes from the build: how failure detection evolved, the printer's MQTT topics, and driving Autodesk Fusion with Claude (MCP) to model parts. |

## How the print guard thinks

- It only ever says **RED** for a clear finding. No suspicion means GREEN, light stringing is YELLOW.
- RED needs **two checks in a row** before it alerts, and the second check comes quickly.
- It can **pause the print for you**, but only if you create the flag file `autopause` in the state folder. Leave it off for the first week and see how often it's right.
- Every YELLOW/RED frame is saved, so you can review what it saw.
- The file name from the printer is treated as untrusted text, and Claude only gets the `Read` tool, no shell, no MCP servers.

Each check costs a little money. The history file records tokens and USD per verdict, so you can see for yourself.

## Setup

You need: a printer in Home Assistant ([Elegoo CC2 integration](https://github.com/danielcherubini/elegoo-homeassistant) via HACS), Python 3.9+, `curl`, and the [Claude Code](https://claude.com/claude-code) CLI logged in (the guard calls `claude -p`).

```bash
git clone https://github.com/kantkatchme/3d-print-lab && cd 3d-print-lab
cp .env.example .env        # fill in your values
set -a; . ./.env; set +a    # load them
python3 printguard/guard.py # one manual run while a print is going
```

Then schedule it. Every 2 minutes for `guard.py` and `cam_watch.py`, every minute for `status_watch.py`, via launchd (macOS) or cron. Example cron line:

```
*/2 * * * * cd /path/to/3d-print-lab && set -a && . ./.env && set +a && python3 printguard/guard.py
```

### Not the same printer?

Entity names come from the integration. If yours differ, change `PRINTER_PREFIX` (and `STATUS_SENSOR` / `ERROR_SENSOR`, which are localised: a German Home Assistant calls them `druckstatus` / `druckfehler`, an English one `print_status` / `print_error`). The camera grab expects an MJPEG stream at `http://<printer>:8080/mjpeg`, which is what the CC2 offers.

## Security notes

- **Secrets stay out of the repo.** The Home Assistant token comes from `HA_TOKEN` or `~/.ha-token`, never from code. It is passed to `curl` via stdin, so it doesn't show up in `ps`.
- **Keep your Home Assistant off the public internet** (or behind a VPN like Tailscale). A long-lived token is full access to your house.
- Camera frames and print data are sent to Anthropic's API for the check. If the chamber camera can see anything you don't want leaving the house, don't run the guard.
- `.env`, G-code and images are git-ignored. Check `git status` before you push your own changes.

## Contributing

It started as a private tool, so some corners are still rough, and I've only tested it on one printer. Issues and pull requests are welcome, especially for other printers, other camera types, and prompts that catch more failure modes with fewer false alarms.

## License

MIT, see [LICENSE](LICENSE).
