# Ridge — No Cold Start

> The accountability agent that remembers what your friends verified.

Ridge is **an agentic layer for [REACH](https://reachtoreach.com), built entirely outside
it** — it plugs in over the same HTTP API the mobile app uses, and its feedback signal is
REACH's core loop: **other humans verifying photographic proof**. Persistent memory lives
in MongoDB Atlas, so run two starts where run one learned; kill it mid-deliberation and
the same command resumes from its checkpoint.

It is built *for* REACH, not sold as a universal layer. The construction is modular — the
entire REACH-specific surface is one MCP server plus one seam file (`agent/reach_tools.py`),
which is what living outside the system forces — but we claim what we built: the agentic
layer that gives one real app a memory grounded in human-verified truth.

Built live at the **MongoDB Persistent Context Sprint Hackathon**, 2026-08-13, Pier 48 SF.

## Provenance — read this first, judges

- **Built during the hackathon: everything in this repository.** First commit 1:40 PM PT,
  ~40 commits over the afternoon — the history is the timesheet.
- **Pre-existing:** [REACH](https://reachtoreach.com) — our shipped social-accountability
  app (App Store). It is the *environment* this agent observes and acts in, reached only
  over its normal HTTP API against a local dev instance. No REACH code is in this repo.
  (Demo-world seed data and demo image styling live in REACH's own private repo — they
  are demo dressing for the pre-existing product, not part of this build.)

## Why this is different

Every accountability/coaching agent trusts **self-report** — the user says they did the
thing, the model believes them. REACH's core loop is *peers verifying photographic proof,
majority-wins*. That gives this agent something rare: **a ground-truth feedback signal
produced by humans.** The agent plans; people judge; the verdicts feed the memory.

Structural rule, enforced in code, not prompt: the agent **never verifies proof and never
posts proof** — humans do. Its only self-executed writes are a peer nudge, an in-app
comment, and (at most one, pattern-warranted) recovery challenge. Everything else is a
proposal.

## What it does

- **Reads the world** through a purpose-built MCP server over REACH's HTTP API: streaks,
  proof posts, the verification event diary.
- **Remembers with evidence.** Every observation stored in MongoDB must carry evidence
  pointers (`post:4293`, `date:2026-08-09`) — an evidence-free observation is refused at
  the storage layer (`agent/memory.py` raises). Observations distill into revisable
  beliefs; beliefs change the next plan.
- **Discovers real patterns.** In the demo world it finds, unprompted, that Carla's only
  streak breaks fall on week edges (Sun 8/09, Mon 8/03 — true in the data), and rebuilds
  her plan around that failure mode.
- **Acts in the real app**: comments as 🤖 Ridge on real posts, nudges peers, creates a
  recovery challenge — all through the same API doors the iOS app uses.
- **Survives death.** LangGraph checkpoints every node to MongoDB. Ctrl-C mid-deliberation,
  run the same command: `[resume]` — it continues mid-thought. **No cold start.**
- **Talks — to whoever is signed in.** A persistent chat interface (Mongo-backed,
  kill-proof) drives everything, and it follows the app's own session: log into REACH as
  any user and the chat acts *for them* — their memory thread, their state, their name in
  the header. An ElevenLabs conversational agent ("Ridge", expressive mode) rides the same
  transcript, with pre-rendered fallback lines in the same voice.
- **Tells the story.** A narrative layer (`agent/story.py`) composes each user's
  observations and beliefs into a coherent per-user history in Mongo — the difference
  between "you missed Tuesday" and "three weeks in — don't stop now."

## Architecture

```
REACH (Django, pre-existing, localhost:8010)
        ▲  HTTP · token auth · same rules as the mobile app
        │
  mcp-server/   FastMCP · 12 REACH tools · dry-run gate + write cap
        ▲
        │  tools (langchain-mcp-adapters)
        │
  agent/        LangGraph: observe → remember → decide → act → brief
        │       models via OpenRouter (planner + fast classifier)
        │       story.py: per-user narrative layer
        ▼
  MongoDB Atlas (hackathon sandbox) ──────────────────────────────
     observations (evidence-REQUIRED) · beliefs · runs · stories
     conversation transcript · LangGraph checkpoints
        ▲
        │
  voice/ + chat  ElevenLabs agent "Ridge" + persistent chat (:8030)
  demo/viewer    live memory dashboard (:8020) — every belief → its evidence
```

## MongoDB usage (the theme, concretely)

| Store | Collection(s) | What it changes |
|---|---|---|
| Episodic memory | `observations` | Facts with mandatory evidence pointers into REACH |
| Semantic memory | `beliefs` | The working model of the person — read into every plan |
| Narrative | `stories` | Per-user coherent history, composed from the above |
| Audit | `runs` | Every deliberation: what it read, concluded, did |
| State | LangGraph checkpoints | Kill-and-resume mid-deliberation |
| Conversation | chat transcript | One persistent thread; voice and text share it |

What's stored **changes what the system does next** — beliefs alter the plan, the plan
alters the actions, verified outcomes alter the beliefs.

## Run it

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r agent/requirements.txt
cp .env.example .env   # fill: Atlas URI, OpenRouter key, ElevenLabs key
.venv/bin/python agent/run.py --user carla_codes     # one deliberation (rerun = resume)
.venv/bin/python voice/bridge.py                     # chat UI on :8030
.venv/bin/python demo/viewer.py                      # memory viewer on :8020
```

Requires a running REACH dev instance on `:8010` — REACH is our shipped product and is
not included here; the demo video shows the live loop end-to-end. Demo script:
[`demo/RUNBOOK.md`](demo/RUNBOOK.md).

## Stack

MongoDB Atlas (memory, checkpoints, transcripts) · LangGraph +
`langgraph-checkpoint-mongodb` · OpenRouter (model routing) · ElevenLabs Agents
(expressive conversational voice) · MCP (FastMCP server + langchain-mcp-adapters) ·
REACH (the pre-existing human-verification substrate).

## Team

Nikhil Marudai — solo human, with a fleet of Claude Code sessions as the build crew
(orchestrator + three lanes), coordinated through a shared checkpoint file. The commit
history shows the lanes landing in parallel.
