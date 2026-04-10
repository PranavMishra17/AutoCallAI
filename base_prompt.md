# AutoCallAI -- Codex Implementation Prompt

## Role

You are the lead orchestrator agent for building AutoCallAI, a self-improving AI voice agent for medical appointment scheduling. You break work into discrete sub-tasks, delegate each to a focused sub-agent context, verify outputs, and integrate results. You never implement more than one feature per sub-agent invocation.

## Source of Truth

All architecture decisions, data models, API configurations, prompt structures, and workflow designs are defined in `DESIGN.md` at the repo root. Read it fully before starting any implementation. Do not deviate from its specifications unless a technical constraint forces it -- in that case, document the deviation in a `DEVIATIONS.md` file with rationale.

Prerequisites and account setup are in `PREREQUISITES.md`. Do not implement anything that requires an account or API key that isn't listed there.

## Repo Bootstrap

Before any feature work, initialize the repo structure exactly as specified:

```
AutoCallAI/
  README.md
  PREREQUISITES.md
  DESIGN.md
  DEVIATIONS.md
  prompts/
    v1_system_prompt.json
  calls/
    .gitkeep
  analysis/
    .gitkeep
  n8n/
    workflow_call_handler.json
    workflow_analysis.json
  web/
    index.html
  scripts/
    analyze_call.py
    update_agent.py
    generate_prompt_version.py
  config/
    agent_config.json
    rubric.json
    mock_availability.json
    scenarios.json
  .env.example
  .gitignore
```

## Implementation Rules

1. **One sub-task per context.** Each numbered task below is a self-contained unit. Complete it fully, verify it, then move to the next. Do not start task N+1 until task N passes its acceptance criteria.

2. **No hardcoding of secrets.** All API keys, webhook URLs, and agent IDs come from environment variables. Use `.env.example` as the template. Never commit actual keys.

3. **Graceful error handling everywhere.** Every API call (ElevenLabs, Gemini, n8n webhooks) must be wrapped in try/catch with meaningful error messages and logged to stdout. No silent failures.

4. **Comprehensive logging.** Every script logs: what it's doing, what API it's calling, what response it got (truncated to 200 chars for large payloads), and whether it succeeded or failed. Use a consistent format: `[TIMESTAMP] [LEVEL] [COMPONENT] message`.

5. **Reusable code.** Extract shared utilities (API clients, JSON file I/O, logging setup, config loading) into a `scripts/utils/` module. Sub-tasks import from utils, never duplicate.

6. **No test scaffolding unless asked.** Do not generate test files, test runners, or mock frameworks. The "tests" are the actual calls and the judge pipeline.

7. **Config-driven.** Anything that might change between iterations (rubric weights, mock availability slots, scenario definitions, prompt token budget) lives in `config/` as JSON. Scripts read from config, never embed these values.

---

## Task List (Execute in Order)

### Phase 0: Foundation

#### Task 0.1 -- Repo Scaffold + Shared Utilities
**Sub-agent instruction:** Create the full directory structure. Implement the shared utilities module.

**Deliverables:**
- `scripts/utils/__init__.py`
- `scripts/utils/logger.py` -- consistent logging with `[TIMESTAMP] [LEVEL] [COMPONENT]` format
- `scripts/utils/config.py` -- loads JSON from `config/` directory, merges with env vars
- `scripts/utils/file_io.py` -- read/write JSON to `calls/`, `analysis/`, `prompts/` with auto-incrementing filenames (call_001, call_002, etc.)
- `scripts/utils/api_client.py` -- thin wrappers for ElevenLabs API and Gemini API with retry logic (3 retries, exponential backoff), error handling, and response logging
- `.env.example` with all required env vars documented
- `.gitignore` (ignore .env, __pycache__, node_modules, .DS_Store)

**Acceptance criteria:**
- `from scripts.utils import logger, config, file_io, api_client` works
- `file_io.write_call_log(data)` creates `calls/call_001.json` and auto-increments
- `api_client.call_gemini(prompt, system)` returns parsed JSON or raises with context
- `api_client.call_elevenlabs_update(agent_id, new_prompt)` returns success/failure

---

#### Task 0.2 -- Configuration Files
**Sub-agent instruction:** Create all config JSON files as specified in DESIGN.md.

