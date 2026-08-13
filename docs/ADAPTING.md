# Pointing Ridge at your own app

Ridge was built for REACH and we only claim REACH. But because it lives outside the
app, the app-specific surface is deliberately small — two files. If you want to try the
agentic layer on your own habit tracker / accountability app, this is the whole job:

## 1. Give your app an MCP server (`mcp-server/`)

Write a FastMCP server exposing your app's API as tools. Ridge's loop needs these
capabilities (names are yours; the shapes matter):

| Capability | Ridge uses it for |
|---|---|
| `login` / identity | act as a specific user |
| `get_state` (streaks, goals, whatever "progress" is in your app) | ground truth about now |
| `list_posts` / activity history | the raw material for observations |
| `get_events` (anything append-only: verifications, completions) | what changed since last run |
| one or two writes (comment, nudge, create-goal) | acting in the app |

Copy `mcp-server/server.py` as the template — keep the dry-run gate and the write cap.

## 2. Update the seam (`agent/reach_tools.py`)

Every tool-call shape the agent makes lives in this one file. Change the tool names and
argument shapes to match your server. Nothing else in `agent/` knows your app exists.

## 3. Point the environment at your stack

```
REACH_BASE_URL=...     # your app's API
MONGODB_URI=...        # your Atlas cluster
OPENROUTER_API_KEY=...
```

That's it. Memory (`agent/memory.py`), the deliberation loop (`agent/loop.py`), the
story layer, chat, and voice are app-agnostic — they only speak to the seam.

## The honest caveat

Ridge's memory is only as good as your app's feedback signal. REACH's signal is peers
verifying photographic proof — human ground truth. If your app's signal is self-report,
Ridge will remember faithfully what users claim, which is a much weaker thing to
remember. The architecture ports; the epistemics are up to your product.
