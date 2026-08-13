"""Entrypoint. Same command runs AND resumes:

    .venv/bin/python agent/run.py --user carla_codes

If the thread has an interrupted run (you killed it mid-deliberation), the same
command resumes from the last MongoDB checkpoint. --fresh forces a new thread.
Writes the voice context blob to demo/context_blob.json on completion.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402
from langgraph.checkpoint.mongodb import MongoDBSaver  # noqa: E402
# (0.4.0's MongoDBSaver implements aput/aget_tuple itself — async-safe, no aio module)

from agent.loop import build_graph  # noqa: E402
from agent.memory import Memory  # noqa: E402
from agent.reach_tools import ReachTools  # noqa: E402

REACH_REPO = pathlib.Path(os.environ.get(
    "REACH_REPO", pathlib.Path.home() / "Desktop/Code/REACH/social_media_project"))
DOSSIERS = REACH_REPO / "backend/challenges/fixtures/demo_personas.json"


def load_dossier(username: str) -> dict:
    try:
        personas = json.loads(DOSSIERS.read_text())
        for p in personas if isinstance(personas, list) else personas.get("personas", []):
            if p.get("username") == username:
                return p
    except (OSError, ValueError):
        pass
    return {"username": username}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--challenge", type=int, default=int(os.environ.get("DEMO_CHALLENGE_ID", "398")))
    ap.add_argument("--thread", default=None)
    ap.add_argument("--fresh", action="store_true", help="force a brand-new thread")
    args = ap.parse_args()
    thread = args.thread or f"demo-{args.user}"
    if args.fresh:
        thread = f"{thread}-{os.urandom(3).hex()}"

    client = MultiServerMCPClient({
        "reach": {
            "command": sys.executable,
            "args": [str(ROOT / "mcp-server" / "server.py")],
            "transport": "stdio",
        }
    })
    tools = ReachTools(await client.get_tools())
    memory = Memory()

    with MongoDBSaver.from_conn_string(
            os.environ["MONGODB_URI"], db_name="reach_agent_checkpoints") as saver:
        graph = build_graph(memory, tools, saver)
        config = {"configurable": {"thread_id": thread}}

        snap = await graph.aget_state(config)
        if snap and snap.next:
            print(f"[resume] thread {thread!r} was interrupted at {snap.next} — resuming")
            result = await graph.ainvoke(None, config)
        else:
            run_id = memory.start_run(args.user, thread, trigger="manual")
            init = {"username": args.user, "challenge_id": args.challenge,
                    "dossier": load_dossier(args.user), "run_id": run_id}
            result = await graph.ainvoke(init, config)

    blob = result.get("blob", {})
    out = ROOT / "demo" / "context_blob.json"
    out.write_text(json.dumps(blob, indent=2, default=str))
    print(f"\n=== {args.user} · thread {thread} ===")
    print(blob.get("message_to_user", "(no message)"))
    if result.get("tool_errors"):
        print(f"\n[tool errors: {result['tool_errors']}]", file=sys.stderr)
    print(f"\nblob → {out}")


if __name__ == "__main__":
    asyncio.run(main())
