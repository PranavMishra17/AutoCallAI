# AutoCallAI -- Design Document

Self-improving AI voice agent that conducts appointment-setting calls for a general medical practice, analyzes outcomes, and iteratively optimizes its own script using LLM reasoning + n8n workflow orchestration.

## Architecture Overview

```
                    REAL-TIME VOICE LAYER                    ORCHESTRATION LAYER
                    (ElevenLabs Managed)                     (n8n Cloud)

 User Browser ──────> ElevenLabs Widget ──────> n8n Webhook (business logic)
 (microphone)         │                         │
                      │ STT: Deepgram Nova-2    │ - Appointment slot lookup
                      │ LLM: Gemini 2.0 Flash   │ - Call state tracking
                      │ TTS: ElevenLabs Turbo    │ - Conversation memory
                      │ Turn Detection: built-in │
                      │                         │
                      │ <── response back ──────│
                      │
                      │ POST-CALL
                      │
                      └──> n8n Webhook (end-of-call) ──> Judge Pipeline
                                                          │
                                                          │ Gemini 2.0 Flash
                                                          │ scores transcript
                                                          │ identifies failures
                                                          │ generates revised prompt
                                                          │
                                                          └──> Git commit
                                                               prompts/vN.json
                                                               calls/call_NNN.json
                                                               analysis/iteration_N.json
```

### Component Responsibilities

**ElevenLabs Conversational AI** handles the entire real-time voice pipeline: speech-to-text (Deepgram Nova-2 under the hood), LLM reasoning (Gemini 2.0 Flash), text-to-speech (ElevenLabs Turbo v2.5), turn detection, interruption handling, and WebRTC audio streaming. We treat this as a managed black box -- no self-hosted infra.

**n8n Cloud** handles everything that is NOT real-time audio: webhook endpoints for ElevenLabs tool calls (checking appointment availability, recording call outcomes), post-call analysis orchestration (trigger the judge, store results), and prompt version management.

**Gemini 2.0 Flash** serves dual roles: (1) the "brain" inside ElevenLabs during live calls, and (2) the "judge" in n8n post-call analysis. Same model, different system prompts, different contexts.

**Git repo** is the single source of truth for prompt versions, call transcripts, scores, and improvement history. Every change is a commit, every improvement is a diff.

---

## Voice AI Pipeline -- Best Practices

### Latency Budget

Human conversation has a ~200ms natural response window. Exceeding 800ms end-to-end triggers noticeable friction. Exceeding 3 seconds causes conversation breakdown. The ElevenLabs managed pipeline targets:

| Stage | Target | Notes |
|-------|--------|-------|
| STT (Deepgram Nova-2) | 100-200ms | Streaming, interim results enabled |
| LLM (Gemini 2.0 Flash) | 200-400ms | Fastest on ElevenLabs platform |
| TTS (ElevenLabs Turbo v2.5) | 100-200ms | Streaming, starts as LLM outputs first tokens |
| Total E2E | 400-800ms | Within acceptable range |

Design implications: keep the system prompt under 500 tokens. Every extra token adds to time-to-first-byte. Use tool calls for detailed knowledge retrieval rather than stuffing everything into the prompt.

### Three-Layer Interruption Handling

ElevenLabs Conversational AI provides built-in turn detection, but understanding the layers matters for prompt design and debugging:

**Layer 1 -- Voice Activity Detection (VAD):**
Continuous audio monitoring at 10-20ms frame intervals. Detects speech vs silence. ElevenLabs uses this as the base signal. The silence threshold for end-of-turn is 300-500ms. For barge-in detection during agent speech, the threshold drops to ~200ms.

**Layer 2 -- Semantic Turn Analysis:**
VAD alone causes false positives from backchannels ("mm-hmm", "yeah", "right"), coughs, and ambient noise. ElevenLabs layers semantic analysis on top -- distinguishing a genuine interruption ("actually wait, I need to ask something") from a backchannel ("uh-huh") where the agent should keep speaking. This is handled internally by their pipeline.

