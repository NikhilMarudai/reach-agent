# Submission video — 60 seconds, one take

**Layout:** REACH app (390×844) LEFT · chat / terminal / memory viewer (:8020) RIGHT.
**Pre-roll (do ALL before recording):** wipe carla (`demo/wipe_memory.py carla_codes`) ·
log in as carla at :3000 + dismiss the "Link your account" gate · pre-type every command
in the terminal history (↑+enter on camera, never type live) · `AGENT_NODE_DELAY=2` so
the ctrl-C window is calm · viewer :8020 open and refreshing · close every other window.

Speak briskly but don't rush — the script is ~150 words. Lines marked ✂ are the cut
order if a take runs long.

---

**0:00–0:07 — HOOK** · *Screen: the feed as carla — scroll two cards slowly.*

> "This is REACH — our shipped accountability app, where real people verify photo
> proof of your goals. Today we built **Ridge**: an agent that gives it a memory.
> Everything agent-side was built this afternoon."

**0:07–0:18 — COLD RUN** · *Screen: `run.py --user carla_codes` left-half terminal;
viewer fills with observations on the right.*

> "Ridge reads Carla's month over our MCP server and writes what it learns to MongoDB.
> Every memory carries evidence — real post ids, real dates. ✂ It just noticed her only
> streak breaks land on week edges. That's true in the data."

**0:18–0:28 — HUMANS VERIFY** · *Screen: app — carla posts proof; switch account or
second window: Alice taps **Verify**.*

> "Then the world moves. Carla posts proof — and Alice, a human, verifies it. Ridge's
> memory is built from what people **confirmed**, not what a chatbot was told."

**0:28–0:40 — WARM RUN, AGENT ACTS** · *Screen: chat (header: "acting for Carla") —
ask "how am I doing?"; then the feed showing the agent-created challenge card + the
🤖 Ridge comment on her post.*

> "Run two starts where run one learned. It rebuilds her week around the Sunday
> problem — and acts inside the real app: a recovery challenge, a comment on her
> post, through the app's own rules. ✂ It plans. It never verifies."

**0:40–0:52 — THE KILL** · *Screen: terminal — ctrl-C mid-deliberation, ↑+enter,
the `[resume] … interrupted at ('decide',) — resuming` line lands.*

> "And the theme, literally: kill it mid-thought. Restart. It resumes from a
> LangGraph checkpoint in MongoDB — the same sentence it was thinking."

**0:52–0:60 — CLOSE** · *Screen: viewer — runs, evidence-linked observations,
beliefs, checkpoint threads in one frame. Hold 2s on the repo/showcase URL.*

> "State, memory, and the app's data in one MongoDB. Kill it anywhere — it comes
> back knowing. **Ridge. No cold start.**"

---

## Optional inserts (only if the platform allows >60s — do NOT trade core beats)

- **+6s iMessage bridge** (after 0:40): phone on camera, text Ridge "did I run today?"
  → reply cites today's verified post. VO: "It's even in your texts."
- **+6s story notification** (after 0:40, ONLY if B's notify_user + O's slip wiring
  landed): grace's bell page open on camera; the notification arrives citing her
  three-week history. VO: "And when someone slips, it writes from their story —
  never a generic reminder."

## Don'ts

- Don't show `.env`, tokens, or the ElevenLabs dashboard.
- Don't claim voice/generality beyond what's on screen.
- Don't let the take show a cold feed — warm every page (lazy-load) by scrolling
  once BEFORE recording.
