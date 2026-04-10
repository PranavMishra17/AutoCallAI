# AutoCallAI -- Prerequisites

## Accounts (All Free Tier)

| Service | What For | Sign Up | Free Tier Limit |
|---------|----------|---------|-----------------|
| ElevenLabs | Voice agent (STT + TTS + Conversational AI) | https://elevenlabs.io/sign-up | 10,000 credits/mo (~10-15 min conversation) |
| Google AI Studio | Gemini 2.0 Flash API key | https://aistudio.google.com | 15 RPM, 1M tokens/day |
| n8n Cloud | Workflow orchestration | https://n8n.io/cloud | 14-day trial, 20 workflows |
| GitHub | Public repo + version-controlled call logs | https://github.com | Unlimited public repos |

## API Keys to Obtain

1. **ElevenLabs API Key** -- Dashboard > Profile + API Key > copy key
2. **Google AI Studio API Key** -- https://aistudio.google.com/apikey > Create API Key
3. **n8n Cloud Webhook URL** -- auto-generated when you create a Webhook trigger node

## Local Development

### Required

- Node.js >= 18 (for any local scripting / ElevenLabs SDK)
- Python >= 3.10 (for analysis scripts, optional)
- Git (version control for prompt iterations)
- A modern browser with microphone access (Chrome/Edge recommended -- ElevenLabs widget uses WebRTC)

### Recommended

- Claude Code with n8n skills installed (see Tooling below)
- A quiet room for test calls (background noise triggers false barge-ins)

## Tooling (Claude Code -- Optional but Accelerates Dev)

### n8n MCP Server + Skills

```bash
# MCP server -- gives Claude Code full n8n node knowledge
# Add to .mcp.json or claude_desktop_config.json:
{
  "mcpServers": {
    "n8n-mcp": {
      "command": "npx",
      "args": ["n8n-mcp"],
      "env": {
        "MCP_MODE": "stdio",
        "LOG_LEVEL": "error",
        "DISABLE_CONSOLE_OUTPUT": "true"
      }
    }
  }
}

# Skills -- teaches Claude Code to generate valid n8n workflows
git clone https://github.com/czlonkowski/n8n-skills.git
cp -r n8n-skills/skills/* ~/.claude/skills/
```

### ElevenLabs MCP Server

```json
{
  "mcpServers": {
    "ElevenLabs": {
      "command": "uvx",
      "args": ["elevenlabs-mcp"],
      "env": {
        "ELEVENLABS_API_KEY": "<your-key>"
      }
    }
  }
}
```

### Voice AI Development Skill

```bash
# Covers Deepgram, ElevenLabs, Vapi, LiveKit patterns
# From: https://agentskills.so/skills/davila7-claude-code-templates-voice-ai-development
# Download and place in ~/.claude/skills/voice-ai-development/
```

## Repository Structure (Target)

```
AutoCallAI/
  README.md                    # Project overview + demo link
  PREREQUISITES.md             # This file
  DESIGN.md                    # Architecture + design decisions
  prompts/
    v1_system_prompt.json      # Initial system prompt
    v2_system_prompt.json      # Post-iteration-1 revision
    v3_system_prompt.json      # Post-iteration-2 revision
  calls/
    call_001.json              # Transcript + score + critique
    call_002.json
    ...
  analysis/
    iteration_1_report.json    # Judge output: scores, failure points, recommendations
    iteration_2_report.json
  n8n/
    workflow_main.json          # Exported n8n workflow (importable)
    workflow_analysis.json      # Post-call analysis workflow
  web/
    index.html                  # ElevenLabs widget embed page
  scripts/
    analyze_call.py             # (Optional) local analysis helper
  .gitignore
```

## Free Tier Budget Planning

With 10 test calls averaging ~90 seconds each:

| Resource | Usage | Free Tier | Remaining |
|----------|-------|-----------|-----------|
| ElevenLabs credits | ~15 min total | 10,000 credits | Tight -- keep calls under 90s |
| Gemini 2.0 Flash | ~50 API calls (10 calls + 10 judge calls + prompt gen) | 1M tokens/day | Plenty |
| n8n Cloud | ~50 workflow executions | 14-day trial | Plenty |
| GitHub | ~30 commits | Unlimited | N/A |

**Important:** ElevenLabs free tier is the bottleneck. Practice the call flow in text before burning voice credits. Each wasted call costs ~1,000 credits.

## Pre-Development Checklist

- [ ] ElevenLabs account created, API key obtained
- [ ] Google AI Studio API key generated
- [ ] n8n Cloud trial activated
- [ ] GitHub repo initialized (`AutoCallAI`, public)
- [ ] Browser microphone permissions tested
- [ ] Local Node.js environment verified (`node -v` >= 18)
- [ ] (Optional) Claude Code n8n skills installed
- [ ] Loom or OBS installed for demo recording