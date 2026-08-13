"""REACH MCP server — built live at the MongoDB Persistent Context Sprint Hackathon, 2026-08-13.

Thin, guarded wrappers over REACH's public HTTP API (localhost dev instance).
REACH itself is a pre-existing product; this server only speaks to it over HTTP,
through the same endpoints the iOS app uses. Endpoint ground truth:
REACH ref/features/AGENT_SURFACE.md (private repo).

Transport: stdio. NEVER print to stdout in this file — it corrupts the MCP framing.

Safety rails (hackathon-grade, deliberate):
  * REACH_DRY_RUN=1 (default): write tools return what they WOULD do, no HTTP.
  * REACH_WRITE_CAP (default 10): hard cap on real writes per process.
  * Tokens are cached in-process and never returned to the model.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# .env lives at the repo root (reach-agent/.env, gitignored).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE = os.environ.get("REACH_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
ADMIN_TOKEN = os.environ.get("REACH_ADMIN_TOKEN", "")
DRY_RUN = os.environ.get("REACH_DRY_RUN", "1") not in ("0", "false", "False")
WRITE_CAP = int(os.environ.get("REACH_WRITE_CAP", "10"))

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[reach-mcp] %(message)s")
log = logging.getLogger("reach-mcp")

mcp = FastMCP("reach")

_tokens: dict[str, str] = {}   # username -> auth_token (never leaves the process)
_writes_done = 0

# 1x1 PNG fallback if Pillow is unavailable.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ── plumbing ──────────────────────────────────────────────────────────────────

def _token(username: str) -> str:
    """dev_login token, cached. Localhost-only by REACH's own design."""
    if username not in _tokens:
        r = requests.get(f"{BASE}/api/users/dev_login/", params={"username": username}, timeout=15)
        r.raise_for_status()
        _tokens[username] = r.json()["auth_token"]
    return _tokens[username]


def _get(path: str, username: str | None = None, admin: bool = False, **params) -> dict | list:
    """GET with auth. Trailing slash enforced (the #1 silent failure)."""
    assert path.endswith("/"), f"REACH URLs need a trailing slash: {path}"
    headers = {}
    if admin:
        if not ADMIN_TOKEN:
            return {"error": "REACH_ADMIN_TOKEN not set in reach-agent/.env"}
        headers["Authorization"] = f"Token {ADMIN_TOKEN}"
    elif username:
        headers["Authorization"] = f"Token {_token(username)}"
    r = requests.get(f"{BASE}{path}", headers=headers, params=params or None, timeout=15)
    if not r.ok:
        return {"error": r.status_code, "body": r.text[:300]}
    return r.json()


def _write_gate(tool: str, summary: dict) -> dict | None:
    """Dry-run + cap gate. Returns a dict to short-circuit with, or None to proceed."""
    global _writes_done
    if DRY_RUN:
        return {"dry_run": True, "tool": tool, "would_do": summary,
                "hint": "set REACH_DRY_RUN=0 in reach-agent/.env to arm writes"}
    if _writes_done >= WRITE_CAP:
        return {"error": f"write cap reached ({WRITE_CAP}/process) — refusing further writes"}
    _writes_done += 1
    return None


def _post(path: str, username: str, json_body: dict | None = None, **kw) -> dict:
    assert path.endswith("/")
    headers = {"Authorization": f"Token {_token(username)}"}
    r = requests.post(f"{BASE}{path}", headers=headers, json=json_body, timeout=30, **kw)
    if not r.ok:
        return {"error": r.status_code, "body": r.text[:300]}
    return r.json()


def _challenge_brief(c: dict) -> dict:
    return {k: c.get(k) for k in (
        "id", "name", "challenge_type", "frequency", "status", "start_date",
        "end_date", "duration_days", "is_hard_mode", "privacy") if k in c}


def _post_brief(p: dict) -> dict:
    user = p.get("user") or {}
    return {
        "id": p.get("id"),
        "challenge": p.get("challenge"),
        "user": user.get("username") if isinstance(user, dict) else user,
        "post_date": p.get("post_date"),
        "is_verified": p.get("is_verified"),
        "content": (p.get("content") or "")[:200],
        "votes": [
            {"by": (v.get("verified_by") or {}).get("username"), "approved": v.get("is_approved")}
            for v in (p.get("verifications") or [])
        ],
        "media_count": len(p.get("media_items") or []),
    }


def _items(payload) -> list:
    """REACH lists are sometimes bare arrays, sometimes {results: [...]}. Normalize."""
    if isinstance(payload, dict):
        return payload.get("results", payload.get("challenges", []))
    return payload if isinstance(payload, list) else []


def _proof_png(text: str) -> bytes:
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 320), (24, 26, 34))
        d = ImageDraw.Draw(img)
        d.text((20, 140), text[:40] or "proof", fill=(235, 235, 235))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return _TINY_PNG


# ── read tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def reach_health() -> dict:
    """Check the REACH API is reachable. Call once at session start."""
    try:
        r = requests.get(f"{BASE}/api/", timeout=5)
        return {"ok": r.ok, "status": r.status_code, "base": BASE}
    except requests.ConnectionError:
        return {"ok": False, "error": f"REACH not reachable at {BASE} — is runserver up?"}


@mcp.tool()
def login_persona(username: str) -> dict:
    """Authenticate as a demo persona (e.g. alice_runner, ben_lifts, coldstart_new).
    Caches the token in-process; the token itself is never exposed."""
    r = requests.get(f"{BASE}/api/users/dev_login/", params={"username": username}, timeout=15)
    if not r.ok:
        return {"error": r.status_code, "body": r.text[:200]}
    p = r.json()
    _tokens[username] = p["auth_token"]
    return {"id": p.get("id"), "username": p.get("username"), "name": p.get("name"),
            "bio": (p.get("bio") or "")[:200], "token_cached": True}


