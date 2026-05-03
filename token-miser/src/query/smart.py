"""
Smart commands — lens fix, lens ask, lens plan.

These combine indexing, selection, and expansion into a single call.
No manual unit IDs, no manual index, no manual expand.
"""

from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


def _ensure_index(repo_path: str) -> str:
    """
    Ensure the repo is indexed. Only runs a full index if the database
    doesn't exist yet. Otherwise trusts that the file-save and file-delete
    hooks keep the index fresh.
    """
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    repo = Path(repo_path).resolve()
    index_path = str(repo / ".token-miser" / "index.db")

    if Path(index_path).exists():
        from storage.db import Database
        from indexer.core import PARSER_VERSION, run_index
        with Database(index_path) as db:
            if db.get_metadata("parser_version") == PARSER_VERSION:
                return index_path
        result = run_index(repo_path)
        return result.index_path

    from indexer.core import run_index
    result = run_index(repo_path)
    return result.index_path


def _format_edge_comment(
    label: str,
    unit_ids: List[int],
    id_to_unit: Dict[int, "CodeUnit"],
) -> str:
    """Format edge info as a comment."""
    if not unit_ids:
        return f"# {label}: (none)"
    items = []
    for uid in unit_ids:
        unit = id_to_unit.get(uid)
        if unit:
            name = unit.symbol_name
            if unit.parent_class:
                name = f"{unit.parent_class}.{name}"
            items.append(f"{name} [{uid}]")
    return f"# {label}: {', '.join(items)}"


def _build_context_block(
    selected_units,  # List[SelectedUnit]
    db: "Database",
) -> str:
    """Build the expanded code block for selected units."""
    units = [su.unit for su in selected_units]
    all_ids = [u.unit_id for u in units if u.unit_id]
    id_to_unit = {u.unit_id: u for u in units if u.unit_id}
    calls, called_by = db.get_edges_for_units(all_ids)

    lines = []
    for su in selected_units:
        unit = su.unit
        uid = unit.unit_id

        header = f"### {unit.file_path} — {unit.symbol_name}"
        if unit.parent_class:
            header = f"### {unit.file_path} — {unit.parent_class}.{unit.symbol_name}"
        header += f" (lines {unit.start_line}–{unit.end_line})"
        lines.append(header)

        if uid:
            lines.append(_format_edge_comment("Called by", called_by.get(uid, []), id_to_unit))
            lines.append(_format_edge_comment("Calls", calls.get(uid, []), id_to_unit))

        lines.append(unit.full_code.rstrip())
        lines.append("")

    return "\n".join(lines)


# ── Caveman mode ───────────────────────────────────────────────────────────────

_CAVEMAN_INSTRUCTIONS = {
    "fix":  "Edit. Use C first. Inspect nearest route/service/test if needed. Add or update tests. Run tests. Reply: Changed, Tests, Result.",
    "ask":  "Answer from C only. If missing, say what file to check.",
    "plan": "Plan only. Use C. Output steps and files.",
}

_CAVEMAN_K = {
    "fix":  8,
    "ask":  5,
    "plan": 10,
}

_UNIT_TRUNCATE_LINES = 120  # lines; units larger than this get trimmed in caveman mode


def _maybe_truncate(code: str) -> str:
    """Truncate very large units in caveman mode, keeping signature + body start."""
    lines = code.splitlines()
    if len(lines) <= _UNIT_TRUNCATE_LINES:
        return code
    kept = lines[:_UNIT_TRUNCATE_LINES]
    kept.append("# ... (truncated)")
    return "\n".join(kept)


def _build_caveman_block(selected_units) -> str:  # List[SelectedUnit]
    """
    Caveman context block — code only, no edge comments, truncated headers.

    Format per unit:
        ### path:start-end
        <code>
    """
    lines = []
    for su in selected_units:
        unit = su.unit
        lines.append(f"### {unit.file_path}:{unit.start_line}-{unit.end_line}")
        lines.append(_maybe_truncate(unit.full_code.rstrip()))
        lines.append("")
    return "\n".join(lines)


def _select_with_reindex_retry(
    repo_path: str,
    index_path: str,
    selector,
    db_cls,
):
    """Run selector, then rebuild once if the current index gives no units."""
    with db_cls(index_path) as db:
        result = selector(db)
        if result.units:
            return result, index_path

    from indexer.core import run_index
    rebuilt = run_index(repo_path)
    with db_cls(rebuilt.index_path) as db:
        return selector(db), rebuilt.index_path


