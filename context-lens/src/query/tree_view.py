"""
Terminal tree view of the indexed repository.

Renders the unit index as a navigable tree:

  example_project/
  ├── routes/
  │   ├── tasks.py  (8 units, 12 edges)
  │   │   ├── [fn]  require_auth          → 0 calls  ← 3 callers
  │   │   ├── [fn]  list_tasks            → 1 call   ← 0 callers
  │   │   ├── [fn]  create_task          → 2 calls  ← 0 callers
  │   │   └── [fn]  get_task             → 0 calls  ← 1 caller   ⚠ no auth check
  │   └── auth.py  (4 units, 5 edges)
  └── models/
      └── task.py  (3 units, 2 edges)
"""

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


# ── ANSI colour helpers ────────────────────────────────────────────────────────

def _supports_color() -> bool:
    """Return True if the terminal supports ANSI colour codes."""
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


USE_COLOR = _supports_color()


def _c(text: str, code: str) -> str:
    """Wrap text in an ANSI colour code if colour is supported."""
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def dim(t):    return _c(t, "2")
def bold(t):   return _c(t, "1")
def cyan(t):   return _c(t, "36")
def blue(t):   return _c(t, "34")
def green(t):  return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t):    return _c(t, "31")
def magenta(t):return _c(t, "35")
def grey(t):   return _c(t, "90")


# ── Unit type icons ────────────────────────────────────────────────────────────

UNIT_ICONS = {
    "function":  cyan("[fn]"),
    "method":    blue("[me]"),
    "class":     green("[cl]"),
    "constant":  yellow("[co]"),
}

UNIT_COLORS = {
    "function":  cyan,
    "method":    blue,
    "class":     green,
    "constant":  yellow,
}


# ── Tree drawing characters ────────────────────────────────────────────────────

PIPE      = "│"
TEE       = "├──"
ELBOW     = "└──"
BLANK     = "   "
PIPE_PAD  = "│  "


# ── Core renderer ─────────────────────────────────────────────────────────────

def build_tree_view(
    db: "Database",
    index_path: Optional[str] = None,
    show_edges: bool = True,
    show_signatures: bool = False,
    filter_type: Optional[str] = None,
) -> str:
    """
    Build a terminal tree view of the indexed repository.

    Args:
        db:               Open database connection
        index_path:       Path to the index db (used for header display only)
        show_edges:       Show call/caller counts next to each unit
        show_signatures:  Show full signature instead of just symbol name
        filter_type:      Only show units of this type (function/class/method/constant)

    Returns:
        Formatted string ready to print
    """
    units = db.get_all_units()
    if not units:
        return red("No units indexed. Run 'context-lens index <repo>' first.")

    unit_ids = [u.unit_id for u in units if u.unit_id]
    calls_map, called_by_map = db.get_edges_for_units(unit_ids)
    edge_count = db.get_edge_count()

    # Apply type filter
    if filter_type:
        units = [u for u in units if u.unit_type == filter_type]

    # Group by file path
    by_file: Dict[str, List["CodeUnit"]] = defaultdict(list)
    for unit in units:
        by_file[unit.file_path].append(unit)

    for path in by_file:
        by_file[path].sort(key=lambda u: u.start_line)

    # Build a directory tree from file paths
    dir_tree: Dict[str, list] = {}  # dir -> list of file paths
    for file_path in sorted(by_file.keys()):
        parts = Path(file_path).parts
        directory = str(Path(*parts[:-1])) if len(parts) > 1 else "."
        dir_tree.setdefault(directory, []).append(file_path)

    # ── Header ────────────────────────────────────────────────────────────────
    lines: List[str] = []

    total_files = len(by_file)
    total_units = len(units)

    header_parts = [
        bold(f"{total_units} units"),
        f"across {total_files} files",
        f"{edge_count} call edges",
    ]
    if filter_type:
        header_parts.append(grey(f"(filtered: {filter_type})"))

    lines.append(bold("Context Lens — Unit Tree"))
    lines.append(grey("  " + "  ·  ".join(header_parts)))
    lines.append("")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_parts = [
        f"{cyan('[fn]')} function",
        f"{blue('[me]')} method",
        f"{green('[cl]')} class",
        f"{yellow('[co]')} constant",
    ]
    if show_edges:
        legend_parts += [
            grey("→ calls out"),
            grey("← called by"),
        ]
    lines.append("  " + "   ".join(legend_parts))
    lines.append("")

    # ── Directory / file tree ─────────────────────────────────────────────────
    sorted_dirs = sorted(dir_tree.keys())

    for dir_idx, directory in enumerate(sorted_dirs):
        is_last_dir = dir_idx == len(sorted_dirs) - 1
        dir_files = sorted(dir_tree[directory])

        # Directory line
        if directory == ".":
            dir_label = grey("./")
        else:
            dir_label = bold(cyan(directory + "/"))

        dir_connector = ELBOW if is_last_dir else TEE
        lines.append(f"{dir_connector} {dir_label}")

        dir_prefix = BLANK if is_last_dir else PIPE_PAD

        for file_idx, file_path in enumerate(dir_files):
            is_last_file = file_idx == len(dir_files) - 1
            file_units = by_file[file_path]
            filename = Path(file_path).name

            # Count edges touching this file's units
            file_unit_ids = [u.unit_id for u in file_units if u.unit_id]
            file_edge_count = sum(
                len(calls_map.get(uid, [])) for uid in file_unit_ids
            )

            # File line
            file_connector = ELBOW if is_last_file else TEE
            unit_word = "unit" if len(file_units) == 1 else "units"
            edge_word = "edge" if file_edge_count == 1 else "edges"
            file_meta = grey(f"  {len(file_units)} {unit_word}, {file_edge_count} {edge_word}")
            lines.append(f"{dir_prefix}{file_connector} {bold(filename)}{file_meta}")

            file_prefix = dir_prefix + (BLANK if is_last_file else PIPE_PAD)

            for unit_idx, unit in enumerate(file_units):
                is_last_unit = unit_idx == len(file_units) - 1
                unit_connector = ELBOW if is_last_unit else TEE

                icon = UNIT_ICONS.get(unit.unit_type, grey("[??]"))
                color_fn = UNIT_COLORS.get(unit.unit_type, lambda x: x)

                # Name or full signature
                if show_signatures:
                    name_str = color_fn(unit.signature)
                else:
                    if unit.parent_class and unit.unit_type == "method":
                        name_str = color_fn(f"{unit.parent_class}.{unit.symbol_name}")
                    else:
                        name_str = color_fn(unit.symbol_name)

                uid = unit.unit_id
                id_str = grey(f"[{uid}]")

                # Edge counts
                edge_str = ""
                if show_edges and uid:
                    out_count = len(calls_map.get(uid, []))
                    in_count = len(called_by_map.get(uid, []))

                    out_label = f"→ {out_count}"
                    in_label  = f"← {in_count}"

                    out_colored = grey(out_label) if out_count == 0 else cyan(out_label)
                    in_colored  = grey(in_label)  if in_count == 0  else magenta(in_label)

                    edge_str = f"  {out_colored}  {in_colored}"

                # Line range
                line_range = grey(f"  :{unit.start_line}–{unit.end_line}")

                lines.append(
                    f"{file_prefix}{unit_connector} {icon} {id_str} {name_str}{line_range}{edge_str}"
                )

    lines.append("")

    # ── Summary footer ────────────────────────────────────────────────────────
    lines.append(grey("  Use 'context-lens expand <ids>' to see full code for any unit."))
    lines.append(grey("  Use 'context-lens query \"<task>\"' to get a task-focused selection prompt."))

    return "\n".join(lines)
