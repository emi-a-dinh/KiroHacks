"""Regex-based fallback parser for extracting code units from unsupported languages."""

import re
from typing import List

from indexer.models import CodeUnit

# Patterns for different languages
PATTERNS = {
    "javascript": {
        "function": [
            # function name(...) { or async function name(...) {
            r"(?P<async>async\s+)?function\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)",
            # const/let/var name = function(...) { or arrow function
            r"(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?P<async>async\s+)?(?:function\s*)?\((?P<params>[^)]*)\)\s*(?:=>|{)",
            # const/let/var name = async (...) =>
            r"(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?P<async>async\s+)?\((?P<params>[^)]*)\)\s*=>",
        ],
        "class": [
            r"class\s+(?P<name>\w+)(?:\s+extends\s+(?P<base>\w+))?",
        ],
        "method": [
            # method(...) { inside class
            r"^\s+(?P<async>async\s+)?(?P<name>\w+)\s*\((?P<params>[^)]*)\)",
        ],
    },
    "typescript": {
        "function": [
            r"(?P<async>async\s+)?function\s+(?P<name>\w+)\s*(?:<[^>]*>)?\s*\((?P<params>[^)]*)\)(?:\s*:\s*(?P<return>[^{]+))?",
            r"(?:const|let|var)\s+(?P<name>\w+)\s*(?::\s*[^=]+)?\s*=\s*(?P<async>async\s+)?(?:function\s*)?\((?P<params>[^)]*)\)",
            r"(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?P<async>async\s+)?\((?P<params>[^)]*)\)\s*(?::\s*(?P<return>[^=]+))?\s*=>",
        ],
        "class": [
            r"(?:export\s+)?class\s+(?P<name>\w+)(?:<[^>]*>)?(?:\s+extends\s+(?P<base>\w+))?(?:\s+implements\s+(?P<impl>[^{]+))?",
        ],
        "method": [
            r"^\s+(?P<async>async\s+)?(?P<name>\w+)\s*(?:<[^>]*>)?\s*\((?P<params>[^)]*)\)(?:\s*:\s*(?P<return>[^{]+))?",
        ],
        "interface": [
            r"(?:export\s+)?interface\s+(?P<name>\w+)(?:<[^>]*>)?(?:\s+extends\s+(?P<base>[^{]+))?",
        ],
    },
    "go": {
        "function": [
            r"func\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)(?:\s*(?P<return>[^{]+))?",
            # Method with receiver
            r"func\s+\((?P<receiver>[^)]+)\)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)(?:\s*(?P<return>[^{]+))?",
        ],
        "struct": [
            r"type\s+(?P<name>\w+)\s+struct",
        ],
        "interface": [
            r"type\s+(?P<name>\w+)\s+interface",
        ],
    },
}


def _find_block_end(lines: List[str], start_idx: int, open_char: str = "{", close_char: str = "}") -> int:
    """Find the end of a code block by counting braces."""
    depth = 0
    in_string = False
    string_char = None
    
    for i in range(start_idx, len(lines)):
        line = lines[i]
        j = 0
        while j < len(line):
            char = line[j]
            
            # Handle string literals
            if char in ('"', "'", "`") and (j == 0 or line[j-1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
            
            if not in_string:
                if char == open_char:
                    depth += 1
                elif char == close_char:
                    depth -= 1
                    if depth == 0:
                        return i
            j += 1
    
    return start_idx


def parse_with_regex(file_path: str, source: str, language: str) -> List[CodeUnit]:
    """
    Parse a file using regex patterns to extract code units.
    
    This is a fallback parser for languages without tree-sitter support.
    It's less accurate but provides basic coverage.
    
    Args:
        file_path: Relative path to the file
        source: Source code content
        language: Language identifier
        
    Returns:
        List of CodeUnit objects
    """
    units: List[CodeUnit] = []
    
    # Get patterns for this language
    lang_patterns = PATTERNS.get(language, PATTERNS.get("javascript", {}))
    
    lines = source.splitlines(keepends=True)
    
    # Track which lines are already part of a unit to avoid duplicates
    used_lines = set()
    
    # Process function patterns
    for pattern in lang_patterns.get("function", []):
        for match in re.finditer(pattern, source, re.MULTILINE):
            # Find line number
            start_pos = match.start()
            line_num = source[:start_pos].count("\n") + 1
            
            if line_num in used_lines:
                continue
            
            name = match.group("name")
            params = match.group("params") if "params" in match.groupdict() else ""
            is_async = bool(match.groupdict().get("async"))
            return_type = match.groupdict().get("return", "")
            
            # Find end of function
            end_line = _find_block_end(lines, line_num - 1) + 1
            
            # Build signature
            async_prefix = "async " if is_async else ""
            return_suffix = f" -> {return_type.strip()}" if return_type and return_type.strip() else ""
            signature = f"{async_prefix}function {name}({params.strip()}){return_suffix}"
            
            full_code = "".join(lines[line_num - 1:end_line])
            
            units.append(CodeUnit(
                unit_id=None,
                file_path=file_path,
                symbol_name=name,
                unit_type="function",
                parent_class=None,
                signature=signature,
                start_line=line_num,
                end_line=end_line,
                full_code=full_code,
            ))
            
            for ln in range(line_num, end_line + 1):
                used_lines.add(ln)
    
    # Process class patterns
    for pattern in lang_patterns.get("class", []) + lang_patterns.get("struct", []) + lang_patterns.get("interface", []):
        for match in re.finditer(pattern, source, re.MULTILINE):
            start_pos = match.start()
            line_num = source[:start_pos].count("\n") + 1
            
            if line_num in used_lines:
                continue
            
            name = match.group("name")
            base = match.groupdict().get("base", "")
            
            # Find end of class
            end_line = _find_block_end(lines, line_num - 1) + 1
            
            # Build signature
            if base:
                signature = f"class {name}({base})"
            else:
                signature = f"class {name}"
            
            full_code = "".join(lines[line_num - 1:end_line])
            
            units.append(CodeUnit(
                unit_id=None,
                file_path=file_path,
                symbol_name=name,
                unit_type="class",
                parent_class=None,
                signature=signature,
                start_line=line_num,
                end_line=end_line,
                full_code=full_code,
            ))
            
            for ln in range(line_num, end_line + 1):
                used_lines.add(ln)
    
    return units
