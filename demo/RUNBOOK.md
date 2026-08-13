# Demo runbook — 4 beats, ~3:00 on stage

Cast (from the seeded world — real values, verified 13:50 PT):

| Role | Who | Why |
|---|---|---|
| The user | **carla_codes** (id 408) — 24, bootcamp grad, night owl, 0.58 adherence | Streak **3**. Her last two breaks: **Sunday 8/09 and Monday 8/03 — the week's edges, never midweek.** Adaptation is visible on her. |
| The peer | **alice_runner** (id 406) — 27-day streak, challenge creator | The human verifier + the contrast. |
| The arena | **"Daily 5K Run", challenge id 398** (started 7/16) | Both enrolled, 28 days of real history. |

Logins: `username / demopassword` via `POST /api/users/login/` (5/min/IP — mint once into
`demo/.tokens/`, reuse). REACH backend must be up on **:8010** (B's lane).

```bash
mkdir -p demo/.tokens
curl -s -X POST http://localhost:8010/api/users/login/ -H "Content-Type: application/json" \
  -d '{"username":"carla_codes","password":"demopassword"}' | python3 -c "import sys,json;open('demo/.tokens/carla','w').write(json.load(sys.stdin)['auth_token'])"
curl -s -X POST http://localhost:8010/api/users/login/ -H "Content-Type: application/json" \
  -d '{"username":"alice_runner","password":"demopassword"}' | python3 -c "import sys,json;open('demo/.tokens/alice','w').write(json.load(sys.stdin)['auth_token'])"
```

---

## Beat 1 — COLD RUN (0:00–0:40)

Agent meets carla with an empty memory. It reads her world over the REACH MCP,
writes its first observations to Mongo, proposes a plan, and speaks.

```bash
cd ~/Desktop/Code/reach-agent
.venv/bin/python agent/run.py --user carla_codes   # thread defaults to demo-carla_codes
# --challenge defaults to 398 · --fresh forces a new thread · blob → demo/context_blob.json
```

**Expect:** docs appear in Mongo `observations` + `runs`; the plan names the
edge-of-week pattern IF retrieval finds it cold (fine either way — run 2 is
where memory must shine). Voice: Ridge introduces the plan, ≤3 sentences.

**Say on stage:** "Everything it just learned is in MongoDB — watch what that
buys us in two minutes."

## Beat 2 — THE WORLD MOVES (0:40–1:20) — humans, not the agent

Carla posts proof; **a human (alice) verifies it.** Run from `reach-agent/`:

```bash
POST_ID=$(curl -s -X POST http://localhost:8010/api/challenges/challenge-posts/ \
  -H "Authorization: Token $(cat demo/.tokens/carla)" \
  -F "challenge=398" -F "content=Morning 5k. Before coffee. Who am I." \
  -F "media_files=@demo/proof_carla.png" -F "client_token=$(uuidgen)" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "post: $POST_ID"

curl -s -X POST http://localhost:8010/api/challenges/verifications/ \
  -H "Authorization: Token $(cat demo/.tokens/alice)" -H "Content-Type: application/json" \
  -d "{\"post_id\": $POST_ID, \"is_approved\": true}" -w "\nHTTP %{http_code}\n" | tail -1
```

**Expect:** 201, then the post flips `is_verified: true` (majority-wins, live-verified
in prep). ⚠️ Field is `post_id`, NOT `post`. Media is REQUIRED — the PNG is committed
at `demo/proof_carla.png`.

**Say:** "No AI verified that. Alice did. That's the signal every other agent
demo here doesn't have."

## Beat 3 — WARM RUN (1:20–2:20) — the memory payoff

Same command as beat 1. The agent retrieves run-1 memory + the new verified
evidence and adapts: it should surface the **week's-edge pattern** (Sunday 8/09,
Monday 8/03) and propose the Monday guard, then SPEAK it (live conversation;
if voice was cut: `afplay voice/fallback/line2.mp3` then `line3.mp3`).

**Expect in Mongo:** `runs` doc #2 references run #1's observation ids — show
the two docs side by side if the room is technical.

## Beat 4 — THE KILL (2:20–2:50) — No Cold Start, literally

Ctrl-C the agent MID-deliberation on a third run. Restart it.

```bash
.venv/bin/python agent/run.py --user carla_codes
# SAME command as beat 1. It detects the interrupted thread and prints:
#   [resume] thread 'demo-carla_codes' was interrupted at ('decide',) — resuming
```

**Expect:** it resumes from the LangGraph checkpoint in Mongo — mid-thought,
not from zero. If voice is live, let Ridge land it; else `afplay voice/fallback/line4.mp3`:
"Cut the power if you want. I keep receipts."

**Close:** "State, memory, and the application data all live in one MongoDB.
Kill it anywhere. It comes back knowing."

---

## Reset & rehearsal notes

- Full world reset (~2 min, run in REACH repo `backend/`):
  `python manage.py seed_fake_data --reset --days-history=28` — **ids change on
  reset**; re-check challenge id + streaks and update this file + the context blob.
- Rehearsal dirties the world (carla gains verified posts today). One rehearsal
  is fine — the story stays true. More than two: reset and re-pin ids.
- Wipe agent memory between rehearsals (O: drop the Mongo collections) so beat 1
  is genuinely cold.
- Record the 1-min video from a CLEAN run of beats 1→4 before 4:35.
