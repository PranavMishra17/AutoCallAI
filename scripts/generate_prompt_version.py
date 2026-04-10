"""
Plan:
- Provide CLI tools to inspect prompt history, view current prompt, diff versions, and rollback.
- Reuse shared file I/O utilities so version creation is consistent across scripts.
- Optionally push rollback output to ElevenLabs for immediate operational recovery.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import difflib
import json
from datetime import datetime, timezone
from typing import Any

from scripts.utils import api_client, config, file_io, logger

log = logger.get_logger("prompt_version")


def _prompt_paths() -> list[Path]:
    return file_io.list_prompt_files()


def _read_prompt(path: Path) -> dict[str, Any]:
    return file_io.read_json(path)


def _normalize_version(value: str) -> str:
    return f"v{value.lower().removeprefix('v')}"


def cmd_list() -> int:
    paths = _prompt_paths()
    if not paths:
        print("No prompt versions found.")
        return 0

    print(f"{'VERSION':<10} {'CREATED_AT':<28} {'TOKENS':<8} {'AVG_SCORE':<10}")
    print("-" * 62)
    for path in paths:
        data = _read_prompt(path)
        version = str(data.get("version", path.stem.split("_")[0]))
        created = str(data.get("created_at", ""))
        tokens = str(data.get("token_count", ""))
        avg = data.get("metadata", {}).get("avg_score_during_use", "")
        print(f"{version:<10} {created:<28} {tokens:<8} {str(avg):<10}")
    return 0


def cmd_current() -> int:
    latest = file_io.get_latest_prompt()
    if not latest:
        print("No prompt versions found.")
        return 1
    data = _read_prompt(latest)
    print(json.dumps(data, indent=2))
    return 0


def cmd_diff(v1: str, v2: str) -> int:
    left = file_io.load_prompt_by_version(v1)
    right = file_io.load_prompt_by_version(v2)

    left_text = str(left.get("prompt", "")).splitlines(keepends=True)
    right_text = str(right.get("prompt", "")).splitlines(keepends=True)

    left_label = _normalize_version(v1)
    right_label = _normalize_version(v2)

    diff = difflib.unified_diff(
        left_text,
        right_text,
        fromfile=f"{left_label}_system_prompt",
        tofile=f"{right_label}_system_prompt",
        lineterm="",
    )
    print("\n".join(diff))
    return 0


def cmd_rollback(version: str, update_agent: bool) -> int:
    source = file_io.load_prompt_by_version(version)
    normalized = _normalize_version(version)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "generate_prompt_version.py:rollback",
        "token_count": source.get("token_count", round(len(str(source.get("prompt", ""))) / 4)),
        "changelog": f"Rollback clone from {normalized}",
        "prompt": source.get("prompt", ""),
        "metadata": {
            "avg_score_during_use": None,
            "calls_made_with_this_version": 0,
            "replaced_by": None,
        },
    }

    new_path = file_io.write_prompt_version(payload)
    output = {
        "success": True,
        "rollback_source": normalized,
        "new_version_file": str(new_path),
    }

    if update_agent:
        agent_id = config.get_env("ELEVENLABS_AGENT_ID")
        if not agent_id:
            raise ValueError("--update-agent requires ELEVENLABS_AGENT_ID in env")
        output["agent_update"] = api_client.call_elevenlabs_update(agent_id, str(payload.get("prompt", "")))

    print(json.dumps(output, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt version manager")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all prompt versions")
    sub.add_parser("current", help="Show current latest prompt metadata")

    diff_parser = sub.add_parser("diff", help="Diff two prompt versions")
    diff_parser.add_argument("v1")
    diff_parser.add_argument("v2")

    rollback_parser = sub.add_parser("rollback", help="Rollback by cloning an older version")
    rollback_parser.add_argument("version")
    rollback_parser.add_argument("--update-agent", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "list":
            return cmd_list()
        if args.command == "current":
            return cmd_current()
        if args.command == "diff":
            return cmd_diff(args.v1, args.v2)
        if args.command == "rollback":
            return cmd_rollback(args.version, args.update_agent)

        parser.print_help()
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("Prompt version command failed: %s", exc)
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

