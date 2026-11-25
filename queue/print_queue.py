#!/usr/bin/env python3
"""Print queue for a shared printer (several people, one machine).

State: <state dir>/queue/queue.json, copies of the G-code under <state dir>/queue/files/<person>/<project>/.
Import from a USB stick laid out as  Planned Prints/<person>/<project>/*.gcode : new files are copied in,
the existing order is kept. Files on the stick move along with their status
(Planned Prints -> finished prints / delayed prints). Nothing is ever deleted:
"removed" only hides an entry, "delayed" parks it outside the queue.

Several processes may write the same queue.json (a lock file keeps them apart).

  python3 print_queue.py import [source]   # default: /Volumes/*/Prints/Planned Prints
"""
import contextlib
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import threading
from pathlib import Path

QDIR = Path(os.environ.get("PRINTLAB_STATE") or Path.home() / ".printlab") / "queue"
FILES = QDIR / "files"
STATE = QDIR / "queue.json"
STATUS = ("waiting", "printing", "printed", "removed", "delayed")
_LOCK = threading.Lock()
# Folder on the stick per status; finished and delayed jobs move there (moved, never deleted)
USB_DIRS = {"waiting": "Planned Prints", "printing": "Planned Prints", "printed": "finished prints", "delayed": "delayed prints"}


