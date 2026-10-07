#!/usr/bin/env python3
"""meeting-alarm daemon: polls Google Calendar and throws a full-screen overlay
when a meeting is about to start (heads-up at T-5, guaranteed alarm at T-0).

Usage:
  python3 alarm.py            # daemon loop
  python3 alarm.py --next     # print upcoming events it would alert on
  python3 alarm.py --test     # show a demo overlay for 6 seconds

State/config live in $MEETING_ALARM_HOME (default ~/.meeting-alarm). Stdlib only.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from strings import t

BASE = os.environ.get("MEETING_ALARM_HOME") or os.path.expanduser("~/.meeting-alarm")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(BASE, "client_secret.json")
CRED = os.path.join(BASE, "credentials.json")
STATE = os.path.join(BASE, "state.json")
CONFIG = os.path.join(BASE, "config.json")
OVERLAY = os.path.join(BASE, "overlay")
LOG = os.path.join(BASE, "alarm.log")
SWIFT_SRC = os.path.join(REPO_DIR, "overlay", "overlay.swift")
TK_OVERLAY = os.path.join(REPO_DIR, "overlay", "overlay_tk.py")

DEFAULTS = {
    "lead_minutes": [5, 0],        # heads-up minutes before start; 0 (at start) is always added
    "poll_seconds": 30,
    "snooze_minutes": 2,
    "repeat_after_start_minutes": 2,   # unacknowledged after start: nag every N min
    "repeat_until_minutes_after": 15,  # ...until this long after start
    "skip_declined": True,
    "only_events_with_link_or_guests": False,
    "calendars": "selected",        # "selected" = calendars ticked in Google Calendar UI, or list of ids
    "language": "en",               # "en" or "tr"
}
URL_RE = re.compile(r"https?://(?:[\w.-]*\.)?(?:meet\.google\.com|zoom\.us|teams\.microsoft\.com|calendly\.com|whereby\.com|meet\.jit\.si)[^\s<>\"']*")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def now_ts() -> float:
    return time.time()


def log(msg: str) -> None:
    line = f"{now_utc().astimezone():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def config() -> dict:
    return {**DEFAULTS, **load_json(CONFIG, {})}


_token: dict = {"value": None, "exp": 0.0}


def client_keys() -> dict:
    """OAuth client id/secret from the Google 'desktop app' download (installed or web)."""
    raw = load_json(CLIENT_SECRET, {})
    return raw.get("installed") or raw["web"]


def access_token() -> str:
    if _token["value"] and now_ts() < _token["exp"] - 60:
        return _token["value"]
    keys = client_keys()
    cred = load_json(CRED, {})
    body = urllib.parse.urlencode({
        "client_id": keys["client_id"], "client_secret": keys["client_secret"],
        "refresh_token": cred["refresh_token"], "grant_type": "refresh_token"}).encode()
    tok = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=20))
    _token["value"] = tok["access_token"]
    _token["exp"] = now_ts() + int(tok.get("expires_in", 3600))
    return _token["value"]


def gapi(path: str, params: dict | None = None) -> dict:
    url = "https://www.googleapis.com/calendar/v3/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + access_token()})
    return json.load(urllib.request.urlopen(req, timeout=20))


def calendar_ids(cfg: dict) -> list[str]:
    if isinstance(cfg["calendars"], list):
        return cfg["calendars"]
    items = gapi("users/me/calendarList").get("items", [])
    return [c["id"] for c in items if c.get("selected") and not c.get("deleted")]


def http_only(url: str) -> str:
    """Only http(s) links may reach the browser; invites can carry arbitrary schemes."""
    return url if url.lower().startswith(("https://", "http://")) else ""


def join_link(ev: dict) -> str:
    candidates = [ev.get("hangoutLink") or ""]
    for ep in ev.get("conferenceData", {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video" and ep.get("uri"):
            candidates.append(ep["uri"])
    for field in ("location", "description"):
        m = URL_RE.search(ev.get(field) or "")
        if m:
            candidates.append(m.group(0))
    return next((u for u in map(http_only, candidates) if u), "")


def self_declined(ev: dict) -> bool:
    for a in ev.get("attendees", []):
        if a.get("self") and a.get("responseStatus") == "declined":
            return True
    return False


def upcoming(cfg: dict) -> list[dict]:
    now = now_utc()
    tmin = (now - dt.timedelta(minutes=cfg["repeat_until_minutes_after"] + 1)).isoformat()
    tmax = (now + dt.timedelta(minutes=max(leads(cfg)) + 60)).isoformat()
    out: list[dict] = []
    seen: set[str] = set()
    for cid in calendar_ids(cfg):
        try:
            res = gapi(f"calendars/{urllib.parse.quote(cid, safe='')}/events", {
                "timeMin": tmin, "timeMax": tmax, "singleEvents": "true", "orderBy": "startTime", "maxResults": 50})
        except urllib.error.HTTPError as e:
            log(f"calendar {cid}: HTTP {e.code}")
            continue
        for ev in res.get("items", []):
            start = ev.get("start", {}).get("dateTime")
            if not start or ev.get("status") == "cancelled":
                continue  # all-day or cancelled
            if cfg["skip_declined"] and self_declined(ev):
                continue
            link = join_link(ev)
            if cfg["only_events_with_link_or_guests"] and not link and not ev.get("attendees"):
                continue
            key = ev.get("iCalUID") or ev["id"]
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "key": key + "@" + start,
                "title": ev.get("summary") or t(cfg["language"], "untitled"),
                "start": dt.datetime.fromisoformat(start),
                "link": link,
                "organizer": ev.get("organizer", {}).get("email", ""),
            })
    out.sort(key=lambda e: e["start"])
    return out


def ensure_overlay() -> None:
    """macOS only: (re)compile the Swift overlay when missing or older than its source."""
    if sys.platform != "darwin":
        return
    if os.path.exists(OVERLAY) and os.path.getmtime(OVERLAY) >= os.path.getmtime(SWIFT_SRC):
        return
    compiler = ["xcrun", "swiftc"] if shutil.which("xcrun") else ["swiftc"]
    log("compiling overlay")
    subprocess.run([*compiler, "-O", "-o", OVERLAY, SWIFT_SRC], check=True)


def overlay_cmd() -> list[str]:
    if sys.platform == "darwin":
        return [OVERLAY]
    return [sys.executable, TK_OVERLAY]


def show_overlay(payload: dict) -> int:
    """Run the overlay with the JSON payload on stdin; returns its exit code."""
    ensure_overlay()
    return subprocess.run(overlay_cmd(), input=json.dumps(payload).encode("utf-8")).returncode


def build_payload(ev: dict, minutes_until: float, cfg: dict) -> dict:
    lang = cfg["language"]
    local = ev["start"].astimezone()
    hhmm = f"{local:%H:%M}"
    if minutes_until > 0.5:
        when = t(lang, "starts_in", minutes=int(round(minutes_until)), time=hhmm)
    elif minutes_until > -0.5:
        when = t(lang, "starts_now", time=hhmm)
    else:
        when = t(lang, "in_progress", minutes=int(round(-minutes_until)), time=hhmm)
    if ev["organizer"]:
        when += f"\n{ev['organizer']}"
    return {
        "header": t(lang, "header"),
        "title": ev["title"],
        "subtitle": when,
        "link": ev["link"],
        "join_label": t(lang, "join" if ev["link"] else "ok"),
        "snooze_label": t(lang, "snooze", minutes=cfg["snooze_minutes"]),
        "dismiss_label": t(lang, "dismiss"),
        "hint": t(lang, "hint"),
        "auto_close": 0,
        "sound": True,
    }


def fire(ev: dict, minutes_until: float, state: dict, cfg: dict) -> None:
    is_start = minutes_until <= 0.5  # this alert is the meeting itself, not a heads-up
    log(f"ALERT {ev['title']!r} ({minutes_until:+.1f} min) link={bool(ev['link'])}")
    rc = show_overlay(build_payload(ev, minutes_until, cfg))
    st = state.setdefault(ev["key"], {"fired": [], "snooze_until": 0, "done": False})
    st["last_fire"] = now_ts()
    if rc == 20:
        snooze = cfg["snooze_minutes"] * 60
        to_start = (ev["start"] - now_utc()).total_seconds()
        if 0 < to_start < snooze:
            snooze = to_start  # never snooze past the start: the meeting moment always rings
        st["snooze_until"] = now_ts() + snooze
        log(f"snoozed {snooze / 60:.1f} min")
    elif rc == 10:
        st["done"] = True
        log("joined")
    elif rc == 0 and is_start:
        st["done"] = True
        log("dismissed")
    elif rc == 0:
        log("pre-alert dismissed; start alarm still armed")
    else:
        log(f"overlay failed (exit {rc}); will retry")  # a crash must never silence the alarm


def leads(cfg: dict) -> list[int]:
    # 0 is mandatory: the alert at the exact meeting time must never be configurable away.
    return sorted(set(cfg["lead_minutes"]) | {0}, reverse=True)


def tick(cfg: dict, state: dict) -> None:
    now = now_utc()
    for ev in upcoming(cfg):
        st = state.setdefault(ev["key"], {"fired": [], "snooze_until": 0, "done": False})
        if st["done"]:
            continue
        until = (ev["start"] - now).total_seconds() / 60
        if now_ts() < st.get("snooze_until", 0):
            continue
        if st.get("snooze_until", 0) and now_ts() >= st["snooze_until"]:
            st["snooze_until"] = 0
            if until <= 0.5:
                st["fired"].append(0)
            fire(ev, until, state, cfg)
            return
        for lead in leads(cfg):
            if lead not in st["fired"] and until <= lead:
                st["fired"].append(lead)
                if until >= -cfg["repeat_until_minutes_after"]:
                    fire(ev, until, state, cfg)
                    return
        if until <= 0 and -cfg["repeat_until_minutes_after"] <= until:
            if now_ts() - st.get("last_fire", 0) >= cfg["repeat_after_start_minutes"] * 60:
                fire(ev, until, state, cfg)
                return


def prune(state: dict) -> None:
    yesterday = (now_utc() - dt.timedelta(days=1)).isoformat()
    for k in list(state):
        if "@" not in k or k.split("@", 1)[1] < yesterday:
            state.pop(k, None)


def run_test(cfg: dict) -> int:
    lang = cfg["language"]
    rc = show_overlay({
        "header": t(lang, "header"), "title": t(lang, "test_title"),
        "subtitle": t(lang, "test_subtitle"), "link": "https://meet.google.com/",
        "join_label": t(lang, "join"), "snooze_label": t(lang, "snooze", minutes=cfg["snooze_minutes"]),
        "dismiss_label": t(lang, "dismiss"), "hint": t(lang, "hint"),
        "auto_close": 6, "sound": True})
    print("overlay exit", rc)
    return 0


def print_next(cfg: dict) -> int:
    now = now_utc()
    for ev in upcoming(cfg):
        print(f"{ev['start'].astimezone():%a %H:%M} ({(ev['start'] - now).total_seconds() / 60:+.0f} min) {ev['title']}  {ev['link'] or '-'}")
    return 0


def main() -> int:
    os.makedirs(BASE, exist_ok=True)
    if "--test" in sys.argv:
        return run_test(config())
    if not os.path.exists(CRED) or not os.path.exists(CLIENT_SECRET):
        log(f"missing credentials in {BASE}; follow the setup steps in the README, then run auth.py")
        return 1
    if "--next" in sys.argv:
        return print_next(config())
    log("daemon start")
    state = load_json(STATE, {})
    backoff = 0
    while True:
        try:
            cfg = config()
            tick(cfg, state)
            prune(state)
            save_json(STATE, state)
            backoff = 0
        except (urllib.error.URLError, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            backoff = min(300, backoff + 30)
            log(f"error: {e!r}; retry in {backoff}s")
            time.sleep(backoff)
            continue
        time.sleep(cfg["poll_seconds"])


if __name__ == "__main__":
    raise SystemExit(main())
