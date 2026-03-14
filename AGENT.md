# Agent Architecture

## Overview

This project implements a system agent (`agent.py`) that can read project documentation, query the backend API, and answer questions with source references. The agent has three tools (`read_file`, `list_files`, `query_api`) and an agentic loop that allows multi-step reasoning.

## LLM Provider

**Provider:** Qwen Code API (self-hosted on VM)

**Model:** `qwen3-coder-plus`

**Why this choice:**

- 1000 free requests per day — sufficient for development and testing.
- Works from Russia without restrictions.
- No credit card required.
- OpenAI-compatible API with function calling support.
- Strong tool-calling capabilities.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │────▶│   agent.py   │────▶│   LLM API       │
│  "Question"     │     │  (CLI tool)  │     │  (Qwen Code)    │
└─────────────────┘     └──────────────┘     └─────────────────┘
                               │                      │
                               │◀──── tool calls ─────│
                               ▼                      │
                        ┌──────────────┐              │
                        │  Tools:      │──────────────┘
                        │  - read_file │
                        │  - list_files│
                        │  - query_api │
                        └──────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  JSON Output │
                        │  {answer,    │
                        │   source,    │
                        │   tool_calls}│
                        └──────────────┘
```

### Components

| Component | Description |
|-----------|-------------|
| `agent.py` | Main CLI entry point. Implements agentic loop. |
| `AgentSettings` | Pydantic settings class. Loads LLM config from `.env.agent.secret`. |
| `AgentConfig` | Pydantic settings class. Loads API config from `.env.docker.secret`. |
| `read_file()` | Tool: reads a file from the project. |
| `list_files()` | Tool: lists files in a directory. |
| `query_api()` | Tool: calls the backend API with authentication. |
| `validate_path()` | Security: prevents directory traversal. |
| `call_llm()` | Async function that makes HTTP POST to LLM API. |
| `run_agent_loop()` | Agentic loop: call LLM → execute tools → repeat. |
| `create_response()` | Formats the answer into JSON structure. |

## Tools

### `read_file`

Read a file from the project repository.

**Parameters:**
- `path` (string, required) — relative path from project root.

**Returns:** File contents as string (up to 30000 chars), or error message.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read a file from the project repository. Use for documentation (wiki/) and source code.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py')"
      }
    },
    "required": ["path"]
  }
}
```

### `list_files`

List files and directories at a given path.

**Parameters:**
- `path` (string, required) — relative directory path from project root.

**Returns:** Newline-separated listing.

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories at a given path. Use to discover files in a directory.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root (e.g., 'wiki', 'backend/app/routers')"
      }
    },
    "required": ["path"]
  }
}
```

### `query_api`

Call the deployed backend API.

**Parameters:**
- `method` (string, required) — HTTP method: GET, POST, PUT, DELETE.
- `path` (string, required) — API path: `/items/`, `/analytics/completion-rate`.
- `body` (string, optional) — JSON request body for POST/PUT.

**Returns:** JSON string with `status_code` and `body`.

**Authentication:** Uses `LMS_API_KEY` from environment in `Authorization: Bearer {key}` header.

**Schema:**
```json
{
  "name": "query_api",
  "description": "Call the deployed backend API. Use for system facts and data queries.",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, PUT, DELETE)"
      },
      "path": {
        "type": "string",
        "description": "API path (e.g., /items/, /analytics/completion-rate)"
      },
      "body": {
        "type": "string",
        "description": "JSON request body for POST/PUT (optional)"
      }
    },
    "required": ["method", "path"]
  }
}
```

## Security

### Path Validation

The `validate_path()` function ensures tools cannot access files outside the project:

1. Rejects paths containing `..` (directory traversal).
2. Resolves path relative to project root.
3. Verifies resolved path is within project root.

### API Authentication

The `query_api` tool uses `LMS_API_KEY` from `.env.docker.secret` for authentication. This is a **different key** from `LLM_API_KEY` — don't mix them up.

## Agentic Loop

The agent follows this loop:

```
1. Send user question + tool schemas to LLM
2. Receive response:
   - If tool_calls present:
     a. Execute each tool
     b. Add results as "tool" role messages
     c. Go to step 1
   - If no tool_calls:
     a. Extract answer and source
     b. Output JSON and exit
3. Maximum 10 iterations
```

### Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    # {"role": "assistant", "content": None, "tool_calls": [...]},
    # {"role": "tool", "content": result, "tool_call_id": "..."},
]
```

## System Prompt

The system prompt instructs the LLM on:

1. **Tool usage guidelines** — when to use each tool.
2. **Reading documentation effectively** — scan table of contents, handle truncated content, cite section anchors.

Key excerpts:

```
When to use query_api:
- Questions about HTTP status codes, ports, frameworks
- Questions about data in the database (item count, scores, learners)
- Questions that require calling a live API endpoint

When to use read_file:
- Questions about documentation in wiki/
- Questions about source code structure
- Questions about configuration files

Reading documentation effectively:
- When looking for specific topics in wiki files, scan the table of contents first.
- If a file is large, the content may be truncated. Focus on finding the relevant section anchor.
- Always cite the specific section anchor when answering from documentation.
```

## Configuration

### Environment Files

**`.env.agent.secret`** — LLM configuration:

```ini
LLM_API_KEY=your-llm-api-key-here
LLM_API_BASE=http://<your-vm-ip>:<qwen-api-port>/v1
LLM_MODEL=qwen3-coder-plus
```

**`.env.docker.secret`** — Backend API configuration:

```ini
LMS_API_KEY=my-secret-api-key
AGENT_API_BASE_URL=http://localhost:42002  # optional, defaults to this
```

> **Note:** These files are gitignored. Never commit API keys.

## How to Run

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Expected Output

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git.md#merge-conflict",
  "tool_calls": [
    {"tool": "read_file", "args": {"path": "wiki/git.md"}, "result": "..."}
  ]
}
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
| `pydantic` | Data validation. |

No new dependencies required.

## Testing

Run tests:

```bash
uv run pytest tests/test_agent_task2.py -v  # Task 2 tests
uv run pytest tests/test_agent_task3.py -v  # Task 3 tests
```

### Test Cases

| Test | Question | Expected Tools |
|------|----------|----------------|
| Merge conflict | "How do you resolve a merge conflict?" | `read_file` |
| List files | "What files are in the wiki?" | `list_files` |
| Framework | "What framework does the backend use?" | `read_file` |
| Items count | "How many items are in the database?" | `query_api` |

## Lessons Learned

### Iteration 1: Content Truncation

**Problem:** The agent was reading large wiki files but the content was truncated at 10000 characters, causing the LLM to miss relevant sections.

**Solution:** Increased the limit to 30000 characters and updated the system prompt to instruct the LLM to scan the table of contents and look for section anchors.

### Iteration 2: Source Extraction

**Problem:** The `source` field was sometimes empty or incorrect.

**Solution:** Improved `extract_source()` to:
1. Look for source patterns in the answer text.
2. Fall back to the last `read_file` call.
3. Use `last_read_file` tracking for API-only answers.

### Iteration 3: Tool Selection

**Problem:** The LLM sometimes used `read_file` for questions that required `query_api`.

**Solution:** Enhanced the system prompt with clearer guidelines on when to use each tool, with explicit examples.

### Iteration 4: Backend Unavailability

**Problem:** The backend API was returning 500 errors due to database connection issues.

**Solution:** The agent gracefully handles API errors and reports them in the answer. For local testing, ensure docker-compose is running.

## Final Architecture Summary

The agent is a **tool-using LLM wrapper** with:

- **Three tools:** `read_file`, `list_files`, `query_api`.
- **Agentic loop:** Maximum 10 iterations, tool results fed back as messages.
- **Security:** Path validation prevents directory traversal.
- **Authentication:** Separate keys for LLM and backend API.
- **Output:** JSON with `answer`, `source`, and `tool_calls`.

The architecture is **modular** — new tools can be added by:
1. Implementing the tool function.
2. Adding the tool schema to `TOOL_SCHEMAS`.
3. Registering in `TOOLS_MAP`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Error loading settings` | Ensure `.env.agent.secret` exists with all required variables. |
| `HTTP error from LLM API: 401` | Check `LLM_API_KEY` is correct. |
| `Request error` (query_api) | Verify backend is running: `curl http://localhost:42002/items/`. |
| `Missing LMS_API_KEY` | Ensure `.env.docker.secret` exists with `LMS_API_KEY`. |
| Agent times out | LLM took >60 seconds. Try again or use a faster model. |
| Max iterations reached | Agent made 10 tool calls without finding answer. |
| Answer is truncated | File content exceeded 30000 char limit. |

## Future Extensions

- **More tools:** `search_code` (grep), `run_command` (sandboxed), `query_database` (direct SQL).
- **Better source extraction:** Parse Markdown headers for anchors automatically.
- **Caching:** Cache file reads to reduce API calls in multi-turn conversations.
- **Streaming:** Stream LLM responses for faster feedback.