**Layer 3 -- Context-Aware Rules (our responsibility):**
We control this through the system prompt. Certain utterances should be non-interruptible (HIPAA compliance disclosures, appointment confirmations). The prompt must instruct the agent on when to yield vs hold the floor:

```
TURN-TAKING RULES:
- Wait 300-500ms after patient stops speaking before responding
- If patient speaks again during your wait, reset and listen
- If patient interrupts you mid-response, stop immediately and listen
- Treat "uh-huh", "yeah", "okay", "right" as backchannels -- continue speaking
- NEVER talk over the patient
- When confirming appointment details, say the full confirmation before pausing
- If you detect frustration (raised voice, "no no no"), pause and acknowledge
```

### Voice-Specific Design Rules

These rules separate production-quality voice agents from demos that sound robotic:

**Sentence length:** 8-12 words max per sentence in the system prompt's example responses. Long sentences sound unnatural when spoken. "I can help you schedule that. What day works best for you?" beats "I would be happy to assist you in scheduling an appointment at your earliest convenience."

**Avoid visual formatting in prompts:** No bullets, no headers, no markdown. The LLM may attempt to "speak" formatting characters. Write the prompt as continuous natural language instructions.

**Include filler acknowledgments:** Instruct the agent to use brief verbal signals: "Got it", "Sure thing", "Makes sense", "Of course". These make the agent sound human and buy processing time.

**Emotion-aware adaptation:** Add explicit instructions for detecting and responding to caller mood: "If the caller sounds rushed, be concise and skip pleasantries. If they sound confused, slow down and offer to repeat. If they sound frustrated, acknowledge their feeling before proceeding."

**Mirror pacing:** "Match the caller's speaking speed. If they speak quickly, respond efficiently. If they speak slowly, don't rush them."

**Explicit negative constraints:** "Never say 'as an AI' or 'I'm just a virtual assistant.' Never apologize more than once for the same issue. Never ask more than one question at a time. Never use medical jargon the patient hasn't used first."

---

## System Prompt Engineering

### The 4-Pillar Structure

Every voice agent system prompt follows four sections. This is industry standard across Vapi, Retell, Synthflow, and ElevenLabs:

**Pillar 1 -- Persona:**
```
You are Sarah, a friendly and efficient receptionist at Greenfield Medical Practice.
You're warm but professional, and you genuinely care about helping patients get the
care they need. You speak in short, clear sentences. You use phrases like "Of course",
"Let me check that for you", and "No problem at all."
```

Always use "You are [Name]" -- not "Act like" or "Pretend to be." The identity frame produces more consistent behavior than role-play framing.

**Pillar 2 -- Context:**
```
PRACTICE INFORMATION:
- Name: Greenfield Medical Practice
- Type: General/family medicine
- Providers: Dr. Emily Chen (Mon-Thu), Dr. James Park (Tue-Fri)
- Hours: Monday-Friday 8:00 AM to 5:00 PM, closed weekends
- New patient appointments: 45 minutes
- Follow-up appointments: 20 minutes
- Location: 123 Health Avenue, Suite 200
- Accepted insurance: Blue Cross, Aetna, United, Cigna, Medicare
- New patients welcome, no referral needed
```

Keep this concise and factual. The agent retrieves from this during conversation -- bloating it adds latency.

**Pillar 3 -- Rules:**
```
CALL FLOW:
1. Greet warmly, confirm you're speaking with the right person
2. Ask if they're a new or existing patient
3. Ask what they'd like to be seen for (brief description only -- no diagnosis)
4. Offer available appointment slots (use tool to check availability)
5. Confirm: patient name, date, time, provider
6. Ask about insurance (just the carrier name)
7. Wrap up with confirmation and any prep instructions

RULES:
- Ask ONE question at a time. Never stack questions.
- If asked about symptoms or medical advice, say: "I'm not able to provide medical
  advice, but Dr. Chen or Dr. Park can absolutely help with that during your visit."
- If asked about costs: "That depends on your insurance coverage. Our billing team
  can give you a detailed estimate -- want me to have them call you?"
- If the caller wants to cancel: "No problem at all. Can I help you reschedule
  for a different time?"
- If the caller is upset: "I'm sorry you're dealing with that. Let me see what
  I can do to help."
- NEVER fabricate appointment availability. Use the check_availability tool.
- NEVER provide a diagnosis or medical opinion.
- Maximum 3 attempts to schedule. If caller declines 3 times, offer to have
  someone call them back.
```

