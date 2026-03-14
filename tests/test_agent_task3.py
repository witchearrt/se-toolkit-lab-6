"""Regression tests for agent.py (Task 3) — System Agent.

These tests verify that the agent uses tools correctly for system questions.
"""

import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent


def run_agent(question: str) -> dict:
    """Run agent.py and return parsed JSON response."""
    agent_path = PROJECT_ROOT / "agent.py"

    result = subprocess.run(
        ["uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=120,  # Longer timeout for agentic loop
        cwd=str(PROJECT_ROOT),
    )

    stdout = result.stdout.strip()
    assert stdout, f"agent.py should output JSON to stdout. stderr: {result.stderr}"

    return json.loads(stdout)


def test_framework_question() -> None:
    """Test that agent uses read_file for framework question."""
    response = run_agent("What Python web framework does this project's backend use?")

    # Check required fields
    assert "answer" in response, "Output must contain 'answer' field"
    assert "source" in response, "Output must contain 'source' field"
    assert "tool_calls" in response, "Output must contain 'tool_calls' field"

    # Check answer is non-empty and contains FastAPI
    assert isinstance(response["answer"], str), "'answer' must be a string"
    assert len(response["answer"]) > 0, "'answer' must not be empty"
    assert "FastAPI" in response["answer"], (
        f"Answer should mention FastAPI, got: {response['answer'][:200]}"
    )

    # Check tool_calls contains read_file
    assert isinstance(response["tool_calls"], list), "'tool_calls' must be an array"
    tool_names = [call.get("tool") for call in response["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected 'read_file' in tool_calls, got: {tool_names}"
    )


def test_api_routers_question() -> None:
    """Test that agent uses list_files for API routers question."""
    response = run_agent("List all API router modules in the backend.")

    # Check required fields
    assert "answer" in response, "Output must contain 'answer' field"
    assert "tool_calls" in response, "Output must contain 'tool_calls' field"

    # Check answer is non-empty
    assert isinstance(response["answer"], str), "'answer' must be a string"
    assert len(response["answer"]) > 0, "'answer' must not be empty"

    # Check tool_calls contains list_files
    assert isinstance(response["tool_calls"], list), "'tool_calls' must be an array"
    tool_names = [call.get("tool") for call in response["tool_calls"]]
    assert "list_files" in tool_names, (
        f"Expected 'list_files' in tool_calls, got: {tool_names}"
    )