def run_fix(
    task: str,
    repo_path: str = ".",
    error_log: Optional[str] = None,
    k: int = 10,
    caveman: bool = False,
) -> str:
    """
    lens fix — the main command.

    1. Ensure index exists
    2. Auto-select relevant units with reasons
    3. Expand them
    4. Return structured context for the agent
    """
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    from query.selector import select_units

    effective_k = _CAVEMAN_K["fix"] if caveman else k
    index_path = _ensure_index(repo_path)

    def selector(db):
        return select_units(
            db, task, error_log, k=effective_k,
            include_neighbors=True,
            include_tests=True,
        )

    result, index_path = _select_with_reindex_retry(repo_path, index_path, selector, Database)

    if not result.units:
        if caveman:
            return f"T\n{task}\n\nC\nNo units found.\n\nD\n{_CAVEMAN_INSTRUCTIONS['fix']}"
        return (
            f"## Task\n{task}\n\n"
            "## Selection\n"
            "No relevant code units found. The index may be empty or the task "
            "description doesn't match any symbols in the codebase.\n"
        )

    if caveman:
        lines = ["T", task, "", "C", "", _build_caveman_block(result.units), "D", _CAVEMAN_INSTRUCTIONS["fix"]]
        return "\n".join(lines)

    with Database(index_path) as db:
        context_block = _build_context_block(result.units, db)

    lines = []
    lines.append("## Task")
    lines.append(task)
    lines.append("")

    if error_log:
        lines.append("## Error")
        error_lines = error_log.strip().splitlines()
        if len(error_lines) > 40:
            error_lines = error_lines[:40]
            error_lines.append("... (truncated)")
        lines.extend(error_lines)
        lines.append("")

    lines.append(f"## Selected Code ({len(result.units)} units)")
    lines.append("")
    lines.append(context_block)

    lines.append("## Instructions")
    lines.append("1. Implement the fix using only the Selected Code above.")
    lines.append("2. Do not search the workspace, list directories, or read additional files after this tool result.")
    lines.append("3. If the Selected Code is insufficient, stop and say exactly what context is missing instead of reading files.")
    lines.append("4. Apply edits directly to the file paths shown in the Selected Code.")
    lines.append("5. Run tests if a test runner is available, then summarize what changed.")

    return "\n".join(lines)


def run_ask(
    question: str,
    repo_path: str = ".",
    error_log: Optional[str] = None,
    k: int = 8,
    caveman: bool = False,
) -> str:
    """lens ask — answer a question about the codebase."""
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    from query.selector import select_units

    effective_k = _CAVEMAN_K["ask"] if caveman else k
    index_path = _ensure_index(repo_path)

    def selector(db):
        return select_units(
            db, question, error_log, k=effective_k,
            include_neighbors=True,
            include_tests=False,
        )

    result, index_path = _select_with_reindex_retry(repo_path, index_path, selector, Database)

    if not result.units:
        if caveman:
            return f"T\n{question}\n\nC\nNo units found.\n\nD\n{_CAVEMAN_INSTRUCTIONS['ask']}"
        return f"## Question\n{question}\n\n## Selection\nNo relevant code units found.\n"

    if caveman:
        lines = ["T", question, "", "C", "", _build_caveman_block(result.units), "D", _CAVEMAN_INSTRUCTIONS["ask"]]
        return "\n".join(lines)

    with Database(index_path) as db:
        context_block = _build_context_block(result.units, db)

    lines = []
    lines.append("## Question")
    lines.append(question)
    lines.append("")

    if error_log:
        lines.append("## Error")
        lines.extend(error_log.strip().splitlines()[:40])
        lines.append("")

    lines.append(f"## Relevant Code ({len(result.units)} units)")
    lines.append("")
    lines.append(context_block)

    lines.append("## Instructions")
    lines.append("Answer the question using only the code above as context.")
    lines.append("Do not edit any files. Explain clearly.")

    return "\n".join(lines)


def run_plan(
    task: str,
    repo_path: str = ".",
    error_log: Optional[str] = None,
    k: int = 12,
    caveman: bool = False,
) -> str:
    """lens plan — create an implementation plan without making changes."""
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    from query.selector import select_units

    effective_k = _CAVEMAN_K["plan"] if caveman else k
    index_path = _ensure_index(repo_path)

    def selector(db):
        return select_units(
            db, task, error_log, k=effective_k,
            include_neighbors=True,
            include_tests=True,
        )

    result, index_path = _select_with_reindex_retry(repo_path, index_path, selector, Database)

    if not result.units:
        if caveman:
            return f"T\n{task}\n\nC\nNo units found.\n\nD\n{_CAVEMAN_INSTRUCTIONS['plan']}"
        return f"## Task\n{task}\n\n## Selection\nNo relevant code units found.\n"

    if caveman:
        lines = ["T", task, "", "C", "", _build_caveman_block(result.units), "D", _CAVEMAN_INSTRUCTIONS["plan"]]
        return "\n".join(lines)

    with Database(index_path) as db:
        context_block = _build_context_block(result.units, db)

    lines = []
    lines.append("## Task")
    lines.append(task)
    lines.append("")

    if error_log:
        lines.append("## Error")
        lines.extend(error_log.strip().splitlines()[:40])
        lines.append("")

    lines.append(f"## Relevant Code ({len(result.units)} units)")
    lines.append("")
    lines.append(context_block)

    lines.append("## Instructions")
    lines.append("Create a step-by-step implementation plan for this task.")
    lines.append("For each step, specify:")
    lines.append("  - Which file and function to modify")
    lines.append("  - What the change should be")
    lines.append("  - What tests to add or update")
    lines.append("Do not implement the changes. Only plan.")

    return "\n".join(lines)
