#!/usr/bin/env python3
"""
Agent CLI — Call an LLM from Code

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    Logs to stderr.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings


class AgentSettings(BaseSettings):
    """Load LLM configuration from .env.agent.secret."""

    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"

    class Config:
        env_file = ".env.agent.secret"
        env_file_encoding = "utf-8"


async def call_llm(
    question: str,
    api_key: str,
    api_base: str,
    model: str,
    timeout: float = 60.0,
) -> str:
    """
    Call the LLM API and return the answer.

    Args:
        question: The user's question.
        api_key: LLM API key.
        api_base: LLM API base URL (OpenAI-compatible).
        model: Model name to use.
        timeout: Request timeout in seconds.

    Returns:
        The LLM's answer as a string.

    Raises:
        httpx.HTTPStatusError: If the API returns an error status.
        httpx.RequestError: If the request fails.
        TimeoutError: If the request times out.
    """
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
            {"role": "user", "content": question},
        ],
        "temperature": 0.3,
    }

    print(f"Calling LLM at {url}...", file=sys.stderr)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    answer = data["choices"][0]["message"]["content"]
    print("Response received from LLM.", file=sys.stderr)
    return answer


def create_response(answer: str, tool_calls: list | None = None) -> dict:
    """
    Create the JSON response structure.

    Args:
        answer: The LLM's answer.
        tool_calls: List of tool calls (empty for this task).

    Returns:
        Dictionary with 'answer' and 'tool_calls' keys.
    """
    return {
        "answer": answer,
        "tool_calls": tool_calls if tool_calls is not None else [],
    }


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
        answer = await call_llm(
            question=question,
            api_key=settings.llm_api_key,
            api_base=settings.llm_api_base,
            model=settings.llm_model,
        )
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
    except KeyError as e:
        print(f"Unexpected response format from LLM: missing key {e}", file=sys.stderr)
        return 1

    response = create_response(answer)
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
