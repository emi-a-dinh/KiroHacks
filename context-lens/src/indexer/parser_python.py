"""Python AST-based parser for extracting code units."""

import ast
from pathlib import Path
from typing import List, Optional, Union

from .models import CodeUnit


def _get_signature(node: "Union[ast.FunctionDef, ast.AsyncFunctionDef]") -> str:
    """Build a compact signature string for a function."""
    # Get function name
    name = node.name
    
    # Get parameters
    params = []
    args = node.args
    
    # Positional args
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        param = arg.arg
        if arg.annotation:
            param += f": {ast.unparse(arg.annotation)}"
        # Check for default value
        default_idx = i - defaults_offset
        if default_idx >= 0 and default_idx < len(args.defaults):
            default = ast.unparse(args.defaults[default_idx])
            param += f" = {default}"
        params.append(param)
    
    # *args
    if args.vararg:
        param = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            param += f": {ast.unparse(args.vararg.annotation)}"
        params.append(param)
    
    # Keyword-only args
    kw_defaults_map = {i: d for i, d in enumerate(args.kw_defaults) if d is not None}
    for i, arg in enumerate(args.kwonlyargs):
        param = arg.arg
        if arg.annotation:
            param += f": {ast.unparse(arg.annotation)}"
        if i in kw_defaults_map:
            param += f" = {ast.unparse(kw_defaults_map[i])}"
        params.append(param)
    
    # **kwargs
    if args.kwarg:
        param = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            param += f": {ast.unparse(args.kwarg.annotation)}"
        params.append(param)
    
    # Return type
    return_type = ""
    if node.returns:
        return_type = f" -> {ast.unparse(node.returns)}"
    
    # Async prefix
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    
    return f"{prefix}def {name}({', '.join(params)}){return_type}"


def _get_class_signature(node: ast.ClassDef) -> str:
    """Build a compact signature string for a class."""
    bases = [ast.unparse(b) for b in node.bases]
    if bases:
        return f"class {node.name}({', '.join(bases)})"
    return f"class {node.name}"


def parse_python_file(file_path: str, source: str) -> List[CodeUnit]:
    """
    Parse a Python file and extract code units.
    
    Args:
        file_path: Relative path to the file
        source: Source code content
        
    Returns:
        List of CodeUnit objects
    """
    units: List[CodeUnit] = []
    
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return units
    
    lines = source.splitlines(keepends=True)
    
    def get_source(start_line: int, end_line: int) -> str:
        """Extract source code for a range of lines (1-indexed)."""
        return "".join(lines[start_line - 1:end_line])
    
    # Process top-level nodes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Top-level function
            signature = _get_signature(node)
            end_line = node.end_lineno or node.lineno
            units.append(CodeUnit(
                unit_id=None,
                file_path=file_path,
                symbol_name=node.name,
                unit_type="function",
                parent_class=None,
                signature=signature,
                start_line=node.lineno,
                end_line=end_line,
                full_code=get_source(node.lineno, end_line),
            ))
        
        elif isinstance(node, ast.ClassDef):
            # Class definition
            class_signature = _get_class_signature(node)
            class_end_line = node.end_lineno or node.lineno
            units.append(CodeUnit(
                unit_id=None,
                file_path=file_path,
                symbol_name=node.name,
                unit_type="class",
                parent_class=None,
                signature=class_signature,
                start_line=node.lineno,
                end_line=class_end_line,
                full_code=get_source(node.lineno, class_end_line),
            ))
            
            # Process methods inside the class
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_signature = _get_signature(child)
                    method_end_line = child.end_lineno or child.lineno
                    units.append(CodeUnit(
                        unit_id=None,
                        file_path=file_path,
                        symbol_name=child.name,
                        unit_type="method",
                        parent_class=node.name,
                        signature=method_signature,
                        start_line=child.lineno,
                        end_line=method_end_line,
                        full_code=get_source(child.lineno, method_end_line),
                    ))
        
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            # Top-level assignment (constant)
            if isinstance(node, ast.AnnAssign) and node.target:
                if isinstance(node.target, ast.Name):
                    name = node.target.id
                    type_ann = ast.unparse(node.annotation) if node.annotation else ""
                    signature = f"{name}: {type_ann}" if type_ann else name
                    end_line = node.end_lineno or node.lineno
                    units.append(CodeUnit(
                        unit_id=None,
                        file_path=file_path,
                        symbol_name=name,
                        unit_type="constant",
                        parent_class=None,
                        signature=signature,
                        start_line=node.lineno,
                        end_line=end_line,
                        full_code=get_source(node.lineno, end_line),
                    ))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # Only include UPPER_CASE names as constants
                        if target.id.isupper() or target.id.startswith("_"):
                            name = target.id
                            end_line = node.end_lineno or node.lineno
                            units.append(CodeUnit(
                                unit_id=None,
                                file_path=file_path,
                                symbol_name=name,
                                unit_type="constant",
                                parent_class=None,
                                signature=name,
                                start_line=node.lineno,
                                end_line=end_line,
                                full_code=get_source(node.lineno, end_line),
                            ))
    
    return units
