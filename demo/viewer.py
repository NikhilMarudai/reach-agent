"""Live viewer for the agent's mind — http://localhost:8020

Auto-refreshes every 2s. Read-only over MongoDB + the latest context blob.
Run:  .venv/bin/python demo/viewer.py
"""
from __future__ import annotations

import html
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent.memory import Memory  # noqa: E402

M = Memory()
CK = M.client["reach_agent_checkpoints"]
e = html.escape


def section(title: str, body: str) -> str:
    return f"<section><h2>{e(title)}</h2>{body}</section>"


def render() -> str:
    obs = list(M.db.observations.find({}, {"_id": 0}).sort("ts", -1).limit(10))
    beliefs = list(M.db.beliefs.find({}, {"_id": 0}).sort("updated_at", -1).limit(8))
    runs = list(M.db.runs.find({}).sort("started_at", -1).limit(6))
    threads = list(CK.checkpoints.aggregate([
        {"$group": {"_id": "$thread_id", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]))

    obs_html = "".join(
        f"<div class='card'><b>{e(o.get('user',''))}</b> · "
        f"<span class='ts'>{e(str(o.get('ts',''))[:19])}</span><br>{e(o.get('fact',''))}"
        f"<div class='ev'>evidence: {e(', '.join(map(str, o.get('evidence', []))))}</div></div>"
        for o in obs) or "<i>none yet — run the agent</i>"

    bel_html = "".join(
        f"<div class='card'><b>{e(b.get('user',''))}</b> · <code>{e(b.get('key',''))}</code>"
        f"<br>{e(b.get('text',''))}</div>" for b in beliefs) or "<i>none yet</i>"

    runs_html = "".join(
        f"<div class='card {'running' if r.get('status')=='running' else ''}'>"
        f"<b>{e(r.get('user',''))}</b> · {e(r.get('thread',''))} · "
        f"<span class='st'>{e(r.get('status',''))}</span>"
        f"<br>{e((r.get('summary') or '')[:220])}"
        + (f"<div class='ev'>proposals: {e(' | '.join(map(str, r.get('proposals', []))))}</div>"
           if r.get("proposals") else "") + "</div>"
        for r in runs) or "<i>none yet</i>"

    thr_html = "".join(
        f"<div class='card'><code>{e(str(t['_id']))}</code> · {t['n']} checkpoints</div>"
        for t in threads) or "<i>none yet</i>"

    blob_path = ROOT / "demo" / "context_blob.json"
    blob = blob_path.read_text() if blob_path.exists() else "{}"
    try:
        blob = json.dumps(json.loads(blob), indent=2)
    except ValueError:
        pass

    counts = (f"observations {M.db.observations.count_documents({})} · "
              f"beliefs {M.db.beliefs.count_documents({})} · "
              f"runs {M.db.runs.count_documents({})}")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="2"><title>agent mind — live</title><style>
 body{{background:#0d1210;color:#dfe7e2;font:13px/1.5 ui-monospace,Menlo,monospace;
      margin:0;padding:16px}}
 h1{{font-size:15px;margin:0 0 4px}} .sub{{color:#7d8f86;margin-bottom:14px}}
 h2{{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#2ee08a;
     border-bottom:1px solid #223129;padding-bottom:4px}}
 main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}}
 .card{{background:#141b17;border:1px solid #223129;border-radius:4px;
        padding:8px 10px;margin:6px 0}}
 .card.running{{border-color:#2ee08a}}
 .ev{{color:#7d8f86;font-size:11px;margin-top:3px}}
 .ts{{color:#7d8f86;font-size:11px}} .st{{color:#2ee08a}}
 pre{{background:#141b17;border:1px solid #223129;border-radius:4px;padding:10px;
      overflow-x:auto;font-size:11px}}
 code{{color:#e0b05a}}</style></head><body>
<h1>reach-agent · live mind</h1>
<div class="sub">{e(counts)} — MongoDB Atlas · refreshes every 2s</div>
<main>
{section("Runs (deliberations)", runs_html)}
{section("Observations (evidence-required)", obs_html)}
{section("Beliefs (working model)", bel_html)}
{section("Checkpoint threads (kill-proof)", thr_html)}
{section("Latest context blob (what voice speaks from)", f"<pre>{e(blob)}</pre>")}
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    print("viewer → http://localhost:8020")
    HTTPServer(("127.0.0.1", 8020), Handler).serve_forever()