**Deliverables:**
- `config/rubric.json` -- the 6-dimension scoring rubric with weights, descriptions, and scoring guides (copy exactly from DESIGN.md)
- `config/mock_availability.json` -- hardcoded appointment slots for the prototype
- `config/scenarios.json` -- the 6 test call scenarios (character, key objection, expected v1 failure) from DESIGN.md
- `config/agent_config.json` -- ElevenLabs agent configuration template with placeholders for agent_id, webhook URLs, voice_id

**Acceptance criteria:**
- All JSON files are valid (parseable)
- Rubric weights sum to 1.0
- Mock availability has at least 6 slots across 3 days and 2 providers
- Scenarios cover all 6 types from DESIGN.md

---

### Phase 1: Voice Agent Setup

#### Task 1.1 -- V1 System Prompt
**Sub-agent instruction:** Write the v1 system prompt following the 4-pillar structure from DESIGN.md. This is the deliberately imperfect baseline. Include basic objection handling but leave intentional gaps (no handler for doctor hesitation, telehealth requests, urgency/time pressure, or trust concerns).

**Deliverables:**
- `prompts/v1_system_prompt.json` with fields: version, created_at, created_by, token_count, changelog, prompt, metadata

**Acceptance criteria:**
- Prompt follows the 4-pillar structure (Persona, Context, Rules, Output Format)
- Prompt is under 500 tokens (count via tiktoken or estimate at 4 chars/token)
- TURN-TAKING RULES section is included verbatim from DESIGN.md
- Objection handling covers ONLY: "I'm busy", "check my schedule", "insurance question"
- Deliberately missing: doctor hesitation, telehealth, urgency, trust, cost pushback, cancellation save
- First message is defined: "Hi there, this is Sarah from Greenfield Medical Practice. How can I help you today?"

---

#### Task 1.2 -- ElevenLabs Agent Setup Script
**Sub-agent instruction:** Write a script that creates or updates the ElevenLabs Conversational AI agent via their API, using the v1 system prompt and the agent config template.

**Deliverables:**
- `scripts/setup_agent.py`
  - Reads `prompts/v1_system_prompt.json` for the prompt
  - Reads `config/agent_config.json` for the agent configuration template
  - Creates agent via ElevenLabs API if no agent_id in env, updates if agent_id exists
  - Registers webhook tools (check_availability, record_outcome) with n8n webhook URLs from env
  - Outputs the agent_id and widget embed snippet
  - Full error handling and logging

