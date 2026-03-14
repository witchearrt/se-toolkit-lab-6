# Agent Architecture

## Overview

This project implements a CLI agent (`agent.py`) that connects to an LLM and answers questions. The agent forms the foundation for subsequent tasks where tools and domain knowledge will be added.

## LLM Provider

**Provider:** Qwen Code API (self-hosted on VM)

**Model:** `qwen3-coder-plus`

**Why this choice:**

- 1000 free requests per day — sufficient for development and testing.
- Works from Russia without restrictions.
- No credit card required.
- OpenAI-compatible API — easy integration.
- Strong tool-calling capabilities for future tasks.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │────▶│   agent.py   │────▶│   LLM API       │
│  "Question"     │     │  (CLI tool)  │     │  (Qwen Code)    │
└─────────────────┘     └──────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  JSON Output │
                        │  {answer,    │
                        │   tool_calls}│
                        └──────────────┘
```

### Components

| Component | Description |
|-----------|-------------|
| `agent.py` | Main CLI entry point. Parses arguments, loads config, calls LLM, outputs JSON. |
| `AgentSettings` | Pydantic settings class. Loads from `.env.agent.secret`. |
| `call_llm()` | Async function that makes HTTP POST to LLM API. |
| `create_response()` | Formats the answer into the required JSON structure. |

### Data Flow

1. User runs: `uv run agent.py "What is REST?"`
2. `agent.py` reads `.env.agent.secret` for API credentials.
3. Agent sends POST request to `{LLM_API_BASE}/chat/completions`.
4. LLM returns response with answer.
5. Agent outputs JSON to stdout: `{"answer": "...", "tool_calls": []}`.
6. All logs go to stderr.

## Configuration

### Environment File: `.env.agent.secret`

Copy from `.env.agent.example`:

```bash
cp .env.agent.example .env.agent.secret
```

Edit `.env.agent.secret`:

```ini
# Your LLM provider API key
LLM_API_KEY=your-llm-api-key-here

# API base URL (OpenAI-compatible endpoint)
LLM_API_BASE=http://<your-vm-ip>:<qwen-api-port>/v1

# Model name
LLM_MODEL=qwen3-coder-plus
```

> **Note:** This file is gitignored. Never commit API keys.

## How to Run

### Basic Usage

```bash
uv run agent.py "What does REST stand for?"
```

### Expected Output

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — valid JSON output. |
| 1 | Error — missing args, config error, API error, timeout. |

## Dependencies

All dependencies are already in `pyproject.toml`:

| Package | Purpose |
|---------|---------|
| `httpx` | Async HTTP client for API calls. |
| `pydantic-settings` | Environment variable loading. |

No new dependencies required.

## Testing

Run unit tests:

```bash
uv run pytest backend/tests/unit/test_agent_task1.py -v
```

The test:

1. Runs `agent.py` as a subprocess.
2. Parses stdout as JSON.
3. Asserts `answer` and `tool_calls` fields exist.

## Future Extensions (Tasks 2–3)

- **Tools:** Add `read_file`, `query_api`, and other tools.
- **Agentic Loop:** Enable multi-step reasoning with tool calls.
- **Domain Knowledge:** Load wiki documentation for context.
- **Enhanced System Prompt:** Add instructions for tool usage.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Error loading settings` | Ensure `.env.agent.secret` exists with all required variables. |
| `HTTP error from LLM API: 401` | Check `LLM_API_KEY` is correct. |
| `HTTP error from LLM API: 404` | Check `LLM_API_BASE` URL is correct (should end with `/v1`). |
| `Request error` | Verify network connectivity to the VM. |
| `Request timed out` | LLM took >60 seconds. Try again or use a faster model. |
