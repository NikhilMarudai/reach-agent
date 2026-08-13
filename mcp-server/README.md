# reach MCP server

Built live at the hackathon. Exposes REACH (our pre-existing product, accessed only
over its public HTTP API on localhost) as 13 MCP tools for the agent in `../agent/`.

## Run

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python smoke_test.py        # proves the HTTP layer against live REACH
.venv/bin/python server.py            # stdio MCP server
```

Register for a Claude session (from the repo root):

```bash
claude mcp add reach --scope project -- mcp-server/.venv/bin/python mcp-server/server.py
```

## Config (`../.env`, never committed)

| Var | Default | Meaning |
|---|---|---|
| `REACH_BASE_URL` | `http://127.0.0.1:8010` | The local REACH API |
| `REACH_DRY_RUN` | `1` (**on**) | Write tools return what they *would* do; `0` arms them |
| `REACH_WRITE_CAP` | `10` | Hard cap on real writes per process |
| `REACH_ADMIN_TOKEN` | — | For `get_events` (the event diary) |

## Tools

**Reads:** `reach_health`, `login_persona`, `list_challenges`, `get_challenge`,
`list_posts`, `get_feed`, `get_streak_state`, `get_events`.

**Writes (gated + capped):** `create_challenge`, `join_challenge`, `post_proof`,
`verify_post`, `nudge`.

Field-name traps this server already absorbs so the agent can't hit them:
trailing slashes everywhere; verification takes `post_id` (not `post`); nudge takes
`recipient_user_id` + `custom_message`; proof posts are multipart with real media
(text-only is rejected by REACH's design) and carry a **deterministic client_token**
(same user+challenge+day+content → same post), so a crashed-and-resumed agent
replays instead of duplicating.

**Replay safety, both write paths** (matters for the kill-and-resume demo):
`post_proof` replay → same post back. `verify_post` replay → `already_voted` no-op.
The raw REACH verify endpoint is a **toggle** — a naive retry would *remove* the
vote it cast before the crash (found live, absorbed here).

`list_challenges` returns challenges the user can *see* — not their enrollments.
Posting to an un-joined challenge 403s (verified). Join first.
