"""Persistent memory in MongoDB Atlas.

Collections:
  observations — facts the agent noticed. Evidence is REQUIRED: a write with no
                 evidence pointer raises. An observation without evidence is a
                 hallucination, and we make that structural, not conventional.
  beliefs      — the agent's current working model of a user, one doc per
                 (user, key). Revisable; sources link back to observations.
  runs         — one doc per deliberation: what was read, concluded, done.
  state        — cursors (last event id seen per user) and other pointers.

The LangGraph checkpointer writes its own collections alongside these.
"""
from __future__ import annotations

import datetime
import os

from pymongo import DESCENDING, MongoClient


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Memory:
    def __init__(self, uri: str | None = None, db_name: str = "reach_agent"):
        self.client = MongoClient(uri or os.environ["MONGODB_URI"])
        self.db = self.client[db_name]

    # ── observations ────────────────────────────────────────────────
    def add_observation(self, user: str, fact: str, evidence: list[str]):
        if not evidence:
            raise ValueError(
                f"observation for {user!r} has no evidence — refusing to store: {fact!r}"
            )
        doc = {"user": user, "fact": fact, "evidence": evidence, "ts": utcnow()}
        return self.db.observations.insert_one(doc).inserted_id

    def recent_observations(self, user: str, k: int = 10) -> list[dict]:
        return list(
            self.db.observations.find({"user": user}).sort("ts", DESCENDING).limit(k)
        )

    # ── beliefs ─────────────────────────────────────────────────────
    def upsert_belief(self, user: str, key: str, text: str, sources: list):
        self.db.beliefs.update_one(
            {"user": user, "key": key},
            {"$set": {"text": text, "updated_at": utcnow()},
             "$addToSet": {"sources": {"$each": sources}}},
            upsert=True,
        )

    def beliefs_for(self, user: str, k: int = 8) -> list[dict]:
        return list(
            self.db.beliefs.find({"user": user})
            .sort("updated_at", DESCENDING).limit(k)
        )

    # ── runs ────────────────────────────────────────────────────────
    def start_run(self, user: str, thread: str, trigger: str) -> str:
        # Returned as str — run ids travel through LangGraph state, and the
        # checkpointer can't serialize raw ObjectIds.
        return str(self.db.runs.insert_one(
            {"user": user, "thread": thread, "trigger": trigger,
             "started_at": utcnow(), "status": "running"}
        ).inserted_id)

    def finish_run(self, run_id: str | None, summary: str,
                   actions: list[dict], proposals: list[dict]):
        if not run_id:
            return
        from bson import ObjectId
        self.db.runs.update_one(
            {"_id": ObjectId(run_id)},
            {"$set": {"status": "done", "finished_at": utcnow(),
                      "summary": summary, "actions": actions, "proposals": proposals}},
        )

    def last_run(self, user: str) -> dict | None:
        return self.db.runs.find_one({"user": user, "status": "done"},
                                     sort=[("finished_at", DESCENDING)])

    # ── cursors ─────────────────────────────────────────────────────
    def get_cursor(self, user: str) -> dict:
        return self.db.state.find_one({"_id": f"cursor:{user}"}) or {}

    def set_cursor(self, user: str, **fields):
        self.db.state.update_one(
            {"_id": f"cursor:{user}"}, {"$set": {**fields, "updated_at": utcnow()}},
            upsert=True,
        )
