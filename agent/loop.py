"""The deliberation loop: observe → remember → decide → act → brief.

Five explicit nodes, one linear pass, checkpointed to MongoDB after every node —
kill the process anywhere and the same command resumes from the last completed
node. Two LLM calls per run (remember + decide), everything else deterministic.

The agent PROPOSES more than it does: the only write it executes itself is a
peer nudge. Plan changes are written to memory and spoken — the human commits.
It never posts proof and never verifies; peers do that. That boundary is the
product, not a hackathon shortcut.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
from typing import Any, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from .memory import Memory
from .reach_tools import ReachTools

ACT_ALLOWLIST = {"nudge", "create_challenge"}
MAX_ACTIONS = 3


class AgentState(TypedDict, total=False):
    username: str
    user_id: int
    challenge_id: int
    dossier: dict
    streak: Any
    posts: Any
    events: Any
    new_observations: list[dict]
    beliefs: list[dict]
    decision: dict
    actions_taken: list[dict]
    blob: dict
    run_id: Any
    tool_errors: list[str]


def _llm(kind: str) -> ChatOpenAI:
    model = os.environ.get(
        "OPENROUTER_PLANNER_MODEL" if kind == "planner" else "OPENROUTER_FAST_MODEL",
        "anthropic/claude-sonnet-4.5" if kind == "planner" else "openai/gpt-4o-mini",
    )
    return ChatOpenAI(
        model=model,
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
        temperature=0.2,
    )


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def build_graph(memory: Memory, tools: ReachTools, checkpointer):
    async def observe(state: AgentState) -> AgentState:
        u = state["username"]
        profile = await tools.login(u)  # warms the token cache; gives numeric id
        user_id = profile.get("id") if isinstance(profile, dict) else None
        cursor = memory.get_cursor(u)
        streak = await tools.streak_state(u)
        posts = await tools.list_posts(u, state["challenge_id"])
        events = await tools.get_events(user_id, cursor.get("last_seen_iso", ""))
        return {"streak": streak, "posts": posts, "events": events,
                "user_id": user_id, "tool_errors": list(tools.errors)}

    async def remember(state: AgentState) -> AgentState:
        u = state["username"]
        prior = memory.beliefs_for(u)
        today = datetime.datetime.now().strftime("%Y-%m-%d (%A)")
        prompt = (
            f"TODAY is {today}.\n"
            "You extract durable observations about a person's accountability "
            "behavior from their app data. Every fact MUST contain at least one "
            "concrete date, number, or username taken from the data — a fact "
            "without one is worthless and must be dropped. Look hard for "
            "day-of-week patterns in post dates and gaps (e.g. 'both breaks fell "
            "on week edges: Sunday 8/09, Monday 8/03'), and note who verified "
            "what, by name. Reply ONLY with JSON:\n"
            '{"observations": [{"fact": str, "evidence": [str, ...]}],\n'
            ' "beliefs": [{"key": str, "text": str}]}\n'
            "Max 4 observations. Evidence entries MUST quote ids/dates that appear "
            "in the data below (e.g. 'post:123', 'date:2026-08-09'). An observation "
            "you cannot evidence, you must not make.\n"
            "beliefs is REQUIRED: 1-3 entries distilling the durable pattern (key = "
            "a stable slug like 'posting_rhythm' or 'failure_mode', text = one "
            "sentence). Update an existing key when the evidence shifts it.\n\n"
            f"PRIOR BELIEFS:\n{json.dumps(prior, default=str)[:2000]}\n\n"
            f"STREAK:\n{json.dumps(state.get('streak'), default=str)[:2000]}\n\n"
            f"POSTS:\n{json.dumps(state.get('posts'), default=str)[:4000]}\n\n"
            f"EVENTS:\n{json.dumps(state.get('events'), default=str)[:3000]}"
        )
        out = _parse_json((await _llm("planner").ainvoke(prompt)).content)
        new_obs = []
        for o in out.get("observations", []):
            try:
                oid = memory.add_observation(u, o["fact"], o.get("evidence", []))
                new_obs.append({**o, "id": str(oid)})
            except (ValueError, KeyError):
                continue  # evidence-free observations are dropped, by design
        for b in out.get("beliefs", []):
            if b.get("key") and b.get("text"):
                memory.upsert_belief(u, b["key"], b["text"],
                                     [o["id"] for o in new_obs])
        return {"new_observations": new_obs, "beliefs": memory.beliefs_for(u)}

    async def decide(state: AgentState) -> AgentState:
        d = state.get("dossier", {})
        today = datetime.datetime.now().strftime("%Y-%m-%d (%A)")
        prompt = (
            f"TODAY is {today}. "
            "If a post was verified by a peer since your last run, acknowledge it "
            "— name the verifier and the date; that verification is your ground "
            "truth. State your single strongest dated pattern from memory as a "
            "discovery (e.g. 'both breaks fell on week edges'). "
            "You are an accountability agent for one person. You NEVER verify "
            "their proof (their peers do), you NEVER post for them, and you never "
            "call yourself a coach. Refer to challenges by NAME, never by id "
            "number — resolve ids against the challenges data before speaking. You may propose plan adjustments and at most "
            f"{MAX_ACTIONS} actions. Executable actions:\n"
            '1. {"tool": "nudge", "args": {"challenge_id": int, "recipient_user_id": '
            'int, "custom_message": str}} (≤140 chars)\n'
            '2. {"tool": "create_challenge", "args": {"name": str, "description": str, '
            '"proof_description": str, "challenge_type": '
            '"fitness|studies|lifestyle|diet|hobbies|professional", "frequency": '
            '"daily", "duration_days": int}} — use ONLY when their pattern warrants a '
            "structural fix: a small recovery challenge (7-14 days), named in their "
            "voice, designed around their failure mode (they are auto-enrolled as "
            "creator). At most one, and only if none of their current challenges "
            "already serves the purpose.\n"
            'Anything else goes in "proposals" (strings). '
            "Speak in the register this person responds to. Reply ONLY with JSON:\n"
            '{"message_to_user": str, "plan": [{"commitment": str, '
            '"adjustment_proposed": str}], "actions": [...], "proposals": [str]}\n\n'
            f"DOSSIER:\n{json.dumps(d, default=str)[:2000]}\n\n"
            f"BELIEFS (your memory of them):\n"
            f"{json.dumps(state.get('beliefs'), default=str)[:3000]}\n\n"
            f"PAST OBSERVATIONS (earlier runs, with evidence):\n"
            f"{json.dumps(memory.recent_observations(state['username'], 8), default=str)[:3000]}\n\n"
            f"TODAY'S STATE:\nstreak={json.dumps(state.get('streak'), default=str)[:1500]}\n"
            f"new_observations={json.dumps(state.get('new_observations'), default=str)[:1500]}"
        )
        decision = _parse_json((await _llm("planner").ainvoke(prompt)).content)
        return {"decision": decision}

    async def act(state: AgentState) -> AgentState:
        taken = []
        for a in state.get("decision", {}).get("actions", [])[:MAX_ACTIONS]:
            tool_name = a.get("tool")
            if tool_name not in ACT_ALLOWLIST:
                continue
            fn = getattr(tools, tool_name)
            try:
                result = await fn(state["username"], **a.get("args", {}))
            except TypeError as exc:  # LLM sent bad args — record, don't crash
                result = {"error": str(exc)}
            taken.append({**a, "result": result})
        return {"actions_taken": taken}

    async def brief(state: AgentState) -> AgentState:
        u, d = state["username"], state.get("dossier", {})
        decision = state.get("decision", {})
        obs = memory.recent_observations(u, k=4)
        blob = {
            "today": datetime.date.today().isoformat(),
            "user": {k: d.get(k) for k in
                     ("username", "name", "age", "communication_style",
                      "psychology", "goals") if k in d} or {"username": u},
            "state": {"challenge_id": state["challenge_id"],
                      "streak": state.get("streak")},
            "observations": [{"fact": o["fact"], "evidence": o["evidence"]}
                             for o in obs],
            "plan": decision.get("plan", []),
            "message_to_user": decision.get("message_to_user", ""),
        }
        # Speak INSIDE the app: land the message as a comment on the user's
        # latest post, prefixed as their agent. The server's write gate decides
        # whether it actually posts (dry-run returns would_do, nothing lands).
        msg = decision.get("message_to_user", "")
        posts = state.get("posts") or []
        mine = [p for p in posts if isinstance(p, dict)
                and p.get("user") == u and p.get("id")]
        if mine and msg:
            latest = max(mine, key=lambda p: (str(p.get("post_date") or ""), p["id"]))
            blob["spoke_in_app"] = await tools.comment_on_post(
                u, latest["id"], f"🤖 Ridge (accountability agent): {msg}")

        memory.set_cursor(u, last_seen_iso=datetime.datetime.now(
            datetime.timezone.utc).isoformat())
        memory.finish_run(
            state.get("run_id"),
            summary=decision.get("message_to_user", "")[:500],
            actions=state.get("actions_taken", []),
            proposals=decision.get("proposals", []),
        )
        return {"blob": blob, "tool_errors": list(tools.errors)}

    def paced(fn):
        # AGENT_NODE_DELAY=<seconds> slows the loop — deterministic ctrl-C window
        # for the kill-and-resume beat, and stage pacing. Default 0.
        async def wrapped(state):
            delay = float(os.environ.get("AGENT_NODE_DELAY", "0"))
            if delay:
                await asyncio.sleep(delay)
            return await fn(state)
        wrapped.__name__ = fn.__name__
        return wrapped

    g = StateGraph(AgentState)
    for name, fn in [("observe", observe), ("remember", remember),
                     ("decide", decide), ("act", act), ("brief", brief)]:
        g.add_node(name, paced(fn))
    g.set_entry_point("observe")
    g.add_edge("observe", "remember")
    g.add_edge("remember", "decide")
    g.add_edge("decide", "act")
    g.add_edge("act", "brief")
    g.add_edge("brief", END)
    return g.compile(checkpointer=checkpointer)
