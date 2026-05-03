"""
Smart commands — context and read.

miser_context  → signatures only, ~300–800 tokens
miser_read     → full source of one unit on demand
"""

from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


def _ensure_index(repo_path: str) -> str:
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


def _format_callees(uid: int, calls: Dict[int, List[int]], id_to_unit: Dict[int, "CodeUnit"]) -> str:
    """Format depth-1 callees as a compact inline annotation."""
    callee_ids = calls.get(uid, [])
    if not callee_ids:
        return ""
    names = []
    for cid in callee_ids[:4]:
        u = id_to_unit.get(cid)
        if u:
            names.append(u.symbol_name)
    if not names:
        return ""
    suffix = f" +{len(callee_ids) - 4}" if len(callee_ids) > 4 else ""
    return f"  → {', '.join(names)}{suffix}"


def _build_context_output(result, db: "Database") -> str:
    """
    Build signature-only context output, one line per unit.

    Format:
        path/to/file.py::signature  → callee1, callee2
    """
    units = [su.unit for su in result.units]
    all_ids = [u.unit_id for u in units if u.unit_id]
    id_to_unit = {u.unit_id: u for u in units if u.unit_id}
    calls, _ = db.get_edges_for_units(all_ids)

    lines = []
    for su in sorted(result.units, key=lambda s: (s.unit.file_path, s.unit.start_line)):
        u = su.unit
        uid = u.unit_id
        callee_str = _format_callees(uid, calls, id_to_unit) if uid else ""
        lines.append(f"{u.file_path}::{u.signature}{callee_str}")

    return "\n".join(lines)


def run_context(
    task: str,
    repo_path: str = ".",
    error_log: Optional[str] = None,
    k: int = 5,
) -> str:
    """Return signatures of relevant units only. ~300–800 tokens."""
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    from query.selector import select_units

    index_path = _ensure_index(repo_path)

    def selector(db):
        return select_units(db, task, error_log, k=k,
                            include_neighbors=True, include_tests=True)

    with Database(index_path) as db:
        result = selector(db)
        if not result.units:
            from indexer.core import run_index
            index_path = run_index(repo_path).index_path

    with Database(index_path) as db:
        if not result.units:
            result = selector(db)
        if not result.units:
            return f"Task: {task}\n\nNo relevant units found."
        ctx = _build_context_output(result, db)

    lines = [f"Task: {task}", ""]
    if error_log:
        err_lines = error_log.strip().splitlines()[:20]
        lines += ["Error:"] + err_lines + [""]
    lines += [
        f"Context ({len(result.units)} units):",
        "",
        ctx,
        "",
        "Use miser_read(symbol_name) to get full source of any unit.",
        "Edit files directly using the paths shown above.",
    ]
    return "\n".join(lines)


def run_read(symbol_name: str, repo_path: str = ".") -> str:
    """Return full source of a single unit by symbol name."""
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database

    index_path = _ensure_index(repo_path)

    with Database(index_path) as db:
        all_units = db.get_all_units()

    needle = symbol_name.lower()
    exact = [u for u in all_units if u.symbol_name == symbol_name]
    if not exact:
        exact = [u for u in all_units if u.symbol_name.lower() == needle]
    if not exact:
        exact = [u for u in all_units if needle in u.symbol_name.lower()]

    if not exact:
        return f"Symbol '{symbol_name}' not found in index."

    if len(exact) > 1:
        preferred = [u for u in exact if "test" not in u.file_path.lower()]
        if preferred:
            exact = preferred

    unit = exact[0]
    header = f"{unit.file_path}:{unit.start_line}–{unit.end_line}  {unit.signature}"
    return f"{header}\n\n{unit.full_code.rstrip()}"
