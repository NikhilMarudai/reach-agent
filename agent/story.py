"""The story layer — one coherent, recreatable document per user.

O's memory.py stores ATOMS (observations/beliefs/runs). This module derives the
MOLECULE: a single readable story of who the user is and what they've been up
to, built ONLY from the REACH API (so it can be recreated or refreshed at any
time), then upserted to MongoDB:

  stories          one doc per username (_id = username), always the latest
  story_snapshots  append-only copy per refresh → run-1 vs run-2 diffs on stage

Run (NOTE the interpreter — reuses the MCP server's HTTP layer, whose venv
pins mcp<2; the root .venv can't import it):

    mcp-server/.venv/bin/python agent/story.py alice_runner
    mcp-server/.venv/bin/python agent/story.py alice_runner --json   # stdout JSON only

O's loop integrates via subprocess (--json) — a process boundary, same as MCP.
Narrative paragraph: OpenRouter if OPENROUTER_API_KEY is set, deterministic
template fallback otherwise. Everything else is deterministic extraction.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp-server"))
import server  # the MCP server's HTTP layer — one source of HTTP truth  # noqa: E402


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── extraction (deterministic, API-only) ─────────────────────────────────────

def extract(username: str) -> dict:
    profile = server.login_persona(username)
    if "error" in profile:
        raise SystemExit(f"no such persona: {username}")
    uid = profile["id"]

    # Her world: fetch posts ONCE and group by each post's own challenge FK.
    # (Never scan per-challenge with a query param: `?challenge=` is silently
    # ignored by the API — the real param is challenge_id — and a wrong param
    # returns EVERYTHING, triple-counting. Grouping by the post's own field is
    # immune to that whole bug class.)
    raw_challenges = server._items(server._get("/api/challenges/", username))
    names = {c.get("id"): c.get("name") for c in raw_challenges}

    import requests as _rq
    posts, seen, url = [], set(), f"{server.BASE}/api/challenges/challenge-posts/"
    headers = {"Authorization": f"Token {server._token(username)}"}
    for _page in range(8):
        r = _rq.get(url, headers=headers, timeout=15)
        if not r.ok:
            break
        payload = r.json()
        for p in server._items(payload):
            pu = p.get("user") or {}
            if (pu.get("id") == uid) and p["id"] not in seen:
                seen.add(p["id"])
                posts.append({**p, "_challenge": names.get(p.get("challenge"),
                                                          f"challenge {p.get('challenge')}")})
        url = payload.get("next") if isinstance(payload, dict) else None
        if not url:
            break

    by_ch = Counter(p.get("challenge") for p in posts)
    commitments = [{
        "id": c.get("id"), "name": c.get("name"),
        "frequency": c.get("frequency"), "status": c.get("status"),
        "role": "creator" if (c.get("creator") or {}).get("id") == uid else "member",
        "my_posts": by_ch.get(c.get("id"), 0),
    } for c in raw_challenges
        if by_ch.get(c.get("id")) or (c.get("creator") or {}).get("id") == uid]
    visible = raw_challenges

    streaks = server.get_streak_state(username)
    lives = (streaks.get("streak_lives") or {})
    events = server.get_events(user_id=uid, page_size=40)
    ev_rows = (events.get("results") or []) if isinstance(events, dict) else []

    verified = [p for p in posts if p.get("is_verified")]
    hours = Counter()
    weekend = weekday = 0
    for p in posts:
        ts = p.get("created_at") or ""
        if len(ts) >= 13:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                hours[dt.hour] += 1
                weekend += dt.weekday() >= 5
                weekday += dt.weekday() < 5
            except ValueError:
                pass

    today = date.today().isoformat()
    posted_today = any(p.get("post_date") == today for p in posts)

    patterns = []
    if hours:
        top = hours.most_common(1)[0][0]
        bucket = "early mornings" if top < 9 else ("daytime" if top < 17 else "evenings")
        patterns.append(f"usually posts in the {bucket} (~{top:02d}:00)")
    if weekday + weekend >= 6:
        wk_rate = weekday / max(weekday + weekend, 1)
        if wk_rate > 0.85:
            patterns.append("weekday-driven — weekends are the weak spot")
        elif wk_rate < 0.55:
            patterns.append("keeps showing up on weekends")
    if posts:
        vr = len(verified) / len(posts)
        patterns.append(f"peers verify {round(vr * 100)}% of their proof")

    timeline = sorted(
        [{"t": p.get("post_date") or "", "what": f"posted proof in “{p['_challenge']}”"
          + (" — verified by peers" if p.get("is_verified") else " — awaiting votes"),
          "ref": f"post:{p['id']}"} for p in posts],
        key=lambda e: e["t"], reverse=True)[:8]
    for e in ev_rows[:6]:
        ch = e.get("channel", "")
        if ch.startswith(("life.", "streak.", "participant.")):
            timeline.append({"t": (e.get("created_at") or "")[:10],
                             "what": ch, "ref": f"event:{e.get('id')}"})
    timeline = sorted(timeline, key=lambda e: e["t"], reverse=True)[:10]

    open_loops = []
    if not posted_today:
        open_loops.append("no proof posted today yet")
    pending = [p for p in posts if not p.get("is_verified")]
    if pending:
        open_loops.append(f"{len(pending)} post(s) awaiting peer verification")
    if isinstance(lives.get("lives_remaining"), int) and lives["lives_remaining"] == 0:
        open_loops.append("ZERO streak lives left — next miss breaks the streak")

    return {
        "_id": username,
        "kind": "user_story",
        "as_of": _utcnow(),
        "profile": {"id": uid, "name": profile.get("name"), "bio": profile.get("bio")},
        "headline": f"{len(posts)} proofs across {len(commitments)} commitment(s) · "
                    f"{round(len(verified) / len(posts) * 100) if posts else 0}% peer-verified · "
                    f"{lives.get('lives_remaining', '?')} lives banked",
        "narrative": "",  # filled by narrate()
        "commitments": commitments,
        "evidence": {
            "posts_total": len(posts), "verified": len(verified),
            "pending": len(pending), "streak_lives": lives,
            "penalties": len(streaks.get("penalties") or []),
        },
        "patterns": patterns,
        "recent_timeline": timeline,
        "open_loops": open_loops,
        "sources": {"challenges_scanned": len(visible),
                    "events_scanned": len(ev_rows),
                    "last_event_id": ev_rows[0].get("id") if ev_rows else None},
    }


# ── narrative (LLM with deterministic fallback) ──────────────────────────────

def narrate(story: dict) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        try:
            import requests
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": os.environ.get("STORY_MODEL", "anthropic/claude-haiku-4.5"),
                    "messages": [{
                        "role": "user",
                        "content": "Write ONE tight paragraph (max 90 words), plain voice, "
                                   "telling this person's accountability story: who they are, what "
                                   "they've committed to, how it's actually going per the verified "
                                   "evidence, and what's at stake right now. No bullet points, no "
                                   "hype. Facts:\n" + json.dumps(
                                       {k: story[k] for k in
                                        ("profile", "headline", "commitments", "evidence",
                                         "patterns", "open_loops")}, default=str),
                    }],
                    "max_tokens": 220,
                },
                timeout=30,
            )
            if r.ok:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
    p = story["profile"]
    return (f"{p.get('name') or story['_id']} is working {len(story['commitments'])} "
            f"commitment(s). {story['headline']}. "
            + (" ".join(story["patterns"]) + ". " if story["patterns"] else "")
            + ("Open: " + "; ".join(story["open_loops"]) + "." if story["open_loops"] else "All caught up."))


# ── storage (Mongo: latest + snapshot) ───────────────────────────────────────

def store(story: dict) -> dict:
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("STORY_DB", "reach_agent")]
    prev = db.stories.find_one({"_id": story["_id"]})
    if prev:
        prev.pop("_id")
        db.story_snapshots.insert_one({"username": story["_id"], "snapshot_of": prev.get("as_of"),
                                       "taken_at": _utcnow(), "story": prev})
    db.stories.replace_one({"_id": story["_id"]}, story, upsert=True)
    return {"stories": db.stories.count_documents({}),
            "snapshots": db.story_snapshots.count_documents({"username": story["_id"]})}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    username = args[0] if args else "alice_runner"
    story = extract(username)
    story["narrative"] = narrate(story)
    counts = store(story)
    if "--json" in sys.argv:
        print(json.dumps(story, default=str))
    else:
        print(json.dumps(story, indent=2, default=str))
        print(f"\nstored: stories={counts['stories']} snapshots({username})={counts['snapshots']}",
              file=sys.stderr)
