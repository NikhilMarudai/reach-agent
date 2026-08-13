"""iMessage ⇄ agent bridge. RUN THIS IN YOUR OWN TERMINAL (it needs your
Terminal's Full Disk Access grant to read chat.db; the agent stack doesn't).

    IMSG_HANDLE="+15551234567" IMSG_USERNAME=carla_codes \
        python3 voice/imessage_bridge.py

Only messages from IMSG_HANDLE are answered — never anyone else. Replies go
through Messages.app (first send pops one Automation permission dialog).
Each text becomes a turn in the SAME per-user Mongo thread the chat page and
voice use — iMessage is just another client of one conversation.

Known limit: on newer macOS some messages store text only in attributedBody;
those arrive as None and are skipped (plain texts usually populate text).
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HANDLE = os.environ.get("IMSG_HANDLE")
BRIDGE = os.environ.get("AGENT_BRIDGE", "http://localhost:8030")
DB = os.path.expanduser("~/Library/Messages/chat.db")

if not HANDLE:
    sys.exit("set IMSG_HANDLE to your iMessage handle (e.g. +15551234567)")


def resolve_username() -> str:
    """The handle→account link made in the app's chat page ('log in')."""
    try:
        with urllib.request.urlopen(
                f"{BRIDGE}/resolve?handle={urllib.parse.quote(HANDLE)}",
                timeout=10) as r:
            row = json.loads(r.read())
        if row.get("username"):
            return row["username"]
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("IMSG_USERNAME", "carla_codes")


def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def send_imessage(text: str) -> None:
    script = (
        'tell application "Messages"\n'
        '  set s to 1st account whose service type = iMessage\n'
        f'  send {json.dumps(text)} to participant {json.dumps(HANDLE)} of s\n'
        'end tell')
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30)


def ask_agent(text: str) -> str:
    req = urllib.request.Request(
        f"{BRIDGE}/chat", method="POST",
        data=json.dumps({"message": text,
                         "username": resolve_username()}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read())
    reply = out.get("reply") or out.get("error") or "(no reply)"
    tools = ", ".join(e["tool"] for e in out.get("events", []))
    return f"{reply}\n[did: {tools}]" if tools else reply


last = q("SELECT COALESCE(MAX(ROWID),0) FROM message")[0][0]
print(f"listening for iMessages from {HANDLE} → acting as {resolve_username()} "
      f"(via /resolve; starting after ROWID {last})")

while True:
    time.sleep(2)
    try:
        rows = q(
            "SELECT m.ROWID, m.text FROM message m "
            "JOIN handle h ON m.handle_id = h.ROWID "
            "WHERE m.is_from_me = 0 AND m.ROWID > ? AND h.id = ? "
            "ORDER BY m.ROWID", (last, HANDLE))
    except sqlite3.OperationalError as e:
        print(f"chat.db read failed ({e}) — does THIS terminal have "
              "Full Disk Access?")
        time.sleep(8)
        continue
    for rowid, text in rows:
        last = max(last, rowid)
        if not text or not text.strip():
            continue
        print(f"← {text[:80]}")
        try:
            reply = ask_agent(text.strip())
        except Exception as e:  # noqa: BLE001
            reply = f"(agent error: {e})"
        send_imessage(reply[:1400])
        print(f"→ {reply[:80]}")
