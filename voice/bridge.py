"""Voice→action bridge — http://localhost:8030

Serves the talk page, mints ElevenLabs signed URLs, and runs deliberations
that Ridge triggers by voice. After each deliberation it re-pushes context,
so Ridge's next turn knows what it just did.

    .venv/bin/python voice/bridge.py
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
PY = str(ROOT / ".venv" / "bin" / "python")
AGENT = os.environ["ELEVENLABS_AGENT_ID"]
KEY = os.environ["ELEVENLABS_API_KEY"]
CHALLENGE = {"carla_codes": "398", "alice_runner": "398"}  # default 398/env


def signed_url() -> str:
    r = urllib.request.Request(
        "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"
        f"?agent_id={AGENT}", headers={"xi-api-key": KEY})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read())["signed_url"]


def deliberate(username: str) -> None:
    """Run the loop, then refresh Ridge's brain. Called on a worker thread."""
    args = [PY, str(ROOT / "agent" / "run.py"), "--user", username]
    ch = CHALLENGE.get(username) or os.environ.get("DEMO_CHALLENGE_ID")
    if ch:
        args += ["--challenge", str(ch)]
    print(f"[bridge] deliberating for {username} …", flush=True)
    done = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          timeout=600)
    tail = (done.stdout or "").strip().splitlines()[-3:]
    print(f"[bridge] loop exit {done.returncode}: {' | '.join(tail)}", flush=True)
    subprocess.run([PY, str(ROOT / "voice" / "push_context.py")], cwd=ROOT,
                   capture_output=True, timeout=60)
    print("[bridge] Ridge context refreshed", flush=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/signed-url"):
            try:
                self._send(200, json.dumps({"signed_url": signed_url()}).encode())
            except Exception as e:  # noqa: BLE001
                self._send(502, json.dumps({"error": str(e)}).encode())
        elif self.path.startswith("/resolve"):  # imessage handle -> username
            import urllib.parse as _up
            import chat_engine
            qh = (_up.parse_qs(_up.urlparse(self.path).query).get("handle")
                  or [""])[0]
            row = chat_engine._MEM.db.imessage_links.find_one(
                {"handle": qh}, {"_id": 0})
            self._send(200, json.dumps(row or {}).encode())
        elif self.path.startswith("/history"):
            import urllib.parse as _up
            import chat_engine
            q = _up.parse_qs(_up.urlparse(self.path).query)
            who = (q.get("username") or [None])[0]
            self._send(200, json.dumps(chat_engine.history(who=who),
                                       default=str).encode())
        elif self.path.startswith("/talk"):  # voice mode (parked, still works)
            self._send(200, (ROOT / "voice" / "talk.html").read_bytes(),
                       "text/html; charset=utf-8")
        else:  # default: text chat
            self._send(200, (ROOT / "voice" / "chat.html").read_bytes(),
                       "text/html; charset=utf-8")

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/chat":
            import chat_engine  # lazy; voice/ is sys.path[0] when run as script
            try:
                out = chat_engine.chat((body.get("message") or "").strip(),
                                       username=body.get("username"))
                self._send(200, json.dumps(out, default=str).encode())
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}).encode())
            return
        if self.path == "/simulate":  # care sweep for the acting user
            import chat_engine
            try:
                out = asyncio.run(chat_engine._exec("care_sweep", {
                    "username": (body.get("username") or "carla_codes").strip(),
                    "tone": body.get("tone") or "auto"}))
                self._send(200, json.dumps(out, default=str).encode())
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}).encode())
            return
        if self.path == "/link":  # bind an iMessage handle to a REACH account
            import chat_engine
            handle = (body.get("handle") or "").strip()
            username = (body.get("username") or "").strip()
            if not handle or not username:
                return self._send(400, b'{"error": "handle and username required"}')
            chat_engine._MEM.db.imessage_links.update_one(
                {"handle": handle}, {"$set": {"username": username}}, upsert=True)
            return self._send(200, json.dumps(
                {"linked": handle, "username": username}).encode())
        if self.path == "/transcript":  # voice lines join the same conversation
            import chat_engine
            role = "user" if body.get("role") == "user" else "assistant"
            content = (body.get("content") or "").strip()
            if content:
                chat_engine.append_turn(role, content, source="voice")
            return self._send(200, b'{"ok": true}')
        if self.path != "/act":
            return self._send(404, b"{}")
        username = (body.get("username") or "carla_codes").strip()
        threading.Thread(target=deliberate, args=(username,), daemon=True).start()
        self._send(200, json.dumps({
            "status": "started", "username": username,
            "note": "deliberation running — the app updates in ~1 minute"}).encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("bridge → http://localhost:8030  (talk page + /act + /signed-url)")
    ThreadingHTTPServer(("127.0.0.1", 8030), Handler).serve_forever()
