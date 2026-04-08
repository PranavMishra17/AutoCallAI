# AutoCallAI
Self-improving AI voice agent that simulates sales calls, analyzes outcomes, and iteratively optimizes its script using LLM reasoning + workflow orchestration (n8n)

# TASK

## **Self-Improving Call Center Agent**

**Objective**: Build an AI agent that conducts sales calls, analyzes outcomes, and iteratively improves its own script.

**Reference Stack**:

- **LLM**: Gemini 3.1 Flash Live, Claude 3.5, or open-source alternative
- **Voice**: Wispr Flow, ElevenLabs, or mock STT/TTS for prototyping
- **Memory**: Conversation history + outcome aggregation for script optimization
- **Workflow**: n8n/Dify for call flow orchestration

**Success Criteria**:

- Agent can simulate a sales conversation (voice)
- Implements a feedback loop: outcome → analysis → script adjustment
- Documents the improvement logic (e.g., "When objection X occurs, try response Y")
- Handles at least 2 iteration cycles in the demo
