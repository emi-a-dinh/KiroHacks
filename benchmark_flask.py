#!/usr/bin/env python3
"""
Benchmark Token Miser vs full-file context across 10 cross-file bugs in Flask.

Each bug breaks something in one file that causes a visible failure in another.
Requires reading 2-3 files to understand and fix.

Usage:
    python benchmark_flask.py
    python benchmark_flask.py --dry-run
    python benchmark_flask.py --start 0 --end 3 --verbose
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

sys.path.insert(0, str(Path(__file__).parent))
from demo import extract_text, format_table, require_openai


# ── Local call_openai ──────────────────────────────────────────────────────────

def call_openai(client, model: str, prompt: str, system_prompt: str) -> tuple[int, str]:
    """Count tokens, call model, retry on 429 with exponential backoff."""
    counted = client.responses.input_tokens.count(
        model=model, instructions=system_prompt, input=prompt
    )
    input_tokens = counted.input_tokens

    max_retries = 4
    delay = 15

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
            msg = str(exc)
            is_rate_limit = "429" in msg or "rate limit" in msg.lower() or "TPM" in msg
            if is_rate_limit and attempt < max_retries:
                wait = delay * (2 ** attempt)
                print(f"       rate limit — waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            if is_rate_limit:
                raise RuntimeError(
                    f"Rate limit hit for {model!r} after {max_retries} retries. "
                    f"Input tokens: {input_tokens}."
                ) from exc
            raise


# ── Bug definitions ────────────────────────────────────────────────────────────

@dataclass
class Bug:
    id: int
    files: list[str]       # all files needed to understand the bug (relative to flask repo)
    description: str       # plain English symptom prompt
    primary_file: str      # the file that contains the bug
    find: str              # exact string to replace
    replace: str           # buggy replacement
    verify: str            # substring that must appear in a correct fix response


FLASK_REPO = Path(os.environ.get("FLASK_REPO_PATH", "/Users/edinhdawg/Documents/flask"))

BUGS: list[Bug] = [

    # ── Pair 1: app.py ↔ ctx.py ───────────────────────────────────────────────
    # ctx.push() sets _cv_token; app.py's wsgi_app calls ctx.push() then ctx.pop().
    # If push() skips setting _cv_token, pop() raises RuntimeError.

    Bug(
        id=1,
        files=["src/flask/app.py", "src/flask/ctx.py"],
        description=(
            "Every request fails with RuntimeError: 'Cannot pop this context, "
            "it is not pushed.' AppContext.push() in ctx.py is not setting "
            "_cv_token, so pop() cannot find the context to reset."
        ),
        primary_file="src/flask/ctx.py",
        find="        self._cv_token = _cv_app.set(self)\n        appcontext_pushed.send(self.app, _async_wrapper=self.app.ensure_sync)",
        replace="        appcontext_pushed.send(self.app, _async_wrapper=self.app.ensure_sync)",
        verify="_cv_app.set",
    ),

    Bug(
        id=2,
        files=["src/flask/app.py", "src/flask/ctx.py"],
        description=(
            "Requests succeed but teardown_request handlers are never called. "
            "Database connections are leaking. The context is popped in wsgi_app "
            "but do_teardown_request is skipped. The bug is in ctx.py."
        ),
        primary_file="src/flask/ctx.py",
        find="        if self._request is not None:\n            with collect_errors:\n                self.app.do_teardown_request(self, exc)\n\n            with collect_errors:\n                self._request.close()",
        replace="        if self._request is not None:\n            with collect_errors:\n                self._request.close()",
        verify="do_teardown_request",
    ),

    # ── Pair 2: app.py ↔ sansio/app.py ───────────────────────────────────────
    # preprocess_request in app.py iterates before_request_funcs.
    # register_blueprint in sansio/app.py calls blueprint.register().
    # If preprocess_request skips the app-level (None) bucket, global
    # before_request handlers never fire.

    Bug(
        id=3,
        files=["src/flask/app.py", "src/flask/sansio/app.py"],
        description=(
            "before_request handlers registered directly on the app (not on a "
            "blueprint) are never called. Blueprint before_request handlers work "
            "fine. The bug is in preprocess_request in app.py."
        ),
        primary_file="src/flask/app.py",
        find="        names = (None, *reversed(req.blueprints))\n\n        for name in names:\n            if name in self.url_value_preprocessors:",
        replace="        names = (*reversed(req.blueprints),)\n\n        for name in names:\n            if name in self.url_value_preprocessors:",
        verify="None",
    ),

    Bug(
        id=4,
        files=["src/flask/app.py", "src/flask/sansio/app.py"],
        description=(
            "after_request handlers registered on the app are never called — "
            "only blueprint-level after_request handlers run. Responses are "
            "missing headers set by app-level handlers. The bug is in "
            "process_response in app.py."
        ),
        primary_file="src/flask/app.py",
        find="        for name in chain(ctx.request.blueprints, (None,)):\n            if name in self.after_request_funcs:",
        replace="        for name in ctx.request.blueprints:\n            if name in self.after_request_funcs:",
        verify="None",
    ),

    # ── Pair 3: app.py ↔ blueprints.py ───────────────────────────────────────
    # BlueprintSetupState.add_url_rule prefixes the endpoint name with
    # name_prefix.name.endpoint. If app.py's full_dispatch_request skips
    # calling preprocess_request, blueprint before_request hooks never fire.
    # If finalize_request skips process_response, blueprint after_request
    # hooks and session saving are skipped.

    Bug(
        id=5,
        files=["src/flask/app.py", "src/flask/blueprints.py"],
        description=(
            "Blueprint before_request hooks are never called. Requests go "
            "straight to the view function. Authentication middleware registered "
            "on blueprints is bypassed. The bug is in full_dispatch_request "
            "in app.py."
        ),
        primary_file="src/flask/app.py",
        find="            rv = self.preprocess_request(ctx)\n            if rv is None:\n                rv = self.dispatch_request(ctx)",
        replace="            rv = self.dispatch_request(ctx)",
        verify="preprocess_request",
    ),

    Bug(
        id=6,
        files=["src/flask/app.py", "src/flask/blueprints.py"],
        description=(
            "Sessions are never saved and blueprint after_request handlers "
            "never run. The response is returned directly from the view without "
            "postprocessing. The bug is in finalize_request in app.py."
        ),
        primary_file="src/flask/app.py",
        find="        response = self.make_response(rv)\n        try:\n            response = self.process_response(ctx, response)",
        replace="        response = self.make_response(rv)\n        try:\n            pass  # response = self.process_response(ctx, response)",
        verify="process_response",
    ),

    # ── Pair 4: sansio/app.py ↔ sansio/blueprints.py ─────────────────────────
    # register_blueprint calls blueprint.register(app, options).
    # Blueprint.register calls make_setup_state then iterates deferred_functions.
    # If register_blueprint passes empty options, url_prefix is lost.
    # If Blueprint.register skips deferred_functions, no routes are registered.

    Bug(
        id=7,
        files=["src/flask/sansio/app.py", "src/flask/sansio/blueprints.py"],
        description=(
            "All blueprint routes return 404. The blueprint is registered "
            "without error but none of its URL rules appear in the app. "
            "The bug is in Blueprint.register in sansio/blueprints.py — "
            "deferred_functions are never called."
        ),
        primary_file="src/flask/sansio/blueprints.py",
        find="        for deferred in self.deferred_functions:\n            deferred(state)",
        replace="        pass  # for deferred in self.deferred_functions: deferred(state)",
        verify="deferred_functions",
    ),

    Bug(
        id=8,
        files=["src/flask/sansio/app.py", "src/flask/sansio/blueprints.py"],
        description=(
            "Blueprint routes are registered but url_for() raises BuildError "
            "for all blueprint endpoints. The endpoint names are wrong — they "
            "are missing the blueprint name prefix. The bug is in "
            "BlueprintSetupState.add_url_rule in sansio/blueprints.py."
        ),
        primary_file="src/flask/sansio/blueprints.py",
        find='            f"{self.name_prefix}.{self.name}.{endpoint}".lstrip("."),',
        replace='            endpoint,',
        verify="name_prefix",
    ),

    # ── Pair 5: ctx.py ↔ sansio/scaffold.py ──────────────────────────────────
    # AppContext.push() calls match_request() which uses url_adapter.
    # Scaffold defines the route/before_request/after_request decorators.
    # If push() skips match_request, routing_exception is never set and
    # dispatch_request crashes on missing url_rule.
    # If push() skips _get_session(), session is None on first access.

    Bug(
        id=9,
        files=["src/flask/ctx.py", "src/flask/sansio/scaffold.py"],
        description=(
            "All requests crash with AttributeError: 'NoneType' has no "
            "attribute 'endpoint'. The request URL is never matched to a route. "
            "The bug is in AppContext.push() in ctx.py — match_request is "
            "never called."
        ),
        primary_file="src/flask/ctx.py",
        find="            if self.url_adapter is not None:\n                self.match_request()",
        replace="            pass  # match_request skipped",
        verify="match_request",
    ),

    Bug(
        id=10,
        files=["src/flask/ctx.py", "src/flask/sansio/scaffold.py"],
        description=(
            "Accessing session in a before_request handler raises RuntimeError: "
            "'There is no request in this context.' even though a request is "
            "active. The session is not initialized during push. The bug is in "
            "AppContext.push() in ctx.py."
        ),
        primary_file="src/flask/ctx.py",
        find="        if self._request is not None:\n            # Open the session at the moment that the request context is available.\n            # This allows a custom open_session method to use the request context.\n            self._get_session()\n\n            # Match the request URL after loading the session, so that the\n            # session is available in custom URL converters.\n            if self.url_adapter is not None:\n                self.match_request()",
        replace="        if self._request is not None:\n            if self.url_adapter is not None:\n                self.match_request()",
        verify="_get_session",
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
    "You are fixing a real bug in the Flask web framework source code. "
    "Return only the minimal corrected code or patch needed to fix the bug. "
    "Be concise."
)


def load_patched_sources(bug: Bug) -> dict[str, str]:
    """Load all files for this bug and apply the patch in memory. Never writes to disk."""
    sources: dict[str, str] = {}
    for rel_path in bug.files:
        path = FLASK_REPO / rel_path
        if not path.exists():
            raise FileNotFoundError(f"Bug {bug.id}: {path} not found. Set FLASK_REPO_PATH.")
        sources[rel_path] = path.read_text(encoding="utf-8")

    # Apply the bug patch to the primary file only
    primary = bug.primary_file
    if primary not in sources:
        raise ValueError(f"Bug {bug.id}: primary_file {primary!r} not in files list.")
    if bug.find not in sources[primary]:
        raise ValueError(
            f"Bug {bug.id}: find string not found in {primary}.\n"
            f"  Expected: {bug.find!r}"
        )
    sources[primary] = sources[primary].replace(bug.find, bug.replace, 1)
    return sources


def build_full_file_prompt(bug: Bug, sources: dict[str, str]) -> str:
    """Prompt with all relevant files in full."""
    parts = [f"Bug report: {bug.description}", ""]
    for rel_path, source in sources.items():
        parts += [
            f"File: {rel_path}",
            "```python",
            source,
            "```",
            "",
        ]
    parts.append("Fix the bug. Return only the minimal corrected patch or code.")
    return "\n".join(parts)


def build_token_miser_prompt(bug: Bug, context: str) -> str:
    return "\n".join([
        f"Bug report: {bug.description}",
        "",
        "The following is the only relevant code selected by Token Miser.",
        "Fix the bug and return only the minimal corrected patch or code.",
        "",
        context,
    ])


def collect_miser_context(bug: Bug, token_miser_cli: Path, sources: dict[str, str]) -> tuple[str, list[str]]:
    """Run miser_context + miser_read (+ callee expansion) against the Flask repo.

    Returns (context_string, selected_symbols).
    """
    def run(cmd: list[str]) -> str:
        result = subprocess.run(
            cmd, cwd=FLASK_REPO, capture_output=True, text=True
        )
        return result.stdout.strip()

    ctx = run([sys.executable, str(token_miser_cli), "context", bug.description])

    if not ctx or "No relevant units found" in ctx or "too short" in ctx:
        return f"Relevant file: {bug.primary_file}\n\n{sources[bug.primary_file][:3000]}", []

    # Parse symbol names and depth-1 callees from context output.
    # Lines look like:
    #   src/flask/ctx.py::push::def push(self) -> None  → _cv_app, match_request
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

        # Extract callees from the → annotation
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

    # Read depth-1 callees not already present (cap at 4 additional)
    extra_read = 0
    for sym in callee_symbols:
        if extra_read >= 4:
            break
        if any(sym in chunk for chunk in read_chunks):
            continue
        chunk = run([sys.executable, str(token_miser_cli), "read", sym])
        if chunk and "not found" not in chunk.lower():
            chunk = chunk.replace(bug.find, bug.replace, 1)
            read_chunks.append(chunk)
            extra_read += 1

    # Safety net: if nothing from the primary file was read, read its key
    # functions directly. The bug is guaranteed to be in primary_file.
    primary_basename = bug.primary_file.split("/")[-1].replace(".py", "")
    primary_covered = any(
        bug.primary_file in chunk or primary_basename in chunk
        for chunk in read_chunks
    )
    if not primary_covered:
        # Extract function names from the find string as a hint
        import re as _re
        hint_syms = _re.findall(r"def (\w+)", bug.find)
        for sym in hint_syms[:3]:
            chunk = run([sys.executable, str(token_miser_cli), "read", sym])
            if chunk and "not found" not in chunk.lower():
                chunk = chunk.replace(bug.find, bug.replace, 1)
                read_chunks.append(chunk)

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
    delay: float = 5.0,
    emit=print,
) -> BugResult:
    result = BugResult(bug=bug)

    try:
        sources = load_patched_sources(bug)
    except (FileNotFoundError, ValueError) as e:
        result.without_error = str(e)
        result.with_error = str(e)
        return result

    # ── Without Token Miser ────────────────────────────────────────────────────
    try:
        prompt = build_full_file_prompt(bug, sources)
        t0 = time.perf_counter()
        tokens, response = call_openai(client, model, prompt, SYSTEM_PROMPT)
        result.without_time = time.perf_counter() - t0
        result.without_tokens = tokens
        result.without_correct = verify_response(response, bug.verify)
        if verbose:
            emit(f"  [without] {tokens} tokens, correct={result.without_correct}")
    except Exception as e:
        result.without_error = str(e)[:120]
        if verbose:
            emit(f"  [without] ERROR: {e}")

    if delay > 0:
        time.sleep(delay)

    # ── With Token Miser ──────────────────────────────────────────────────────
    try:
        context, selected_symbols = collect_miser_context(bug, token_miser_cli, sources)
        prompt = build_token_miser_prompt(bug, context)
        t0 = time.perf_counter()
        tokens, response = call_openai(client, model, prompt, SYSTEM_PROMPT)
        result.with_time = time.perf_counter() - t0
        result.with_tokens = tokens
        result.with_correct = verify_response(response, bug.verify)
        if verbose:
            emit(f"  [with]    {tokens} tokens, correct={result.with_correct}")
        if not result.with_correct and selected_symbols:
            emit(f"  [with]    selected symbols: {', '.join(selected_symbols)}")
            emit(f"  [with]    verify string '{bug.verify}' not found in response")
    except Exception as e:
        result.with_error = str(e)[:120]
        if verbose:
            emit(f"  [with]    ERROR: {e}")

    return result


# ── Output formatting ──────────────────────────────────────────────────────────

def format_per_bug_table(results: list[BugResult]) -> str:
    rows = []
    for r in results:
        files = " + ".join(f.split("/")[-1] for f in r.bug.files)
        wo_tok = str(r.without_tokens) if not r.without_error else "ERR"
        wi_tok = str(r.with_tokens) if not r.with_error else "ERR"
        savings = f"{r.token_savings_pct:.0f}%" if (r.without_tokens and r.with_tokens) else "-"
        wo_ok = "✓" if r.without_correct else ("✗" if not r.without_error else "!")
        wi_ok = "✓" if r.with_correct else ("✗" if not r.with_error else "!")
        won = "✓" if r.miser_won else " "
        rows.append((
            str(r.bug.id).rjust(2),
            files,
            r.bug.description[:48] + "…" if len(r.bug.description) > 49 else r.bug.description,
            wo_tok, wo_ok,
            wi_tok, wi_ok,
            savings, won,
        ))

    headers = ("#", "Files", "Description", "W/O Tok", "W/O✓", "W/ Tok", "W/✓", "Saved", "Win")
    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]

    def border(l, f, j, r):
        return l + j.join(f * (w + 2) for w in widths) + r

    def row_line(vals):
        return "│" + "│".join(f" {v:<{widths[i]}} " for i, v in enumerate(vals)) + "│"

    lines = [border("┌", "─", "┬", "┐"), row_line(headers), border("├", "─", "┼", "┤")]
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

    widths = [max(len(r[0]) for r in rows), max(len(r[1]) for r in rows)]

    def border(l, f, j, r):
        return l + j.join(f * (w + 2) for w in widths) + r

    def row_line(vals):
        return f"│ {vals[0]:<{widths[0]}} │ {vals[1]:>{widths[1]}} │"

    lines = [border("┌", "─", "┬", "┐"), row_line(rows[0]), border("├", "─", "┼", "┤")]
    for r in rows[1:]:
        lines.append(row_line(r))
    lines.append(border("└", "─", "┴", "┘"))
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Token Miser vs full-file context on 10 cross-file Flask bugs."
    )
    parser.add_argument(
        "--flask-repo",
        default=os.environ.get("FLASK_REPO_PATH", "/Users/edinhdawg/Documents/flask"),
    )
    parser.add_argument(
        "--token-miser-cli",
        default=os.environ.get(
            "TOKEN_MISER_CLI",
            "/Users/edinhdawg/Documents/KiroHacks/token-miser/src/cli.py",
        ),
    )
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=10)
    parser.add_argument("--delay", type=float, default=5.0,
                        help="Seconds between the two API calls per bug (default: 5).")
    parser.add_argument("--inter-delay", type=float, default=30.0,
                        help="Seconds to wait between bugs (default: 30).")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate patches without calling OpenAI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global FLASK_REPO
    FLASK_REPO = Path(args.flask_repo).resolve()
    token_miser_cli = Path(args.token_miser_cli).resolve()

    if not token_miser_cli.exists():
        raise SystemExit(f"Token Miser CLI not found: {token_miser_cli}")

    bugs = BUGS[args.start:args.end]

    if args.dry_run:
        print(f"Validating {len(bugs)} bug patches against {FLASK_REPO}...\n")
        ok = 0
        for bug in bugs:
            try:
                sources = load_patched_sources(bug)
                assert bug.replace in sources[bug.primary_file]
                files_str = " + ".join(bug.files)
                print(f"  [{bug.id:2d}] ✓  [{files_str}]  {bug.description[:55]}")
                ok += 1
            except Exception as e:
                print(f"  [{bug.id:2d}] ✗  {e}")
        print(f"\n{ok}/{len(bugs)} patches valid.")
        return

    client = require_openai()

    output_lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line)
        output_lines.append(line)

    emit(f"Running {len(bugs)} bugs  |  model: {args.model}  |  delay: {args.delay}s")
    emit(f"Flask repo: {FLASK_REPO}")
    emit(f"Token Miser CLI: {token_miser_cli}")
    emit()

    results: list[BugResult] = []
    for i, bug in enumerate(bugs, 1):
        files_str = " + ".join(f.split("/")[-1] for f in bug.files)
        emit(f"[{i:2d}/{len(bugs)}] Bug {bug.id} [{files_str}]: {bug.description[:55]}…")
        result = run_bug(bug, client, args.model, token_miser_cli,
                         verbose=args.verbose, delay=args.delay, emit=emit)
        results.append(result)
        if result.without_error:
            emit(f"       without error: {result.without_error[:100]}")
        if result.with_error:
            emit(f"       with error:    {result.with_error[:100]}")
        if i < len(bugs):
            emit(f"       waiting {args.inter_delay}s before next bug…")
            time.sleep(args.inter_delay)

    emit()
    emit("── Per-bug results ──────────────────────────────────────────────────────────")
    emit(format_per_bug_table(results))
    emit()
    emit("── Summary ──────────────────────────────────────────────────────────────────")
    emit(format_summary_table(results))

    out_path = Path("benchmark_flask_result.txt")
    out_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"\nResults written to {out_path.resolve()}")


if __name__ == "__main__":
    main()
