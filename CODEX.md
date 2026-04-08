# CODEX Working Memory

## Project Objective

AutoCallAI is a self-improving AI voice agent that simulates sales calls, analyzes outcomes, and iteratively optimizes its script using LLM reasoning and n8n orchestration.

### Primary success criteria
- Simulate a sales conversation in voice mode.
- Implement feedback loop: outcome -> analysis -> script adjustment.
- Document improvement logic (example: objection X -> response Y).
- Demonstrate at least 2 improvement iterations.

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

## Pre-Response Checklist (for Codex)

Before finalizing any change:
- Confirm objective alignment with self-improving call agent goals.
- Re-check relevant skill docs before implementing provider-specific code.
- Capture one entry in `Iteration Log`.
- State any assumptions explicitly in the response.