@mcp.tool()
def list_challenges(username: str) -> list | dict:
    """Challenges visible to this user (their enrollments first)."""
    return [_challenge_brief(c) for c in _items(_get("/api/challenges/", username))]


@mcp.tool()
def get_challenge(username: str, challenge_id: int, target_user: int | None = None) -> dict:
    """One challenge, with enrollment/streak context. target_user = whose view (backend
    param is target_user, NOT the frontend's ?participant=)."""
    params = {"target_user": target_user} if target_user else {}
    return _get(f"/api/challenges/{challenge_id}/", username, **params)


@mcp.tool()
def list_posts(username: str, challenge_id: int) -> list | dict:
    """Proof posts for a challenge. NOTE: new posts emit NO event on the diary —
    this poll is the only way to see them before anyone votes."""
    payload = _get("/api/challenges/challenge-posts/", username, challenge=challenge_id)
    return [_post_brief(p) for p in _items(payload)]


@mcp.tool()
def get_feed(username: str) -> list | dict:
    """The user's unified social feed (peers' recent proof, trimmed)."""
    payload = _get("/api/challenges/unified-feed/", username)
    return [_post_brief(p) for p in _items(payload)][:25]


@mcp.tool()
def get_streak_state(username: str) -> dict:
    """Streak lives + hard-mode penalties for this user — the stakes picture."""
    return {"streak_lives": _get("/api/challenges/streak-lives/", username),
            "penalties": _items(_get("/api/challenges/penalties/", username))}


@mcp.tool()
def get_events(channel: str = "", user_id: int | None = None,
               since: str = "", page_size: int = 20) -> dict:
    """REACH's append-only event diary (verification outcomes, streak finalization,
    lives, participants). Requires REACH_ADMIN_TOKEN. There is NO post-creation
    channel — use list_posts to see new proof."""
    params = {"page_size": page_size}
    if channel:
        params["channel"] = channel
    if user_id:
        params["user_id"] = user_id
    if since:
        params["since"] = since
    return _get("/api/admin/events/", admin=True, **params)


# ── write tools (dry-run gated + capped) ──────────────────────────────────────

@mcp.tool()
def create_challenge(username: str, name: str, description: str,
                     proof_description: str, challenge_type: str = "fitness",
                     frequency: str = "daily", duration_days: int = 30) -> dict:
    """Create a challenge; creator is auto-enrolled. challenge_type: fitness|studies|
    lifestyle|diet|hobbies|professional. frequency: daily|weekly|biweekly|custom."""
    body = {"name": name, "description": description, "proof_description": proof_description,
            "challenge_type": challenge_type, "frequency": frequency,
            "duration_days": duration_days, "privacy": "public"}
    return _write_gate("create_challenge", body) or _post("/api/challenges/", username, body)


@mcp.tool()
def join_challenge(username: str, challenge_id: int) -> dict:
    """Enroll this user in a challenge."""
    gate = _write_gate("join_challenge", {"challenge_id": challenge_id})
    return gate or _post(f"/api/challenges/{challenge_id}/join/", username, {})


@mcp.tool()
def post_proof(username: str, challenge_id: int, content: str = "") -> dict:
    """Submit today's proof post (generated PNG attached — REACH rejects text-only
    proof by design). Idempotent: same user+challenge+day+content → same post."""
    gate = _write_gate("post_proof", {"challenge_id": challenge_id, "content": content[:80]})
    if gate:
        return gate
    # Deterministic client_token → a retry (even after a crash) returns the same post.
    token = uuid.uuid5(uuid.NAMESPACE_URL,
                       f"reach-proof:{username}:{challenge_id}:{date.today()}:{content}")
    headers = {"Authorization": f"Token {_token(username)}"}
    r = requests.post(
        f"{BASE}/api/challenges/challenge-posts/",
        headers=headers,
        data={"challenge": challenge_id, "content": content, "client_token": str(token)},
        files={"media_files": ("proof.png", _proof_png(content), "image/png")},
        timeout=30,
    )
    if not r.ok:
        return {"error": r.status_code, "body": r.text[:300]}
    out = _post_brief(r.json())
    out["idempotent_replay"] = r.status_code == 200  # 200 = same client_token replayed
    return out


@mcp.tool()
def verify_post(username: str, post_id: int, approve: bool = True) -> dict:
    """Cast this user's peer-verification vote on a proof post. Majority wins;
    author cannot vote. IDEMPOTENT at this layer: REACH's raw endpoint is a
    TOGGLE (re-sending the same vote REMOVES it) — so we check for an existing
    matching vote first and no-op, making crash-resume replays safe."""
    for v in _items(_get("/api/challenges/verifications/", username, post_id=post_id)):
        by = v.get("verified_by") or {}
        if by.get("username") == username and v.get("is_approved") == approve:
            return {"already_voted": True, "post_id": post_id, "is_approved": approve}
    body = {"post_id": post_id, "is_approved": approve}
    return _write_gate("verify_post", body) or _post("/api/challenges/verifications/", username, body)


@mcp.tool()
def nudge(username: str, challenge_id: int, recipient_user_id: int,
          custom_message: str = "") -> dict:
    """Nudge a fellow participant (≤140 chars). REACH enforces eligibility,
    3-per-person limit, weekly quota, and block checks server-side."""
    body = {"recipient_user_id": recipient_user_id, "custom_message": custom_message[:140]}
    return _write_gate("nudge", body) or _post(f"/api/challenges/{challenge_id}/nudge/", username, body)


if __name__ == "__main__":
    log.info("starting: base=%s dry_run=%s cap=%s", BASE, DRY_RUN, WRITE_CAP)
    mcp.run()