**Pillar 4 -- Output Format (end-of-call):**
```
END OF CALL:
When the call ends, internally classify the outcome as one of:
- BOOKED: appointment successfully scheduled
- CALLBACK: caller requested a callback
- DECLINED: caller not interested
- DROPPED: caller hung up or disconnected
- TRANSFERRED: caller needed something outside your scope

Store this classification for post-call analysis.
```

### Objection Handling Library (v1 -- deliberately imperfect)

The v1 prompt intentionally leaves gaps in objection handling. This gives the self-improvement loop something to catch and fix. In v1, include only basic handling:

```
OBJECTION HANDLING:
- "I'm busy right now" -> "No problem. When would be a better time to call?"
- "I need to check my schedule" -> "Of course. I can also hold for a moment if
  you'd like to check now."
- "Do you take [insurance]?" -> Check the accepted list. If yes: "Yes, we do accept
  [insurance]." If not listed: "I'm not 100% sure about that one. Let me have our
  billing team verify and call you back."
```

Deliberately MISSING from v1 (for the judge to catch):
- "I'll just go to urgent care instead" (no urgency counter)
- "I don't like going to the doctor" (no empathy + reframe)
- "Can I do a telehealth visit instead?" (no alternative offering)
- "I heard bad reviews about that doctor" (no trust-building response)
- Price/cost pushback beyond the basic insurance redirect

This creates clear "before/after" improvement material for the demo.

---

## Self-Improvement Loop -- The LLM-as-Judge Pipeline

### Loop Architecture

```
CALL ENDS
    │
    v
n8n receives end-of-call webhook from ElevenLabs
    │
    ├── Extract: full transcript, call duration, outcome classification
    │
    v
STORE RAW DATA
    │
    ├── Write calls/call_NNN.json (transcript + metadata)
    │
    v
JUDGE EVALUATION (Gemini 2.0 Flash, separate call)
    │
    ├── Input: transcript + current system prompt + scoring rubric
    │
    ├── Output: structured JSON with per-dimension scores, failure analysis,
    │           and specific prompt revision suggestions
    │
    v
PROMPT REVISION (Gemini 2.0 Flash, separate call)
    │
    ├── Input: current prompt + judge critique + all prior call scores
    │
    ├── Output: revised system prompt with tracked changes
    │
    v
STORE + VERSION
    │
    ├── Write analysis/iteration_N_report.json
    ├── Write prompts/vN+1_system_prompt.json
    ├── Update ElevenLabs agent config with new prompt (via API)
    │
    v
NEXT CALL uses updated prompt
```

### Scoring Rubric (6 Dimensions)

The judge evaluates each call on a 1-5 scale across these dimensions:

```json
{
  "rubric": {
    "appointment_conversion": {
      "weight": 0.30,
      "description": "Did the agent successfully guide toward booking?",
      "scoring": {
        "5": "Appointment booked with full confirmation",
        "4": "Strong attempt, callback scheduled",
        "3": "Partial progress, interest maintained",
        "2": "Missed clear booking opportunity",
        "1": "Caller lost interest due to agent behavior"
      }
    },
    "objection_handling": {
      "weight": 0.25,
      "description": "Did the agent address concerns effectively?",
      "scoring": {
        "5": "All objections addressed with empathy and resolution",
        "4": "Most objections handled, minor misses",
        "3": "Basic handling, lacked depth on key objection",
        "2": "Fumbled primary objection, generic response",
        "1": "Ignored or argued with caller's concern"
      }
    },
    "conversation_flow": {
      "weight": 0.15,
      "description": "Natural pacing, one question at a time, appropriate pauses",
      "scoring": {
        "5": "Flowed like a natural phone conversation",
        "4": "Mostly natural with minor awkward transitions",
        "3": "Some robotic patterns or stacked questions",
        "2": "Frequently unnatural, multiple stacked questions",
        "1": "Completely scripted feel, no adaptation"
      }
    },
    "information_accuracy": {
      "weight": 0.15,
      "description": "Did the agent provide correct practice information?",
      "scoring": {
        "5": "All information accurate and relevant",
        "4": "Accurate with minor omissions",
        "3": "Mostly accurate, one notable error",
        "2": "Multiple inaccuracies",
        "1": "Fabricated information or hallucinated details"
      }
    },
    "rapport_building": {
      "weight": 0.10,
      "description": "Did the agent build trust and show empathy?",
      "scoring": {
        "5": "Warm, empathetic, caller felt heard",
        "4": "Friendly and professional",
        "3": "Polite but impersonal",
        "2": "Cold or transactional",
        "1": "Rude, dismissive, or argumentative"
      }
    },
    "compliance": {
      "weight": 0.05,
      "description": "No medical advice, no fabricated availability, proper boundaries",
      "scoring": {
        "5": "Perfect boundary maintenance",
        "4": "Minor boundary softness, no harm",
        "3": "Came close to overstepping once",
        "2": "Provided quasi-medical guidance",
        "1": "Gave medical advice or fabricated data"
      }
    }
  }
}
```

### Judge System Prompt

```
You are an expert call center quality analyst evaluating AI voice agent performance.

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
5. Output structured JSON only, no other text

Example failure point:
{
  "moment": "Caller: 'I heard some bad reviews about that practice online.'
             Agent: 'I understand. Would you like to schedule an appointment?'",
  "failure": "Ignored a trust concern. The agent should have acknowledged the
              concern and offered reassurance before redirecting to scheduling.",
  "prompt_fix": "Add to OBJECTION HANDLING: 'Bad reviews/trust concerns' ->
                 'I understand that can be concerning. Dr. Chen and Dr. Park both
                 have excellent patient satisfaction scores, and we welcome you
                 to come meet the team. Many of our happiest patients started
                 with a similar concern.'"
}
```

### Prompt Revision System Prompt

```
You are a prompt engineer specializing in voice AI agent optimization.

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
- If the prompt is approaching 500 tokens, condense existing sections
  rather than cutting new additions.
- Preserve the 4-pillar structure (Persona, Context, Rules, Output Format).
```

### Measuring Improvement Across Iterations

The key metric is **weighted total score** trending upward across iterations:

```
Iteration 1 (calls 1-3):  avg score 2.8 / 5.0
  - v1 prompt, basic objection handling
  - Judge catches: missed urgency counter, no telehealth option, stacked questions

Iteration 2 (calls 4-7):  avg score 3.6 / 5.0
  - v2 prompt with fixes applied
  - Judge catches: still weak on cost pushback, rapport could be warmer

Iteration 3 (calls 8-10): avg score 4.1 / 5.0
  - v3 prompt with refinements
  - Judge notes: significant improvement in objection handling and flow
```

This trajectory is the demo narrative. The Loom recording walks through each iteration showing the prompt diff, a representative call transcript, and the score improvement.

---

## n8n Workflow Design

### Starter Template

Base on n8n template #9429 ("Automated phone receptionist for scheduling with Twilio, ElevenLabs & Claude AI"). Strip Twilio nodes, replace Claude with Gemini HTTP Request nodes.

### Workflow 1: Live Call Handler

**Trigger:** Webhook node (receives tool calls from ElevenLabs during active conversation)

