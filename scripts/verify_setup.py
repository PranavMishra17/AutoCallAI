"""
Plan:
- Validate API credentials, webhook wiring, and required local project files.
- Print a pass/fail checklist for each dependency in a single run.
- Exit non-zero when any critical setup check fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import urllib.error
import urllib.request

from scripts.utils import api_client, config, file_io, logger

log = logger.get_logger("verify_setup")


def _check(name: str, fn):
    try:
        result = fn()
        print(f"[PASS] {name} - {result}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name} - {exc}")
        return False


def check_required_env() -> str:
    keys = [
        "ELEVENLABS_API_KEY",
        "GEMINI_API_KEY",
        "N8N_CALL_HANDLER_WEBHOOK_URL",
        "N8N_ANALYSIS_WEBHOOK_URL",
    ]
    missing = [k for k in keys if not config.get_env(k)]
    if missing:
        raise ValueError(f"Missing env vars: {', '.join(missing)}")
    return "Required env vars present"


def check_elevenlabs_key() -> str:
    user = api_client.get_elevenlabs_user()
    return f"User lookup OK ({'user_id' if 'user_id' in user else 'response_received'})"


def check_gemini_key() -> str:
    text = api_client.call_gemini_text(
        prompt='Return exactly: {"ok": true}',
        system="You are a JSON-only assistant.",
    )
    return f"Gemini response OK: {text[:80]}"


def _post_json(url: str, payload: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")[:200]


def check_call_handler_webhook() -> str:
    url = config.get_env("N8N_CALL_HANDLER_WEBHOOK_URL", required=True)
    status, body = _post_json(url, {"tool_name": "check_availability"})
    if status != 200:
        raise RuntimeError(f"Unexpected status {status}: {body}")
    return f"Status {status}"


def check_analysis_webhook() -> str:
    url = config.get_env("N8N_ANALYSIS_WEBHOOK_URL", required=True)
    payload = {
        "call_id": "verify_call",
        "outcome": "BOOKED",
        "transcript": [{"role": "user", "text": "test"}],
        "duration_seconds": 5,
        "patient_info": {"name": "Verifier"},
    }
    status, body = _post_json(url, payload)
    if status != 200:
        raise RuntimeError(f"Unexpected status {status}: {body}")
    return f"Status {status}"


def check_agent_exists() -> str:
    agent_id = config.get_env("ELEVENLABS_AGENT_ID", required=True)
    agent = api_client.get_elevenlabs_agent(agent_id)
    tools = (((agent.get("conversation_config") or {}).get("tools")) or [])
    return f"Agent reachable, tools configured={len(tools)}"


def check_prompt_file() -> str:
    path = Path("prompts/v1_system_prompt.json")
    if not path.exists():
        raise FileNotFoundError("prompts/v1_system_prompt.json missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "prompt" not in data:
        raise ValueError("v1_system_prompt.json missing required fields")
    return "v1 prompt valid"


def check_config_files() -> str:
    names = ["rubric", "mock_availability", "scenarios", "agent_config"]
    for name in names:
        config.load_json_config(name)
    return "All config files parse"


def main() -> int:
    checks = [
        ("Required environment", check_required_env),
        ("ElevenLabs API key", check_elevenlabs_key),
        ("Gemini API key", check_gemini_key),
        ("n8n call handler webhook", check_call_handler_webhook),
        ("n8n analysis webhook", check_analysis_webhook),
        ("ElevenLabs agent config", check_agent_exists),
        ("Prompt file", check_prompt_file),
        ("Config files", check_config_files),
    ]

    ok = True
    for name, fn in checks:
        ok = _check(name, fn) and ok

    if ok:
        print("\nAll checks passed.")
        return 0

    print("\nOne or more checks failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

