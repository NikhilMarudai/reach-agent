# Fallback TTS lines — used only if live conversation gets cut at 3:45

Four pre-rendered lines for the run-2 (warm) demo beat. Written number-light
so they stay true even if the live state drifts during rehearsal. Generate
with `python voice/generate_fallback.py` once `.env` has `ELEVENLABS_API_KEY`
→ writes `voice/fallback/line1.mp3` … `line4.mp3`. Play with `afplay`.

1. **After alice verifies the demo post:**
   "Verified. Alice signed off on this morning's run — that's not me being
   nice, that's a witness."

2. **The memory discovery (the money line):**
   "Your breaks come at the week's edges — a Sunday, then a Monday. Midweek
   you don't miss. So from now on, we guard Mondays."

3. **The peer contrast, warm:**
   "Alice is four weeks deep. You don't need her streak. You need Thursday."

4. **The kill-and-resume closer (play right after the restart):**
   "Cut the power if you want. I keep receipts. When I come back, I know
   exactly where we left off."
