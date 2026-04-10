# CODEX Working Memory

## Canonical Design Reference

- Primary design source for all future implementation work: `DESIGN.md`
- Link: [DESIGN.md](/e:/AutoCallAI/DESIGN.md)
- Rule: Do not duplicate full design content in this file. Keep only concise execution constraints and always defer to `DESIGN.md` when conflicts appear.

## Project Objective

AutoCallAI is a self-improving AI voice agent that simulates sales calls, analyzes outcomes, and iteratively optimizes its script using LLM reasoning and n8n orchestration.

### Primary success criteria
- Simulate a sales conversation in voice mode.
- Implement feedback loop: outcome -> analysis -> script adjustment.
- Document improvement logic (example: objection X -> response Y).
- Demonstrate at least 2 improvement iterations.

## Design-Aligned Constraints (Summary)

- Voice stack direction: ElevenLabs managed conversational pipeline for realtime voice, n8n for orchestration and post-call workflows.
- Optimization target: preserve low-latency behavior; keep prompt edits concise and controlled.
- Prompt evolution policy: iterative, surgical updates across versions with clear changelog and score-based rationale.
- Data/versioning policy: treat repository artifacts (prompts/calls/analysis) as versioned source of truth.
- Domain guardrails: fictional medical-practice demo, no real patient data, no medical advice generation.

## Available Skills (.agents/skills)

### 1) `agents`
- Purpose: Build real-time voice AI agents on ElevenLabs.
- Typical use: agent creation, configuration, tools, embedding, outbound calls.
- Key dependency: `ELEVENLABS_API_KEY`.
- Path: `.agents/skills/agents/SKILL.md`

### 2) `speech-to-text`
- Purpose: Audio/video transcription with ElevenLabs Scribe v2.
- Typical use: transcripts, diarization, timestamps, realtime STT.
- Key dependency: `ELEVENLABS_API_KEY`.
- Path: `.agents/skills/speech-to-text/SKILL.md`

### 3) `text-to-speech`
- Purpose: Generate speech audio from text with ElevenLabs TTS models.
- Typical use: voiceovers, streaming speech, telephony-friendly output.
- Key dependency: `ELEVENLABS_API_KEY`.
- Path: `.agents/skills/text-to-speech/SKILL.md`

### 4) `voice-ai-development`
- Purpose: Architecture guidance for low-latency voice AI systems.
- Typical use: OpenAI Realtime, Vapi, Deepgram, ElevenLabs, LiveKit, WebRTC patterns.
- Key dependency: provider API keys depending on stack.
- Path: `.agents/skills/voice-ai-development/SKILL.md`

## Codex Self-Bug List (Persistent)

This section tracks mistakes, near-misses, or recurring friction from prior iterations so they do not repeat.

### Update rule (every iteration)
- After each Codex iteration, append one new entry to `Iteration Log`.
- If no bug occurred, add a "No bug" entry plus one prevention check.
- If a bug occurred, include: trigger, impact, root cause, prevention rule, and verification.

### Iteration Log

#### 2026-04-08 - Iteration 1
- Status: No bug.
- Prevention check added: Always read `README.md` before creating project memory docs.
- Verification: Objective and success criteria were copied from `README.md` first, then documented here.

#### 2026-04-08 - Iteration 2
- Status: No bug.
- Prevention check added: Add and preserve canonical design doc link in `CODEX.md`, and defer future implementation decisions to that source.
- Verification: Added `Canonical Design Reference` section with direct link to `DESIGN.md` and concise constraint summary.

#### 2026-04-08 - Iteration 3
- Status: No bug.
- Prevention check added: Complete implementation in strict task order and verify acceptance criteria before advancing phases.
- Verification: Started at Phase 0, completed Task 0.1 utilities first, and captured explicit verification outputs.


#### 2026-04-08 - Iteration 4
- Status: No bug.
- Prevention check added: Follow user preference for direct phase-wise file implementation without blocking on local verification.
- Verification: Completed code-first updates across all phases and added TODO.md for execution tracking.
## Pre-Response Checklist (for Codex)

Before finalizing any change:
- Confirm objective alignment with self-improving call agent goals.
- Re-check relevant skill docs before implementing provider-specific code.
- Capture one entry in `Iteration Log`.
- State any assumptions explicitly in the response.