**Nodes:**
1. **Webhook Trigger** -- receives POST from ElevenLabs when agent invokes a tool
2. **Switch Node** -- routes by tool name:
   - `check_availability` -> returns mock appointment slots
   - `record_outcome` -> logs call result
3. **check_availability handler:**
   - Code Node: returns 3 available slots from a hardcoded schedule
   - (No real calendar -- this is a prototype. Slots are deterministic for reproducibility.)
4. **record_outcome handler:**
   - Code Node: formats call data (outcome, duration, patient info)
   - HTTP Request Node: POST to Workflow 2's webhook (triggers analysis)

Mock availability response format:
```json
{
  "available_slots": [
    {"date": "2026-04-13", "time": "10:00 AM", "provider": "Dr. Emily Chen", "type": "New Patient"},
    {"date": "2026-04-14", "time": "2:30 PM", "provider": "Dr. James Park", "type": "New Patient"},
    {"date": "2026-04-15", "time": "9:00 AM", "provider": "Dr. Emily Chen", "type": "New Patient"}
  ]
}
```

### Workflow 2: Post-Call Analysis (Judge Pipeline)

**Trigger:** Webhook node (called by Workflow 1 after each call ends)

**Nodes:**
1. **Webhook Trigger** -- receives call transcript + outcome + metadata
2. **HTTP Request (Judge):**
   - POST to `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`
   - Body: transcript + current prompt + scoring rubric
   - Headers: `x-goog-api-key: {{$env.GEMINI_API_KEY}}`
3. **Code Node (Parse Judge Response):**
   - Extract scores, failure points, prompt fixes from JSON response
   - Calculate weighted total
4. **HTTP Request (Prompt Reviser):**
   - POST to Gemini with current prompt + judge critique
   - Returns revised prompt + changelog
5. **Code Node (Format Outputs):**
   - Structure call log JSON (for calls/ directory)
   - Structure analysis report JSON (for analysis/ directory)
   - Structure new prompt JSON (for prompts/ directory)
6. **HTTP Request (Update ElevenLabs Agent):**
   - PATCH to ElevenLabs API to update the agent's system prompt
   - `https://api.elevenlabs.io/v1/convai/agents/{agent_id}`
   - This makes the next call automatically use the improved prompt
7. **Respond to Webhook** -- returns success confirmation

### ElevenLabs Agent Configuration

Configure via ElevenLabs dashboard or API:

```json
{
  "name": "AutoCallAI - Greenfield Medical",
  "conversation_config": {
    "agent": {
      "prompt": {
        "prompt": "<contents of prompts/v1_system_prompt.json>",
        "llm": "gemini-2.0-flash",
        "temperature": 0.7,
        "max_tokens": 300
      },
      "first_message": "Hi there, this is Sarah from Greenfield Medical Practice. How can I help you today?",
      "language": "en"
    },
    "tts": {
      "model_id": "eleven_turbo_v2_5",
      "voice_id": "<choose a warm, professional female voice>"
    },
    "turn": {
      "mode": "turn_based",
      "silence_threshold_ms": 400
    },
    "tools": [
      {
        "type": "webhook",
        "name": "check_availability",
        "description": "Check available appointment slots. Call this when the patient wants to schedule.",
        "webhook_url": "<n8n webhook URL>/check-availability"
      },
      {
        "type": "webhook",
        "name": "record_outcome",
        "description": "Record the call outcome when the conversation is ending.",
        "webhook_url": "<n8n webhook URL>/record-outcome"
      }
    ]
  }
}
```

---

## Data Models

### Call Log (calls/call_NNN.json)

