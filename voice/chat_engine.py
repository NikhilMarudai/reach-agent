"""Text chat with Ridge — OpenRouter tool-calling over the same MCP seam.

The chat model gets the persona + live context blob and four tools. Writes go
through B's MCP server exactly like the loop's — same gate, same audit.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys

from openai import OpenAI

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.reach_tools import ReachTools  # noqa: E402
from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402

HISTORY: list[dict] = []  # user/assistant text turns only

TOOLS = [
    {"type": "function", "function": {
        "name": "get_state",
        "description": "Live REACH state for a user: streak/lives/penalties + their challenges.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"}}, "required": ["username"]}}},
    {"type": "function", "function": {
        "name": "create_challenge",
        "description": "Create a REACH challenge (the user is auto-enrolled as creator). "
                       "Use for structural fixes: small recovery challenges named in the user's voice.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "proof_description": {"type": "string"},
            "challenge_type": {"type": "string", "enum": [
                "fitness", "studies", "lifestyle", "diet", "hobbies", "professional"]},
            "frequency": {"type": "string", "enum": ["daily", "weekly"]},
            "duration_days": {"type": "integer"}},
            "required": ["username", "name", "description", "proof_description"]}}},
    {"type": "function", "function": {
        "name": "nudge",
        "description": "Nudge a fellow participant (≤140 chars). REACH enforces quotas/blocks.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"},
            "challenge_id": {"type": "integer"},
            "recipient_user_id": {"type": "integer"},
            "custom_message": {"type": "string"}},
            "required": ["username", "challenge_id", "recipient_user_id"]}}},
    {"type": "function", "function": {
        "name": "run_deliberation",
        "description": "Fire a FULL background deliberation for a user (re-read world, update "
                       "memory, adapt plan, comment in-app). Takes ~1 min; the feed updates.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"}}, "required": ["username"]}}},
]


def _system() -> str:
    persona = (ROOT / "voice" / "persona.md").read_text()
    blob_path = ROOT / "demo" / "context_blob.json"
    blob = blob_path.read_text() if blob_path.exists() else "{}"
    return (persona
            + "\n\nMODE: text chat. Be concise — 1-4 sentences unless asked for more. "
              "Cite evidence (dates, names) from the live context. Use tools to act "
              "or to fetch fresh state; never invent state. Primary user: carla_codes."
            + "\n\n## LIVE CONTEXT\n" + blob)


async def _exec(name: str, args: dict):
    if name == "run_deliberation":
        subprocess.Popen(
            [str(ROOT / ".venv/bin/python"), str(ROOT / "agent/run.py"),
             "--user", args["username"]], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"status": "started", "note": "~1 minute; the feed will update"}
    client = MultiServerMCPClient({"reach": {
        "command": sys.executable, "args": [str(ROOT / "mcp-server" / "server.py")],
        "transport": "stdio"}})
    t = ReachTools(await client.get_tools())
    if name == "get_state":
        u = args["username"]
        return {"streak": await t.streak_state(u),
                "challenges": await t.list_challenges(u)}
    if name == "create_challenge":
        return await t.create_challenge(**args)
    if name == "nudge":
        return await t.nudge(**args)
    return {"error": f"unknown tool {name}"}


def chat(user_msg: str) -> dict:
    HISTORY.append({"role": "user", "content": user_msg})
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"])
    model = os.environ.get("OPENROUTER_PLANNER_MODEL", "anthropic/claude-sonnet-4.5")
    msgs = [{"role": "system", "content": _system()}] + HISTORY[-20:]
    events: list[dict] = []
    for _ in range(5):
        r = client.chat.completions.create(model=model, messages=msgs,
                                           tools=TOOLS, temperature=0.3)
        m = r.choices[0].message
        if not m.tool_calls:
            HISTORY.append({"role": "assistant", "content": m.content or ""})
            return {"reply": m.content or "", "events": events}
        msgs.append({"role": "assistant", "content": m.content,
                     "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
        for tc in m.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {}
            try:
                out = asyncio.run(_exec(tc.function.name, args))
            except Exception as e:  # noqa: BLE001 — surface, don't crash the chat
                out = {"error": str(e)}
            events.append({"tool": tc.function.name, "args": args,
                           "result": json.loads(json.dumps(out, default=str))
                           if isinstance(out, (dict, list)) else str(out)[:300]})
            msgs.append({"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps(out, default=str)[:2500]})
    HISTORY.append({"role": "assistant", "content": "(hit tool-loop limit)"})
    return {"reply": "(hit tool-loop limit)", "events": events}
