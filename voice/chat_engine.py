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

from agent.memory import Memory  # noqa: E402
from agent.reach_tools import ReachTools  # noqa: E402
from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402

# One conversation, persisted in Atlas — text and voice both read/write it.
# Kill this process, reopen the page: the conversation survives. No cold start.
_MEM = Memory()


def append_turn(role: str, content: str, source: str = "text",
                events: list | None = None, who: str = "carla_codes") -> None:
    _MEM.db.chat_messages.insert_one({
        "role": role, "content": content, "source": source, "who": who,
        "events": events or [], "ts": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc)})


def history(limit: int = 200, who: str | None = None) -> list[dict]:
    # Per-user threads: each primary user has their OWN conversation with the
    # agent (a shared one let rich's chatter hijack alice's questions).
    q = {"who": who} if who else {}
    rows = list(_MEM.db.chat_messages.find(q, {"_id": 0})
                .sort("ts", -1).limit(limit))
    return list(reversed(rows))

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
        "name": "care_sweep",
        "description": "Reach out to a user UNPROMPTED: read their story + live "
                       "state, compose a check-in citing why they started, and "
                       "deliver it to their Ridge chat thread AND their in-app "
                       "bell. Use when asked to check on / encourage / "
                       "congratulate someone, or when they're missing posts.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"},
            "tone": {"type": "string", "enum": ["auto", "encourage", "celebrate"],
                     "description": "auto decides from their state"}},
            "required": ["username"]}}},
    {"type": "function", "function": {
        "name": "run_deliberation",
        "description": "Fire a FULL background deliberation for a user (re-read world, update "
                       "memory, adapt plan, comment in-app). Takes ~1 min; the feed updates.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"}}, "required": ["username"]}}},
]


def _system(primary: str) -> str:
    persona = (ROOT / "voice" / "persona.md").read_text()
    blob_path = ROOT / "demo" / "context_blob.json"
    blob = blob_path.read_text() if blob_path.exists() else "{}"
    # The blob is from the LAST deliberation — it may be about a different
    # user. Attaching it for the wrong primary makes the model answer from
    # someone else's life (verified live: alice asked, got rich's penalties).
    try:
        blob_user = (json.loads(blob).get("user") or {}).get("username")
    except ValueError:
        blob_user = None
    if blob_user != primary:
        blob = ('{"note": "no cached context for this user — call get_state '
                'before answering anything about their state"}')
    return (persona
            + "\n\nMODE: text chat. Be concise — 1-4 sentences unless asked for more. "
              "Cite evidence (dates, names) from the live context. Use tools to act "
              "or to fetch fresh state; never invent state. "
              f"Primary user: {primary} — 'me'/'my' in their messages means "
              f"{primary}; default every tool call to them unless another user "
              "is named. "
              "NEVER refer to a challenge by its number — always use its NAME "
              "(map ids via the challenges list in get_state; fetch it if you only "
              "have an id). Same for people: display names, not usernames, when known."
            + "\n\n## LIVE CONTEXT\n" + blob)


async def _exec(name: str, args: dict):
    if name == "care_sweep":
        cmd = [str(ROOT / ".venv/bin/python"), str(ROOT / "agent/care.py"),
               args["username"]]
        if args.get("tone") and args["tone"] != "auto":
            cmd += ["--tone", args["tone"]]
        done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              timeout=300)
        lines = [ln for ln in (done.stdout or "").splitlines()
                 if ln.startswith(("TITLE:", "MESSAGE:", "bell:"))]
        return {"delivered": done.returncode == 0, "detail": lines or
                (done.stderr or "")[-300:]}
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


def chat(user_msg: str, username: str | None = None) -> dict:
    primary = (username or "carla_codes").strip()
    append_turn("user", user_msg, source="text", who=primary)
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"])
    model = os.environ.get("OPENROUTER_PLANNER_MODEL", "anthropic/claude-sonnet-4.5")
    window = [{"role": m["role"], "content": m["content"]}
              for m in history(24, who=primary) if m["role"] in ("user", "assistant")
              and m.get("content")]
    msgs = [{"role": "system", "content": _system(primary)}] + window
    events: list[dict] = []
    for _ in range(5):
        r = client.chat.completions.create(model=model, messages=msgs,
                                           tools=TOOLS, temperature=0.3)
        m = r.choices[0].message
        if not m.tool_calls:
            append_turn("assistant", m.content or "", source="text",
                        events=events, who=primary)
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
