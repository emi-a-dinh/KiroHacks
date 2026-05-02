"""Build signature maps for querying."""

from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


MAX_EDGE_ANNOTATIONS = 5  # Cap edge annotations per unit


def _format_edge_list(
    unit_ids: List[int],
    id_to_unit: Dict[int, "CodeUnit"],
    max_items: int = MAX_EDGE_ANNOTATIONS,
) -> str:
    """Format a list of unit IDs as a readable edge annotation."""
    if not unit_ids:
        return "(none)"
    
    items = []
    for uid in unit_ids[:max_items]:
        unit = id_to_unit.get(uid)
        if unit:
            name = unit.symbol_name
            if unit.parent_class:
                name = f"{unit.parent_class}.{name}"
            items.append(f"{name} [{uid}]")
    
    result = ", ".join(items)
    if len(unit_ids) > max_items:
        result += f", ... (+{len(unit_ids) - max_items} more)"
    
    return result


def build_signature_map(
    db: "Database",
    task: str,
    error_log: Optional[str] = None,
    k: int = 10,
) -> str:
    """
    Build a signature map prompt for the given task.
    
    Args:
        db: Database connection
        task: Natural language task description
        error_log: Optional error log/traceback
        k: Maximum number of units to select
        
    Returns:
        Formatted signature map prompt
    """
    # Get all units and edges
    units = db.get_all_units()
    unit_count = len(units)
    edge_count = db.get_edge_count()
    
    # Build lookup structures
    id_to_unit: Dict[int, "CodeUnit"] = {u.unit_id: u for u in units if u.unit_id}
    unit_ids = list(id_to_unit.keys())
    
    # Get edges for all units
    calls, called_by = db.get_edges_for_units(unit_ids)
    
    # Group units by file
    units_by_file: Dict[str, List["CodeUnit"]] = {}
    for unit in units:
        units_by_file.setdefault(unit.file_path, []).append(unit)
    
    # Sort files
    sorted_files = sorted(units_by_file.keys())
    
    # Count unique files
    file_count = len(sorted_files)
    
    # Build the signature map
    lines: List[str] = []
    
    # Task section
    lines.append("## Task")
    lines.append(task)
    lines.append("")
    
    # Error section (if provided)
    if error_log:
        lines.append("## Error")
        # Truncate to 80 lines
        error_lines = error_log.strip().splitlines()
        if len(error_lines) > 80:
            error_lines = error_lines[:80]
            error_lines.append("... (truncated)")
        lines.extend(error_lines)
        lines.append("")
    
    # Signature map header
    lines.append(f"## Repository Signature Map ({unit_count} units, {edge_count} call edges, across {file_count} files)")
    lines.append("")
    
    # Build map for each file
    for file_path in sorted_files:
        file_units = units_by_file[file_path]
        # Sort by start line
        file_units.sort(key=lambda u: u.start_line)
        
        lines.append(f"### {file_path}")
        
        for unit in file_units:
            uid = unit.unit_id
            
            # Indent methods
            indent = "  " if unit.unit_type == "method" else ""
            
            # Format signature line
            sig_line = f"{indent}[{uid}] {unit.signature}"
            sig_line += f"  (lines {unit.start_line}–{unit.end_line})"
            lines.append(sig_line)
            
            # Add edge annotations
            if uid and uid in calls and calls[uid]:
                edge_str = _format_edge_list(calls[uid], id_to_unit)
                lines.append(f"{indent}     → calls: {edge_str}")
            
            if uid and uid in called_by and called_by[uid]:
                edge_str = _format_edge_list(called_by[uid], id_to_unit)
                lines.append(f"{indent}     ← called by: {edge_str}")
        
        lines.append("")
    
    # Instruction
    lines.append("## Instruction")
    lines.append(f"Select up to {k} unit IDs whose full source code is needed to complete the task.")
    lines.append("The → and ← annotations show call relationships. Consider including callers and")
    lines.append("callees of your selected units if they are relevant to the task.")
    
    return "\n".join(lines)
