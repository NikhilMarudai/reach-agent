"""Render the 4 fallback lines to voice/fallback/*.mp3 via ElevenLabs TTS.

Usage:
    python voice/generate_fallback.py            # needs ELEVENLABS_API_KEY in ../.env or env
    VOICE_ID=<id> python voice/generate_fallback.py   # pin a specific voice

Voice selection: $VOICE_ID if set; otherwise picks a deep/confident prebuilt
voice by name preference, else the first voice on the account. Uses
eleven_flash_v2_5 (the low-latency model — same one the live agent should use).
"""
import os
import sys
import urllib.request
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINES = [
    "Verified. Alice signed off on this morning's run — that's not me being nice, that's a witness.",
    "Your breaks come at the week's edges — a Sunday, then a Monday. Midweek you don't miss. So from now on, we guard Mondays.",
    "Alice is four weeks deep. You don't need her streak. You need Thursday.",
    "Cut the power if you want. I keep receipts. When I come back, I know exactly where we left off.",
]
PREFERRED = ['Adam', 'Clyde', 'Antoni', 'Brian']


def _key():
    if os.environ.get('ELEVENLABS_API_KEY'):
        return os.environ['ELEVENLABS_API_KEY']
    env = HERE.parent / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith('ELEVENLABS_API_KEY='):
                return line.split('=', 1)[1].strip().strip('"')
    sys.exit('ELEVENLABS_API_KEY not found (env or ../.env)')


def _req(url, key, data=None):
    r = urllib.request.Request(url, data=data, headers={
        'xi-api-key': key, 'Content-Type': 'application/json'})
    return urllib.request.urlopen(r, timeout=60)


def main():
    key = _key()
    voice_id = os.environ.get('VOICE_ID')
    if not voice_id:
        voices = json.load(_req('https://api.elevenlabs.io/v1/voices', key))['voices']
        by_name = {v['name']: v['voice_id'] for v in voices}
        voice_id = next((by_name[n] for n in PREFERRED if n in by_name),
                        voices[0]['voice_id'])
        print(f'voice: {next(n for n, i in by_name.items() if i == voice_id)}')

    out = HERE / 'fallback'
    out.mkdir(exist_ok=True)
    for i, text in enumerate(LINES, 1):
        body = json.dumps({
            'text': text,
            'model_id': 'eleven_flash_v2_5',
            'voice_settings': {'stability': 0.45, 'similarity_boost': 0.8, 'style': 0.35},
        }).encode()
        audio = _req(f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}',
                     key, body).read()
        path = out / f'line{i}.mp3'
        path.write_bytes(audio)
        print(f'wrote {path} ({len(audio) // 1024} KB)')


if __name__ == '__main__':
    main()