```json
{
  "call_id": "call_001",
  "timestamp": "2026-04-10T14:30:00Z",
  "duration_seconds": 87,
  "prompt_version": "v1",
  "outcome": "BOOKED",
  "patient_info": {
    "name": "Test Patient",
    "type": "new_patient",
    "insurance": "Blue Cross",
    "reason": "annual checkup"
  },
  "appointment": {
    "date": "2026-04-13",
    "time": "10:00 AM",
    "provider": "Dr. Emily Chen"
  },
  "transcript": [
    {"role": "agent", "text": "Hi there, this is Sarah from Greenfield Medical Practice..."},
    {"role": "user", "text": "Hi, I'm looking to schedule a checkup..."},
    ...
  ],
  "objections_encountered": ["insurance_coverage", "scheduling_flexibility"],
  "notes": "Caller was cooperative, straightforward booking"
}
```

### Analysis Report (analysis/iteration_N_report.json)

```json
{
  "iteration": 1,
  "calls_analyzed": ["call_001", "call_002", "call_003"],
  "prompt_version_evaluated": "v1",
  "aggregate_scores": {
    "appointment_conversion": 3.3,
    "objection_handling": 2.3,
    "conversation_flow": 3.0,
    "information_accuracy": 4.7,
    "rapport_building": 2.7,
    "compliance": 5.0,
    "weighted_total": 3.1
  },
  "top_failure_points": [
    {
      "frequency": "2/3 calls",
      "moment": "Caller expressed hesitation about visiting a new doctor",
      "failure": "Agent moved directly to scheduling without addressing the emotional concern",
      "prompt_fix": "Add empathy-first response for doctor hesitation objections"
    }
  ],
  "strengths_to_preserve": [
    "Accurate practice information in all calls",
    "Clean one-question-at-a-time flow"
  ],
  "prompt_changes": {
    "from_version": "v1",
    "to_version": "v2",
    "changelog": [
      "Added 3 new objection handlers: doctor_hesitation, telehealth_request, urgency_counter",
      "Refined greeting to include patient name confirmation earlier",
      "Added emotion-aware pacing instruction"
    ]
  }
}
```

### Prompt Version (prompts/vN_system_prompt.json)

```json
{
  "version": "v1",
  "created_at": "2026-04-10T10:00:00Z",
  "created_by": "manual",
  "token_count": 420,
  "changelog": "Initial prompt -- baseline with deliberately sparse objection handling",
  "prompt": "<full system prompt text>",
  "metadata": {
    "avg_score_during_use": null,
    "calls_made_with_this_version": 0,
    "replaced_by": null
  }
}
```

---

## Feedback Loop -- Best Practices

### What Makes a Good Self-Improvement Signal

The quality of the feedback loop depends on the quality of the signal. These principles keep the loop honest:

**Grade on a spectrum, not binary.** A 1-5 rubric across 6 dimensions gives 30 data points per call vs a single "pass/fail." This lets the judge identify which specific dimension degraded even when the overall score improved.

**Quote before you critique.** The judge must cite the exact transcript moment before offering a fix. This prevents hallucinated critiques and makes the improvement traceable.

**Preserve what works.** Every revision must explicitly protect high-scoring sections. Without this constraint, the reviser may "improve" the prompt in ways that regress previously good behavior. The instruction "Never remove an objection handler that scored 4+ in prior calls" acts as a ratchet.

**Minimal edits per iteration.** Large rewrites between versions make it impossible to attribute improvement to a specific change. Surgical fixes (add one objection handler, tweak one pacing instruction) create clear cause-effect chains.

**Track regression.** If iteration N+1 scores lower than iteration N on any dimension, the analysis report must flag it and the next revision must investigate. This prevents the optimizer from thrashing.

### Avoiding Common Feedback Loop Failures

**Overfitting to the judge's preferences:** The judge is also an LLM (Gemini 2.0 Flash). It has biases. Mitigate by keeping the rubric explicit and asking the judge to justify scores against the rubric criteria, not its own taste.

**Prompt bloat:** Each iteration adds tokens. Without a token budget constraint (500 tokens max), the prompt grows until it hurts latency. The reviser must condense when approaching the limit.

**Echo chamber:** The same model (Gemini) is both the agent and the judge. It may rate its own outputs more favorably. Mitigate by making the rubric behavioral and transcript-evidence-based rather than subjective.

