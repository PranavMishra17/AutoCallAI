"""
Plan:
- Run the full judge-and-revise loop locally using the latest prompt + a call transcript file.
- Persist outputs into calls/, analysis/, and prompts/ with versioned filenames.
- Optionally push the revised prompt to ElevenLabs and print a clear score summary.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import json
from datetime import datetime, timezone
from typing import Any

from scripts.utils import api_client, config, file_io, logger

log = logger.get_logger("analyze_call")

JUDGE_SYSTEM_PROMPT = """You are an expert call center quality analyst evaluating AI voice agent performance.

You will receive:
1. A full call transcript
2. The system prompt the agent was using
3. The scoring rubric with 6 dimensions

Your job:
1. Score each dimension 1-5 with a brief justification
2. Calculate the weighted total score (0.0 to 5.0)
3. Identify the TOP 3 specific failure points in the conversation
   - Quote the exact transcript moment
   - Explain what went wrong
   - Suggest the specific prompt addition that would fix it
4. Identify what the agent did WELL (reinforce in next version)
5. Output structured JSON only, no other text"""

REVISER_SYSTEM_PROMPT = """You are a prompt engineer specializing in voice AI agent optimization.

You will receive:
1. The current system prompt (version N)
2. The judge's evaluation with failure points and suggested fixes
3. Historical scores from all prior calls

Your job:
1. Apply ONLY the fixes the judge recommended -- do not rewrite unrelated sections
2. Preserve everything that scored well (4-5)
3. Add new objection handlers for identified gaps
4. Keep the total prompt under 500 tokens (voice latency constraint)
5. Output the complete revised prompt
6. Output a changelog: what changed and why

RULES:
- Minimal edits. Surgical fixes, not rewrites.
- Never remove an objection handler that worked. Only add or refine.
- If the prompt is approaching 500 tokens, condense existing sections rather than cutting new additions.
- Preserve the 4-pillar structure (Persona, Context, Rules, Output Format).

Output JSON only with keys: revised_prompt, changelog"""


def _load_call(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Call transcript input must be a JSON object")
    return data


def _weighted_total(scores: dict[str, Any], rubric: dict[str, Any]) -> float:
    total = 0.0
    for key, cfg in rubric.items():
        weight = float(cfg.get("weight", 0))
        value = scores.get(key, 0)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        total += numeric * weight
    return round(total, 3)


def _next_prompt_version() -> int:
    latest = file_io.get_latest_prompt()
    if latest is None:
        return 1
    return file_io.get_prompt_version_number(latest) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze one call and generate next prompt version")
    parser.add_argument("call_path", help="Path to call transcript JSON")
    parser.add_argument("--update-agent", action="store_true", help="Update ElevenLabs agent with revised prompt")
    args = parser.parse_args()

    try:
        call_data = _load_call(Path(args.call_path))
        latest_prompt_path = file_io.get_latest_prompt()
        if latest_prompt_path is None:
            raise FileNotFoundError("No prompt versions found in prompts/")

        current_prompt_obj = file_io.read_json(latest_prompt_path)
        current_prompt_text = str(current_prompt_obj.get("prompt", ""))
        current_prompt_version = str(current_prompt_obj.get("version", latest_prompt_path.stem.split("_")[0]))

        rubric_data = config.load_json_config("rubric")
        rubric = rubric_data.get("rubric", {})

        judge_input = {
            "transcript": call_data.get("transcript", call_data),
            "outcome": call_data.get("outcome"),
            "current_prompt": current_prompt_text,
            "rubric": rubric,
        }

        log.info("Calling Gemini judge model")
        judge = api_client.call_gemini(
            prompt=json.dumps(judge_input, indent=2),
            system=JUDGE_SYSTEM_PROMPT,
        )

        judge_scores = judge.get("scores", {})
        weighted_total = float(judge.get("weighted_total", _weighted_total(judge_scores, rubric)))

        reviser_input = {
            "current_prompt": current_prompt_text,
            "judge": judge,
            "historical_scores": call_data.get("historical_scores", []),
        }

        log.info("Calling Gemini prompt reviser")
        revised = api_client.call_gemini(
            prompt=json.dumps(reviser_input, indent=2),
            system=REVISER_SYSTEM_PROMPT,
        )

        revised_prompt = str(revised.get("revised_prompt", current_prompt_text))
        changelog = revised.get("changelog", [])
        if isinstance(changelog, str):
            changelog_list = [changelog]
        elif isinstance(changelog, list):
            changelog_list = [str(item) for item in changelog]
        else:
            changelog_list = ["No changelog provided."]

        call_log = {
            **call_data,
            "timestamp": call_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "prompt_version": current_prompt_version,
            "judge_scores": judge_scores,
            "weighted_total": weighted_total,
            "top_failure_points": judge.get("top_failure_points", []),
            "strengths_to_preserve": judge.get("strengths_to_preserve", []),
        }

        analysis_report = {
            "iteration": None,
            "calls_analyzed": [call_log.get("call_id", "call_unknown")],
            "prompt_version_evaluated": current_prompt_version,
            "aggregate_scores": {**judge_scores, "weighted_total": weighted_total},
            "top_failure_points": judge.get("top_failure_points", []),
            "strengths_to_preserve": judge.get("strengths_to_preserve", []),
            "prompt_changes": {
                "from_version": current_prompt_version,
                "to_version": f"v{_next_prompt_version()}",
                "changelog": changelog_list,
            },
        }

        new_prompt_payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "analyze_call.py",
            "token_count": round(len(revised_prompt) / 4),
            "changelog": " | ".join(changelog_list),
            "prompt": revised_prompt,
            "metadata": {
                "avg_score_during_use": None,
                "calls_made_with_this_version": 0,
                "replaced_by": None,
            },
        }

        call_path = file_io.write_call_log(call_log)
        analysis_path = file_io.write_analysis_report(analysis_report)
        prompt_path = file_io.write_prompt_version(new_prompt_payload)

        update_result: dict[str, Any] = {"success": False, "skipped": True}
        if args.update_agent:
            agent_id = config.get_env("ELEVENLABS_AGENT_ID")
            if not agent_id:
                raise ValueError("--update-agent requires ELEVENLABS_AGENT_ID in env")
            update_result = api_client.call_elevenlabs_update(agent_id=agent_id, new_prompt=revised_prompt)

        print("\n=== AutoCallAI Analysis Summary ===")
        print(f"Call log: {call_path}")
        print(f"Analysis report: {analysis_path}")
        print(f"New prompt: {prompt_path}")
        print(f"Prompt from -> to: {current_prompt_version} -> {new_prompt_payload.get('version', prompt_path.stem.split('_')[0])}")
        print("Scores:")
        for key, value in judge_scores.items():
            print(f"  - {key}: {value}")
        print(f"  - weighted_total: {weighted_total}")
        print("Top failures:")
        for item in judge.get("top_failure_points", [])[:3]:
            print(f"  - {item}")
        print("Changelog:")
        for item in changelog_list:
            print(f"  - {item}")
        if args.update_agent:
            print(f"Agent update result: {update_result}")

        return 0

    except Exception as exc:  # noqa: BLE001
        log.error("analyze_call failed: %s", exc)
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

