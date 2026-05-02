"""
Automatic unit selection — the brain of lens fix/ask/plan.

Given a task description (and optional error log), scores every unit in the index
and returns the top K most relevant ones, plus their neighbors.
"""

import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


# Words that appear everywhere and carry no signal
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
    "my", "your", "his", "its", "our", "their",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "and", "or", "but", "if", "then", "else", "when", "where", "how", "why",
    "not", "no", "nor", "so", "too", "very", "just", "also", "only",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "about", "between", "through", "after", "before",
    "all", "each", "every", "both", "few", "more", "most", "some", "any",
    "def", "class", "return", "self", "import", "from", "none", "true", "false",
    "function", "const", "let", "var", "async", "await",
}


def _tokenize(text: str) -> Set[str]:
    """Extract meaningful tokens from a text string."""
    # Split on non-alphanumeric, lowercase
    raw = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
    # Also split camelCase and snake_case
    tokens = set()
    for word in raw:
        # snake_case
        parts = word.split("_")
        for part in parts:
            # camelCase
            sub = re.findall(r'[a-z]+|[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)', part)
            for s in sub:
                s = s.lower()
                if len(s) > 1 and s not in STOP_WORDS:
                    tokens.add(s)
        if len(word) > 1 and word not in STOP_WORDS:
            tokens.add(word)
    return tokens


def _score_unit(
    unit: "CodeUnit",
    task_tokens: Set[str],
    error_tokens: Set[str],
    file_path_hits: Set[str],
) -> float:
    """
    Score a single unit's relevance to the task.
    
    Scoring:
      +10  symbol_name matches a task token exactly
      +8   file_path matches a task/error token
      +5   signature tokens overlap with task tokens
      +4   signature tokens overlap with error tokens
      +3   full_code tokens overlap with task tokens (capped)
      +2   unit is a test file related to a matched source file
    """
    score = 0.0
    
    name_lower = unit.symbol_name.lower()
    name_parts = set(name_lower.split("_"))
    name_parts.add(name_lower)
    
    # Symbol name match
    if name_lower in task_tokens or name_parts & task_tokens:
        score += 10
    
    # File path match
    path_parts = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', unit.file_path.lower()))
    if path_parts & task_tokens:
        score += 8
    if path_parts & error_tokens:
        score += 8
    if unit.file_path in file_path_hits:
        score += 6
    
    # Signature token overlap
    sig_tokens = _tokenize(unit.signature)
    sig_task_overlap = len(sig_tokens & task_tokens)
    if sig_task_overlap:
        score += min(5, sig_task_overlap * 2)
    
    sig_error_overlap = len(sig_tokens & error_tokens)
    if sig_error_overlap:
        score += min(4, sig_error_overlap * 2)
    
    # Code body overlap (lighter weight, capped)
    code_tokens = _tokenize(unit.full_code)
    code_task_overlap = len(code_tokens & task_tokens)
    if code_task_overlap:
        score += min(3, code_task_overlap)
    
    # Test file bonus — if this is a test for a file that scored well
    if "test" in unit.file_path.lower():
        # Check if there's a matching source file
        test_name = unit.file_path.lower().replace("test_", "").replace("tests/", "").replace("test/", "")
        for fp in file_path_hits:
            if test_name in fp.lower() or fp.lower().replace("routes/", "").replace("models/", "") in test_name:
                score += 2
                break
    
    return score


def select_units(
    db: "Database",
    task: str,
    error_log: Optional[str] = None,
    k: int = 10,
    include_neighbors: bool = True,
    include_tests: bool = True,
) -> Tuple[List["CodeUnit"], float]:
    """
    Automatically select the most relevant units for a task.
    
    Args:
        db: Database connection
        task: Natural language task description
        error_log: Optional error log/traceback
        k: Target number of units to return
        include_neighbors: Also include call graph neighbors of top hits
        include_tests: Try to include related test units
        
    Returns:
        Tuple of (selected_units, confidence_score)
        confidence is 0.0-1.0 indicating how confident the selection is
    """
    all_units = db.get_all_units()
    if not all_units:
        return [], 0.0
    
    # Tokenize task and error
    task_tokens = _tokenize(task)
    error_tokens = _tokenize(error_log) if error_log else set()
    
    # Extract file paths mentioned in error log
    file_path_hits = set()
    if error_log:
        # Match patterns like "File "routes/tasks.py", line 42"
        for match in re.finditer(r'["\']?([a-zA-Z0-9_/\\]+\.\w+)["\']?', error_log):
            file_path_hits.add(match.group(1))
    
    # Score all units
    scored = []
    for unit in all_units:
        score = _score_unit(unit, task_tokens, error_tokens, file_path_hits)
        if score > 0:
            scored.append((score, unit))
    
    # Sort by score descending
    scored.sort(key=lambda x: -x[0])
    
    # Take top K
    selected_ids = set()
    selected = []
    
    # Phase 1: top scored units
    for score, unit in scored[:k]:
        if unit.unit_id and unit.unit_id not in selected_ids:
            selected_ids.add(unit.unit_id)
            selected.append(unit)
    
    # Phase 2: add same-file siblings of top hits
    top_files = {u.file_path for u in selected}
    for unit in all_units:
        if len(selected) >= k * 1.5:
            break
        if unit.file_path in top_files and unit.unit_id not in selected_ids:
            if unit.unit_type in ("function", "method"):  # skip constants
                selected_ids.add(unit.unit_id)
                selected.append(unit)
    
    # Phase 3: add call graph neighbors
    if include_neighbors and selected_ids:
        neighbor_ids = db.get_neighbors(list(selected_ids))
        neighbor_units = db.get_units_by_ids(neighbor_ids)
        for unit in neighbor_units:
            if len(selected) >= k * 2:
                break
            if unit.unit_id not in selected_ids:
                # Only add neighbors that have some relevance
                neighbor_score = _score_unit(unit, task_tokens, error_tokens, file_path_hits)
                if neighbor_score > 0 or unit.file_path in top_files:
                    selected_ids.add(unit.unit_id)
                    selected.append(unit)
    
    # Phase 4: add related tests
    if include_tests:
        test_units = [u for u in all_units if "test" in u.file_path.lower() and u.unit_id not in selected_ids]
        for unit in test_units:
            if len(selected) >= k * 2:
                break
            test_score = _score_unit(unit, task_tokens, error_tokens, file_path_hits)
            if test_score > 0:
                selected_ids.add(unit.unit_id)
                selected.append(unit)
    
    # Compute confidence
    if not scored:
        confidence = 0.0
    else:
        top_score = scored[0][0]
        if top_score >= 15:
            confidence = 1.0
        elif top_score >= 10:
            confidence = 0.8
        elif top_score >= 5:
            confidence = 0.6
        else:
            confidence = 0.3
    
    # Sort selected by file path and line number for clean output
    selected.sort(key=lambda u: (u.file_path, u.start_line))
    
    return selected, confidence
