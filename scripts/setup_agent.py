"""
Plan:
- Build the agent payload from config template + env vars + v1 prompt.
- Create a new ElevenLabs agent if no agent id exists; otherwise update existing.
- Output agent id and a widget embed snippet for immediate web integration.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from typing import Any

from scripts.utils import api_client, config, logger

log = logger.get_logger("setup_agent")


def _read_prompt() -> str:
    prompt_path = Path("prompts/v1_system_prompt.json")
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    prompt = data.get("prompt", "")
    if not prompt:
        raise ValueError("prompts/v1_system_prompt.json is missing 'prompt'")
    return str(prompt)


def _substitute(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        out = value
        for key, replacement in replacements.items():
            out = out.replace(key, replacement)
        return out
    if isinstance(value, list):
        return [_substitute(item, replacements) for item in value]
    if isinstance(value, dict):
        return {k: _substitute(v, replacements) for k, v in value.items()}
    return value


def _extract_agent_id(response: dict[str, Any]) -> str | None:
    candidates = [
        response.get("agent_id"),
        response.get("id"),
        response.get("agentId"),
        (response.get("agent") or {}).get("agent_id") if isinstance(response.get("agent"), dict) else None,
        (response.get("agent") or {}).get("id") if isinstance(response.get("agent"), dict) else None,
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
    return None


def main() -> int:
    try:
        prompt = _read_prompt()
        template = config.load_json_config("agent_config")

        replacements = {
            "${SYSTEM_PROMPT}": prompt,
            "${ELEVENLABS_AGENT_ID}": config.get_env("ELEVENLABS_AGENT_ID", "") or "",
            "${ELEVENLABS_FIRST_MESSAGE}": config.get_env(
                "ELEVENLABS_FIRST_MESSAGE",
                "Hi there, this is Sarah from Greenfield Medical Practice. How can I help you today?",
            )
            or "",
            "${ELEVENLABS_VOICE_ID}": config.get_env("ELEVENLABS_VOICE_ID", "") or "",
            "${N8N_CALL_HANDLER_WEBHOOK_URL}": config.get_env("N8N_CALL_HANDLER_WEBHOOK_URL", "") or "",
        }

        payload = _substitute(template, replacements)
        env_agent_id = config.get_env("ELEVENLABS_AGENT_ID")

        if env_agent_id:
            log.info("Updating existing agent: %s", env_agent_id)
            response = api_client.update_elevenlabs_agent(env_agent_id, payload)
            agent_id = env_agent_id
        else:
            log.info("Creating a new ElevenLabs agent")
            response = api_client.create_elevenlabs_agent(payload)
            agent_id = _extract_agent_id(response)
            if not agent_id:
                raise RuntimeError("Agent created but agent id not found in response")

        embed = (
            f"<elevenlabs-convai agent-id=\"{agent_id}\"></elevenlabs-convai>\n"
            "<script src=\"https://unpkg.com/@elevenlabs/convai-widget-embed\" async type=\"text/javascript\"></script>"
        )

        output = {
            "success": True,
            "agent_id": agent_id,
            "widget_embed": embed,
            "response": response,
        }
        print(json.dumps(output, indent=2))
        return 0

    except Exception as exc:  # noqa: BLE001
        log.error("setup_agent failed: %s", exc)
        print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

