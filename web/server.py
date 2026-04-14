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
import re
import subprocess
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
ENV_FILE      = REPO_ROOT / ".env"

for d in (CALLS_DIR, ANALYSIS_DIR, PROMPTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _update_env_var(key: str, value: str) -> None:
    """Update or append a key=value line in the .env file."""
    if not ENV_FILE.exists():
        print(f"  [tunnel] .env not found at {ENV_FILE}", flush=True)
        return
    text = ENV_FILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    os.environ[key] = value
    print(f"  [tunnel] Updated {key} → {value}", flush=True)


def _start_ngrok_tunnel(n8n_port: int = 5678) -> str | None:
    """
    Start an ngrok tunnel to the n8n port.
    Updates .env and auto-patches the ElevenLabs agent webhook URL.
    Returns the public base URL or None if pyngrok is unavailable.
    """
    try:
        from pyngrok import ngrok  # type: ignore
    except ImportError:
        print(
            "\n  [tunnel] pyngrok not installed — webhook tool calls will fail.\n"
            "  Run:  pip install pyngrok\n"
            "  Then restart server.py.\n",
            flush=True,
        )
        return None

    print(f"  [tunnel] Starting ngrok tunnel → localhost:{n8n_port} ...", flush=True)
    try:
        tunnel = ngrok.connect(n8n_port, "http")
        public_url = tunnel.public_url  # e.g. https://abc123.ngrok-free.app
        webhook_url = f"{public_url}/webhook/call-handler"
        print(f"  [tunnel] Public webhook URL: {webhook_url}", flush=True)

        _update_env_var("N8N_CALL_HANDLER_WEBHOOK_URL", webhook_url)

        setup_script = REPO_ROOT / "scripts" / "setup_agent.py"
        if setup_script.exists():
            print("  [tunnel] Patching ElevenLabs agent with new webhook URL...", flush=True)
            result = subprocess.run(
                [sys.executable, str(setup_script)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                print("  [tunnel] ElevenLabs agent patched successfully.", flush=True)
            else:
                print(f"  [tunnel] WARNING: setup_agent.py failed:\n{result.stdout}\n{result.stderr}", flush=True)
        else:
            print("  [tunnel] WARNING: scripts/setup_agent.py not found, skipping agent patch.", flush=True)

        return public_url
    except Exception as exc:
        print(f"  [tunnel] ERROR starting ngrok: {exc}", flush=True)
        return None


def _save_analysis_artifacts(call_log: dict, analysis_report: dict, prompt_version: dict) -> None:
    """Save call log, analysis report, and prompt version to disk and update iteration status."""
    if call_log:
        call_file = _next_filename(CALLS_DIR, "call")
        call_file.write_text(json.dumps(call_log, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  → Saved call log: {call_file.name}", flush=True)

    if analysis_report:
        n = len(list(ANALYSIS_DIR.glob("iteration_*.json"))) + 1
        ar_file = ANALYSIS_DIR / f"iteration_{n}_report.json"
        ar_file.write_text(json.dumps(analysis_report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  → Saved analysis report: {ar_file.name}", flush=True)

    if prompt_version and prompt_version.get("prompt"):
        ver = prompt_version.get("version", "v2")
        pf = PROMPTS_DIR / f"{ver}_system_prompt.json"
        pf.write_text(json.dumps(prompt_version, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  → Saved prompt: {pf.name}", flush=True)

    scores    = (analysis_report.get("aggregate_scores") or {})
    total     = scores.get("weighted_total")
    changelog = prompt_version.get("changelog_list") or []
    ver_num   = prompt_version.get("version", "v?")
    timestamp = datetime.now(timezone.utc).isoformat()

    status = _load_status()
    status["prompt_version"]       = ver_num
    status["weighted_total"]       = total
    status["changelog"]            = changelog
    status["last_updated"]         = timestamp
    status["total_calls_analyzed"] = status.get("total_calls_analyzed", 0) + 1
    history = status.get("history") or []
    history.append({"version": ver_num, "score": total, "changelog": changelog,
                    "timestamp": timestamp, "call_outcome": call_log.get("outcome")})
    status["history"] = history[-10:]
    _save_status(status)
    print(f"  → Status updated: {ver_num}, score={total}", flush=True)


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
        elif self.path == "/api/current-prompt":
            self._handle_current_prompt()
        elif self.path == "/api/signed-url":
            self._handle_signed_url()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/report":
            self._handle_report()
        elif self.path == "/api/trigger-analysis":
            self._handle_trigger_analysis()
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

    def _handle_current_prompt(self):
        try:
            prompt_files = sorted(
                PROMPTS_DIR.glob("v*_system_prompt.json"),
                key=lambda p: int(p.stem.split("_")[0][1:]) if p.stem.split("_")[0][1:].isdigit() else 0
            )
            if not prompt_files:
                raise FileNotFoundError("No prompt files found in prompts/")
            latest = prompt_files[-1]
            data = json.loads(latest.read_text(encoding="utf-8"))
            prompt_text = data.get("prompt", "")
            print(f"  [current-prompt] Serving {latest.name} ({len(prompt_text)} chars)", flush=True)
            body = json.dumps({
                "prompt": prompt_text,
                "version": data.get("version", "unknown"),
                "file": latest.name
            }).encode()
            self._cors_headers(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            print(f"  [ERROR] /api/current-prompt: {exc}", flush=True)
            self.send_error(500, str(exc))

    def _handle_signed_url(self):
        try:
            import urllib.request as _req
            api_key = os.environ.get("ELEVENLABS_API_KEY", "")
            agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "")
            if not api_key or not agent_id:
                raise ValueError("ELEVENLABS_API_KEY or ELEVENLABS_AGENT_ID not set in environment")
            url = f"https://api.elevenlabs.io/v1/convai/conversation/token?agent_id={agent_id}"
            req = _req.Request(url, headers={"xi-api-key": api_key}, method="GET")
            with _req.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            print(f"  [signed-url] ElevenLabs response keys: {list(data.keys())}", flush=True)
            # API may return a full wss:// URL or just a bare token string
            signed_url = data.get("signed_url") or data.get("url")
            if not signed_url:
                # If only a token/JWT is returned, build the full WSS URL
                token = data.get("token") or data.get("access_token")
                if not token:
                    raise ValueError(f"No signed_url or token in ElevenLabs response: {data}")
                signed_url = f"wss://api.elevenlabs.io/v1/convai/conversation?token={token}"
            print(f"  [signed-url] Issued for agent {agent_id}: {signed_url[:60]}...", flush=True)
            body = json.dumps({"signed_url": signed_url}).encode()
            self._cors_headers(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            print(f"  [ERROR] /api/signed-url: {exc}", flush=True)
            self.send_error(500, str(exc))

    def _handle_trigger_analysis(self):
        """
        Called by the browser on every call disconnect.
        Forwards the transcript + call metadata to the n8n analysis webhook
        in a background thread so the browser gets an immediate 202 response.
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            call_data = json.loads(raw)
        except Exception as exc:
            self.send_error(400, f"Bad request: {exc}")
            return

        # Inject full context so n8n cloud never needs to call localhost
        try:
            prompt_files = sorted(
                PROMPTS_DIR.glob("v*_system_prompt.json"),
                key=lambda p: int(p.stem.split("_")[0][1:]) if p.stem.split("_")[0][1:].isdigit() else 0
            )
            if prompt_files:
                pd = json.loads(prompt_files[-1].read_text(encoding="utf-8"))
                call_data["current_prompt"] = pd.get("prompt", "")
                call_data["prompt_version"] = pd.get("version", "v1")
        except Exception as pe:
            print(f"  [trigger-analysis] Could not read prompt file: {pe}", flush=True)

        try:
            status = _load_status()
            history = status.get("history", [])
            call_data["prior_scores"] = [
                {"version": h.get("version"), "score": h.get("score"), "timestamp": h.get("timestamp")}
                for h in history[-5:]
            ]
            call_data["changelog_history"] = [
                f"{h.get('version')}: {' | '.join(h.get('changelog') or [])}"
                for h in history[-5:] if h.get("changelog")
            ]
        except Exception as se:
            print(f"  [trigger-analysis] Could not read status history: {se}", flush=True)

        analysis_url = os.environ.get("N8N_ANALYSIS_WEBHOOK_URL", "")
        if not analysis_url:
            print("  [trigger-analysis] N8N_ANALYSIS_WEBHOOK_URL not set — skipping", flush=True)
            self._cors_headers(503)
            self.end_headers()
            return

        # Respond immediately so the browser doesn't wait
        self._cors_headers(202)
        self.send_header("Content-Type", "application/json")
        body = b'{"queued": true}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

        # Fire-and-forget in a background thread
        import threading, urllib.request as _req, urllib.error as _uerr
        def _post():
            try:
                payload = json.dumps(call_data).encode("utf-8")
                req = _req.Request(
                    analysis_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with _req.urlopen(req, timeout=60) as resp:
                    status = resp.status
                    raw = resp.read().decode("utf-8", errors="replace")
                print(f"  [trigger-analysis] call_id={call_data.get('call_id')} → n8n {status}", flush=True)
                # n8n Respond Success returns full analysis — save artifacts locally
                try:
                    result = json.loads(raw)
                    if result.get("success") and result.get("prompt_version_payload"):
                        _save_analysis_artifacts(
                            call_log=result.get("call_log") or call_data,
                            analysis_report=result.get("analysis_report") or {},
                            prompt_version=result.get("prompt_version_payload") or {},
                        )
                except Exception as parse_exc:
                    print(f"  [trigger-analysis] Could not parse n8n response: {parse_exc}", flush=True)
            except _uerr.HTTPError as exc:
                print(f"  [trigger-analysis] n8n HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}", flush=True)
            except Exception as exc:
                print(f"  [trigger-analysis] ERROR: {exc}", flush=True)

        threading.Thread(target=_post, daemon=True).start()

    def _handle_report(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length)
            data   = json.loads(raw)
        except Exception as exc:
            self.send_error(400, f"Bad request: {exc}")
            return

        try:
            print(f"  [/api/report] payload keys: {list(data.keys())}", flush=True)
            _save_analysis_artifacts(
                call_log=data.get("call_log") or {},
                analysis_report=data.get("analysis_report") or {},
                prompt_version=data.get("prompt_version") or {},
            )
            version_num = (data.get("prompt_version") or {}).get("version", "v?")
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


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from .env into os.environ (skips comments and blanks)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:  # don't override real env vars
            os.environ[key] = value
    print(f"  [env] Loaded {ENV_FILE}", flush=True)


def main():
    _load_dotenv()
    port = int(os.environ.get("PORT", 8000))

    # Start ngrok tunnel only if no permanent public webhook URL is configured
    existing_webhook = os.environ.get("N8N_CALL_HANDLER_WEBHOOK_URL", "")
    needs_tunnel = not existing_webhook or "localhost" in existing_webhook or "127.0.0.1" in existing_webhook
    if needs_tunnel:
        _start_ngrok_tunnel(n8n_port=5678)
    else:
        print(f"  [tunnel] Using existing webhook URL: {existing_webhook}", flush=True)

    server = HTTPServer(("", port), AutoCallHandler)
    print(f"\nAutoCallAI server running at http://localhost:{port}", flush=True)
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
