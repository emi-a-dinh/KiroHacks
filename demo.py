#!/usr/bin/env python3
"""Compare fixing a Flask bug with and without Token Miser using OpenAI."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BUG_DESCRIPTION = (
    "In src/flask/app.py, full_dispatch_request is calling "
    "self.dispatch_request() without passing ctx, causing all requests "
    "to fail with a TypeError."
)
MODEL = "gpt-4.1-mini"
TARGET_RELATIVE_PATH = Path("src/flask/app.py")
FIXED_CALL = "rv = self.dispatch_request(ctx)"
BUGGY_CALL = "rv = self.dispatch_request()"
SYSTEM_PROMPT = (
    "You are fixing a real bug in a Python codebase. "
    "Return only the minimal patch or corrected code needed to fix the bug."
)


@dataclass
class ApproachResult:
    name: str
    input_tokens: int
    elapsed_seconds: float
    response_text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare OpenAI token usage with and without Token Miser."
    )
    parser.add_argument(
        "--flask-repo",
        default=os.environ.get("FLASK_REPO_PATH", "/Users/edinhdawg/Documents/flask"),
        help="Path to the local Flask repository.",
    )
    parser.add_argument(
        "--token-miser-cli",
        default=os.environ.get(
            "TOKEN_MISER_CLI",
            "/Users/edinhdawg/Documents/KiroHacks/token-miser/src/cli.py",
        ),
        help="Path to Token Miser's cli.py.",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help="OpenAI model to use.",
    )
    return parser.parse_args()


def require_openai():
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency check
        raise SystemExit(
            "The OpenAI SDK is required. Install it with `pip install openai`."
        ) from exc

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENAI_API_KEY before running this demo.")

    return OpenAI(api_key=api_key)


def load_source(flask_repo: Path) -> tuple[Path, str, bool]:
    target_path = flask_repo / TARGET_RELATIVE_PATH
    if not target_path.exists():
        raise SystemExit(f"Target file not found: {target_path}")

    source = target_path.read_text(encoding="utf-8")
    synthesized_bug = BUGGY_CALL not in source and FIXED_CALL in source

    if synthesized_bug:
        source = source.replace(FIXED_CALL, BUGGY_CALL, 1)

    return target_path, source, synthesized_bug


def run_subprocess(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def parse_symbols(context_output: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    for line in context_output.splitlines():
        if "::" not in line:
            continue
        parts = line.split("::", 2)
        if len(parts) < 3:
            continue
        symbol = parts[1].strip()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)

    if not symbols:
        raise RuntimeError("Token Miser returned no readable symbols.")

    return symbols


def maybe_synthesize_bug(text: str, synthesize: bool) -> str:
    if synthesize and FIXED_CALL in text and BUGGY_CALL not in text:
        return text.replace(FIXED_CALL, BUGGY_CALL, 1)
    return text


def collect_token_miser_context(
    flask_repo: Path, token_miser_cli: Path, synthesize_bug: bool
) -> str:
    context_output = run_subprocess(
        [sys.executable, str(token_miser_cli), "context", BUG_DESCRIPTION],
        cwd=flask_repo,
    )
    symbols = parse_symbols(context_output)

    read_chunks = []
    for symbol in symbols:
        chunk = run_subprocess(
            [sys.executable, str(token_miser_cli), "read", symbol],
            cwd=flask_repo,
        )
        read_chunks.append(maybe_synthesize_bug(chunk, synthesize_bug))

    return "\n\n".join(
        [
            "Signature context:",
            maybe_synthesize_bug(context_output, synthesize_bug),
            "",
            "Full source for selected symbols:",
            *read_chunks,
        ]
    )


def extract_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    parts: list[str] = []
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    for block in getattr(response, "content", []):
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def verify_fix(response_text: str) -> None:
    if not re.search(r"dispatch_request\s*\(\s*ctx\s*\)", response_text):
        raise RuntimeError(
            "The model response did not include `dispatch_request(ctx)`."
        )


def count_input_tokens(client, model: str, prompt: str) -> int:
    counted = client.responses.input_tokens.count(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=prompt,
    )
    return counted.input_tokens


def call_openai(client, model: str, prompt: str) -> tuple[int, str]:
    input_tokens = count_input_tokens(client, model, prompt)

    try:
        response = client.responses.create(
        model=model,
        max_output_tokens=600,
        instructions=SYSTEM_PROMPT,
        input=prompt,
        )
    except Exception as exc:
        message = str(exc)
        if "tokens per min" in message or "TPM" in message:
            raise RuntimeError(
                f"OpenAI rejected model {model!r} for this prompt under your current "
                f"rate limits. Preflight input tokens: {input_tokens}. "
                "Try a higher-TPM model such as `gpt-4.1-mini`, or increase your "
                "account limits in the OpenAI dashboard."
            ) from exc
        raise

    text = extract_text(response)
    verify_fix(text)
    return input_tokens, text


def build_full_file_prompt(source: str) -> str:
    return "\n".join(
        [
            f"Bug report: {BUG_DESCRIPTION}",
            "",
            "The code below is the full contents of src/flask/app.py.",
            "Fix the bug and return only the minimal corrected patch or code.",
            "",
            "```python",
            source,
            "```",
        ]
    )


def build_token_miser_prompt(context: str) -> str:
    return "\n".join(
        [
            f"Bug report: {BUG_DESCRIPTION}",
            "",
            "The following is the only relevant code selected by Token Miser.",
            "Fix the bug and return only the minimal corrected patch or code.",
            "",
            context,
        ]
    )


def run_approach(name: str, runner) -> ApproachResult:
    started = time.perf_counter()
    input_tokens, response_text = runner()
    elapsed = time.perf_counter() - started
    return ApproachResult(
        name=name,
        input_tokens=input_tokens,
        elapsed_seconds=elapsed,
        response_text=response_text,
    )


def format_table(rows: Iterable[tuple[str, str, str]]) -> str:
    rows = list(rows)
    headers = ("Approach", "Input Tokens", "Time")
    widths = [
        max(len(headers[0]), *(len(row[0]) for row in rows)),
        max(len(headers[1]), *(len(row[1]) for row in rows)),
        max(len(headers[2]), *(len(row[2]) for row in rows)),
    ]

    def border(left: str, fill: str, join: str, right: str) -> str:
        return left + join.join(fill * (width + 2) for width in widths) + right

    def line(values: tuple[str, str, str]) -> str:
        return (
            f"│ {values[0]:<{widths[0]}} │ "
            f"{values[1]:>{widths[1]}} │ "
            f"{values[2]:>{widths[2]}} │"
        )

    parts = [
        border("┌", "─", "┬", "┐"),
        line(headers),
        border("├", "─", "┼", "┤"),
    ]
    parts.extend(line(row) for row in rows)
    parts.append(border("└", "─", "┴", "┘"))
    return "\n".join(parts)


def main() -> None:
    args = parse_args()
    flask_repo = Path(args.flask_repo).resolve()
    token_miser_cli = Path(args.token_miser_cli).resolve()

    if not token_miser_cli.exists():
        raise SystemExit(f"Token Miser CLI not found: {token_miser_cli}")

    target_path, full_source, synthesized_bug = load_source(flask_repo)
    client = require_openai()

    without_result = run_approach(
        "Without Token Miser",
        lambda: call_openai(
            client,
            args.model,
            build_full_file_prompt(full_source),
        ),
    )

    with_result = run_approach(
        "With Token Miser",
        lambda: call_openai(
            client,
            args.model,
            build_token_miser_prompt(
                collect_token_miser_context(
                    flask_repo=flask_repo,
                    token_miser_cli=token_miser_cli,
                    synthesize_bug=synthesized_bug,
                )
            ),
        ),
    )

    token_savings = without_result.input_tokens - with_result.input_tokens
    token_pct = (token_savings / without_result.input_tokens) * 100
    time_savings = without_result.elapsed_seconds - with_result.elapsed_seconds

    if synthesized_bug:
        print(
            "Note: the local Flask checkout already contains the fix, so the demo "
            "recreates the buggy `dispatch_request()` call in memory before sending "
            "context to OpenAI."
        )
        print()

    print(f"Target: {target_path}")
    print(f"Model: {args.model}")
    print()
    print(
        format_table(
            [
                (
                    without_result.name,
                    str(without_result.input_tokens),
                    f"{without_result.elapsed_seconds:.1f}s",
                ),
                (
                    with_result.name,
                    str(with_result.input_tokens),
                    f"{with_result.elapsed_seconds:.1f}s",
                ),
                (
                    "Savings",
                    f"{token_savings} ({token_pct:.1f}%)",
                    f"{time_savings:.1f}s",
                ),
            ]
        )
    )


if __name__ == "__main__":
    main()
