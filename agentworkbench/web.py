from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .runner import RUNS_DIR, list_runs, run_workflow
from .workflows import list_workflows


def _page() -> str:
    workflows = list_workflows()
    runs = list_runs()
    options = "".join(
        f'<option value="{html.escape(w.id)}">{html.escape(w.name)}</option>' for w in workflows
    )
    run_items = "".join(
        f'<li><a href="/runs/{html.escape(r["id"])}">{html.escape(r["subject"] or r["id"])} — {html.escape(r["workflow"] or "")}</a></li>'
        for r in runs[:50]
    ) or "<li>No runs yet.</li>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>AgentWorkbench</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;margin:2rem;max-width:960px;background:#0f172a;color:#e2e8f0}}
input,select,textarea,button{{font:inherit;padding:.6rem;border-radius:.5rem;border:1px solid #334155;background:#111827;color:#e2e8f0;width:100%;box-sizing:border-box}}
button{{background:#2563eb;border:0;cursor:pointer;font-weight:700}} label{{display:block;margin-top:1rem;color:#93c5fd}}
.card{{background:#111827;border:1px solid #334155;border-radius:1rem;padding:1rem;margin:1rem 0}}
a{{color:#93c5fd}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
</style></head><body>
<h1>AgentWorkbench</h1>
<p>Run configurable multi-agent workflows against any subject by choosing roles and providing a data pack.</p>
<div class="card"><form method="post" action="/runs">
<label>Workflow<select name="workflow">{options}</select></label>
<label>Subject<input name="subject" placeholder="BTC-USD, repo URL, product idea, policy proposal..." required></label>
<label>Objective<textarea name="objective" rows="3">Produce a decision-ready analysis.</textarea></label>
<div class="grid"><label>LLM provider<input name="llm_provider" value="codex"></label><label>Model<input name="model" value="default"></label></div>
<label>Repository path (optional)<input name="repo_path" placeholder="/Users/you/Developer/my-repo"></label>
<label>Pull request number/URL (optional, requires repo path)<input name="pr" placeholder="12 or https://github.com/owner/repo/pull/12"></label>
<label>Data files (comma-separated paths, optional)<input name="data_files" placeholder="docs/brief.md,/tmp/data.txt"></label>
<label><button type="submit">Run workflow</button></label>
</form></div>
<div class="card"><h2>Recent runs</h2><ul>{run_items}</ul></div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str | bytes, *, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(_page())
        elif parsed.path == "/api/workflows":
            self._send(json.dumps([w.__dict__ for w in list_workflows()], default=lambda o: o.__dict__), content_type="application/json")
        elif parsed.path == "/api/runs":
            self._send(json.dumps(list_runs()), content_type="application/json")
        elif parsed.path.startswith("/runs/"):
            run_id = parsed.path.rsplit("/", 1)[-1]
            report = RUNS_DIR / run_id / "report.md"
            if not report.exists():
                self._send("Not found", status=404)
            else:
                body = f"<pre>{html.escape(report.read_text(errors='replace'))}</pre><p><a href='/'>Back</a></p>"
                self._send(body)
        else:
            self._send("Not found", status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/runs":
            self._send("Not found", status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        data_files_raw = form.get("data_files", [""])[0].strip()
        data_files = [part.strip() for part in data_files_raw.split(",") if part.strip()] or None
        repo_path = form.get("repo_path", [""])[0].strip() or None
        pr = form.get("pr", [""])[0].strip() or None
        try:
            payload = run_workflow(
                form.get("workflow", ["general_research"])[0],
                subject=form.get("subject", [""])[0],
                objective=form.get("objective", ["Produce a decision-ready analysis."])[0],
                data_files=data_files,
                repo_path=repo_path,
                pr=pr,
                llm_provider=form.get("llm_provider", ["codex"])[0],
                model=form.get("model", ["default"])[0],
            )
        except Exception as exc:  # keep web UI simple and visible
            self._send(f"<h1>Run failed</h1><pre>{html.escape(str(exc))}</pre><p><a href='/'>Back</a></p>", status=500)
            return
        self.send_response(303)
        self.send_header("Location", f"/runs/{payload['id']}")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AgentWorkbench web UI listening at http://{host}:{port}")
    server.serve_forever()
