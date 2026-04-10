"""
Plan:
- Centralize JSON read/write operations for prompts, calls, and analysis artifacts.
- Auto-increment filenames so each write is versioned and never overwrites prior data.
- Provide helper functions used by scripts for prompt and report lifecycle management.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .logger import get_logger

log = get_logger("file_io")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALLS_DIR = PROJECT_ROOT / "calls"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

CALL_PATTERN = re.compile(r"^call_(\d{3})\.json$")
ITERATION_PATTERN = re.compile(r"^iteration_(\d+)_report\.json$")
PROMPT_PATTERN = re.compile(r"^v(\d+)_system_prompt\.json$")


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> Path:
    _ensure_directory(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    log.info("Wrote JSON file: %s", path)
    return path


def _next_number(directory: Path, pattern: re.Pattern[str]) -> int:
    _ensure_directory(directory)
    values: list[int] = []
    for item in directory.glob("*.json"):
        match = pattern.match(item.name)
        if match:
            values.append(int(match.group(1)))
    return max(values) + 1 if values else 1


def write_call_log(data: dict[str, Any]) -> Path:
    next_id = _next_number(CALLS_DIR, CALL_PATTERN)
    file_name = f"call_{next_id:03d}.json"
    payload = dict(data)
    payload.setdefault("call_id", f"call_{next_id:03d}")
    return write_json(CALLS_DIR / file_name, payload)


def write_analysis_report(data: dict[str, Any]) -> Path:
    next_id = _next_number(ANALYSIS_DIR, ITERATION_PATTERN)
    file_name = f"iteration_{next_id}_report.json"
    payload = dict(data)
    payload.setdefault("iteration", next_id)
    return write_json(ANALYSIS_DIR / file_name, payload)


def get_prompt_version_number(path: Path) -> int:
    match = PROMPT_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"Invalid prompt filename: {path.name}")
    return int(match.group(1))


def list_prompt_files() -> list[Path]:
    _ensure_directory(PROMPTS_DIR)
    return sorted(
        [p for p in PROMPTS_DIR.glob("v*_system_prompt.json") if PROMPT_PATTERN.match(p.name)],
        key=get_prompt_version_number,
    )


def get_latest_prompt() -> Path | None:
    prompts = list_prompt_files()
    return prompts[-1] if prompts else None


def write_prompt_version(data: dict[str, Any], version: int | None = None) -> Path:
    if version is None:
        latest = get_latest_prompt()
        version = get_prompt_version_number(latest) + 1 if latest else 1

    file_name = f"v{version}_system_prompt.json"
    payload = dict(data)
    payload["version"] = f"v{version}"
    return write_json(PROMPTS_DIR / file_name, payload)


def load_prompt_by_version(version: str) -> dict[str, Any]:
    normalized = version.lower().removeprefix("v")
    file_path = PROMPTS_DIR / f"v{normalized}_system_prompt.json"
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt version not found: {version}")
    return read_json(file_path)
