#!/usr/bin/env python3
"""
Benchmark Token Miser vs full-file context across 20 bugs in the example Flask project.

Usage:
    python benchmark.py
    python benchmark.py --model gpt-4.1-mini --start 0 --end 5
    python benchmark.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Reuse non-OpenAI helpers from demo.py ─────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent))
from demo import extract_text, format_table, require_openai


# ── Local call_openai (accepts custom system prompt, no hardcoded verify) ──────

def call_openai(client, model: str, prompt: str, system_prompt: str) -> tuple[int, str]:
    """Count input tokens, call the model, return (token_count, response_text).
    Retries up to 4 times on 429 with exponential backoff.
    """
    import time as _time

    counted = client.responses.input_tokens.count(
        model=model,
        instructions=system_prompt,
        input=prompt,
    )
    input_tokens = counted.input_tokens

    max_retries = 4
    delay = 15  # seconds, doubles each retry

    for attempt in range(max_retries + 1):
        try:
            response = client.responses.create(
                model=model,
                max_output_tokens=600,
                instructions=system_prompt,
                input=prompt,
            )
            return input_tokens, extract_text(response)
        except Exception as exc:
            message = str(exc)
            is_rate_limit = "429" in message or "rate limit" in message.lower() or "TPM" in message
            if is_rate_limit and attempt < max_retries:
                wait = delay * (2 ** attempt)
                print(f"       rate limit — waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                _time.sleep(wait)
                continue
            if is_rate_limit:
                raise RuntimeError(
                    f"Rate limit hit for model {model!r} after {max_retries} retries. "
                    f"Input tokens: {input_tokens}."
                ) from exc
            raise

# ── Bug definitions ────────────────────────────────────────────────────────────

@dataclass
class Bug:
    id: int
    category: str          # single_line | wrong_function | multi_function | silent
    description: str       # plain English symptom prompt
    file: str              # relative path from example_project/
    find: str              # exact string to replace
    replace: str           # buggy replacement
    verify: str            # substring that must appear in a correct fix response


BUGS: list[Bug] = [
    # ── 1–5: Single-line bugs ─────────────────────────────────────────────────

    Bug(
        id=1,
        category="single_line",
        description=(
            "In routes/auth.py, the login route returns 200 even when the "
            "password is wrong. Users with bad passwords are being let in."
        ),
        file="routes/auth.py",
        find='return jsonify({"error": "Invalid email or password"}), 401',
        replace='return jsonify({"error": "Invalid email or password"}), 200',
        verify="401",
    ),
    Bug(
        id=2,
        category="single_line",
        description=(
            "In routes/tasks.py, creating a task always returns 200 instead "
            "of 201. API clients that check for 201 on creation are breaking."
        ),
        file="routes/tasks.py",
        find="return jsonify(task.to_dict()), 201",
        replace="return jsonify(task.to_dict()), 200",
        verify="201",
    ),
    Bug(
        id=3,
        category="single_line",
        description=(
            "In routes/tasks.py, the delete endpoint returns 200 with a "
            "message but the task is never actually removed from the database."
        ),
        file="routes/tasks.py",
        find="    db.session.delete(task)\n    db.session.commit()\n    return jsonify({\"message\": \"Task deleted\"}), 200",
        replace="    return jsonify({\"message\": \"Task deleted\"}), 200",
        verify="db.session.delete",
    ),
    Bug(
        id=4,
        category="single_line",
        description=(
            "In routes/users.py, update_user checks the wrong condition for "
            "the ownership guard — it allows any user to edit any profile."
        ),
        file="routes/users.py",
        find="    if current_user_id != user_id:",
        replace="    if current_user_id == user_id:",
        verify="!=",
    ),
    Bug(
        id=5,
        category="single_line",
        description=(
            "In routes/auth.py, the logout route clears the wrong session key. "
            "Users remain logged in after calling /logout."
        ),
        file="routes/auth.py",
        find='    session.pop("user_id", None)',
        replace='    session.pop("user", None)',
        verify='user_id',
    ),

    # ── 6–10: Wrong-function bugs ─────────────────────────────────────────────

    Bug(
        id=6,
        category="wrong_function",
        description=(
            "In routes/tasks.py, list_tasks calls get_current_user_id() "
            "instead of require_auth(), so unauthenticated requests are not "
            "rejected and the 401 guard never fires."
        ),
        file="routes/tasks.py",
        find="def list_tasks():\n    user_id = require_auth()",
        replace="def list_tasks():\n    user_id = get_current_user_id()",
        verify="require_auth",
    ),
    Bug(
        id=7,
        category="wrong_function",
        description=(
            "In routes/auth.py, register is calling hash_password on the "
            "email instead of the password, so all stored hashes are wrong "
            "and login always fails."
        ),
        file="routes/auth.py",
        find="        password_hash=hash_password(password),",
        replace="        password_hash=hash_password(email),",
        verify="hash_password(password)",
    ),
    Bug(
        id=8,
        category="wrong_function",
        description=(
            "In routes/tasks.py, update_task is calling filter_by instead of "
            "get when looking up the task by ID, causing a type error because "
            "filter_by returns a query object not a task."
        ),
        file="routes/tasks.py",
        find="    task = Task.query.get(task_id)\n    if not task:\n        return jsonify({\"error\": \"Task not found\"}), 404\n\n    if task.user_id != user_id:\n        return jsonify({\"error\": \"Forbidden\"}), 403\n\n    data = request.get_json()",
        replace="    task = Task.query.filter_by(id=task_id)\n    if not task:\n        return jsonify({\"error\": \"Task not found\"}), 404\n\n    if task.user_id != user_id:\n        return jsonify({\"error\": \"Forbidden\"}), 403\n\n    data = request.get_json()",
        verify="Task.query.get",
    ),
    Bug(
        id=9,
        category="wrong_function",
        description=(
            "In routes/users.py, delete_user calls db.session.add(user) "
            "instead of db.session.delete(user), so the user is re-added "
            "rather than removed."
        ),
        file="routes/users.py",
        find="    db.session.delete(user)\n    db.session.commit()\n    return jsonify({\"message\": \"User deleted\"}), 200",
        replace="    db.session.add(user)\n    db.session.commit()\n    return jsonify({\"message\": \"User deleted\"}), 200",
        verify="db.session.delete",
    ),
    Bug(
        id=10,
        category="wrong_function",
        description=(
            "In routes/auth.py, check_password compares the hash against the "
            "raw password instead of the hashed password, so login always "
            "fails even with the correct password."
        ),
        file="routes/auth.py",
        find="    return hash_password(password) == password_hash",
        replace="    return password == password_hash",
        verify="hash_password",
    ),

    # ── 11–15: Multi-function bugs ────────────────────────────────────────────

    Bug(
        id=11,
        category="multi_function",
        description=(
            "In routes/tasks.py, require_auth returns the user_id but "
            "create_task ignores the return value and uses None as user_id, "
            "so all created tasks have no owner."
        ),
        file="routes/tasks.py",
        find="def create_task():\n    user_id = require_auth()\n    if not user_id:",
        replace="def create_task():\n    require_auth()\n    user_id = None\n    if not user_id:",
        verify="user_id = require_auth()",
    ),
    Bug(
        id=12,
        category="multi_function",
        description=(
            "In routes/tasks.py, task_stats filters by the wrong field — it "
            "uses filter_by(id=user_id) instead of filter_by(user_id=user_id), "
            "returning stats for the wrong tasks."
        ),
        file="routes/tasks.py",
        find="    tasks = Task.query.filter_by(user_id=user_id).all()\n\n    stats = {",
        replace="    tasks = Task.query.filter_by(id=user_id).all()\n\n    stats = {",
        verify="filter_by(user_id=user_id)",
    ),
    Bug(
        id=13,
        category="multi_function",
        description=(
            "In routes/tasks.py, update_task commits the session before "
            "applying the tag changes, so tag updates are never persisted."
        ),
        file="routes/tasks.py",
        find='    # updated_at is NOT set here — see Issue 2 in models/task.py\n    db.session.commit()\n    return jsonify(task.to_dict()), 200',
        replace='    db.session.commit()\n    # updated_at is NOT set here — see Issue 2 in models/task.py\n    if "tags" in data:\n        db.session.commit()\n    return jsonify(task.to_dict()), 200',
        verify="db.session.commit",
    ),
    Bug(
        id=14,
        category="multi_function",
        description=(
            "In routes/auth.py, register stores the user but never commits "
            "the session, so new users are lost on every request."
        ),
        file="routes/auth.py",
        find="    db.session.add(user)\n    db.session.commit()\n\n    return jsonify({\"message\": \"User registered successfully\"",
        replace="    db.session.add(user)\n\n    return jsonify({\"message\": \"User registered successfully\"",
        verify="db.session.commit",
    ),
    Bug(
        id=15,
        category="multi_function",
        description=(
            "In routes/users.py, get_user_tasks returns tasks for the wrong "
            "user — it fetches user.tasks but user is looked up by user_id "
            "without checking that current_user_id matches, leaking other "
            "users' tasks."
        ),
        file="routes/users.py",
        find="    if current_user_id != user_id:\n        return jsonify({\"error\": \"Forbidden\"}), 403\n\n    user = User.query.get(user_id)\n    if not user:\n        return jsonify({\"error\": \"User not found\"}), 404\n\n    # Same pagination issue as tasks list — no limit/offset\n    tasks = user.tasks",
        replace="    user = User.query.get(user_id)\n    if not user:\n        return jsonify({\"error\": \"User not found\"}), 404\n\n    # Same pagination issue as tasks list — no limit/offset\n    tasks = user.tasks",
        verify="current_user_id != user_id",
    ),

    # ── 16–20: Silent bugs ────────────────────────────────────────────────────

    Bug(
        id=16,
        category="silent",
        description=(
            "In routes/tasks.py, the auth check in get_task was removed. "
            "The route no longer returns 401 for unauthenticated requests — "
            "it silently serves task data to anyone."
        ),
        file="routes/tasks.py",
        find="def get_task(task_id):\n    user_id = require_auth()\n    if not user_id:\n        return jsonify({\"error\": \"Not authenticated\"}), 401\n\n    task = Task.query.get(task_id)",
        replace="def get_task(task_id):\n    task = Task.query.get(task_id)",
        verify="require_auth",
    ),
    Bug(
        id=17,
        category="silent",
        description=(
            "In routes/auth.py, the is_active check was removed from login. "
            "Deactivated accounts can now log in without any error."
        ),
        file="routes/auth.py",
        find="    if not user.is_active:\n        return jsonify({\"error\": \"Account is deactivated\"}), 403\n\n    session[\"user_id\"] = user.id",
        replace="    session[\"user_id\"] = user.id",
        verify="is_active",
    ),
    Bug(
        id=18,
        category="silent",
        description=(
            "In routes/tasks.py, the ownership check was silently dropped "
            "from delete_task. Any authenticated user can now delete any task."
        ),
        file="routes/tasks.py",
        find="    if task.user_id != user_id:\n        return jsonify({\"error\": \"Forbidden\"}), 403\n\n    db.session.delete(task)",
        replace="    db.session.delete(task)",
        verify="task.user_id != user_id",
    ),
    Bug(
        id=19,
        category="silent",
        description=(
            "In routes/users.py, update_user no longer checks for duplicate "
            "emails. Two users can now share the same email address."
        ),
        file="routes/users.py",
        find="        existing = User.query.filter_by(email=email).first()\n        if existing and existing.id != user_id:\n            return jsonify({\"error\": \"Email already in use\"}), 409\n        user.email = email",
        replace="        user.email = email",
        verify="filter_by(email=email)",
    ),
    Bug(
        id=20,
        category="silent",
        description=(
            "In routes/auth.py, logout no longer clears the session. "
            "Calling /logout returns 200 but the user stays authenticated."
        ),
        file="routes/auth.py",
        find='    session.pop("user_id", None)\n    return jsonify({"message": "Logged out successfully"}), 200',
        replace='    return jsonify({"message": "Logged out successfully"}), 200',
        verify='session.pop',
    ),
]

# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class BugResult:
    bug: Bug
    without_tokens: int = 0
    with_tokens: int = 0
    without_time: float = 0.0
    with_time: float = 0.0
    without_correct: bool = False
    with_correct: bool = False
    without_error: str = ""
    with_error: str = ""

    @property
    def token_savings(self) -> int:
        return self.without_tokens - self.with_tokens

    @property
    def token_savings_pct(self) -> float:
        if not self.without_tokens:
            return 0.0
        return self.token_savings / self.without_tokens * 100

    @property
    def time_savings(self) -> float:
        return self.without_time - self.with_time

    @property
    def miser_won(self) -> bool:
        return self.with_tokens < self.without_tokens


# ── Helpers ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are fixing a real bug in a Python Flask codebase. "
    "Return only the minimal patch or corrected code needed to fix the bug. "
    "Be concise."
)

EXAMPLE_PROJECT = Path(__file__).parent / "example_project"


def load_patched_source(bug: Bug) -> str:
    """Load the file and apply the bug in memory. Never writes to disk."""
    path = EXAMPLE_PROJECT / bug.file
    source = path.read_text(encoding="utf-8")
    if bug.find not in source:
        raise ValueError(
            f"Bug {bug.id}: find string not found in {bug.file}.\n"
            f"  Expected: {bug.find!r}"
        )
    return source.replace(bug.find, bug.replace, 1)


def build_full_file_prompt(bug: Bug, source: str) -> str:
    return "\n".join([
        f"Bug report: {bug.description}",
        "",
        f"The code below is the full contents of example_project/{bug.file}.",
        "Fix the bug and return only the minimal corrected patch or code.",
        "",
        "```python",
        source,
        "```",
    ])


def build_token_miser_prompt(bug: Bug, context: str) -> str:
    return "\n".join([
        f"Bug report: {bug.description}",
        "",
        "The following is the only relevant code selected by Token Miser.",
        "Fix the bug and return only the minimal corrected patch or code.",
        "",
        context,
    ])


def collect_miser_context_for_bug(
    bug: Bug,
    token_miser_cli: Path,
    patched_source: str,
) -> tuple[str, list[str]]:
    """Run miser_context + miser_read (+ callee expansion) against the example_project.

    Returns (context_string, selected_symbols).
    """
    def run(cmd: list[str]) -> str:
        result = subprocess.run(
            cmd, cwd=EXAMPLE_PROJECT, capture_output=True, text=True
        )
        return result.stdout.strip()

    ctx = run([sys.executable, str(token_miser_cli), "context", bug.description])
    if not ctx or "No relevant units found" in ctx:
        return f"Relevant file: example_project/{bug.file}\n\n{patched_source[:2000]}", []

    # Parse symbols and their depth-1 callees from context output.
    # Context lines look like:
    #   routes/auth.py::hash_password::def hash_password(password: str) -> str
    #   tests/test_auth.py::test_login::def test_login(client)  → User, hash_password
    symbols: list[str] = []
    callee_symbols: list[str] = []
    seen: set[str] = set()

    for line in ctx.splitlines():
        if "::" not in line:
            continue
        parts_line = line.split("::")
        # Format: file::symbol_name::signature  OR  file::signature (old format)
        if len(parts_line) >= 3:
            sym = parts_line[1].strip()
        else:
            sig_part = parts_line[-1].strip()
            m = re.search(r"(?:def|class)\s+(\w+)", sig_part)
            sym = m.group(1) if m else None

        if sym and sym not in seen:
            symbols.append(sym)
            seen.add(sym)

        # Extract callees from the → annotation (last segment of the line)
        last_part = parts_line[-1]
        arrow_idx = last_part.find("→")
        if arrow_idx != -1:
            callee_str = last_part[arrow_idx + 1:].strip()
            callee_str = re.sub(r"\s*\+\d+ more$", "", callee_str)
            for callee in callee_str.split(","):
                callee = callee.strip()
                if callee and callee not in seen:
                    callee_symbols.append(callee)
                    seen.add(callee)

    # Read initial symbols (cap at 6)
    read_chunks: list[str] = []
    for sym in symbols[:6]:
        chunk = run([sys.executable, str(token_miser_cli), "read", sym])
        if chunk and "not found" not in chunk.lower():
            chunk = chunk.replace(bug.find, bug.replace, 1)
            read_chunks.append(chunk)

    # Read depth-1 callees that weren't already read (cap at 4 additional)
    extra_read = 0
    for sym in callee_symbols:
        if extra_read >= 4:
            break
        if any(sym in chunk for chunk in read_chunks):
            continue  # already present in a read chunk
        chunk = run([sys.executable, str(token_miser_cli), "read", sym])
        if chunk and "not found" not in chunk.lower():
            chunk = chunk.replace(bug.find, bug.replace, 1)
            read_chunks.append(chunk)
            extra_read += 1

    parts = ["Signature context:", ctx, "", "Full source for selected symbols:"]
    parts.extend(read_chunks)
    return "\n\n".join(parts), symbols


def verify_response(response_text: str, verify: str) -> bool:
    return verify.lower() in response_text.lower()


def run_bug(
    bug: Bug,
    client,
    model: str,
    token_miser_cli: Path,
    verbose: bool = False,
    delay: float = 3.0,
) -> BugResult:
    result = BugResult(bug=bug)

    try:
        patched_source = load_patched_source(bug)
    except ValueError as e:
        result.without_error = str(e)
        result.with_error = str(e)
        return result

    # ── Without Token Miser ────────────────────────────────────────────────────
    try:
        prompt = build_full_file_prompt(bug, patched_source)
        t0 = time.perf_counter()
        tokens, response = call_openai(client, model, prompt, SYSTEM_PROMPT)
        result.without_time = time.perf_counter() - t0
        result.without_tokens = tokens
        result.without_correct = verify_response(response, bug.verify)
        if verbose:
            print(f"  [without] {tokens} tokens, correct={result.without_correct}")
    except Exception as e:
        result.without_error = str(e)
        if verbose:
            print(f"  [without] ERROR: {e}")

    if delay > 0:
        time.sleep(delay)

    # ── With Token Miser ──────────────────────────────────────────────────────
    try:
        context, selected_symbols = collect_miser_context_for_bug(bug, token_miser_cli, patched_source)
        prompt = build_token_miser_prompt(bug, context)
        t0 = time.perf_counter()
        tokens, response = call_openai(client, model, prompt, SYSTEM_PROMPT)
        result.with_time = time.perf_counter() - t0
        result.with_tokens = tokens
        result.with_correct = verify_response(response, bug.verify)
        if verbose:
            print(f"  [with]    {tokens} tokens, correct={result.with_correct}")
        if not result.with_correct and selected_symbols:
            print(f"  [with]    selected symbols: {', '.join(selected_symbols)}")
            print(f"  [with]    verify string '{bug.verify}' not found in response")
    except Exception as e:
        result.with_error = str(e)
        if verbose:
            print(f"  [with]    ERROR: {e}")

    return result


# ── Output formatting ──────────────────────────────────────────────────────────

CATEGORY_LABELS = {
    "single_line":    "Single-line",
    "wrong_function": "Wrong func",
    "multi_function": "Multi-func",
    "silent":         "Silent",
}


def format_per_bug_table(results: list[BugResult]) -> str:
    rows = []
    for r in results:
        cat = CATEGORY_LABELS.get(r.bug.category, r.bug.category)
        wo_tok = str(r.without_tokens) if not r.without_error else "ERR"
        wi_tok = str(r.with_tokens) if not r.with_error else "ERR"
        savings = f"{r.token_savings_pct:.0f}%" if (r.without_tokens and r.with_tokens) else "-"
        wo_ok = "✓" if r.without_correct else ("✗" if not r.without_error else "!")
        wi_ok = "✓" if r.with_correct else ("✗" if not r.with_error else "!")
        won = "✓" if r.miser_won else " "
        rows.append((
            str(r.bug.id).rjust(2),
            cat,
            r.bug.description[:52] + "…" if len(r.bug.description) > 53 else r.bug.description,
            wo_tok,
            wo_ok,
            wi_tok,
            wi_ok,
            savings,
            won,
        ))

    headers = ("#", "Category", "Description", "W/O Tok", "W/O✓", "W/ Tok", "W/✓", "Saved", "Win")
    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]

    def border(l, f, j, r):
        return l + j.join(f * (w + 2) for w in widths) + r

    def row_line(vals):
        return "│" + "│".join(f" {v:<{widths[i]}} " for i, v in enumerate(vals)) + "│"

    lines = [
        border("┌", "─", "┬", "┐"),
        row_line(headers),
        border("├", "─", "┼", "┤"),
    ]
    for r in rows:
        lines.append(row_line(r))
    lines.append(border("└", "─", "┴", "┘"))
    return "\n".join(lines)


def format_summary_table(results: list[BugResult]) -> str:
    valid = [r for r in results if r.without_tokens and r.with_tokens]
    if not valid:
        return "No valid results to summarize."

    avg_savings_pct = sum(r.token_savings_pct for r in valid) / len(valid)
    avg_time_savings = sum(r.time_savings for r in valid) / len(valid)
    win_rate = sum(1 for r in valid if r.miser_won) / len(valid) * 100
    without_accuracy = sum(1 for r in results if r.without_correct) / len(results) * 100
    with_accuracy = sum(1 for r in results if r.with_correct) / len(results) * 100

    by_cat: dict[str, list[BugResult]] = {}
    for r in valid:
        by_cat.setdefault(r.bug.category, []).append(r)

    rows = [
        ("Metric", "Value"),
        ("Bugs run", str(len(results))),
        ("Valid comparisons", str(len(valid))),
        ("Avg token savings", f"{avg_savings_pct:.1f}%"),
        ("Avg time savings", f"{avg_time_savings:.2f}s"),
        ("Win rate (tokens)", f"{win_rate:.0f}%"),
        ("Fix accuracy (without)", f"{without_accuracy:.0f}%"),
        ("Fix accuracy (with)", f"{with_accuracy:.0f}%"),
    ]
    for cat, cat_results in sorted(by_cat.items()):
        label = CATEGORY_LABELS.get(cat, cat)
        avg = sum(r.token_savings_pct for r in cat_results) / len(cat_results)
        rows.append((f"  Savings — {label}", f"{avg:.1f}%"))

    widths = [
        max(len(r[0]) for r in rows),
        max(len(r[1]) for r in rows),
    ]

    def border(l, f, j, r):
        return l + j.join(f * (w + 2) for w in widths) + r

    def row_line(vals):
        return f"│ {vals[0]:<{widths[0]}} │ {vals[1]:>{widths[1]}} │"

    lines = [
        border("┌", "─", "┬", "┐"),
        row_line(rows[0]),
        border("├", "─", "┼", "┤"),
    ]
    for r in rows[1:]:
        lines.append(row_line(r))
    lines.append(border("└", "─", "┴", "┘"))
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Token Miser vs full-file context across 20 Flask bugs."
    )
    parser.add_argument(
        "--token-miser-cli",
        default=os.environ.get(
            "TOKEN_MISER_CLI",
            "/Users/edinhdawg/Documents/KiroHacks/token-miser/src/cli.py",
        ),
    )
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--start", type=int, default=0, help="First bug index (0-based)")
    parser.add_argument("--end", type=int, default=20, help="Last bug index (exclusive)")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Seconds to wait between the two API calls per bug (default: 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate all bug patches without calling OpenAI.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token_miser_cli = Path(args.token_miser_cli).resolve()

    if not token_miser_cli.exists():
        raise SystemExit(f"Token Miser CLI not found: {token_miser_cli}")

    bugs = BUGS[args.start:args.end]

    # ── Dry run: just validate patches ────────────────────────────────────────
    if args.dry_run:
        print(f"Validating {len(bugs)} bug patches against example_project/...\n")
        ok = 0
        for bug in bugs:
            try:
                patched = load_patched_source(bug)
                assert bug.replace in patched, "replace string not in patched source"
                print(f"  [{bug.id:2d}] ✓  {bug.description[:60]}")
                ok += 1
            except Exception as e:
                print(f"  [{bug.id:2d}] ✗  {e}")
        print(f"\n{ok}/{len(bugs)} patches valid.")
        return

    client = require_openai()

    print(f"Running {len(bugs)} bugs  |  model: {args.model}")
    print(f"Token Miser CLI: {token_miser_cli}\n")

    results: list[BugResult] = []
    for i, bug in enumerate(bugs, 1):
        print(f"[{i:2d}/{len(bugs)}] Bug {bug.id} ({bug.category}): {bug.description[:60]}…")
        result = run_bug(bug, client, args.model, token_miser_cli, verbose=args.verbose, delay=args.delay)
        results.append(result)

        if result.without_error or result.with_error:
            if result.without_error:
                print(f"       without error: {result.without_error[:80]}")
            if result.with_error:
                print(f"       with error:    {result.with_error[:80]}")

    print()
    print("── Per-bug results ──────────────────────────────────────────────────────────")
    print(format_per_bug_table(results))
    print()
    print("── Summary ──────────────────────────────────────────────────────────────────")
    print(format_summary_table(results))


if __name__ == "__main__":
    main()
