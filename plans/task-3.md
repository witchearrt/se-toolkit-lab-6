# Plan: Task 3 — System Agent

## Overview

В этом задании я добавлю инструмент `query_api` для взаимодействия с backend API и обновлю агента для работы с системными фактами и data-dependent запросами.

## LLM Provider и Model

Те же настройки:
- **Provider:** Qwen Code API
- **Model:** `qwen3-coder-plus`

## Environment Variables

Агент должен читать все конфигурации из переменных окружения:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for query_api auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for query_api (optional) | env, default: `http://localhost:42002` |

**Важно:** Autochecker injects свои значения. Нельзя hardcode'ить.

## Инструмент: query_api

### Назначение

Вызов backend API агента.

### Параметры

- `method` (string) — HTTP метод: GET, POST, PUT, DELETE.
- `path` (string) — путь API: `/items/`, `/analytics/completion-rate`.
- `body` (string, optional) — JSON request body для POST/PUT.

### Возвращает

JSON string с `status_code` и `body`.

### Authentication

Использовать `LMS_API_KEY` из `.env.docker.secret` в заголовке:
```
Authorization: Bearer {LMS_API_KEY}
```

### Схема для function calling

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

### Реализация

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend API with LMS_API_KEY auth."""
    url = f"{AGENT_API_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {LMS_API_KEY}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, json=body)
    
    return json.dumps({
        "status_code": response.status_code,
        "body": response.json() if response.content else None
    })
```

## Обновление System Prompt

Новый system prompt должен инструктировать LLM, когда использовать каждый инструмент:

```
You are a documentation and system assistant for a software engineering project.
You have access to tools to read files, list directories, and query the backend API.

Tool usage guidelines:
1. Use list_files to discover relevant files in the wiki/ or backend/ directories.
2. Use read_file to read the contents of files (documentation, source code, configs).
3. Use query_api to query the running backend API for system facts and data.

When to use query_api:
- Questions about HTTP status codes, ports, frameworks
- Questions about data in the database (item count, scores)
- Questions that require calling a live API endpoint

When to use read_file:
- Questions about documentation in wiki/
- Questions about source code structure
- Questions about configuration files

Always include the source field when referencing documentation or source code.
For API queries, mention the endpoint path in your answer.
```

## Benchmark Questions Analysis

| # | Question | Tools Required | Notes |
|---|----------|----------------|-------|
| 0 | Protect a branch on GitHub | read_file | wiki/git-workflow.md или wiki/github.md |
| 1 | SSH connection steps | read_file | wiki/ssh.md или wiki/vm.md |
| 2 | Python web framework | read_file | backend/app/main.py или pyproject.toml |
| 3 | API router modules | list_files | backend/app/routers/ |
| 4 | Items in database | query_api | GET /items/ |
| 5 | Status code without auth | query_api | GET /items/ без заголовка |
| 6 | /analytics/completion-rate error | query_api + read_file | ZeroDivisionError |
| 7 | /analytics/top-learners crash | query_api + read_file | TypeError/NoneType |
| 8 | Request journey | read_file | docker-compose.yml + backend Dockerfile |
| 9 | ETL idempotency | read_file | backend/app/routers/pipeline.py |

## Iteration Strategy

1. **Первый запуск:** Запустить `uv run run_eval.py`, зафиксировать failures.
2. **Анализ ошибок:**
   - Неправильный инструмент → улучшить system prompt.
   - Ошибка в tool → исправить код.
   - Неправильный source → улучшить extract_source().
3. **Повторять** до прохождения всех 10 вопросов.

## Initial Run Results

**Score:** Тесты с query_api не работают из-за недоступности backend (database connection error).

**Observations:**
1. **Question 0 (Protect a branch):** Агент нашёл `wiki/github.md`, но ответ пустой — LLM не нашёл секцию из-за truncation. Увеличил лимит с 10000 до 30000 символов.
2. **Question 2 (Framework):** Работает — агент читает `backend/app/main.py` и находит FastAPI.
3. **Question 4 (Items count):** Backend возвращает 500 (database connection error). Инфраструктурная проблема — нужен запущенный docker-compose.

**Next iterations:**
- Улучшить system prompt для более точного поиска секций.
- Для вопросов с query_api нужен запущенный backend.

## Deployment to VM

The autochecker runs the agent on the VM at `10.93.25.169`. Files deployed:

```bash
scp agent.py root@10.93.25.169:/root/se-toolkit-lab-6/
scp -r tests plans AGENT.md root@10.93.25.169:/root/se-toolkit-lab-6/
scp .env.agent.secret .env.docker.secret root@10.93.25.169:/root/se-toolkit-lab-6/
```

**Verification:**
```bash
ssh root@10.93.25.169 "cd /root/se-toolkit-lab-6 && /root/.local/bin/uv run agent.py 'What is 2 + 2?'"
# Output: {"answer": "2 + 2 = 4.", "source": "", "tool_calls": []}
```

**Note:** The `uv` binary is at `/root/.local/bin/uv` on the VM.

## Тесты

### Test 1: Framework question

**Вопрос:** "What framework does the backend use?"

**Ожидается:**
- `read_file` в tool_calls.
- Ответ содержит "FastAPI".

### Test 2: Items count question

**Вопрос:** "How many items are in the database?"

**Ожидается:**
- `query_api` в tool_calls.
- Ответ содержит число > 0.

## Файловая структура

```
se-toolkit-lab-6/
├── plans/
│   └── task-3.md          # Этот план
├── agent.py               # Обновлённый агент с query_api
├── AGENT.md               # Обновлённая документация
├── tests/
│   └── test_agent_task3.py  # 2 регрессионных теста
└── ...
```

## Git Workflow

1. Создать issue: `[Task] System Agent`.
2. Создать branch: `task-3-system-agent`.
3. Закоммитить план первым.
4. Реализовать query_api и обновить prompt.
5. Запустить run_eval.py, итеративно исправить.
6. Добавить тесты.
7. PR с `Closes #<номер>`.
8. Partner review → merge.
