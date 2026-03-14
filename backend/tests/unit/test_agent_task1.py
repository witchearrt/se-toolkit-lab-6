"""Regression test for agent.py (Task 1).

This test runs agent.py as a subprocess, parses the stdout JSON,
and verifies that 'answer' and 'tool_calls' fields are present.
"""

import json
import subprocess
from pathlib import Path


def test_agent_outputs_valid_json() -> None:
    """Test that agent.py outputs valid JSON with required fields."""
    project_root = Path(__file__).parent.parent.parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        ["uv", "run", str(agent_path), "What is 2 + 2?"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(project_root),
    )

    stdout = result.stdout.strip()
    assert stdout, "agent.py should output JSON to stdout"

    data = json.loads(stdout)

    assert "answer" in data, "Output must contain 'answer' field"
    assert isinstance(data["answer"], str), "'answer' must be a string"
    assert len(data["answer"]) > 0, "'answer' must not be empty"

    assert "tool_calls" in data, "Output must contain 'tool_calls' field"
    assert isinstance(data["tool_calls"], list), "'tool_calls' must be an array"
