# reach-agent — No Cold Start

Built live at the **MongoDB Persistent Context Sprint Hackathon** (2026-08-13, Pier 48 SF).

## Provenance — read this first, judges

- **Built during the hackathon: everything in this repository.** First commit ~1:40 PM PT.
- **Pre-existing:** [REACH](https://reachtoreach.com) — our shipped social-accountability
  app (App Store). It is used ONLY as the external environment this agent observes and
  controls, through its normal HTTP API against a local dev instance. No REACH code is
  in this repo.

## What it is

Every accountability app trusts self-report. REACH's feedback signal is **other humans
verifying photographic proof**. This agent plans your commitments, watches what your
peers actually verified, and adapts — with persistent memory in MongoDB Atlas, so run
two starts where run one learned. Kill it mid-run; it resumes from its checkpoint.
No cold start.

## Architecture

```
REACH API (Django, pre-existing, localhost:8010)
        ▲  HTTP · token auth
        │
  mcp-server/   FastMCP · ~10 REACH tools · dry-run + write cap
        ▲  tools
        │
  agent/        LangGraph loop · OpenRouter models
        │       wake → read → remember → decide → act → speak
        ▼
  MongoDB Atlas (hackathon sandbox)
        observations · beliefs (vector search) · runs · checkpoints
        +
  voice/        ElevenLabs conversational agent
```

## Layout

| Dir | What |
|---|---|
| `mcp-server/` | FastMCP server wrapping the REACH HTTP API |
| `agent/` | LangGraph loop, MongoDB memory, checkpointer |
| `voice/` | ElevenLabs conversational wiring + personality |
| `demo/` | Demo runbook, seed notes, the 1-minute video |

## Setup

Copy `.env.example` → `.env` and fill it. Never commit `.env`.
