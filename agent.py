#!/usr/bin/env python3
"""
System Agent — Task 3

An agentic CLI that can read documentation, query the backend API, and answer questions with sources.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    Logs to stderr.
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

# =============================================================================
# Configuration
# =============================================================================


class AgentSettings(BaseSettings):
    """Load LLM configuration from .env.agent.secret."""

    model_config = ConfigDict(env_file=".env.agent.secret", env_file_encoding="utf-8")

    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"


class AgentConfig(BaseSettings):
    """Load agent configuration from environment variables."""

    model_config = ConfigDict(
        env_file=".env.docker.secret",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"


# =============================================================================
# Tools
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.resolve()
MAX_TOOL_CALLS = 10


def validate_path(path: str) -> Path:
    """
    Validate and resolve a path relative to project root.

    Security: prevents directory traversal (../).

    Args:
        path: Relative path from project root.

    Returns:
        Absolute Path object.

    Raises:
        ValueError: If path is invalid or outside project root.
    """
    if ".." in path:
        raise ValueError(f"Path traversal not allowed: {path}")

    resolved = (PROJECT_ROOT / path).resolve()

    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"Path outside project root: {path}")

    return resolved


def read_file(path: str) -> str:
    """
    Read a file from the project repository.

    Args:
        path: Relative path from project root.

    Returns:
        File contents as string, or error message.
    """
    try:
        file_path = validate_path(path)
        if not file_path.is_file():
            return f"Error: Not a file: {path}"
        content = file_path.read_text(encoding="utf-8")
        # Limit content size to avoid token limits, but try to keep more for large files
        max_chars = 30000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... (truncated)"
        return content
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root.

    Returns:
        Newline-separated listing, or error message.
    """
    try:
        dir_path = validate_path(path)
        if not dir_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = sorted(dir_path.iterdir())
        lines = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        return "\n".join(lines)
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(method: str, path: str, body: str | None = None, config: AgentConfig | None = None) -> str:
    """
    Call the deployed backend API.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: API path (e.g., /items/, /analytics/completion-rate).
        body: Optional JSON request body for POST/PUT.
        config: Agent configuration with API key and base URL.

    Returns:
        JSON string with status_code and body.
    """
    if config is None:
        config = AgentConfig()

    base_url = config.agent_api_base_url.rstrip("/")
    url = f"{base_url}{path}"
    headers = {}

    if config.lms_api_key:
        headers["Authorization"] = f"Bearer {config.lms_api_key}"

    try:
        if method.upper() == "GET":
            response = httpx.get(url, headers=headers, timeout=30.0)
        elif method.upper() == "POST":
            json_body = json.loads(body) if body else None
            response = httpx.post(url, headers=headers, json=json_body, timeout=30.0)
        elif method.upper() == "PUT":
            json_body = json.loads(body) if body else None
            response = httpx.put(url, headers=headers, json=json_body, timeout=30.0)
        elif method.upper() == "DELETE":
            response = httpx.delete(url, headers=headers, timeout=30.0)
        else:
            return json.dumps({"status_code": 400, "error": f"Unknown method: {method}"})

        result = {
            "status_code": response.status_code,
            "body": response.json() if response.content else None,
        }
        return json.dumps(result)
    except httpx.RequestError as e:
        return json.dumps({"status_code": 0, "error": str(e)})
    except json.JSONDecodeError:
        return json.dumps({"status_code": response.status_code, "body": response.text})


# =============================================================================
# Tool Schemas for LLM Function Calling
# =============================================================================

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository. Use for documentation (wiki/) and source code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path. Use to discover files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki', 'backend/app/routers')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the deployed backend API. Use for system facts (ports, frameworks, status codes) and data queries (item count, scores).",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API path (e.g., '/items/', '/analytics/completion-rate')",
                    },
                    "body": {
                        "type": "string",
                        "description": "JSON request body for POST/PUT (optional)",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

TOOLS_MAP = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
}


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are a documentation and system assistant for a software engineering project.
You have access to tools to read files, list directories, and query the backend API.

Tool usage guidelines:
1. Use list_files to discover relevant files in the wiki/, backend/, or other directories.
2. Use read_file to read the contents of files (documentation, source code, configs).
3. Use query_api to query the running backend API for system facts and data.

When to use query_api:
- Questions about HTTP status codes, ports, frameworks
- Questions about data in the database (item count, scores, learners)
- Questions that require calling a live API endpoint
- Questions about API behavior (errors, responses)

When to use read_file:
- Questions about documentation in wiki/
- Questions about source code structure
- Questions about configuration files (docker-compose.yml, pyproject.toml, etc.)

When to use list_files:
- Discovering what files exist in a directory
- Finding API routers, models, or modules

