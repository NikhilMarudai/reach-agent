"""Register the client tool `trigger_deliberation` on Ridge (merge, not clobber).

GET the agent, append/replace the tool in its prompt config, PATCH back.
    .venv/bin/python voice/register_tool.py
"""
import json
import os
import pathlib
import sys
import urllib.request

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
AGENT = os.environ.get("ELEVENLABS_AGENT_ID")
KEY = os.environ.get("ELEVENLABS_API_KEY")
if not AGENT or not KEY:
    sys.exit("missing ELEVENLABS_AGENT_ID / ELEVENLABS_API_KEY")

BASE = "https://api.elevenlabs.io/v1/convai/agents"
TOOL = {
    "type": "client",
    "name": "trigger_deliberation",
    "description": (
        "Run a full deliberation for the user RIGHT NOW: re-read their REACH "
        "world, update memory, adapt the plan, and act in the app (comment, "
        "possibly a recovery challenge). Call this when the user asks you to "
        "act, replan, rebuild their week, or check on someone. Takes ~1 minute; "
        "tell them to watch their feed."),
    "parameters": {
        "type": "object",
        "properties": {"username": {
            "type": "string",
            "description": "REACH username to deliberate for, e.g. carla_codes"}},
        "required": ["username"],
    },
}


def req(method: str, url: str, body: dict | None = None):
    r = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read())


agent = req("GET", f"{BASE}/{AGENT}")
prompt = agent["conversation_config"]["agent"]["prompt"]
tools = [t for t in prompt.get("tools", []) if t.get("name") != TOOL["name"]]
tools.append(TOOL)
prompt["tools"] = tools
req("PATCH", f"{BASE}/{AGENT}",
    {"conversation_config": {"agent": {"prompt": prompt}}})
print(f"tool registered: trigger_deliberation (agent tools now: "
      f"{[t.get('name') for t in tools]})")
