"""
AutoCallAI local web server.

Serves static files from the web/ directory AND provides two API endpoints:

  POST /api/report  — called by n8n analysis workflow after each iteration.
                      Writes call log, analysis report, and new prompt version
                      to the repo artefact directories (calls/, analysis/, prompts/).
                      Updates web/iteration_status.json for UI polling.

  GET  /api/status  — returns the latest iteration status for the UI to display.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent  # e.g. E:\AutoCallAI
WEB_DIR   = REPO_ROOT / "web"
CALLS_DIR     = REPO_ROOT / "calls"
ANALYSIS_DIR  = REPO_ROOT / "analysis"
PROMPTS_DIR   = REPO_ROOT / "prompts"
STATUS_FILE   = WEB_DIR / "iteration_status.json"

for d in (CALLS_DIR, ANALYSIS_DIR, PROMPTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _next_filename(directory: Path, prefix: str, ext: str = "json") -> Path:
    """Return calls/call_001.json, call_002.json, etc. (auto-increment)."""
    existing = sorted(directory.glob(f"{prefix}_*.{ext}"))
    if not existing:
        return directory / f"{prefix}_001.{ext}"
    last = existing[-1].stem  # e.g. "call_007"
    try:
        num = int(last.split("_")[-1]) + 1
    except ValueError:
        num = len(existing) + 1
    return directory / f"{prefix}_{num:03d}.{ext}"


def _load_status() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "initialized": True,
        "prompt_version": "v1",
        "weighted_total": None,
        "changelog": [],
        "last_updated": None,
        "total_calls_analyzed": 0,
        "history": [],
        "n8n_webhook": os.environ.get("N8N_CALL_HANDLER_WEBHOOK_URL", "http://localhost:5678/webhook/call-handler")
    }


def _save_status(status: dict) -> None:
    STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")


class AutoCallHandler(SimpleHTTPRequestHandler):
    """Static file server + API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, fmt, *args):  # quieter logs
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] {self.address_string()} {fmt % args}", flush=True)

    # ── Routing ──────────────────────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/api/status":
            self._handle_status()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/report":
            self._handle_report()
        else:
            self.send_error(404, "Not found")

    def do_OPTIONS(self):
        self._cors_headers(200)
        self.end_headers()

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_status(self):
        status = _load_status()
        body = json.dumps(status, ensure_ascii=False).encode()
        self._cors_headers(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_report(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length)
            data   = json.loads(raw)
        except Exception as exc:
            self.send_error(400, f"Bad request: {exc}")
            return

        try:
            prompt_version  = data.get("prompt_version") or {}
            analysis_report = data.get("analysis_report") or {}
            call_log        = data.get("call_log") or {}

            # ── Write call log ────────────────────────────────────────────
            if call_log:
                call_file = _next_filename(CALLS_DIR, "call")
                call_file.write_text(json.dumps(call_log, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  → Saved call log: {call_file.name}", flush=True)

            # ── Write analysis report ─────────────────────────────────────
            if analysis_report:
                n = len(list(ANALYSIS_DIR.glob("iteration_*.json"))) + 1
                ar_file = ANALYSIS_DIR / f"iteration_{n}_report.json"
                ar_file.write_text(json.dumps(analysis_report, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  → Saved analysis report: {ar_file.name}", flush=True)

            # ── Write new prompt version ──────────────────────────────────
            if prompt_version and prompt_version.get("prompt"):
                ver     = prompt_version.get("version", "v2")
                pf_name = f"{ver}_system_prompt.json"
                pf      = PROMPTS_DIR / pf_name
                pf.write_text(json.dumps(prompt_version, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  → Saved prompt: {pf_name}", flush=True)

            # ── Update iteration status for UI ────────────────────────────
            scores      = analysis_report.get("aggregate_scores") or {}
            total       = scores.get("weighted_total")
            changelog   = prompt_version.get("changelog_list") or []
            version_num = prompt_version.get("version", "v?")
            timestamp   = datetime.now(timezone.utc).isoformat()

            status = _load_status()
            status["prompt_version"]       = version_num
            status["weighted_total"]       = total
            status["changelog"]            = changelog
            status["last_updated"]         = timestamp
            status["total_calls_analyzed"] = status.get("total_calls_analyzed", 0) + 1

            # Keep last 10 history entries
            history_entry = {
                "version":     version_num,
                "score":       total,
                "changelog":   changelog,
                "timestamp":   timestamp,
                "call_outcome": call_log.get("outcome")
            }
            history = status.get("history") or []
            history.append(history_entry)
            status["history"] = history[-10:]
            _save_status(status)
            print(f"  → Status updated: {version_num}, score={total}", flush=True)

            resp = {"success": True, "version": version_num}
            body = json.dumps(resp).encode()
            self._cors_headers(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception as exc:
            print(f"  [ERROR] /api/report: {exc}", flush=True)
            self.send_error(500, str(exc))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cors_headers(self, code: int):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def main():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("", port), AutoCallHandler)
    print(f"AutoCallAI server running at http://localhost:{port}", flush=True)
    print(f"  Serving static files from: {WEB_DIR}", flush=True)
    print(f"  Repo root:                 {REPO_ROOT}", flush=True)
    print(f"  Status file:               {STATUS_FILE}", flush=True)
    print("  Press Ctrl+C to stop.\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
