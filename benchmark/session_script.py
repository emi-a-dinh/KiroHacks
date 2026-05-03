"""Session script generator for the AI IDE Token Benchmark.

Parses example_project/ISSUES.md to extract coding issues and generates
a structured session script with multi-turn conversations for benchmarking.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import List

from benchmark.models import Session, SessionScript, Turn


# ---------------------------------------------------------------------------
# 3.1  parse_issues_md
# ---------------------------------------------------------------------------


def _extract_files(block: str) -> List[str]:
    """Extract file paths from a **File:** or **Files:** line in an issue block.

    Handles two formats:
      **File:** `models/user.py`
      **Files:** `models/task.py`, `routes/tasks.py`
    """
    # Try **Files:** (plural) first, then **File:** (singular)
    pattern = re.compile(r"\*\*Files?:\*\*\s*(.+)", re.IGNORECASE)
    match = pattern.search(block)
    if not match:
        return []

    line = match.group(1).strip()
    # Extract all backtick-wrapped paths
    files = re.findall(r"`([^`]+)`", line)
    return files


def _extract_prompt(block: str) -> str:
    """Extract the LLM prompt from a blockquote line starting with > "..." """
    # Match lines starting with > " and capture everything inside the quotes.
    # The prompt may span multiple lines of blockquote.
    lines = block.split("\n")
    prompt_lines: List[str] = []
    capturing = False

    for line in lines:
        stripped = line.strip()
        if not capturing:
            # Look for the start of a blockquote prompt: > "..."
            m = re.match(r'^>\s*"(.*)$', stripped)
            if m:
                capturing = True
                text = m.group(1)
                # Check if the quote closes on the same line
                if text.endswith('"'):
                    prompt_lines.append(text[:-1])
                    break
                else:
                    prompt_lines.append(text)
        else:
            # Continue capturing blockquote lines
            if stripped.startswith(">"):
                text = stripped[1:].strip()
            else:
                text = stripped
            if text.endswith('"'):
                prompt_lines.append(text[:-1])
                break
            else:
                prompt_lines.append(text)

    return " ".join(prompt_lines).strip()


def parse_issues_md(path: str) -> List[dict]:
    """Parse ISSUES.md and extract issue metadata.

    Args:
        path: Path to the ISSUES.md file.

    Returns:
        A list of dicts, each with keys:
        - issue_number (int)
        - title (str)
        - files (List[str])
        - prompt (str)
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split on issue headers: ## Issue N — Title
    issue_pattern = re.compile(
        r"^## Issue (\d+)\s*\u2014\s*(.+)$", re.MULTILINE
    )

    matches = list(issue_pattern.finditer(content))
    issues: List[dict] = []

    for i, match in enumerate(matches):
        issue_number = int(match.group(1))
        title = match.group(2).strip()

        # Get the block of text for this issue (until next issue or end)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end]

        # Extract files from **File:** or **Files:** line
        files = _extract_files(block)

        # Extract prompt from blockquote after **Prompt to LLM:**
        prompt = _extract_prompt(block)

        issues.append({
            "issue_number": issue_number,
            "title": title,
            "files": files,
            "prompt": prompt,
        })

    return issues


# ---------------------------------------------------------------------------
# 3.2  generate_session_script
# ---------------------------------------------------------------------------


def generate_session_script(issues: List[dict], repo_path: str) -> SessionScript:
    """Expand parsed issues into a full SessionScript with 4-turn sessions.

    For each issue dict, creates a Session with 4 turns:
      Turn 1 (task_description): The extracted LLM prompt verbatim
      Turn 2 (clarifying_question): Ask to see the current code in the listed files
      Turn 3 (implementation): Request to make the changes
      Turn 4 (verification): Ask if the changes look correct

    Args:
        issues: List of dicts from parse_issues_md.
        repo_path: Path to the target repository.

    Returns:
        A SessionScript instance.
    """
    sessions: List[Session] = []

    for idx, issue in enumerate(issues, start=1):
        files: List[str] = issue["files"]
        task_type = "single-file" if len(files) <= 1 else "cross-file"

        files_str = ", ".join(files)

        turns = [
            Turn(
                turn_number=1,
                role="task_description",
                prompt=issue["prompt"],
            ),
            Turn(
                turn_number=2,
                role="clarifying_question",
                prompt=f"Can you show me the current code in {files_str} so I can understand what needs to change?",
            ),
            Turn(
                turn_number=3,
                role="implementation",
                prompt="Go ahead and make the changes we discussed.",
            ),
            Turn(
                turn_number=4,
                role="verification",
                prompt="Does this look correct? Are there any edge cases we should handle?",
            ),
        ]

        session = Session(
            session_id=idx,
            issue_number=issue["issue_number"],
            title=issue["title"],
            task_type=task_type,
            files=files,
            turns=turns,
        )
        sessions.append(session)

    generated_at = datetime.now(timezone.utc).isoformat()

    return SessionScript(
        generated_at=generated_at,
        repo_path=repo_path,
        sessions=sessions,
    )


# ---------------------------------------------------------------------------
# 3.3  serialize / parse round-trip
# ---------------------------------------------------------------------------


def serialize_session_script(script: SessionScript) -> str:
    """Serialize a SessionScript to a JSON string.

    Args:
        script: The SessionScript to serialize.

    Returns:
        A JSON string with indent=2.
    """
    return json.dumps(script.to_dict(), indent=2)