**Catastrophic forgetting:** v3 fixes a problem from v1 that v2 already fixed differently, reintroducing the v1 failure. Mitigate by including the full changelog history in the reviser's context so it sees what was already tried.

---

## Demo Execution Plan

### Pre-Recording Setup

1. Deploy n8n workflows (import JSON, configure webhook URLs, set env vars)
2. Configure ElevenLabs agent with v1 system prompt
3. Embed the ElevenLabs widget on a simple HTML page
4. Test one throwaway call to verify the full pipeline (ElevenLabs -> n8n -> judge -> prompt update)

### Recording Plan (Loom, ~8-10 minutes)

**Segment 1: Architecture Overview (1 min)**
- Show the repo structure
- Show the n8n workflow canvas
- Explain the feedback loop in one sentence

**Segment 2: Iteration 1 -- Baseline (3 min)**
- Show v1 prompt (highlight deliberately sparse objection handling)
- Make 2-3 calls with different scenarios:
  - Call A: straightforward booking (should succeed)
  - Call B: caller has objection the prompt doesn't cover (should fumble)
  - Call C: caller is hesitant/emotional (should feel robotic)
- Show the judge's analysis in n8n execution log
- Show the scores and failure points

**Segment 3: Iteration 2 -- Improvement (3 min)**
- Show the v2 prompt diff (highlight new objection handlers)
- Make 2-3 more calls with similar scenarios
- Show improved handling of the same objections that failed in iteration 1
- Show the score improvement in the analysis report

**Segment 4: Results (1 min)**
- Side-by-side: v1 scores vs v2 scores
- Git log showing the prompt evolution
- Key takeaway: the agent learned from its failures automatically

### Test Call Scenarios (scripted for reproducibility)

Each scenario is a "character" the human caller plays:

| Scenario | Character | Key Objection | Expected v1 Failure |
|----------|-----------|---------------|---------------------|
| Easy booking | Cooperative new patient | None | Should succeed (baseline) |
| Insurance concern | Worried about cost | "Does my insurance cover this?" | Basic handling only |
| Doctor hesitation | Nervous about new doctor | "I heard mixed reviews" | No handler in v1 |
| Time pressure | Very busy, impatient | "I don't have time for this" | No urgency reframe |
| Telehealth request | Prefers virtual visit | "Can I just do video?" | No alternative offering |
| Cancellation save | Wants to cancel existing | "I want to cancel my appointment" | Minimal retention effort |

Run scenarios 1-3 in iteration 1, then 1-3 again (plus 4-5) in iteration 2 to show improvement on the same objection types.

---

## Security and Compliance Notes

- No real patient data is used. All callers are the developer role-playing test scenarios.
- No real medical practice is represented. "Greenfield Medical Practice" is fictional.
- ElevenLabs free tier data is processed per their standard terms (not HIPAA). Acceptable for a demo; would require their Enterprise tier for production.
- Gemini API calls go through Google AI Studio, not Vertex AI. No BAA. Again, acceptable for demo.
- The web widget should display a clear notice: "This is an AI demo agent. No real appointments are being scheduled."

---

## Estimated Build Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Setup accounts + configure ElevenLabs agent | 2-3 hours | Working voice widget with v1 prompt |
| Build n8n Workflow 1 (live call handler) | 2-3 hours | Webhook endpoints, mock availability |
| Build n8n Workflow 2 (judge pipeline) | 3-4 hours | Full analysis + prompt revision chain |
| Build web embed page | 1 hour | Simple HTML with widget + disclaimer |
| Run iteration 1 (3 calls + analysis) | 1-2 hours | v2 prompt generated, call logs committed |
| Run iteration 2 (3-4 calls + analysis) | 1-2 hours | v3 prompt generated, improvement documented |
| Record Loom demo | 1-2 hours | 8-10 min walkthrough |
| Polish README + repo | 1-2 hours | Public repo ready for evaluation |
| **Total** | **~12-18 hours** | |