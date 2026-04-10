"""
Plan:
- Load a prompt from file/text and update an existing ElevenLabs Conversational AI agent.
- Use shared utils for config/env loading, logging, and API calls.
- Print structured success/failure output for downstream scripts and n8n handoffs.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import json

from scripts.utils import api_client, config, logger

log = logger.get_logger("update_agent")


def _load_prompt_from_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Prompt file is empty: {path}")

    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        if isinstance(data, dict) and "prompt" in data:
            return str(data["prompt"])
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Update ElevenLabs agent prompt")
    parser.add_argument("--agent-id", default=config.get_env("ELEVENLABS_AGENT_ID"))
    parser.add_argument("--prompt-file", default="prompts/v1_system_prompt.json")
    parser.add_argument("--prompt-text", default=None)
    args = parser.parse_args()

    if not args.agent_id:
        log.error("Missing agent id. Set ELEVENLABS_AGENT_ID or pass --agent-id.")
        return 1

    try:
        if args.prompt_text:
            prompt = args.prompt_text
        else:
            prompt = _load_prompt_from_file(Path(args.prompt_file))

        payload = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": prompt,
                        "llm": config.get_env("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash",
                        "temperature": 0.7,
                        "max_tokens": 300,
                    }
                }
            }
        }

        log.info("Updating ElevenLabs agent: %s", args.agent_id)
        response = api_client.update_elevenlabs_agent(args.agent_id, payload)
        print(json.dumps({"success": True, "agent_id": args.agent_id, "response": response}, indent=2))
        return 0

    except Exception as exc:  # noqa: BLE001
        log.error("Agent update failed: %s", exc)
        print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

