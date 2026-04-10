"""
Plan:
- Provide thin HTTP wrappers for Gemini and ElevenLabs APIs.
- Add standardized retries (3 attempts, exponential backoff) and structured logging.
- Return parsed objects on success and rich context on errors/failures.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from . import config
from .logger import get_logger, truncate_text

log = get_logger("api_client")


class ApiClientError(RuntimeError):
    pass


def _timeout_seconds() -> int:
    return int(config.get_env("REQUEST_TIMEOUT_SECONDS", "30") or "30")


def _max_attempts() -> int:
    return int(config.get_env("RETRY_MAX_ATTEMPTS", "3") or "3")


def _base_backoff_seconds() -> float:
    return float(config.get_env("RETRY_BASE_SECONDS", "1") or "1")


def _should_retry_http(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _extract_json_block(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return stripped[start : end + 1]
    return stripped


def _request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    component: str,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    attempts = _max_attempts()

    for attempt in range(1, attempts + 1):
        try:
            log.info("Calling API: %s %s (attempt %s/%s)", method, url, attempt, attempts)
            req = urllib.request.Request(url=url, headers=headers, data=body, method=method)
            with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:
                raw = resp.read().decode("utf-8")
                log.info("[%s] Response (%s): %s", component, resp.status, truncate_text(raw))
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            log.error("[%s] HTTP %s: %s", component, exc.code, truncate_text(error_body))
            if attempt < attempts and _should_retry_http(exc.code):
                time.sleep(_base_backoff_seconds() * (2 ** (attempt - 1)))
                continue
            raise ApiClientError(
                f"{component} API call failed: {method} {url}, status={exc.code}, body={truncate_text(error_body)}"
            ) from exc
        except urllib.error.URLError as exc:
            log.error("[%s] Network error: %s", component, exc.reason)
            if attempt < attempts:
                time.sleep(_base_backoff_seconds() * (2 ** (attempt - 1)))
                continue
            raise ApiClientError(
                f"{component} network failure after {attempt} attempts: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ApiClientError(f"{component} response JSON parse failed: {exc}") from exc

    raise ApiClientError(f"{component} request exhausted retries without success")


def elevenlabs_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    api_key = config.get_env("ELEVENLABS_API_KEY", required=True)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    url = f"https://api.elevenlabs.io{path}"
    return _request_json(method=method, url=url, headers=headers, payload=payload, component="elevenlabs")


def gemini_request(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = config.get_env("GEMINI_API_KEY", required=True)
    model = config.get_env("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    return _request_json(method="POST", url=url, headers=headers, payload=payload, component="gemini")


def extract_gemini_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates", [])
    if not candidates:
        raise ApiClientError("Gemini response missing candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(str(part.get("text", "")) for part in parts).strip()
    if not text:
        raise ApiClientError("Gemini response missing text content")
    return text


def call_gemini_text(prompt: str, system: str) -> str:
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    }
    response = gemini_request(payload)
    return extract_gemini_text(response)


def call_gemini(prompt: str, system: str) -> dict[str, Any]:
    text = call_gemini_text(prompt, system)
    try:
        parsed = json.loads(_extract_json_block(text))
    except json.JSONDecodeError as exc:
        raise ApiClientError(f"Gemini JSON parse failed. Raw text: {truncate_text(text)}") from exc

    if not isinstance(parsed, dict):
        raise ApiClientError("Gemini JSON output was not an object")
    return parsed


def call_elevenlabs_update(agent_id: str, new_prompt: str) -> dict[str, Any]:
    payload = {
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": new_prompt,
                }
            }
        }
    }
    try:
        response = elevenlabs_request("PATCH", f"/v1/convai/agents/{agent_id}", payload)
        return {"success": True, "response": response}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


def create_elevenlabs_agent(payload: dict[str, Any]) -> dict[str, Any]:
    return elevenlabs_request("POST", "/v1/convai/agents/create?enable_versioning=true", payload)


def update_elevenlabs_agent(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return elevenlabs_request("PATCH", f"/v1/convai/agents/{agent_id}", payload)


def get_elevenlabs_agent(agent_id: str) -> dict[str, Any]:
    return elevenlabs_request("GET", f"/v1/convai/agents/{agent_id}")


def get_elevenlabs_user() -> dict[str, Any]:
    return elevenlabs_request("GET", "/v1/user")
