"""
Smart commands — lens fix, lens ask, lens plan.

These combine indexing, selection, and expansion into a single call.
No manual unit IDs, no manual index, no manual expand.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


def _ensure_index(repo_path: str) -> str:
    """
    Ensure the repo is indexed. Only runs a full index if the database
    doesn't exist yet. Otherwise trusts that the file-save and file-delete
    hooks keep the index fresh.
    
    Returns the index database path.
    """
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    repo = Path(repo_path).resolve()
    index_path = str(repo / ".context-lens" / "index.db")

    if Path(index_path).exists():
        # Index exists — hooks keep it fresh, no need to re-scan
        return index_path

    # No index yet — create one
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
    units: List["CodeUnit"],
    db: "Database",
) -> str:
    """Build the expanded code block for selected units."""
    all_ids = [u.unit_id for u in units if u.unit_id]
    id_to_unit = {u.unit_id: u for u in units if u.unit_id}
    calls, called_by = db.get_edges_for_units(all_ids)

    lines = []
    for unit in units:
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


def run_fix(
    task: str,
    repo_path: str = ".",
    error_log: Optional[str] = None,
    k: int = 10,
) -> str:
    """
    lens fix — the main command.
    
    1. Ensure index exists and is up to date
    2. Auto-select relevant units
    3. Expand them
    4. Return structured context for the agent
    """
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    from query.selector import select_units

    # Step 1: ensure index
    index_path = _ensure_index(repo_path)

    # Step 2: select relevant units
    with Database(index_path) as db:
        selected, confidence = select_units(
            db, task, error_log, k=k,
            include_neighbors=True,
            include_tests=True,
        )

        if not selected:
            return (
                f"## Task\n{task}\n\n"
                "## Selection\n"
                "No relevant code units found. The index may be empty or the task "
                "description doesn't match any symbols in the codebase.\n"
                "Selection confidence: low\n"
            )

        # Step 3: build context
        context_block = _build_context_block(selected, db)

        # Confidence label
        if confidence >= 0.8:
            conf_label = "high"
        elif confidence >= 0.5:
            conf_label = "medium"
        else:
            conf_label = "low"

    # Step 4: assemble structured output
    lines = []
    lines.append(f"## Task")
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

    lines.append(f"## Selected Code ({len(selected)} units, confidence: {conf_label})")
    lines.append("")
    lines.append(context_block)

    lines.append("## Instructions")
    lines.append("1. Implement the fix using the code above as context.")
    lines.append("2. Follow patterns from similar functions in the same file.")
    lines.append("3. Update or add tests to cover the change.")
    lines.append("4. Run tests if a test runner is available.")
    lines.append("5. Summarize what changed.")
    lines.append("")
    lines.append(f"Selection confidence: {conf_label}")
    if conf_label == "low":
        lines.append("Consider expanding additional units if the context is insufficient.")

    return "\n".join(lines)


def run_ask(
    question: str,
    repo_path: str = ".",
    error_log: Optional[str] = None,
    k: int = 8,
) -> str:
    """
    lens ask — answer a question about the codebase.
    
    Same selection logic as fix, but instructions are for explanation, not editing.
    """
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    from query.selector import select_units

    index_path = _ensure_index(repo_path)

    with Database(index_path) as db:
        selected, confidence = select_units(
            db, question, error_log, k=k,
            include_neighbors=True,
            include_tests=False,
        )

        if not selected:
            return (
                f"## Question\n{question}\n\n"
                "## Selection\nNo relevant code units found.\n"
            )

        context_block = _build_context_block(selected, db)

        if confidence >= 0.8:
            conf_label = "high"
        elif confidence >= 0.5:
            conf_label = "medium"
        else:
            conf_label = "low"

    lines = []
    lines.append(f"## Question")
    lines.append(question)
    lines.append("")

    if error_log:
        lines.append("## Error")
        lines.extend(error_log.strip().splitlines()[:40])
        lines.append("")

    lines.append(f"## Relevant Code ({len(selected)} units, confidence: {conf_label})")
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
) -> str:
    """
    lens plan — create an implementation plan without making changes.
    
    Selects more units than fix (wider context) and asks for a plan, not edits.
    """
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    from query.selector import select_units

    index_path = _ensure_index(repo_path)

    with Database(index_path) as db:
        selected, confidence = select_units(
            db, task, error_log, k=k,
            include_neighbors=True,
            include_tests=True,
        )

        if not selected:
            return (
                f"## Task\n{task}\n\n"
                "## Selection\nNo relevant code units found.\n"
            )

        context_block = _build_context_block(selected, db)

        if confidence >= 0.8:
            conf_label = "high"
        elif confidence >= 0.5:
            conf_label = "medium"
        else:
            conf_label = "low"

    lines = []
    lines.append(f"## Task")
    lines.append(task)
    lines.append("")

    if error_log:
        lines.append("## Error")
        lines.extend(error_log.strip().splitlines()[:40])
        lines.append("")

    lines.append(f"## Relevant Code ({len(selected)} units, confidence: {conf_label})")
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
