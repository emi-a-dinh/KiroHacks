"""Build call edges between code units."""

import re
from typing import Dict, List, Set, Tuple

from indexer.models import CodeUnit, Edge


def build_edges(units: List[CodeUnit]) -> List[Edge]:
    """
    Build call edges between code units by scanning for function calls.
    
    This uses simple name-based matching:
    - `symbol_name(` for function calls
    - `self.symbol_name(` for method calls
    - `ClassName.symbol_name(` for static method calls
    
    Args:
        units: List of all code units with their unit_ids set
        
    Returns:
        List of Edge objects representing caller -> callee relationships
    """
    edges: List[Edge] = []
    
    # Build lookup structures
    # symbol_name -> list of unit_ids (may have duplicates for common names)
    symbol_to_ids: Dict[str, List[int]] = {}
    # unit_id -> CodeUnit
    id_to_unit: Dict[int, CodeUnit] = {}
    
    for unit in units:
        if unit.unit_id is None:
            continue
        id_to_unit[unit.unit_id] = unit
        symbol_to_ids.setdefault(unit.symbol_name, []).append(unit.unit_id)
    
    # Build set of all symbol names for fast lookup
    all_symbols: Set[str] = set(symbol_to_ids.keys())
    
    # Filter out very common names that would create too much noise
    NOISE_SYMBOLS = {
        "get", "set", "run", "call", "init", "__init__", "new", "create",
        "update", "delete", "read", "write", "open", "close", "start", "stop",
        "add", "remove", "push", "pop", "append", "extend", "insert",
        "print", "log", "debug", "info", "warn", "error",
        "str", "int", "float", "bool", "list", "dict", "tuple", "len",
        "map", "filter", "reduce", "sort", "sorted", "reverse", "reversed",
        "join", "split", "strip", "replace", "format", "encode", "decode",
        "keys", "values", "items", "copy", "clear",
        "then", "catch", "finally", "resolve", "reject",
        "toString", "valueOf", "hasOwnProperty",
    }
    
    # Patterns to find function calls
    # Match: symbol_name( but not .symbol_name( or symbol_name_more(
    call_pattern = re.compile(r'(?<![.\w])(\w+)\s*\(')
    # Match: self.symbol_name( or this.symbol_name(
    method_call_pattern = re.compile(r'(?:self|this)\.(\w+)\s*\(')
    # Match: ClassName.symbol_name(
    static_call_pattern = re.compile(r'([A-Z]\w*)\.(\w+)\s*\(')
    
    seen_edges: Set[Tuple[int, int]] = set()
    
    for unit in units:
        if unit.unit_id is None:
            continue
        
        caller_id = unit.unit_id
        code = unit.full_code
        
        # Find all potential calls
        called_symbols: Set[str] = set()
        
        # Direct function calls
        for match in call_pattern.finditer(code):
            symbol = match.group(1)
            if symbol in all_symbols and symbol not in NOISE_SYMBOLS:
                called_symbols.add(symbol)
        
        # Method calls via self/this
        for match in method_call_pattern.finditer(code):
            symbol = match.group(1)
            if symbol in all_symbols and symbol not in NOISE_SYMBOLS:
                called_symbols.add(symbol)
        
        # Static method calls
        for match in static_call_pattern.finditer(code):
            class_name = match.group(1)
            method_name = match.group(2)
            # Try to match the method name
            if method_name in all_symbols and method_name not in NOISE_SYMBOLS:
                called_symbols.add(method_name)
        
        # Create edges
        for symbol in called_symbols:
            for callee_id in symbol_to_ids.get(symbol, []):
                # Don't create self-edges
                if callee_id == caller_id:
                    continue
                
                edge_key = (caller_id, callee_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(Edge(caller_id=caller_id, callee_id=callee_id))
    
    return edges


def get_edges_for_unit(
    unit_id: int,
    all_edges: List[Edge],
) -> Tuple[List[int], List[int]]:
    """
    Get the callers and callees for a specific unit.
    
    Args:
        unit_id: The unit to get edges for
        all_edges: List of all edges
        
    Returns:
        Tuple of (callee_ids, caller_ids) - what this unit calls, what calls this unit
    """
    callees: List[int] = []
    callers: List[int] = []
    
    for edge in all_edges:
        if edge.caller_id == unit_id:
            callees.append(edge.callee_id)
        if edge.callee_id == unit_id:
            callers.append(edge.caller_id)
    
    return callees, callers
