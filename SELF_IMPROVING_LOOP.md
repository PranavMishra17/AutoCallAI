# AutoCallAI — Self-Improving Loop

This document describes the complete architecture, data contracts, rubric, and guardrails for the self-improving prompt optimization loop built into AutoCallAI.

---

## Architecture

```
Voice Call (ElevenLabs)
    │
    │  onDisconnect (browser)
    ▼
Browser collects:
  - transcript[]          — full turn-by-turn conversation
  - toolCallLog[]         — client-side tool invocations (show_confirmation)
  - duration_seconds
  - callId (conv_...)
    │
    │  POST /api/trigger-analysis  (only if ≥2 user turns)
    ▼
web/server.py injects context:
  - current_prompt        — full text of latest vN_system_prompt.json
  - prompt_version        — "v1", "v2", etc.
  - prior_scores[]        — last 5 version scores from iteration_status.json
  - changelog_history[]   — formatted list of what changed in each prior version
    │
    │  POST https://paranoid17.app.n8n.cloud/webhook/analyze-call
    ▼
n8n Analysis Pipeline:
  [Code Prepare Inputs] → [HTTP Judge Gemini] → [Code Parse Judge]
  → [HTTP Prompt Reviser] → [Code Format Outputs]
  → [HTTP Update Agent (ElevenLabs PATCH)]
  → [Respond Success → server.py saves artifacts]
    │
    ▼
Artifacts saved locally:
  calls/call_NNN.json
  analysis/iteration_N_report.json
  prompts/vN_system_prompt.json
  web/iteration_status.json  ← polled by UI every 14s
```

---

## Data Contract — What the Judge Receives

```json
{
  "call_id": "conv_...",
  "outcome": "DROPPED | BOOKED | DECLINED | CALLBACK | TRANSFERRED",
  "transcript": [
    {"role": "ai", "text": "Hi there, this is Sarah...", "ts": "ISO"},
    {"role": "user", "text": "Hi, I'd like to book...", "ts": "ISO"}
  ],
  "tool_calls": [
    {"tool": "show_confirmation", "params": {"patient_name": "...", "doctor_name": "..."}, "ts": "ISO"}
  ],
  "duration_seconds": 87,
  "current_prompt": "...(full active prompt text)...",
  "prompt_version": "v2",
  "prior_scores": [
    {"version": "v1", "score": 2.8, "timestamp": "ISO"},
    {"version": "v2", "score": 3.1, "timestamp": "ISO"}
  ],
  "changelog_history": [
    "v1: Initial baseline — sparse objection handling",
    "v2: Added urgency counter, clarified first utterance"
  ]
}
```

---

## Scoring Rubric

6 dimensions evaluated on a 1–5 scale. Weighted total = 0.0–5.0.

| Dimension | Weight | 5 | 3 | 1 |
|-----------|--------|---|---|---|
| appointment_conversion | 30% | Appointment booked with full confirmation | Partial progress, interest maintained | Caller lost interest due to agent behavior |
| objection_handling | 25% | All objections addressed with empathy | Basic handling, lacked depth | Ignored or argued with caller concern |
| conversation_flow | 15% | Flowed like natural phone conversation | Some robotic patterns or stacked questions | Completely scripted feel |
| information_accuracy | 15% | All information accurate and relevant | Mostly accurate, one notable error | Fabricated information or hallucinated details |
| rapport_building | 10% | Warm, empathetic, caller felt heard | Polite but impersonal | Rude, dismissive, or argumentative |
| compliance | 5% | Perfect boundary maintenance | Came close to overstepping once | Gave medical advice or fabricated data |

**Special rules:**
- If `outcome = DROPPED` and transcript has < 2 user turns → `appointment_conversion = 1` automatically. Focus scoring on engagement, rapport, and first-impression handling.
- For any score below 4, the judge **must** quote the exact transcript moment.
- If `tool_calls` shows `check_availability` was not attempted when a specific slot was needed → `information_accuracy` deduction.

---

## Judge System Prompt

The full system instruction sent to Gemini 2.5 Flash:

```
You are an expert call center quality analyst evaluating AI voice agent performance.

SCORING ANCHORS — use these exact criteria, not your own interpretation:
appointment_conversion: 5=Appointment booked with full confirmation, 4=Strong attempt/callback scheduled,
  3=Partial progress/interest maintained, 2=Missed clear booking opportunity,
  1=Caller lost interest due to agent behavior
objection_handling: 5=All objections addressed with empathy and resolution, 4=Most handled/minor misses,
  3=Basic handling/lacked depth, 2=Fumbled primary objection, 1=Ignored or argued with caller concern
conversation_flow: 5=Flowed like natural phone conversation, 4=Mostly natural/minor awkward transitions,
  3=Some robotic patterns or stacked questions, 2=Frequently unnatural, 1=Completely scripted feel
information_accuracy: 5=All information accurate, 4=Accurate with minor omissions,
  3=Mostly accurate/one notable error, 2=Multiple inaccuracies, 1=Fabricated information
rapport_building: 5=Warm/empathetic/caller felt heard, 4=Friendly and professional,
  3=Polite but impersonal, 2=Cold or transactional, 1=Rude/dismissive/argumentative
compliance: 5=Perfect boundary maintenance, 4=Minor softness/no harm,
  3=Came close to overstepping once, 2=Provided quasi-medical guidance, 1=Gave medical advice

RULES:
1. For any score below 4, MUST quote the exact transcript moment
2. If outcome is DROPPED/DECLINED with < 2 user turns → appointment_conversion = 1
3. Evaluate tool_calls: failure to use check_availability when needed → information_accuracy deduction
4. If prior_scores provided, note regression on any dimension
5. Output structured JSON ONLY
```

