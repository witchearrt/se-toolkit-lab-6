# Plan: Task 2 — Documentation Agent

## Overview

В этом задании я превращу простой CLI-агент из Task 1 в настоящего агента с инструментами и циклом. Агент сможет читать документацию проекта и отвечать на вопросы со ссылками на источники.

## LLM Provider и Model

**Provider:** Qwen Code API (self-hosted on VM)
**Model:** `qwen3-coder-plus`

Те же настройки, что и в Task 1. Модель поддерживает function calling — это необходимо для работы с инструментами.

## Инструменты

### 1. `read_file`

**Назначение:** Чтение файла из репозитория.

**Параметры:**
- `path` (string, required) — относительный путь от корня проекта.

**Возвращает:** Содержимое файла как строку, или сообщение об ошибке.

**Безопасность:**
- Запрет на выход за пределы проекта (блокировка `../`).
- Проверка, что путь существует и это файл.

**Схема для function calling:**
```json
{
  "name": "read_file",
  "description": "Read a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Relative path from project root"}
    },
    "required": ["path"]
  }
}
```

### 2. `list_files`

**Назначение:** Список файлов и директорий по пути.

**Параметры:**
- `path` (string, required) — относительный путь директории от корня проекта.

**Возвращает:** Построчный список entries.

**Безопасность:**
- Запрет на выход за пределы проекта.
- Проверка, что путь существует и это директория.

**Схема для function calling:**
```json
{
  "name": "list_files",
  "description": "List files and directories at a given path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Relative directory path from project root"}
    },
    "required": ["path"]
  }
}
```

## System Prompt

System prompt будет инструктировать LLM:

1. Использовать `list_files` для обнаружения файлов в wiki.
2. Использовать `read_file` для чтения содержимого.
3. Извлекать ответ и источник (file path + section anchor).
4. Не выходить за пределы проекта.

**Пример system prompt:**

```
You are a documentation assistant for a software engineering project.
You have access to tools to read files and list directories.

When answering questions:
1. Use list_files to discover relevant files in the wiki/ directory.
2. Use read_file to read the contents of files.
3. Provide concise answers with source references (file path + section anchor).
4. Never access files outside the project directory.

Always include the source field in your final answer.
```

## Agentic Loop

Алгоритм работы:

```
1. Отправить вопрос + tool schemas в LLM
2. Получить ответ:
   - Если есть tool_calls:
     a. Выполнить каждый инструмент
     b. Добавить результаты как tool role messages
     c. Вернуться к шагу 1
   - Если нет tool_calls:
     a. Извлечь answer и source
     b. Вернуть JSON и завершить
3. Максимум 10 итераций (tool calls)
```

**Структура messages:**

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # После каждого tool call добавляем:
    # {"role": "assistant", "content": None, "tool_calls": [...]}
    # {"role": "tool", "content": tool_result, "tool_call_id": "..."}
]
```

## Обработка source

LLM должен указать источник в ответе. Формат:
- `wiki/git-workflow.md#resolving-merge-conflicts`

Если LLM не указал source явно, нужно извлечь его из прочитанных файлов (последний прочитанный файл + заголовок раздела).

## Структура ответа

```json
{
  "answer": "текст ответа",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

## Безопасность путей

Функция `validate_path(path: str) -> Path`:

1. Resolve path относительно project root.
2. Проверить, что resolved path начинается с project root.
3. Заблокировать `..` в input.
4. Проверить существование файла/директории.

## Тесты

### Test 1: Merge conflict question

**Вопрос:** "How do you resolve a merge conflict?"

**Ожидается:**
- `read_file` в tool_calls.
- `wiki/git-workflow.md` в source.

### Test 2: List files question

**Вопрос:** "What files are in the wiki?"

**Ожидается:**
- `list_files` в tool_calls.

## Файловая структура

```
se-toolkit-lab-6/
├── plans/
│   └── task-2.md          # Этот план
├── agent.py               # Обновлённый агент с инструментами
├── AGENT.md               # Обновлённая документация
├── tests/
│   └── test_agent_task2.py  # 2 регрессионных теста
└── ...
```

## Git Workflow

1. Создать issue: `[Task] Documentation Agent`.
2. Создать branch: `task-2-doc-agent`.
3. Закоммитить план первым.
4. Реализовать инструменты и цикл.
5. Добавить тесты.
6. PR с `Closes #<номер>`.
7. Partner review → merge.
