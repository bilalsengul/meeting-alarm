#!/usr/bin/env python3
"""One-time Google Calendar (read-only) consent for meeting-alarm.

Usage: python3 auth.py [--client-secret PATH] [--email HINT] [--port 8898]
                       [--timeout 600] [--language en|tr]

Needs a Google OAuth "desktop app" client (client_secret.json, see the README).
Writes credentials.json into $MEETING_ALARM_HOME (default ~/.meeting-alarm).
"""
import argparse
import json
import os
import shutil
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from strings import t

SCOPES = "https://www.googleapis.com/auth/calendar.readonly"
BASE = os.environ.get("MEETING_ALARM_HOME") or os.path.expanduser("~/.meeting-alarm")
CLIENT_SECRET = os.path.join(BASE, "client_secret.json")
CRED = os.path.join(BASE, "credentials.json")


def private_chmod(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # not supported on every filesystem (e.g. Windows)


def default_language() -> str:
    try:
        with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
            return json.load(f).get("language", "en")
    except (OSError, ValueError, AttributeError):
        return "en"


def wait_for_code(port: int, timeout: int, lang: str) -> str | None:
    got: dict[str, str] = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q:
                got["code"] = q["code"][0]
                body = t(lang, "auth_page_ok").encode("utf-8")
            else:
                body = t(lang, "auth_page_nocode").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    srv = HTTPServer(("127.0.0.1", port), H)
    srv.timeout = 5
    deadline = time.time() + timeout
    while "code" not in got and time.time() < deadline:
        srv.handle_request()
    srv.server_close()
    return got.get("code")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-secret", help="path to the downloaded client_secret.json (copied into the data dir)")
    ap.add_argument("--email", help="optional login_hint for the Google account picker")
    ap.add_argument("--port", type=int, default=8898)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--language", choices=["en", "tr"], default=None)
    a = ap.parse_args()
    lang = a.language or default_language()
    os.makedirs(BASE, exist_ok=True)
    if a.client_secret:
        shutil.copyfile(a.client_secret, CLIENT_SECRET)
        private_chmod(CLIENT_SECRET)
    if not os.path.exists(CLIENT_SECRET):
        print(f"ERROR {CLIENT_SECRET} not found. Follow the 'Google OAuth client' section of the README, "
              "then run: python3 auth.py --client-secret /path/to/client_secret.json", flush=True)
        return 1
    with open(CLIENT_SECRET, encoding="utf-8") as f:
        raw = json.load(f)
    keys = raw.get("installed") or raw["web"]
    redirect = f"http://localhost:{a.port}"
    params = {"client_id": keys["client_id"], "redirect_uri": redirect, "response_type": "code",
              "scope": SCOPES, "access_type": "offline", "prompt": "consent"}
    if a.email:
        params["login_hint"] = a.email
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    print(f"CONSENT_URL {url}", flush=True)
    webbrowser.open(url)
    code = wait_for_code(a.port, a.timeout, lang)
    if not code:
        print("TIMEOUT no consent received", flush=True)
        return 2
    body = urllib.parse.urlencode({
        "code": code, "client_id": keys["client_id"], "client_secret": keys["client_secret"],
        "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    tok = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))
    if "refresh_token" not in tok:
        print("ERROR token response has no refresh_token", flush=True)
        return 3
    out = {"refresh_token": tok["refresh_token"], "scope": tok.get("scope", SCOPES)}
    if a.email:
        out["email"] = a.email
    with open(CRED, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    private_chmod(CRED)
    print(f"OK wrote {CRED}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
