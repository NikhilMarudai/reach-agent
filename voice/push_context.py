"""Push the latest context blob into Ridge's brain.

    .venv/bin/python voice/push_context.py

Composes persona.md + demo/context_blob.json into Ridge's system prompt via
the ElevenLabs agent PATCH API. Run after any agent deliberation so the next
voice conversation knows the current world. Prints status only — never keys.
"""
import json
import os
import pathlib
import sys
import urllib.request

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
api_key = os.environ.get("ELEVENLABS_API_KEY")
if not agent_id or not api_key:
    sys.exit("missing ELEVENLABS_AGENT_ID / ELEVENLABS_API_KEY in .env")

persona = (ROOT / "voice" / "persona.md").read_text()
blob_path = ROOT / "demo" / "context_blob.json"
blob = blob_path.read_text() if blob_path.exists() else "{}"

# Voice works OFF the chat: recent transcript (text + voice) rides along so a
# voice session continues the same conversation the chat page shows.
convo = ""
try:
    sys.path.insert(0, str(ROOT))
    from agent.memory import Memory
    rows = list(Memory().db.chat_messages.find({}, {"_id": 0})
                .sort("ts", -1).limit(12))
    convo = "\n".join(f"{m['role']}{' (voice)' if m.get('source')=='voice' else ''}: "
                      f"{(m.get('content') or '')[:280]}" for m in reversed(rows))
except Exception:  # noqa: BLE001 — context push must not die on a read
    pass

prompt = (persona + "\n\n## LIVE CONTEXT — the current true state, cite it\n"
          + blob
          + ("\n\n## RECENT CONVERSATION (text + voice — CONTINUE it, "
             "don't restart it)\n" + convo if convo else ""))

body = json.dumps({"conversation_config": {"agent": {"prompt": {"prompt": prompt}}}})
req = urllib.request.Request(
    f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
    data=body.encode(), method="PATCH",
    headers={"xi-api-key": api_key, "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        print(f"Ridge updated: HTTP {r.status} · prompt {len(prompt)} chars "
              f"· blob from {blob_path.name}")
except urllib.error.HTTPError as e:
    print(f"PATCH failed: HTTP {e.code} — {e.read()[:200]!r}")
    sys.exit(1)
