"""Tests for benchmark/session_script.py — session script generation and utilities."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.models import Session, SessionScript, Turn
from benchmark.session_script import (
    generate_session_script,
    parse_issues_md,
    parse_session_script,
    serialize_session_script,
    validate_session_script,
    write_session_script,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ISSUES_MD_PATH = str(Path(__file__).parent.parent / "example_project" / "ISSUES.md")


@pytest.fixture
def parsed_issues():
    """Parse the real ISSUES.md once for reuse."""
    return parse_issues_md(ISSUES_MD_PATH)


@pytest.fixture
def sample_script():
    """A minimal SessionScript for unit tests."""
    turns = [
        Turn(1, "task_description", "Fix the bug"),
        Turn(2, "clarifying_question", "Can you show me the current code in app.py so I can understand what needs to change?"),
        Turn(3, "implementation", "Go ahead and make the changes we discussed."),
        Turn(4, "verification", "Does this look correct? Are there any edge cases we should handle?"),
    ]
    session = Session(
        session_id=1,
        issue_number=1,
        title="Bug: Duplicate usernames",
        task_type="single-file",
        files=["models/user.py"],
        turns=turns,
    )
    return SessionScript(
        generated_at="2024-01-01T00:00:00+00:00",
        repo_path="example_project",
        sessions=[session],
    )


# ---------------------------------------------------------------------------
# 3.1  parse_issues_md
# ---------------------------------------------------------------------------


class TestParseIssuesMd:
    def test_returns_10_issues(self, parsed_issues):
        assert len(parsed_issues) == 10

    def test_issue_numbers_sequential(self, parsed_issues):
        numbers = [i["issue_number"] for i in parsed_issues]
        assert numbers == list(range(1, 11))

    def test_titles_are_nonempty_strings(self, parsed_issues):
        for issue in parsed_issues:
            assert isinstance(issue["title"], str)
            assert len(issue["title"]) > 0

    def test_files_are_lists_of_strings(self, parsed_issues):
        for issue in parsed_issues:
            assert isinstance(issue["files"], list)
            assert len(issue["files"]) >= 1
            for f in issue["files"]:
                assert isinstance(f, str)

    def test_prompts_are_nonempty_strings(self, parsed_issues):
        for issue in parsed_issues:
            assert isinstance(issue["prompt"], str)
            assert len(issue["prompt"]) > 0

    def test_single_file_issue(self, parsed_issues):
        # Issue 1 has **File:** `models/user.py`
        issue1 = parsed_issues[0]
        assert issue1["issue_number"] == 1
        assert issue1["files"] == ["models/user.py"]

    def test_multi_file_issue(self, parsed_issues):
        # Issue 2 has **Files:** `models/task.py`, `routes/tasks.py`
        issue2 = parsed_issues[1]
        assert issue2["issue_number"] == 2
        assert issue2["files"] == ["models/task.py", "routes/tasks.py"]

    def test_prompt_content(self, parsed_issues):
        # Issue 1 prompt should mention duplicate usernames
        assert "duplicate usernames" in parsed_issues[0]["prompt"].lower()

    def test_dict_keys(self, parsed_issues):
        for issue in parsed_issues:
            assert set(issue.keys()) == {"issue_number", "title", "files", "prompt"}


# ---------------------------------------------------------------------------
# 3.2  generate_session_script
# ---------------------------------------------------------------------------


class TestGenerateSessionScript:
    def test_generates_correct_number_of_sessions(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        assert len(script.sessions) == 10

    def test_each_session_has_4_turns(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        for session in script.sessions:
            assert len(session.turns) == 4

    def test_turn_roles(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        expected_roles = ["task_description", "clarifying_question", "implementation", "verification"]
        for session in script.sessions:
            roles = [t.role for t in session.turns]
            assert roles == expected_roles

    def test_turn_numbers(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        for session in script.sessions:
            numbers = [t.turn_number for t in session.turns]
            assert numbers == [1, 2, 3, 4]

    def test_task_description_is_verbatim_prompt(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        for session, issue in zip(script.sessions, parsed_issues):
            assert session.turns[0].prompt == issue["prompt"]

    def test_single_file_task_type(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        # Issue 1 has 1 file → single-file
        assert script.sessions[0].task_type == "single-file"

    def test_cross_file_task_type(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        # Issue 2 has 2 files → cross-file
        assert script.sessions[1].task_type == "cross-file"

    def test_repo_path_set(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        assert script.repo_path == "example_project"

    def test_generated_at_is_iso_timestamp(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        # Should be parseable as ISO format
        assert "T" in script.generated_at

    def test_clarifying_question_mentions_files(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        for session, issue in zip(script.sessions, parsed_issues):
            for f in issue["files"]:
                assert f in session.turns[1].prompt

    def test_session_ids_sequential(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        ids = [s.session_id for s in script.sessions]
        assert ids == list(range(1, 11))


# ---------------------------------------------------------------------------
# 3.3  serialize / parse round-trip
# ---------------------------------------------------------------------------


class TestSerializeParseRoundTrip:
    def test_round_trip(self, sample_script):
        json_str = serialize_session_script(sample_script)
        restored = parse_session_script(json_str)
        assert restored == sample_script

    def test_serialize_produces_valid_json(self, sample_script):
        json_str = serialize_session_script(sample_script)
        data = json.loads(json_str)
        assert isinstance(data, dict)
        assert "sessions" in data

    def test_round_trip_with_generated_script(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        json_str = serialize_session_script(script)
        restored = parse_session_script(json_str)
        assert restored == script


# ---------------------------------------------------------------------------
# 3.4  validate_session_script
# ---------------------------------------------------------------------------


class TestValidateSessionScript:
    def test_valid_script_passes(self, sample_script):
        data = sample_script.to_dict()
        validate_session_script(data)  # should not raise

    def test_missing_generated_at(self, sample_script):
        data = sample_script.to_dict()
        del data["generated_at"]
        with pytest.raises(ValueError, match="generated_at"):
            validate_session_script(data)

    def test_missing_repo_path(self, sample_script):
        data = sample_script.to_dict()
        del data["repo_path"]
        with pytest.raises(ValueError, match="repo_path"):
            validate_session_script(data)

    def test_missing_sessions(self, sample_script):
        data = sample_script.to_dict()
        del data["sessions"]
        with pytest.raises(ValueError, match="sessions"):
            validate_session_script(data)

    def test_invalid_task_type(self, sample_script):
        data = sample_script.to_dict()
        data["sessions"][0]["task_type"] = "invalid"
        with pytest.raises(ValueError, match="task_type"):
            validate_session_script(data)

    def test_invalid_role(self, sample_script):
        data = sample_script.to_dict()
        data["sessions"][0]["turns"][0]["role"] = "invalid"
        with pytest.raises(ValueError, match="role"):
            validate_session_script(data)

    def test_missing_session_key(self, sample_script):
        data = sample_script.to_dict()
        del data["sessions"][0]["title"]
        with pytest.raises(ValueError, match="title"):
            validate_session_script(data)

    def test_missing_turn_key(self, sample_script):
        data = sample_script.to_dict()
        del data["sessions"][0]["turns"][0]["prompt"]
        with pytest.raises(ValueError, match="prompt"):
            validate_session_script(data)

    def test_not_a_dict(self):
        with pytest.raises(ValueError, match="dict"):
            validate_session_script("not a dict")

    def test_sessions_not_a_list(self, sample_script):
        data = sample_script.to_dict()
        data["sessions"] = "not a list"
        with pytest.raises(ValueError, match="array"):
            validate_session_script(data)

    def test_generated_script_validates(self, parsed_issues):
        script = generate_session_script(parsed_issues, "example_project")
        data = script.to_dict()
        validate_session_script(data)  # should not raise


# ---------------------------------------------------------------------------
# 3.5  write_session_script
# ---------------------------------------------------------------------------


class TestWriteSessionScript:
    def test_writes_file(self, sample_script):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.json")
            write_session_script(sample_script, path)
            assert os.path.exists(path)

    def test_written_file_is_valid_json(self, sample_script):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.json")
            write_session_script(sample_script, path)
            with open(path) as f:
                data = json.load(f)
            assert isinstance(data, dict)
            assert "sessions" in data

    def test_round_trip_through_file(self, sample_script):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.json")
            write_session_script(sample_script, path)
            with open(path) as f:
                restored = parse_session_script(f.read())
            assert restored == sample_script

    def test_creates_output_directory(self, sample_script):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "a", "b", "c")
            path = os.path.join(nested, "output.json")
            write_session_script(sample_script, path)
            assert os.path.exists(path)


# ---------------------------------------------------------------------------
# 8.1  Property-based test: session script JSON round-trip
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings


# Strategy for generating Turn instances
turns_strategy = st.builds(
    Turn,
    turn_number=st.integers(min_value=1, max_value=100),
    role=st.sampled_from(["task_description", "clarifying_question", "implementation", "verification"]),
    prompt=st.text(min_size=1, max_size=200),
)

# Strategy for generating Session instances
sessions_strategy = st.builds(
    Session,
    session_id=st.integers(min_value=1, max_value=100),
    issue_number=st.integers(min_value=1, max_value=100),
    title=st.text(min_size=1, max_size=100),
    task_type=st.sampled_from(["single-file", "cross-file"]),
    files=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
    turns=st.lists(turns_strategy, min_size=1, max_size=10),
)

session_script_strategy = st.builds(
    SessionScript,
    generated_at=st.text(min_size=1, max_size=50),
    repo_path=st.text(min_size=1, max_size=100),
    sessions=st.lists(sessions_strategy, min_size=1, max_size=5),
)


class TestSessionScriptRoundTripProperty:
    """**Validates: Requirements 1.7**"""

    @given(script=session_script_strategy)
    @settings(max_examples=50)
    def test_session_script_round_trip_property(self, script):
        """parse(serialize(s)) == s for arbitrary SessionScript instances."""
        json_str = serialize_session_script(script)
        restored = parse_session_script(json_str)
        assert restored == script