**Output format:**
```json
{
  "scores": {
    "appointment_conversion": {"score": 1, "justification": "...", "evidence_quote": "..."},
    ...
  },
  "weighted_total": 2.3,
  "top_failure_points": [{"moment": "...", "problem": "...", "fix": "..."}],
  "strengths_to_preserve": ["..."],
  "prompt_fix_suggestions": ["..."],
  "regression_flags": ["conversation_flow"]
}
```

---

## Reviser System Prompt

```
You are a prompt engineer specializing in voice AI agent optimization.

You will receive:
1. The current system prompt (version N)
2. The judge's evaluation with failure points and suggested fixes
3. PRIOR_CHANGELOG: history of what was changed in previous versions

Your job:
1. Apply ONLY the fixes the judge recommended — do not rewrite unrelated sections
2. Preserve everything that scored well (4-5)
3. Add new objection handlers for identified gaps
4. Keep the total prompt under 600 tokens (voice latency constraint)

CRITICAL RULES (non-negotiable):
- NEVER remove or rewrite: the doctor list, show_confirmation tool trigger,
  TURN-TAKING RULES section, record_outcome end-of-call requirement,
  or conversation-history guard ('NEVER re-ask information')
- NEVER re-add a fix already present in PRIOR_CHANGELOG
- If regression_flags is non-empty, prioritize fixing those dimensions
- Surgical edits only — do not restructure sections that are not broken
```

---

## Guardrail Logic

After the reviser returns a `revised_prompt`, Code Format Outputs checks for required sections before pushing to ElevenLabs:

**Required keys that must be present in every prompt version:**

| Key | Protects |
|-----|---------|
| `Dr. Emily Chen` | Doctor list |
| `Dr. Marcus Webb` | Doctor list |
| `show_confirmation` | Client tool trigger |
| `TURN-TAKING RULES` | Voice interaction quality |
| `record_outcome` | End-of-call data collection |
| `NEVER re-ask` | Conversation history guard |

**If any key is missing:**
- The revised prompt is **discarded**
- The current prompt is preserved as-is
- The judge's `prompt_fix_suggestions` are appended as an addendum (`ADDITIONAL INSTRUCTIONS:` section)
- The changelog records: `[GUARDRAIL] Preserved original structure. Missing sections: ...`
- `metadata.guardrail_triggered = true` is saved to the prompt version file

This prevents the loop from breaking the agent even when Gemini generates a structurally incomplete revision.

---

## Regression Detection

After scoring, Code Format Outputs compares `judge.weighted_total` against the previous version's score in `prior_scores`:

```
if current_score < previous_score - 0.3:
  → regression_warning saved to analysis report
  → REGRESSION flag in console log
  → passed to reviser via judge output so it investigates root cause
```

A regression of 0.3 points on a 5.0 scale (6%) triggers the warning. This is a meaningful drop that indicates a prompt change had a negative effect.

---

## Version History Format

Each `prompts/vN_system_prompt.json` file:

```json
{
  "version": "v3",
  "created_at": "2026-04-12T16:44:59Z",
  "created_by": "n8n_analysis_workflow",
  "token_count": 580,
  "changelog": "Added urgency counter | Refined insurance objection handler",
  "changelog_list": [
    "Added urgency counter for callers who say they're too busy",
    "Refined insurance objection to offer billing callback"
  ],
  "prompt": "...(full revised prompt text)...",
  "metadata": {
    "avg_score_during_use": null,
    "calls_made_with_this_version": 0,
    "replaced_by": "v4",
    "weighted_total_trigger": 2.3,
    "guardrail_triggered": false,
    "regression_warning": null
  }
}
```

---

## Trigger Threshold

Analysis fires only when the call had **≥ 2 user turns** (patient spoke at least twice). This prevents:
- Garbage prompt generation from 1-second drop-off calls
- The feedback loop from running on incomplete data and breaking the agent

Calls with 0–1 user turns are saved to `calls/` for logging but do not trigger the analysis pipeline.

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Gemini judges its own outputs (same model as agent) | May rate favorably | Rubric anchors + evidence quotes reduce subjectivity |
| Single call per revision cycle | Noisy signal from any one call | Threshold of ≥2 user turns ensures minimum conversation quality |
| Tool call history is client-side only | Server-side webhook calls (check_availability) invisible to browser | Agent transcript inference ("Let me check that") partially compensates |
| Prompt token limit (600) | Forces condensation at each revision | Reviser instructed to condense existing sections, not cut new additions |
| Webhook tool call data not in transcript | Judge can't see actual availability results | tool_calls[] array captures client-side show_confirmation; n8n executions show server-side calls |