def parse_session_script(json_str: str) -> SessionScript:
    """Parse a JSON string into a SessionScript.

    Args:
        json_str: A JSON string representing a SessionScript.

    Returns:
        A SessionScript instance.
    """
    data = json.loads(json_str)
    return SessionScript.from_dict(data)


# ---------------------------------------------------------------------------
# 3.4  JSON schema validation (manual, no jsonschema dependency)
# ---------------------------------------------------------------------------

SESSION_SCRIPT_SCHEMA = {
    "type": "object",
    "required": ["generated_at", "repo_path", "sessions"],
    "properties": {
        "generated_at": {"type": "string"},
        "repo_path": {"type": "string"},
        "sessions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "session_id",
                    "issue_number",
                    "title",
                    "task_type",
                    "files",
                    "turns",
                ],
                "properties": {
                    "session_id": {"type": "integer"},
                    "issue_number": {"type": "integer"},
                    "title": {"type": "string"},
                    "task_type": {"type": "string", "enum": ["single-file", "cross-file"]},
                    "files": {"type": "array", "items": {"type": "string"}},
                    "turns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["turn_number", "role", "prompt"],
                            "properties": {
                                "turn_number": {"type": "integer"},
                                "role": {
                                    "type": "string",
                                    "enum": [
                                        "task_description",
                                        "clarifying_question",
                                        "implementation",
                                        "verification",
                                    ],
                                },
                                "prompt": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}

_VALID_TASK_TYPES = {"single-file", "cross-file"}
_VALID_ROLES = {"task_description", "clarifying_question", "implementation", "verification"}


def validate_session_script(data: dict) -> None:
    """Validate a session script dict against the expected schema.

    Raises ValueError with a descriptive message if validation fails.
    Manual validation — no jsonschema dependency required.

    Args:
        data: A dict representing a session script (e.g. from json.loads).

    Raises:
        ValueError: If the data does not conform to the schema.
    """
    if not isinstance(data, dict):
        raise ValueError("Session script must be a JSON object (dict).")

    # Top-level required keys
    for key in ("generated_at", "repo_path", "sessions"):
        if key not in data:
            raise ValueError(f"Missing required top-level key: '{key}'.")

    if not isinstance(data["generated_at"], str):
        raise ValueError("'generated_at' must be a string.")
    if not isinstance(data["repo_path"], str):
        raise ValueError("'repo_path' must be a string.")
    if not isinstance(data["sessions"], list):
        raise ValueError("'sessions' must be an array.")

    for i, session in enumerate(data["sessions"]):
        _validate_session(session, i)


def _validate_session(session: dict, index: int) -> None:
    """Validate a single session dict."""
    prefix = f"sessions[{index}]"

    if not isinstance(session, dict):
        raise ValueError(f"{prefix} must be a JSON object (dict).")

    for key in ("session_id", "issue_number", "title", "task_type", "files", "turns"):
        if key not in session:
            raise ValueError(f"{prefix}: missing required key '{key}'.")

    if not isinstance(session["session_id"], int):
        raise ValueError(f"{prefix}.session_id must be an integer.")
    if not isinstance(session["issue_number"], int):
        raise ValueError(f"{prefix}.issue_number must be an integer.")
    if not isinstance(session["title"], str):
        raise ValueError(f"{prefix}.title must be a string.")

    if session["task_type"] not in _VALID_TASK_TYPES:
        raise ValueError(
            f"{prefix}.task_type must be one of {_VALID_TASK_TYPES}, "
            f"got '{session['task_type']}'."
        )

    if not isinstance(session["files"], list):
        raise ValueError(f"{prefix}.files must be an array.")
    for j, f in enumerate(session["files"]):
        if not isinstance(f, str):
            raise ValueError(f"{prefix}.files[{j}] must be a string.")

    if not isinstance(session["turns"], list):
        raise ValueError(f"{prefix}.turns must be an array.")
    for j, turn in enumerate(session["turns"]):
        _validate_turn(turn, prefix, j)


def _validate_turn(turn: dict, session_prefix: str, index: int) -> None:
    """Validate a single turn dict."""
    prefix = f"{session_prefix}.turns[{index}]"

    if not isinstance(turn, dict):
        raise ValueError(f"{prefix} must be a JSON object (dict).")

    for key in ("turn_number", "role", "prompt"):
        if key not in turn:
            raise ValueError(f"{prefix}: missing required key '{key}'.")

    if not isinstance(turn["turn_number"], int):
        raise ValueError(f"{prefix}.turn_number must be an integer.")

    if turn["role"] not in _VALID_ROLES:
        raise ValueError(
            f"{prefix}.role must be one of {_VALID_ROLES}, "
            f"got '{turn['role']}'."
        )

    if not isinstance(turn["prompt"], str):
        raise ValueError(f"{prefix}.prompt must be a string.")


# ---------------------------------------------------------------------------
# 3.5  write_session_script
# ---------------------------------------------------------------------------


def write_session_script(script: SessionScript, output_path: str) -> None:
    """Serialize a SessionScript to JSON and write it to a file.

    Creates the output directory if it doesn't exist.

    Args:
        script: The SessionScript to write.
        output_path: File path to write the JSON to.
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    json_str = serialize_session_script(script)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)
