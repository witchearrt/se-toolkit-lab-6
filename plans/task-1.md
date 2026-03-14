# Plan: Task 1 — Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM)

**Model:** `qwen3-coder-plus`

**Reasons for this choice:**

- 1000 free requests per day — sufficient for development and testing.
- Works from Russia without restrictions.
- No credit card required.
- OpenAI-compatible API — easy integration with standard libraries.
- Strong tool-calling capabilities (will be used in Tasks 2–3).

**Environment configuration:**

- Copy `.env.agent.example` to `.env.agent.secret`.
- Set `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` in `.env.agent.secret`.
- The file is gitignored — no secrets committed.

## Agent Structure

### Input

- Command-line argument: `uv run agent.py "Question text"`
- The question is passed as the first argument (`sys.argv[1]`).

### Processing

1. **Load environment** from `.env.agent.secret` using `pydantic-settings`.
2. **Create HTTP client** (`httpx.AsyncClient`) for async requests.
3. **Build the request** to the LLM:
   - Endpoint: `{LLM_API_BASE}/chat/completions`
   - Method: `POST`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Body:
     ```json
     {
       "model": "qwen3-coder-plus",
       "messages": [
         {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
         {"role": "user", "content": "<question>"}
       ],
       "temperature": 0.3
     }
     ```
4. **Parse the response**:
   - Extract `choices[0].message.content` as the answer.
   - If tool calls are present (future), extract them from `choices[0].message.tool_calls`.
5. **Format output** as JSON:
   ```json
   {"answer": "<answer text>", "tool_calls": []}
   ```

### Output

- **stdout:** Single valid JSON line.
- **stderr:** All debug/log messages (e.g., "Calling LLM...", "Response received").
- **Exit code:** 0 on success, non-zero on error.

### Error Handling

- Missing environment variables → print error to stderr, exit 1.
- HTTP error from LLM → print error to stderr, exit 1.
- Invalid JSON response → print error to stderr, exit 1.
- Timeout (>60 seconds) → print error to stderr, exit 1.

## Dependencies

- `httpx` — async HTTP client (already in `pyproject.toml`).
- `pydantic-settings` — environment loading (already in `pyproject.toml`).
- `json` — standard library.
- `sys` — standard library.
- `argparse` or `sys.argv` — command-line parsing.

No new dependencies required.

## Testing Strategy

**Test file:** `backend/tests/unit/test_agent_task1.py` (or similar)

**Test approach:**

1. Run `agent.py` as subprocess with a test question.
2. Capture stdout.
3. Parse JSON.
4. Assert:
   - `answer` key exists and is a non-empty string.
   - `tool_calls` key exists and is an array.

**Example test question:** "What is 2 + 2?"

## File Structure

```
se-toolkit-lab-6/
├── plans/
│   └── task-1.md          # This plan
├── agent.py               # Main agent CLI
├── AGENT.md               # Documentation
├── .env.agent.secret      # LLM credentials (gitignored)
└── backend/tests/
    └── unit/
        └── test_agent_task1.py  # Regression test
```

## Git Workflow

1. Create issue: `[Task] Call an LLM from Code`.
2. Create branch: `task-1-llm-call`.
3. Commit plan first: `git add plans/task-1.md && git commit -m "Add plan for task 1"`.
4. Implement agent and test.
5. Create PR with `Closes #<issue-number>`.
6. Request partner review.
7. Merge after approval.