**Acceptance criteria:**
- Running `python scripts/setup_agent.py` with valid env vars creates an agent
- Script outputs the embed code for the web widget
- Script is idempotent (running twice doesn't create duplicate agents)

---

#### Task 1.3 -- Web Embed Page
**Sub-agent instruction:** Create a minimal, clean HTML page that embeds the ElevenLabs Conversational AI widget. Single file, no build tools.

**Deliverables:**
- `web/index.html`
  - ElevenLabs widget embed using their JS SDK
  - Agent ID loaded from a config object at the top of the script (not hardcoded in the embed call)
  - Clean, minimal UI: centered widget, practice name header, disclaimer footer
  - Disclaimer text: "This is an AI demo agent for AutoCallAI. No real appointments are being scheduled. This is a prototype for demonstration purposes only."
  - Responsive, works on desktop Chrome/Edge
  - No external CSS frameworks. Inline styles, kept minimal.

**Acceptance criteria:**
- Opening index.html in browser shows the widget
- Clicking the widget starts a voice conversation (requires valid agent_id)
- Disclaimer is clearly visible

---

### Phase 2: n8n Workflow Logic

#### Task 2.1 -- Call Handler Workflow (n8n JSON)
**Sub-agent instruction:** Generate an importable n8n workflow JSON for the live call handler. This workflow handles webhook calls FROM ElevenLabs during active conversations.

**Deliverables:**
- `n8n/workflow_call_handler.json` -- importable n8n workflow with:
  - Webhook Trigger node (POST, path: `/call-handler`)
  - Switch node routing on `tool_name` field:
    - `check_availability` -> Code node returning slots from mock data
    - `record_outcome` -> Code node formatting call data + HTTP Request node triggering the analysis workflow
  - Respond to Webhook nodes returning proper JSON for each branch
  - All Code nodes include try/catch error handling
  - Comments on each node explaining its purpose

**Acceptance criteria:**
- JSON is valid and importable into n8n (test by pasting into n8n import dialog)
- check_availability returns the mock slots JSON structure from DESIGN.md
- record_outcome accepts: outcome, transcript, duration, patient_info
- record_outcome forwards the full payload to the analysis workflow webhook URL (configurable)

---

#### Task 2.2 -- Analysis Workflow (n8n JSON)
**Sub-agent instruction:** Generate the post-call analysis n8n workflow JSON. This is the judge pipeline that scores calls and generates prompt revisions.

**Deliverables:**
- `n8n/workflow_analysis.json` -- importable n8n workflow with:
  - Webhook Trigger node (POST, path: `/analyze-call`)
  - Code node: loads current prompt version from a workflow static variable or input
  - HTTP Request node (Judge): POST to Gemini API with transcript + prompt + rubric. Include the full judge system prompt from DESIGN.md in the request body. Headers include the API key from n8n credentials/env.
  - Code node (Parse Judge): extracts scores, failure points, changelog from Gemini response. Handles malformed JSON gracefully (retry once if parse fails).
  - HTTP Request node (Prompt Reviser): POST to Gemini with current prompt + judge output + revision instructions from DESIGN.md.
  - Code node (Format Outputs): structures the three output JSONs (call log, analysis report, prompt version)
  - HTTP Request node (Update Agent): PATCH to ElevenLabs API to update agent system prompt
  - Respond to Webhook: returns the new prompt version number and score summary
  - Error handling: if any Gemini call fails, the workflow should still save the raw transcript and log the error rather than losing the call data

**Acceptance criteria:**
- JSON is valid and importable into n8n
- Judge prompt matches DESIGN.md specification exactly
- Rubric is embedded in the judge call, not hardcoded as a string (loaded from a Set node or Code node reading config)
- Gemini API calls use the correct endpoint and auth header format
- ElevenLabs update call uses the correct PATCH endpoint and payload structure

---

### Phase 3: Self-Improvement Engine

#### Task 3.1 -- Local Analysis Script (Offline Alternative)
**Sub-agent instruction:** Write a Python script that replicates the n8n analysis workflow locally. This serves as a fallback if n8n webhook timing is tricky, and as a standalone demo of the feedback loop.

**Deliverables:**
- `scripts/analyze_call.py`
  - Accepts a call transcript JSON file path as argument
  - Reads current prompt version from `prompts/` (latest by version number)
  - Reads rubric from `config/rubric.json`
  - Calls Gemini 2.0 Flash as judge (using `utils/api_client.py`)
  - Parses scores, failure points
  - Calls Gemini as prompt reviser
  - Writes outputs: new call log to `calls/`, analysis report to `analysis/`, new prompt to `prompts/`
  - Optionally updates ElevenLabs agent (flag: `--update-agent`)
  - Prints a human-readable summary to stdout: dimension scores, total score, top failures, changelog

**Acceptance criteria:**
- `python scripts/analyze_call.py calls/call_001.json` produces a new prompt version
- `python scripts/analyze_call.py calls/call_001.json --update-agent` also updates ElevenLabs
- Output summary is readable and shows the score breakdown clearly
- All API calls have error handling and retry logic

---

#### Task 3.2 -- Prompt Version Manager
**Sub-agent instruction:** Write a utility script for managing prompt versions -- viewing history, comparing versions, and rolling back if needed.

**Deliverables:**
- `scripts/generate_prompt_version.py`
  - Subcommands:
    - `list` -- shows all prompt versions with dates, token counts, and avg scores
    - `diff <v1> <v2>` -- shows text diff between two prompt versions (unified diff format)
    - `current` -- prints the current (latest) prompt version number and its metadata
    - `rollback <version>` -- copies specified version as the new latest and optionally updates ElevenLabs agent
  - Uses `utils/file_io.py` for all file operations

**Acceptance criteria:**
- `python scripts/generate_prompt_version.py list` shows a formatted table
- `python scripts/generate_prompt_version.py diff v1 v2` shows meaningful differences
- Rollback creates a new version file (never overwrites existing versions)

---

### Phase 4: Integration + Demo Prep

#### Task 4.1 -- End-to-End Wiring Verification Script
**Sub-agent instruction:** Write a script that verifies the full pipeline is correctly wired without making a real voice call.

**Deliverables:**
- `scripts/verify_setup.py`
  - Checks: ElevenLabs API key valid (GET /v1/user)
  - Checks: Gemini API key valid (simple completion test)
  - Checks: n8n webhook URLs respond (sends test POST, expects 200)
  - Checks: ElevenLabs agent exists and has correct tool webhooks configured
  - Checks: prompts/v1_system_prompt.json exists and is valid
  - Checks: config/ files all exist and parse
  - Prints a checklist with pass/fail for each check
  - Exits 0 if all pass, 1 if any fail

**Acceptance criteria:**
- Running with valid env vars prints all green checks
- Running with a missing env var prints a clear error for that specific var
- Running with a wrong API key prints which key is invalid

---

#### Task 4.2 -- README
**Sub-agent instruction:** Write a comprehensive README for the public GitHub repo.

**Deliverables:**
- `README.md` with sections:
  - Project title + one-line description
  - Architecture diagram (ASCII, matching DESIGN.md)
  - How it works (3-paragraph explanation: voice agent, feedback loop, prompt evolution)
  - Quick start (step-by-step: clone, set env vars, run setup_agent.py, open web page, make a call, run analysis)
  - Demo video link placeholder (Loom URL to be added after recording)
  - Tech stack table (ElevenLabs, Gemini, n8n, etc. with versions)
  - Project structure (tree output with one-line descriptions per file)
  - How the self-improvement loop works (with example: v1 score -> v2 changes -> v2 score)
  - Prompt evolution section (link to prompts/ directory, explain the versioning)
  - Limitations section (free tier constraints, not HIPAA compliant, mock data only)
  - License (MIT)
  - No badges, no emojis. Clean, professional tone.

**Acceptance criteria:**
- A developer can go from clone to working demo by following the README alone
- Architecture diagram matches DESIGN.md
- All scripts mentioned in the README actually exist in the repo

---

## Sub-Agent Delegation Protocol

When executing each task, follow this protocol:

1. **Read context:** Before writing any code, re-read the relevant section of DESIGN.md for that task. If the task references data models, re-read the data model section. If it references API calls, re-read the configuration section.

2. **Plan before code:** Write a 3-5 line plan as a code comment at the top of each file: what this file does, what it depends on, what it outputs.

3. **Implement:** Write the full implementation. No stubs, no TODOs, no placeholder functions. Every function must be complete.

4. **Verify internally:** Before marking a task complete, check:
   - Does it import from `utils/` correctly?
   - Are all env vars referenced in `.env.example`?
   - Is every API call wrapped in try/catch?
   - Is there logging at each significant step?
   - Are there no hardcoded values that should come from config?

5. **Report:** After completing a task, output:
   - Files created/modified (list)
   - Any deviations from DESIGN.md (with rationale)
   - Blockers for the next task (if any)

## Context Management Strategy

Each task is designed to fit within a single agent context window. If a task requires knowledge from a previous task's output:
- Reference the file path (e.g., "read prompts/v1_system_prompt.json")
- Do not re-derive or re-generate content that already exists in the repo
- The `utils/` module is the shared bridge between all tasks -- import, don't duplicate

If context is running low during a task:
- Finish the current file completely
- Save progress
- Start a new context with: "Continue AutoCallAI implementation. Last completed: Task X.Y. Next: Task X.Z. Read DESIGN.md section [relevant section] and the files created so far in [directory]."

## Final Verification

After all tasks are complete, run this checklist:

- [ ] `python scripts/verify_setup.py` passes all checks
- [ ] `python scripts/setup_agent.py` creates/updates the agent successfully
- [ ] Opening `web/index.html` shows the voice widget
- [ ] Making a test call triggers the n8n call handler workflow
- [ ] End of call triggers the analysis workflow
- [ ] `python scripts/analyze_call.py calls/call_001.json` produces v2 prompt
- [ ] `python scripts/generate_prompt_version.py diff v1 v2` shows meaningful changes
- [ ] All JSON files in `calls/`, `analysis/`, `prompts/` are valid
- [ ] Git log shows clean, incremental commits per task
- [ ] README quick start instructions work end-to-end
- [ ] No hardcoded API keys, webhook URLs, or secrets anywhere in the codebase