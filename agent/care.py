"""Care sweep — the agent reaches out FIRST.

    .venv/bin/python agent/care.py hank_hikes            # tone decided from state
    .venv/bin/python agent/care.py elena_reads --tone encourage
    .venv/bin/python agent/care.py alice_runner --tone celebrate

For the given user it reads their STORY (Mongo), their dossier, and live REACH
state, then composes a personal check-in that cites why they started and what
their history shows — never a generic "you missed your post." Delivery, both
in-app surfaces at once:
  1. an unprompted agent message in their Ridge chat thread (they open the
     chat — the agent already texted them), and
  2. a bell notification (NotificationLog → the app's activity page).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import subprocess
import sys

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "voice"))
load_dotenv(ROOT / ".env")

from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

import chat_engine  # noqa: E402 — reuse the per-user thread + Mongo client
from agent.reach_tools import ReachTools  # noqa: E402
from agent.run import REACH_REPO, load_dossier  # noqa: E402


async def gather(username: str) -> dict:
    client = MultiServerMCPClient({"reach": {
        "command": sys.executable, "args": [str(ROOT / "mcp-server" / "server.py")],
        "transport": "stdio"}})
    t = ReachTools(await client.get_tools())
    await t.login(username)
    return {"streak": await t.streak_state(username),
            "challenges": await t.list_challenges(username)}


def compose(username: str, tone: str, story: dict, dossier: dict,
            state: dict) -> dict:
    llm = ChatOpenAI(
        model=os.environ.get("OPENROUTER_PLANNER_MODEL", "anthropic/claude-sonnet-4.5"),
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1", temperature=0.4)
    prompt = (
        "You are Ridge, an accountability agent reaching out UNPROMPTED — the "
        "user did not message you. Write a check-in for them.\n"
        f"TONE: {tone} (auto = judge from the state: slipping → encourage, "
        "strong week → celebrate).\n"
        "Rules: 2-4 sentences. Cite WHY they started (their goals/why below) — "
        "that is the heart of the message. Include at least one dated or "
        "numbered specific from their story or state. Warm and direct, their "
        "register (see dossier), never call yourself a coach, never guilt-trip. "
        "End with ONE small concrete ask or acknowledgment.\n"
        'Reply ONLY JSON: {"title": "≤50 chars, no emoji spam", "message": str}\n\n'
        f"DOSSIER:\n{json.dumps(dossier, default=str)[:1800]}\n\n"
        f"THEIR STORY (agent's long-term memory):\n"
        f"{json.dumps({k: v for k, v in story.items() if k != '_id'}, default=str)[:3500]}\n\n"
        f"LIVE STATE:\n{json.dumps(state, default=str)[:2500]}"
    )
    from agent.loop import _parse_json
    return _parse_json(llm.invoke(prompt).content)


def deliver(username: str, title: str, message: str) -> None:
    # Surface 1: the Ridge chat thread — the agent has already texted them.
    chat_engine.append_turn("assistant", message, source="care", who=username)
    # Surface 2: the bell — write the NotificationLog row as an IN-APP
    # delivery (was_sent=True). The FCM path would mark it unsent locally
    # and the activity page filters unsent rows out.
    py = REACH_REPO / "backend" / "venv" / "bin" / "python"
    code = (
        "from notifications.models import NotificationLog\n"
        "from django.contrib.auth import get_user_model\n"
        f"u = get_user_model().objects.get(username={username!r})\n"
        "NotificationLog.objects.create(user=u, notification_type='admin_message',"
        f" title={title[:80]!r}, body={message[:900]!r}, was_sent=True)\n"
        "print('bell row created')")
    done = subprocess.run([str(py), "manage.py", "shell", "-c", code],
                          cwd=REACH_REPO / "backend", capture_output=True,
                          text=True, timeout=60)
    tail = (done.stdout or done.stderr or "").strip().splitlines()[-1:]
    print(f"bell: exit {done.returncode} {' '.join(tail)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--tone", choices=["auto", "encourage", "celebrate"],
                    default="auto")
    args = ap.parse_args()
    u = args.username

    story = chat_engine._MEM.db.stories.find_one({"_id": u}) or {}
    dossier = load_dossier(u)
    state = asyncio.run(gather(u))
    out = compose(u, args.tone, story, dossier, state)
    title, message = out.get("title", "Ridge checked in"), out["message"]
    print(f"→ {u}\nTITLE: {title}\nMESSAGE: {message}\n")
    deliver(u, title, message)
    print("chat thread: appended (source=care) — opens with the message waiting")


if __name__ == "__main__":
    main()
