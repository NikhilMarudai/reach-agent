"""The single seam between the agent and B's MCP server.

Every tool-call shape lives HERE and nowhere else, so when B's server lands,
reconciling argument names is a one-file edit. Tools arrive as LangChain tool
objects from langchain-mcp-adapters (async-only — always ainvoke).

If a tool is missing or a call fails, we degrade to a recorded error instead of
crashing — the loop must survive a half-built server during integration.
"""
from __future__ import annotations

import json
from typing import Any


class ReachTools:
    def __init__(self, tools: list):
        self.by_name = {t.name: t for t in tools}
        self.errors: list[str] = []

    async def _call(self, name: str, args: dict) -> Any:
        tool = self.by_name.get(name)
        if tool is None:
            self.errors.append(f"tool missing: {name}")
            return None
        try:
            out = await tool.ainvoke(args)
            if isinstance(out, str):
                try:
                    return json.loads(out)
                except (ValueError, TypeError):
                    return out
            return out
        except Exception as e:  # noqa: BLE001 — integration resilience
            self.errors.append(f"{name}({args}) failed: {e}")
            return None

    # ── reads ───────────────────────────────────────────────────────
    async def streak_state(self, username: str):
        return await self._call("get_streak_state", {"username": username})

    async def list_posts(self, username: str, challenge_id: int):
        return await self._call(
            "list_posts", {"username": username, "challenge_id": challenge_id})

    async def get_events(self, username: str, since_id: int | None = None):
        args: dict = {"username": username}
        if since_id is not None:
            args["since_id"] = since_id
        return await self._call("get_events", args)

    async def list_challenges(self, username: str):
        return await self._call("list_challenges", {"username": username})

    # ── writes (the server enforces DRY_RUN + the cap) ──────────────
    async def nudge(self, username: str, challenge_id: int, target_username: str,
                    message: str):
        return await self._call("nudge", {
            "username": username, "challenge_id": challenge_id,
            "target_username": target_username, "message": message})
