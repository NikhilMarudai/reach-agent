"""Smoke test for the REACH MCP server — calls the tool functions directly
(bypassing the stdio transport; the HTTP layer is what needs proving).

Run:  .venv/bin/python smoke_test.py
Live-write leg uses the uifix_* fixture pair so the demo cast stays pristine.
"""
import os
import sys

# Arm writes for THIS process only (.env stays REACH_DRY_RUN=1 for real sessions).
os.environ["REACH_DRY_RUN"] = "0"
os.environ["REACH_WRITE_CAP"] = "4"

import server  # noqa: E402


def check(name, result, pred=lambda r: not (isinstance(r, dict) and "error" in r)):
    ok = pred(result)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {str(result)[:140]}")
    if not ok:
        sys.exit(1)
    return result


# ── reads (demo cast, read-only) ─────────────────────────────────────────────
check("health", server.reach_health(), lambda r: r.get("ok"))
alice = check("login alice_runner", server.login_persona("alice_runner"))
chals = check("list_challenges", server.list_challenges("alice_runner"),
              lambda r: isinstance(r, list) and len(r) > 0)
check("get_challenge", server.get_challenge("alice_runner", chals[0]["id"]))
check("get_feed", server.get_feed("alice_runner"), lambda r: isinstance(r, list))
check("get_streak_state", server.get_streak_state("alice_runner"))
check("get_events", server.get_events(page_size=3),
      lambda r: isinstance(r, dict) and "error" not in r)

# ── dry-run gate (fresh process would default ON; simulate here) ─────────────
server.DRY_RUN = True
check("dry-run gate", server.post_proof("uifix_rich", 383, "gate test"),
      lambda r: r.get("dry_run") is True)
server.DRY_RUN = False

# ── live writes (uifix pair — NOT the demo cast) ─────────────────────────────
server.login_persona("uifix_rich")
server.login_persona("uifix_author")
# 383 = the fixture challenge rich+author share (verified live this morning).
# list_challenges shows VISIBLE challenges, not enrollments — posting to an
# un-joined one 403s. If the uifix world gets reseeded, re-read the manifest.
cid = 383
post = check("post_proof (live)", server.post_proof("uifix_rich", cid, "MCP smoke proof"))
replay = check("post_proof idempotent replay", server.post_proof("uifix_rich", cid, "MCP smoke proof"),
               lambda r: r.get("id") == post.get("id"))
check("verify_post (live)", server.verify_post("uifix_author", post["id"], approve=True))
check("write cap counting", {"writes": server._writes_done},
      lambda r: r["writes"] == 3)  # replay hit the gate too — it IS a write attempt

print("\nALL PASS — MCP server HTTP layer verified against live REACH.")
