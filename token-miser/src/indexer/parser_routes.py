"""Supplemental parser for common web route declarations."""

import re
from typing import List, Optional

from indexer.models import CodeUnit


ROUTE_CALL_RE = re.compile(
    r"\b(?P<router>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*"
    r"(?P<method>get|post|put|patch|delete)\s*\(",
    re.IGNORECASE,
)


def _line_number(source: str, offset: int) -> int:
    return source[:offset].count("\n") + 1


def _sanitize_route(route_path: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", route_path.replace(":", " "))
    return "_".join(part.lower() for part in parts) or "root"


def _read_first_string(source: str, start: int) -> Optional[str]:
    i = start
    while i < len(source) and source[i].isspace():
        i += 1
    if i >= len(source) or source[i] not in ("'", '"', "`"):
        return None

    quote = source[i]
    i += 1
    chars = []
    escaped = False
    while i < len(source):
        char = source[i]
        if escaped:
            chars.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return "".join(chars)
        else:
            chars.append(char)
        i += 1
    return None


def _find_call_end(source: str, open_paren: int) -> int:
    depth = 0
    quote = None
    escaped = False
    i = open_paren

    while i < len(source):
        char = source[i]

        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        else:
            if char in ("'", '"', "`"):
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    while i < len(source) and source[i].isspace():
                        i += 1
                    if i < len(source) and source[i] == ";":
                        i += 1
                    return i

        i += 1

    return open_paren


def _route_prefix(lines: List[str], route_start_line: int) -> str:
    prefix = []
    for line in lines[:route_start_line - 1]:
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("import ")
            or stripped.startswith("export const ")
            or stripped.startswith("const ")
            or stripped.startswith("let ")
            or stripped.startswith("var ")
        ):
            prefix.append(line)
    return "".join(prefix).rstrip()


def parse_route_handlers(file_path: str, source: str, language: str) -> List[CodeUnit]:
    """Extract Express-style route handlers from JavaScript and TypeScript files."""
    if language not in ("javascript", "typescript"):
        return []

    units: List[CodeUnit] = []
    lines = source.splitlines(keepends=True)

    for match in ROUTE_CALL_RE.finditer(source):
        router = match.group("router")
        method = match.group("method").lower()
        open_paren = source.find("(", match.start())
        if open_paren == -1:
            continue

        route_path = _read_first_string(source, open_paren + 1)
        if route_path is None:
            continue

        end_offset = _find_call_end(source, open_paren)
        if end_offset <= open_paren:
            continue

        start_line = _line_number(source, match.start())
        end_line = _line_number(source, end_offset)
        route_label = _sanitize_route(route_path)
        symbol_name = f"{method}_{route_label}"
        signature = f'route {method.upper()} "{route_path}"'

        route_source = source[match.start():end_offset].rstrip()
        prefix = _route_prefix(lines, start_line)
        full_code = f"{prefix}\n\n{route_source}" if prefix else route_source

        units.append(CodeUnit(
            unit_id=None,
            file_path=file_path,
            symbol_name=symbol_name,
            unit_type="route",
            parent_class=router,
            signature=signature,
            start_line=start_line,
            end_line=end_line,
            full_code=full_code,
        ))

    return units
