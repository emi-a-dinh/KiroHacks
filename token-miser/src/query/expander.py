"""Expand selected units into full source code."""

from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


def _format_edge_comment(
    label: str,
    unit_ids: List[int],
    id_to_unit: Dict[int, "CodeUnit"],
) -> str:
    """Format edge information as a code comment."""
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


def build_expanded_prompt(
    db: "Database",
    unit_ids: List[int],
    task: Optional[str] = None,
    error_summary: Optional[str] = None,
    include_neighbors: bool = False,
) -> str:
    """
    Build an expanded prompt with full source code for selected units.
    
    Args:
        db: Database connection
        unit_ids: List of unit IDs to expand
        task: Optional task description to include
        error_summary: Optional error summary to include
        include_neighbors: If True, also include direct callers/callees
        
    Returns:
        Formatted prompt with full source code
    """
    # Expand to include neighbors if requested
    all_unit_ids = list(unit_ids)
    if include_neighbors:
        neighbors = db.get_neighbors(unit_ids)
        all_unit_ids.extend(neighbors)
        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for uid in all_unit_ids:
            if uid not in seen:
                seen.add(uid)
                unique_ids.append(uid)
        all_unit_ids = unique_ids
    
    # Get units
    units = db.get_units_by_ids(all_unit_ids)
    
    # Build lookup
    id_to_unit: Dict[int, "CodeUnit"] = {u.unit_id: u for u in units if u.unit_id}
    
    # Get edges for these units
    calls, called_by = db.get_edges_for_units(all_unit_ids)
    
    # Sort units by file path and start line
    units.sort(key=lambda u: (u.file_path, u.start_line))
    
    lines: List[str] = []
    
    # Task section
    if task:
        lines.append("## Task")
        lines.append(task)
        lines.append("")
    
    # Error summary section
    if error_summary:
        lines.append("## Error Summary")
        lines.append(error_summary)
        lines.append("")
    
    # Selected code section
    lines.append("## Selected Code")
    lines.append("")
    
    for unit in units:
        uid = unit.unit_id
        
        # Header
        header = f"### {unit.file_path} — {unit.symbol_name}"
        if unit.parent_class:
            header = f"### {unit.file_path} — {unit.parent_class}.{unit.symbol_name}"
        header += f" (lines {unit.start_line}–{unit.end_line})"
        lines.append(header)
        
        # Edge comments
        if uid:
            callers = called_by.get(uid, [])
            callees = calls.get(uid, [])
            lines.append(_format_edge_comment("Called by", callers, id_to_unit))
            lines.append(_format_edge_comment("Calls", callees, id_to_unit))
        
        # Full code
        lines.append(unit.full_code.rstrip())
        lines.append("")
    
    return "\n".join(lines)
