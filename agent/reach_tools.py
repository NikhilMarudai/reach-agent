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
            # Adapters may return MCP content blocks: [{'type':'text','text':...}]
            if isinstance(out, list) and out and isinstance(out[0], dict) \
                    and out[0].get("type") == "text":
                out = "".join(b.get("text", "") for b in out)
            if isinstance(out, str):
                try:
                    return json.loads(out)
                except (ValueError, TypeError):
                    return out
            return out
        except Exception as e:  # noqa: BLE001 — integration resilience
            self.errors.append(f"{name}({args}) failed: {e}")
            return None

    # ── reads (signatures reconciled against B's server, 14:20) ─────
    async def login(self, username: str):
        return await self._call("login_persona", {"username": username})

    async def streak_state(self, username: str):
        return await self._call("get_streak_state", {"username": username})

    async def list_posts(self, username: str, challenge_id: int):
        return await self._call(
            "list_posts", {"username": username, "challenge_id": challenge_id})

    async def get_events(self, user_id: int | None = None, since: str = ""):
        # Admin-scoped on B's side: numeric user_id + ISO `since`, no username.
        args: dict = {"page_size": 40}
        if user_id is not None:
            args["user_id"] = user_id
        if since:
            args["since"] = since
        return await self._call("get_events", args)

    async def list_challenges(self, username: str):
        return await self._call("list_challenges", {"username": username})

    # ── writes (the server enforces the dry-run gate + the cap) ─────
    async def nudge(self, username: str, challenge_id: int,
                    recipient_user_id: int, custom_message: str = ""):
        return await self._call("nudge", {
            "username": username, "challenge_id": challenge_id,
            "recipient_user_id": recipient_user_id,
            "custom_message": custom_message[:140]})

    async def comment_on_post(self, username: str, post_id: int, content: str):
        return await self._call("comment_on_post", {
            "username": username, "post_id": post_id, "content": content[:990]})

    async def create_challenge(self, username: str, name: str, description: str,
                               proof_description: str, challenge_type: str = "fitness",
                               frequency: str = "daily", duration_days: int = 14):
        return await self._call("create_challenge", {
            "username": username, "name": name[:100], "description": description,
            "proof_description": proof_description, "challenge_type": challenge_type,
            "frequency": frequency, "duration_days": duration_days})