@contextlib.contextmanager
def _lock():
    with _LOCK:
        QDIR.mkdir(parents=True, exist_ok=True)
        with open(QDIR / ".lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield


def _load():
    try:
        d = json.loads(STATE.read_text())
        if isinstance(d.get("items"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"items": [], "updated": None}


def _save(d):
    QDIR.mkdir(parents=True, exist_ok=True)
    d["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


def parse_name(fn):
    """ECC2_0.4_<title>_<material> _0.2_1d2h32m.gcode -> title, material, layer height, minutes."""
    stem = re.sub(r"\.gcode$", "", fn, flags=re.I)
    m = re.fullmatch(r"(?:ECC?2?_)?(?P<nozzle>\d\.\d)_(?P<title>.+)_(?P<mat>Elegoo [^_]*?) ?_(?P<h>\d\.\d+)_(?P<time>[\dhdms]+)", stem)
    if not m:
        return {"title": stem, "material": "", "layer": "", "duration_min": None}
    mins = sum(int(n) * {"d": 1440, "h": 60, "m": 1, "s": 0}[u] for n, u in re.findall(r"(\d+)([dhms])", m.group("time")))
    if "s" in m.group("time") and not ("m" in m.group("time") or "h" in m.group("time")):
        mins = 1
    return {"title": re.sub(r"^obj_\d+_|\.step$", "", m.group("title").replace("+", " ").strip()),
            "material": m.group("mat").replace("Elegoo ", "").strip(), "layer": m.group("h"), "duration_min": mins}


def find_source():
    hits = sorted(glob.glob("/Volumes/*/Prints/Planned Prints"))
    return Path(hits[0]) if hits else None


def import_usb(src=None):
    src = Path(src) if src else find_source()
    if not src or not src.is_dir():
        return {"ok": False, "error": "USB stick / source not found"}
    with _lock():
        d = _load()
        known = {i["file"] for i in d["items"]}
        new = copied = 0
        for f in sorted(src.rglob("*.gcode")):
            if f.name.startswith("._"):  # macOS resource forks
                continue
            rel = f.relative_to(src)
            if len(rel.parts) < 3:
                person, project = (rel.parts[0] if len(rel.parts) == 2 else "?"), ""
            else:
                person, project = rel.parts[0].strip(), rel.parts[1].strip()
            key = "/".join([person, project, f.name])
            target = FILES / person / project / f.name
            if not target.exists() or target.stat().st_size != f.stat().st_size:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                copied += 1
            if key in known:
                continue
            d["items"].append({"id": hashlib.sha1(key.encode()).hexdigest()[:10], "file": key, "person": person, "project": project,
                               "status": "waiting", "group": "", "note": "", "added": dt.date.today().isoformat(), **parse_name(f.name)})
            new += 1
        _save(d)
        usb = usb_sync(d["items"])
    return {"ok": True, "new": new, "copied": copied, "total": len(d["items"]), "usb": usb}


def _under(root, parts):
    """Folder below `root` for `parts`; names are compared ignoring stray spaces ("Anna " on the stick)."""
    cur = root
    for part in parts:
        hit = next((c for c in sorted(cur.iterdir()) if c.is_dir() and c.name.strip() == part.strip()), None) if cur.is_dir() else None
        cur = hit or (cur / part)
    return cur


def usb_sync(items, dry=False):
    """Moves files on the stick into the folder matching their status. No stick: no-op.
    Nothing is overwritten or deleted; if the target already exists it is counted as a conflict."""
    src = find_source()
    if not src:
        return {"stick": False, "moved": 0, "conflicts": 0}
    base, moved, conflicts, plan = src.parent, 0, 0, []
    roots = {n: base / n for n in set(USB_DIRS.values())}
    for i in items:
        want = USB_DIRS.get(i.get("status"))
        if not want:
            continue
        parts, name = [x for x in (i["person"], i["project"]) if x], Path(i["file"]).name
        found = next((_under(r, parts) / name for n, r in roots.items() if n != want and (_under(r, parts) / name).is_file()), None)
        if not found:
            continue
        dst = _under(roots[want], parts) / name
        if dst.exists():
            conflicts += 1
            continue
        plan.append((str(found.relative_to(base)), str(dst.relative_to(base))))
        if not dry:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(found), str(dst))
                moved += 1
            except OSError:
                conflicts += 1
    return {"stick": True, "moved": moved if not dry else len(plan), "conflicts": conflicts, "plan": plan if dry else None}


def queue_get():
    d = _load()
    return {"ok": True, "items": [i for i in d["items"] if i.get("status") != "removed"], "updated": d.get("updated")}


def _normalize(items):
    """Groups stay together (at the spot of their first waiting member); the current print goes first."""
    out, seen = [], set()
    for i in items:
        g = i.get("group") or ""
        if i["status"] != "waiting" or not g:
            out.append(i)
        elif g not in seen:
            seen.add(g)
            out.extend(x for x in items if x["status"] == "waiting" and x.get("group") == g)
    items[:] = sorted(out, key=lambda x: x["status"] != "printing")


def queue_update(body):
    """action: order (ids = order of the waiting ones, optional groups {id: name}), status (id, status), note (id, note),
    rename (id, title), rename_group (group, name), group (ids, name), ungroup (ids or group),
    current (id = what is on the printer right now; null = nothing)."""
    a = body.get("action")
    with _lock():
        d = _load()
        items = d["items"]
        byid = {i["id"]: i for i in items}
        if a == "order":
            ids = [x for x in body.get("ids", []) if x in byid]
            for k, g in (body.get("groups") or {}).items():
                if k in byid:
                    byid[k]["group"] = str(g or "")[:40].strip()
            rest = [i for i in items if i["id"] not in set(ids)]
            items[:] = [byid[x] for x in ids] + [i for i in rest if i["status"] == "waiting"] + [i for i in rest if i["status"] != "waiting"]
        elif a == "status" and body.get("id") in byid and body.get("status") in STATUS:
            byid[body["id"]]["status"] = body["status"]
            if body["status"] == "printed":
                byid[body["id"]]["finished"] = dt.date.today().isoformat()
        elif a == "note" and body.get("id") in byid:
            byid[body["id"]]["note"] = str(body.get("note", ""))[:200]
        elif a == "rename" and body.get("id") in byid:
            title = " ".join(str(body.get("title", "")).split())[:80]
            if not title:
                return {"ok": False, "error": "name must not be empty"}
            byid[body["id"]]["title"] = title
        elif a == "rename_group":
            old, new = str(body.get("group", "")), " ".join(str(body.get("name", "")).split())[:40]
            if not old or not new:
                return {"ok": False, "error": "name must not be empty"}
            for i in items:
                if i.get("group") == old:
                    i["group"] = new
        elif a == "group":
            ids = [x for x in body.get("ids", []) if x in byid]
            name = str(body.get("name", "")).strip()[:40]
            if not ids or not name:
                return {"ok": False, "error": "a name and at least one file are required"}
            first = min(items.index(byid[x]) for x in ids)
            for x in ids:
                byid[x]["group"] = name
            sel = [i for i in items if i["id"] in set(ids)]
            items[:] = [i for i in items[:first] if i["id"] not in set(ids)] + sel + [i for i in items[first:] if i["id"] not in set(ids)]
        elif a == "ungroup":
            for i in items:
                if i["id"] in (body.get("ids") or []) or (body.get("group") and i.get("group") == body["group"]):
                    i["group"] = ""
        elif a == "current":
            cid = body.get("id")
            if cid is not None and (cid not in byid or byid[cid]["status"] == "removed"):
                return {"ok": False, "error": "unknown entry"}
            for i in items:
                if i["status"] == "printing":
                    i["status"] = "waiting"
            if cid:
                byid[cid]["status"] = "printing"
                byid[cid]["started"] = dt.datetime.now().isoformat(timespec="minutes")
        else:
            return {"ok": False, "error": "invalid action"}
        _normalize(items)
        _save(d)
        usb = usb_sync(items) if a in ("status", "current") else None
    r = queue_get()
    if usb:
        r["usb"] = usb
    return r


def queue_public():
    """Housemate view: current print + waiting jobs, no file paths. `before_min` = summed print time ahead of the job."""
    its = queue_get()["items"]
    cur = next((i for i in its if i["status"] == "printing"), None)
    out, acc = [], 0
    for n, i in enumerate([x for x in its if x["status"] == "waiting"], 1):
        out.append({"pos": n, "title": i["title"], "person": i["person"], "project": i["project"], "group": i.get("group", ""),
                    "material": i["material"], "duration_min": i["duration_min"], "before_min": acc})
        acc += i["duration_min"] or 0
    current = {k: cur.get(k) for k in ("title", "person", "project", "group", "material", "duration_min")} if cur else None
    return {"current": current, "items": out, "total_min": acc}


def file_path(item_id):
    for i in _load()["items"]:
        if i["id"] == item_id:
            p = FILES / i["person"] / i["project"] / Path(i["file"]).name
            return p if p.exists() else None
    return None


if __name__ == "__main__":
    if sys.argv[1:2] == ["import"]:
        print(json.dumps(import_usb(sys.argv[2] if len(sys.argv) > 2 else None), ensure_ascii=False))
    else:
        print(__doc__)
