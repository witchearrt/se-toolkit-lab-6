#!/usr/bin/env python3
"""
Documentation Agent — Task 2

An agentic CLI that can read project documentation and answer questions with sources.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    Logs to stderr.
"""

import asyncio
import json
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
        return file_path.read_text(encoding="utf-8")
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


# =============================================================================
# Tool Schemas for LLM Function Calling
# =============================================================================

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
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
            "description": "List files and directories at a given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki')",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

TOOLS_MAP = {
    "read_file": read_file,
    "list_files": list_files,
}


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are a documentation assistant for a software engineering project.
You have access to tools to read files and list directories in the project repository.

When answering questions:
1. Use list_files to discover relevant files in the wiki/ directory.
2. Use read_file to read the contents of files.
3. Provide concise answers with source references (file path + section anchor).
4. Never access files outside the project directory.

Always include the source field in your final answer. The source should be in format: wiki/filename.md#section-anchor

If you don't find the answer in the documentation, say so honestly."""


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
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Run the agentic loop: call LLM, execute tools, repeat until answer.

    Args:
        question: User's question.
        settings: Agent configuration.

    Returns:
        Tuple of (answer, source, tool_calls_list).
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log: list[dict[str, Any]] = []

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
            answer = message.get("content", "")
            source = extract_source(answer, tool_calls_log)
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
            if tool_name in TOOLS_MAP:
                result = TOOLS_MAP[tool_name](**args)
            else:
                result = f"Error: Unknown tool '{tool_name}'"

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
    source = extract_source("", tool_calls_log)
    return answer, source, tool_calls_log


def extract_source(answer: str, tool_calls_log: list[dict[str, Any]]) -> str:
    """
    Extract or generate the source reference.

    Args:
        answer: The LLM's answer text.
        tool_calls_log: List of tool calls made.

    Returns:
        Source reference string (e.g., "wiki/git-workflow.md#section").
    """
    # Try to find source in the answer text (pattern: wiki/...md#...)
    import re

    pattern = r"(wiki/[\w-]+\.md#[\w-]+)"
    match = re.search(pattern, answer)
    if match:
        return match.group(1)

    # Try to extract from last read_file call
    for call in reversed(tool_calls_log):
        if call["tool"] == "read_file":
            path = call["args"].get("path", "")
            if path.startswith("wiki/"):
                # Try to find section from answer
                section_match = re.search(r"#([\w-]+)", answer)
                if section_match:
                    return f"{path}#{section_match.group(1)}"
                return path

    return "wiki/"


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
        print(f"Error loading settings: {e}", file=sys.stderr)
        print(
            "Make sure .env.agent.secret exists with LLM_API_KEY, LLM_API_BASE, LLM_MODEL",
            file=sys.stderr,
        )
        return 1

    try:
        answer, source, tool_calls_log = await run_agent_loop(question, settings)
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
