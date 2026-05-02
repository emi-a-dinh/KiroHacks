"""Tree-sitter based parser for extracting code units."""

from typing import List, Optional

from indexer.models import CodeUnit

# Try to import tree-sitter-languages
try:
    import tree_sitter_languages
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


# Language mapping
LANGUAGE_MAP = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "ruby": "ruby",
    "php": "php",
    "c": "c",
    "cpp": "cpp",
}


def _get_node_text(source_bytes: bytes, node) -> str:
    """Extract text from a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_python_signature(source_bytes: bytes, node) -> str:
    """Extract a Python function/method signature."""
    name = ""
    params = ""
    return_type = ""
    is_async = False
    
    for child in node.children:
        if child.type == "name" or child.type == "identifier":
            name = _get_node_text(source_bytes, child)
        elif child.type == "parameters":
            params = _get_node_text(source_bytes, child)
        elif child.type == "type":
            return_type = _get_node_text(source_bytes, child)
    
    # Check if async
    if node.type == "async_function_definition":
        is_async = True
    
    prefix = "async " if is_async else ""
    suffix = f" -> {return_type}" if return_type else ""
    return f"{prefix}def {name}{params}{suffix}"


def _extract_js_signature(source_bytes: bytes, node) -> str:
    """Extract a JavaScript/TypeScript function signature."""
    name = ""
    params = ""
    is_async = False
    
    for child in node.children:
        if child.type in ("identifier", "property_identifier"):
            name = _get_node_text(source_bytes, child)
        elif child.type == "formal_parameters":
            params = _get_node_text(source_bytes, child)
        elif child.type == "async":
            is_async = True
    
    prefix = "async " if is_async else ""
    return f"{prefix}function {name}{params}"


def _extract_class_signature(source_bytes: bytes, node, language: str) -> str:
    """Extract a class signature."""
    name = ""
    bases = []
    
    for child in node.children:
        if child.type in ("identifier", "name", "type_identifier"):
            if not name:
                name = _get_node_text(source_bytes, child)
        elif child.type in ("argument_list", "superclass"):
            bases.append(_get_node_text(source_bytes, child))
        elif child.type == "class_heritage":
            # TypeScript extends/implements
            bases.append(_get_node_text(source_bytes, child))
    
    if bases:
        return f"class {name}({', '.join(bases)})"
    return f"class {name}"


def parse_with_treesitter(file_path: str, source: str, language: str) -> List[CodeUnit]:
    """
    Parse a file using tree-sitter and extract code units.
    
    Args:
        file_path: Relative path to the file
        source: Source code content
        language: Language identifier
        
    Returns:
        List of CodeUnit objects
    """
    if not TREE_SITTER_AVAILABLE:
        return []
    
    ts_language = LANGUAGE_MAP.get(language)
    if not ts_language:
        return []
    
    try:
        parser = tree_sitter_languages.get_parser(ts_language)
    except Exception:
        return []
    
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    
    units: List[CodeUnit] = []
    lines = source.splitlines(keepends=True)
    
    def get_source(start_line: int, end_line: int) -> str:
        """Extract source code for a range of lines (1-indexed)."""
        return "".join(lines[start_line - 1:end_line])
    
    def process_node(node, parent_class: Optional[str] = None):
        """Recursively process tree-sitter nodes."""
        node_type = node.type
        
        # Python
        if language == "python":
            if node_type in ("function_definition", "async_function_definition"):
                # Check if this is a method (inside a class)
                is_method = parent_class is not None
                
                name = ""
                for child in node.children:
                    if child.type == "name" or child.type == "identifier":
                        name = _get_node_text(source_bytes, child)
                        break
                
                signature = _extract_python_signature(source_bytes, node)
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                
                units.append(CodeUnit(
                    unit_id=None,
                    file_path=file_path,
                    symbol_name=name,
                    unit_type="method" if is_method else "function",
                    parent_class=parent_class,
                    signature=signature,
                    start_line=start_line,
                    end_line=end_line,
                    full_code=get_source(start_line, end_line),
                ))
                return  # Don't recurse into function body
            
            elif node_type == "class_definition":
                name = ""
                for child in node.children:
                    if child.type == "name" or child.type == "identifier":
                        name = _get_node_text(source_bytes, child)
                        break
                
                signature = _extract_class_signature(source_bytes, node, language)
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                
                units.append(CodeUnit(
                    unit_id=None,
                    file_path=file_path,
                    symbol_name=name,
                    unit_type="class",
                    parent_class=None,
                    signature=signature,
                    start_line=start_line,
                    end_line=end_line,
                    full_code=get_source(start_line, end_line),
                ))
                
                # Process methods inside the class
                for child in node.children:
                    if child.type == "block":
                        for block_child in child.children:
                            process_node(block_child, parent_class=name)
                return
        
        # JavaScript/TypeScript
        elif language in ("javascript", "typescript"):
            if node_type in ("function_declaration", "method_definition", "function"):
                name = ""
                for child in node.children:
                    if child.type in ("identifier", "property_identifier"):
                        name = _get_node_text(source_bytes, child)
                        break
                
                if not name:
                    return
                
                signature = _extract_js_signature(source_bytes, node)
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                
                is_method = parent_class is not None or node_type == "method_definition"
                
                units.append(CodeUnit(
                    unit_id=None,
                    file_path=file_path,
                    symbol_name=name,
                    unit_type="method" if is_method else "function",
                    parent_class=parent_class,
                    signature=signature,
                    start_line=start_line,
                    end_line=end_line,
                    full_code=get_source(start_line, end_line),
                ))
                return
            
            elif node_type == "class_declaration":
                name = ""
                for child in node.children:
                    if child.type in ("identifier", "type_identifier"):
                        name = _get_node_text(source_bytes, child)
                        break
                
                signature = _extract_class_signature(source_bytes, node, language)
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                
                units.append(CodeUnit(
                    unit_id=None,
                    file_path=file_path,
                    symbol_name=name,
                    unit_type="class",
                    parent_class=None,
                    signature=signature,
                    start_line=start_line,
                    end_line=end_line,
                    full_code=get_source(start_line, end_line),
                ))
                
                # Process methods inside the class
                for child in node.children:
                    if child.type == "class_body":
                        for body_child in child.children:
                            process_node(body_child, parent_class=name)
                return
            
            # Arrow functions assigned to variables
            elif node_type in ("lexical_declaration", "variable_declaration"):
                for child in node.children:
                    if child.type == "variable_declarator":
                        name = ""
                        has_arrow = False
                        for vc in child.children:
                            if vc.type == "identifier":
                                name = _get_node_text(source_bytes, vc)
                            elif vc.type == "arrow_function":
                                has_arrow = True
                        
                        if name and has_arrow:
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1
                            
                            units.append(CodeUnit(
                                unit_id=None,
                                file_path=file_path,
                                symbol_name=name,
                                unit_type="function",
                                parent_class=None,
                                signature=f"const {name} = (...) =>",
                                start_line=start_line,
                                end_line=end_line,
                                full_code=get_source(start_line, end_line),
                            ))
                return
        
        # Recurse into children
        for child in node.children:
            process_node(child, parent_class)
    
    process_node(tree.root_node)
    return units