Reading documentation effectively:
- When looking for specific topics in wiki files, scan the table of contents first (lines near the top with # anchors).
- If a file is large, the content may be truncated. Focus on finding the relevant section anchor (e.g., #protect-a-branch) and mention that the full details are in that section.
- Always cite the specific section anchor when answering from documentation.

Always include the source field when referencing documentation or source code.
For API queries, mention the endpoint path in your answer.
If you don't find the answer, say so honestly."""


# =============================================================================
# LLM Communication
# =============================================================================


async def call_llm(
    messages: list[dict[str, Any]],
    api_key: str,
    api_base: str,
    model: str,
    tools: list[dict[str, Any]] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """
    Call the LLM API and return the response.

    Args:
        messages: List of message dicts (role, content, tool_calls, etc.).
        api_key: LLM API key.
        api_base: LLM API base URL.
        model: Model name.
        tools: Optional tool schemas for function calling.
        timeout: Request timeout in seconds.

    Returns:
        The LLM's response data as a dict.
    """
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
    }

    if tools:
        payload["tools"] = tools

    print(f"Calling LLM at {url}...", file=sys.stderr)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    print("Response received from LLM.", file=sys.stderr)
    return data


# =============================================================================
# Agentic Loop
# =============================================================================


async def run_agent_loop(
    question: str,
    settings: AgentSettings,
    config: AgentConfig,
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Run the agentic loop: call LLM, execute tools, repeat until answer.

    Args:
        question: User's question.
        settings: LLM configuration.
        config: Agent configuration (API key, base URL).

    Returns:
        Tuple of (answer, source, tool_calls_list).
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log: list[dict[str, Any]] = []
    last_read_file: str | None = None

    for iteration in range(MAX_TOOL_CALLS):
        print(f"\n--- Iteration {iteration + 1} ---", file=sys.stderr)

        response_data = await call_llm(
            messages=messages,
            api_key=settings.llm_api_key,
            api_base=settings.llm_api_base,
            model=settings.llm_model,
            tools=TOOL_SCHEMAS,
        )

        choice = response_data["choices"][0]
        message = choice["message"]

        # Check for tool calls
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            # No tool calls - LLM provided final answer
            answer = message.get("content") or ""
            source = extract_source(answer, tool_calls_log, last_read_file)
            print(f"\nFinal answer received. Source: {source}", file=sys.stderr)
            return answer, source, tool_calls_log

        # Execute tool calls
        messages.append(message)  # Add assistant message with tool_calls

        for tool_call in tool_calls:
            tool_call_id = tool_call["id"]
            function = tool_call["function"]
            tool_name = function["name"]
            args = json.loads(function["arguments"])

            print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

            # Execute the tool
            if tool_name == "query_api":
                result = TOOLS_MAP[tool_name](config=config, **args)
            elif tool_name in TOOLS_MAP:
                result = TOOLS_MAP[tool_name](**args)
            else:
                result = f"Error: Unknown tool '{tool_name}'"

            # Track last read_file for source extraction
            if tool_name == "read_file":
                last_read_file = args.get("path", "")

            print(f"Tool result: {result[:200]}...", file=sys.stderr)

            # Log the tool call
            tool_calls_log.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "result": result,
                }
            )

            # Add tool result to messages
            messages.append(
                {
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call_id,
                }
            )

    # Max iterations reached
    print("\nMax tool calls reached.", file=sys.stderr)
    answer = "I reached the maximum number of tool calls (10) without finding a complete answer."
    source = extract_source("", tool_calls_log, last_read_file)
    return answer, source, tool_calls_log


def extract_source(
    answer: str,
    tool_calls_log: list[dict[str, Any]],
    last_read_file: str | None = None,
) -> str:
    """
    Extract or generate the source reference.

    Args:
        answer: The LLM's answer text.
        tool_calls_log: List of tool calls made.
        last_read_file: Last file read via read_file.

    Returns:
        Source reference string (e.g., "wiki/git-workflow.md#section").
    """
    # Try to find source in the answer text (pattern: wiki/...md#... or backend/...py)
    pattern = r"(wiki/[\w-]+\.md#[\w-]+|backend/[\w_/]+\.py)"
    match = re.search(pattern, answer)
    if match:
        return match.group(1)

    # Try to extract from last read_file call
    for call in reversed(tool_calls_log):
        if call["tool"] == "read_file":
            path = call["args"].get("path", "")
            if path.endswith(".md") or path.endswith(".py") or path.endswith(".yml") or path.endswith(".toml"):
                # Try to find section from answer
                section_match = re.search(r"#([\w-]+)", answer)
                if section_match:
                    return f"{path}#{section_match.group(1)}"
                return path

    # Fallback: use last_read_file
    if last_read_file:
        return last_read_file

    return ""


# =============================================================================
# Response Formatting
# =============================================================================


def create_response(answer: str, source: str, tool_calls: list[dict[str, Any]]) -> dict:
    """
    Create the JSON response structure.

    Args:
        answer: The LLM's answer.
        source: Source reference.
        tool_calls: List of tool calls made.

    Returns:
        Dictionary with answer, source, and tool_calls.
    """
    return {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }


# =============================================================================
# Main Entry Point
# =============================================================================


async def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        return 1

    question = sys.argv[1]

    try:
        settings = AgentSettings()
    except Exception as e:
        print(f"Error loading LLM settings: {e}", file=sys.stderr)
        print(
            "Make sure .env.agent.secret exists with LLM_API_KEY, LLM_API_BASE, LLM_MODEL",
            file=sys.stderr,
        )
        return 1

    try:
        config = AgentConfig()
    except Exception as e:
        print(f"Warning: Could not load agent config: {e}", file=sys.stderr)
        config = AgentConfig()

    try:
        answer, source, tool_calls_log = await run_agent_loop(question, settings, config)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error from LLM API: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Request error: {e}", file=sys.stderr)
        return 1
    except TimeoutError:
        print("Request timed out after 60 seconds", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    response = create_response(answer, source, tool_calls_log)
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
