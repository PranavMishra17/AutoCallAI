"""
Plan:
- Load environment variables from .env/.env.example into process context.
- Read JSON configuration files from config/ using project-root-relative paths.
- Provide helpers to merge static config with env overrides for runtime flexibility.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .logger import get_logger

log = get_logger("config")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_env_file(path: Path | None = None, override: bool = False) -> None:
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if override or key not in os.environ:
            os.environ[key] = value


def get_env(key: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(key, default)
    if required and (value is None or value == ""):
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def require_env(keys: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in keys:
        value = get_env(key, required=True)
        assert value is not None
        values[key] = value
    return values


def load_json_config(name: str) -> dict[str, Any]:
    filename = name if name.endswith(".json") else f"{name}.json"
    config_path = CONFIG_DIR / filename

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    content = config_path.read_text(encoding="utf-8").strip()
    if not content:
        return {}

    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a JSON object: {config_path}")
    return data


def load_config(name: str, env_map: dict[str, str] | None = None) -> dict[str, Any]:
    data = load_json_config(name)
    if not env_map:
        return data

    merged = dict(data)
    for config_key, env_key in env_map.items():
        env_value = os.getenv(env_key)
        if env_value not in (None, ""):
            merged[config_key] = env_value
    return merged


load_env_file()
log.debug("Environment loaded for config module.")
