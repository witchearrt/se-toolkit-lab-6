# Agent Architecture

## Overview

This project implements a documentation agent (`agent.py`) that can read project documentation and answer questions with source references. The agent has tools (`read_file`, `list_files`) and an agentic loop that allows multi-step reasoning.

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
| `AgentSettings` | Pydantic settings class. Loads from `.env.agent.secret`. |
| `read_file()` | Tool: reads a file from the project. |
| `list_files()` | Tool: lists files in a directory. |
| `validate_path()` | Security: prevents directory traversal. |
| `call_llm()` | Async function that makes HTTP POST to LLM API. |
| `run_agent_loop()` | Agentic loop: call LLM → execute tools → repeat. |
| `create_response()` | Formats the answer into JSON structure. |

## Tools

### `read_file`

Read a file from the project repository.

**Parameters:**
- `path` (string, required) — relative path from project root.

**Returns:** File contents as string, or error message.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root"
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
  "description": "List files and directories at a given path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root"
      }
    },
    "required": ["path"]
  }
}
```

## Security

### Path Validation

The `validate_path()` function ensures tools cannot access files outside the project:

1. Rejects paths containing `..` (directory traversal).
2. Resolves path relative to project root.
3. Verifies resolved path is within project root.

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

```
You are a documentation assistant for a software engineering project.
You have access to tools to read files and list directories in the project repository.

When answering questions:
1. Use list_files to discover relevant files in the wiki/ directory.
2. Use read_file to read the contents of files.
3. Provide concise answers with source references (file path + section anchor).
4. Never access files outside the project directory.

Always include the source field in your final answer. The source should be in format: wiki/filename.md#section-anchor

If you don't find the answer in the documentation, say so honestly.
```

## Configuration

### Environment File: `.env.agent.secret`

```bash
cp .env.agent.example .env.agent.secret
```

Edit `.env.agent.secret`:

```ini
LLM_API_KEY=your-llm-api-key-here
LLM_API_BASE=http://<your-vm-ip>:<qwen-api-port>/v1
LLM_MODEL=qwen3-coder-plus
```

> **Note:** This file is gitignored. Never commit API keys.

## How to Run

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Expected Output

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
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
uv run pytest tests/test_agent_task2.py -v
```

### Test Cases

| Test | Question | Expected |
|------|----------|----------|
| Merge conflict | "How do you resolve a merge conflict?" | `read_file` in tool_calls, `wiki/git-workflow.md` in source |
| List files | "What files are in the wiki?" | `list_files` in tool_calls |

## Data Flow

```
User Question
      │
      ▼
┌─────────────────────────────────┐
│ 1. Build messages array         │
│    - system prompt              │
│    - user question              │
└─────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────┐
│ 2. Call LLM with tools          │
│    - POST /chat/completions     │
│    - Include tool schemas       │
└─────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────┐
│ 3. Check response               │
│    - tool_calls? → execute      │
│    - no tool_calls? → answer    │
└─────────────────────────────────┘
      │
      ├─── tool_calls ───▶ Execute tools ───▶ Add tool results to messages ───┐
      │                                                                          │
      └─── no tool_calls ───▶ Extract answer & source ───▶ Output JSON ───▶ Done
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Error loading settings` | Ensure `.env.agent.secret` exists with all required variables. |
| `HTTP error from LLM API: 401` | Check `LLM_API_KEY` is correct. |
| `HTTP error from LLM API: 404` | Check `LLM_API_BASE` URL is correct (should end with `/v1`). |
| `Request error` | Verify network connectivity to the VM. |
| `Request timed out` | LLM took >60 seconds. Try again or use a faster model. |
| `Path traversal not allowed` | Agent blocked attempt to access files outside project. |
| Max iterations reached | Agent made 10 tool calls without finding answer. |

## Future Extensions (Task 3)

- **More tools:** `query_api`, `search_code`, `run_command`.
- **Domain knowledge:** Load wiki context into system prompt.
- **Better source extraction:** Parse Markdown headers for anchors.
- **Caching:** Cache file reads to reduce API calls.
