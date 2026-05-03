"""Automatic unit selection for fix/ask/plan commands."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer.models import CodeUnit
    from ..storage.db import Database


# ── Stop words ─────────────────────────────────────────────────────────────────

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
    "def", "class", "return", "self", "import", "none", "true", "false",
    "function", "const", "let", "var", "async", "await",
}


# ── Intent terms and aliases ──────────────────────────────────────────────────

WRITE_TERMS = {"write", "writes", "writing", "post", "put", "patch", "delete", "create", "update", "insert", "save"}
READ_TERMS = {"read", "get", "list", "search", "fetch", "find", "query"}
AUTH_TERMS = {"auth", "authentication", "authorization", "jwt", "session", "user", "owner", "permission", "401", "403"}
BACKEND_TERMS = {"backend", "server", "api", "route", "routes", "endpoint", "handler", "middleware", "controller", "service"}
FRONTEND_TERMS = {"frontend", "front", "ui", "ux", "component", "components", "page", "pages", "hook", "hooks", "form", "button"}
TEST_TERMS = {"test", "tests", "spec", "assert", "expect", "coverage"}

WRITE_METHODS = {"post", "put", "patch", "delete"}
READ_METHODS = {"get"}

GENERIC_PATH_TOKENS = {
    "src", "app", "apps", "api", "web", "lib", "utils", "shared",
    "routes", "route", "services", "service", "middleware", "types",
    "hooks", "pages", "components", "repositories", "repository",
}

ROUTE_CALL_RE = re.compile(
    r"\b(?:router|app|[A-Za-z_][A-Za-z0-9_]*Router)\s*\.\s*"
    r"(get|post|put|patch|delete)\s*\(",
    re.IGNORECASE,
)


ALIASES = {
    "write":          {"post", "put", "patch", "delete", "create", "update"},
    "writes":         {"write", "post", "put", "patch", "delete", "create", "update"},
    "writing":        {"write", "post", "put", "patch", "delete", "create", "update"},
    "create":         {"post", "insert", "add", "save"},
    "update":         {"modify", "edit", "change"},
    "remove":         {"delete", "destroy"},
    "read":           {"get", "list", "search", "fetch", "query"},
    "list":           {"get", "read", "fetch"},
    "search":         {"get", "read", "query", "filter"},
    "auth":           {"authentication", "authorization", "jwt", "session", "user", "owner", "permission", "401", "403"},
    "authentication": {"auth", "jwt", "session", "user"},
    "authorization":  {"auth", "owner", "permission", "401", "403"},
    "authenticated":  {"auth", "session", "user"},
    "middleware":     {"requireauth", "auth"},
    "endpoint":       {"route", "handler", "api"},
    "route":          {"endpoint", "handler", "api", "router"},
    "attribution":    {"createdby", "created", "creator", "owner", "user"},
    "attribute":      {"createdby", "created", "creator", "owner", "user"},
    "created":        {"create", "createdby", "creator", "owner", "user"},
    "createdby":      {"created", "creator", "owner", "user"},
    "bug":            {"fix", "issue", "broken", "error", "wrong"},
    "fix":            {"bug", "repair", "patch", "resolve"},
    "pagination":     {"paginate", "page", "offset", "limit", "page_size"},
    "test":           {"spec", "assert", "expect", "verify", "check"},
    "task":           {"todo", "item", "ticket", "issue"},
}


# ── Result types (improvement #6) ─────────────────────────────────────────────

@dataclass
class SelectedUnit:
    """A selected unit with its score and reasons."""
    unit: "CodeUnit"
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class SelectionResult:
    """Full selection result."""
    units: List[SelectedUnit] = field(default_factory=list)
    confidence: float = 0.0
    confidence_label: str = "low"
    coverage: Dict[str, bool] = field(default_factory=dict)
    excluded: List[str] = field(default_factory=list)


# ── Tokenizer (improvement #1) ────────────────────────────────────────────────

def _tokenize(text: str) -> Set[str]:
    """
    Extract meaningful tokens from text.
    Splits camelCase and snake_case BEFORE lowercasing to preserve signal.
    """
    # Find identifiers (preserve case for camelCase splitting)
    raw = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text)
    tokens = set()

    for word in raw:
        # Split snake_case
        snake_parts = word.split("_")
        for part in snake_parts:
            # Split camelCase (before lowercasing)
            camel_parts = re.findall(
                r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+',
                part
            )
            for s in camel_parts:
                s = s.lower()
                if len(s) > 1 and s not in STOP_WORDS:
                    tokens.add(s)
                    if len(s) > 3 and s.endswith("s"):
                        tokens.add(s[:-1])
                    if len(s) > 4 and s.endswith("ed"):
                        tokens.add(s[:-2])

        # Also add the full word lowered
        lowered = word.lower()
        if len(lowered) > 1 and lowered not in STOP_WORDS:
            tokens.add(lowered)
            if len(lowered) > 3 and lowered.endswith("s"):
                tokens.add(lowered[:-1])
            if len(lowered) > 4 and lowered.endswith("ed"):
                tokens.add(lowered[:-2])

    return tokens


def _expand_aliases(tokens: Set[str]) -> Set[str]:
    """Expand tokens with domain aliases."""
    expanded = set(tokens)
    for token in tokens:
        if token in ALIASES:
            expanded.update(ALIASES[token])
    return expanded


def _detect_intent(task_tokens: Set[str], expanded_tokens: Set[str]) -> Dict[str, bool]:
    """Classify the task using simple internal keyword rules."""
    tokens = task_tokens | expanded_tokens
    write = bool(tokens & WRITE_TERMS)
    read = bool(tokens & READ_TERMS)
    auth = bool(tokens & AUTH_TERMS)
    frontend = bool(tokens & FRONTEND_TERMS)
    api = bool(tokens & BACKEND_TERMS) or (auth and write)
    backend = bool(tokens & BACKEND_TERMS) or api

    return {
        "write": write,
        "read": read and not write,
        "auth": auth,
        "backend": backend,
        "frontend": frontend,
        "api": api,
        "tests": bool(tokens & TEST_TERMS),
    }


def _is_route_unit(unit: "CodeUnit") -> bool:
    """Return true only for explicitly typed route handler units.

    We intentionally do NOT match by file path alone. Functions that live in a
    routes/ directory (helpers, middleware, etc.) are regular functions and
    should not be subject to HTTP-method filtering.
    """
    return unit.unit_type == "route"


def _task_wants_write_endpoint(intent: Dict[str, bool]) -> bool:
    """Detect tasks that need write endpoint context.

    Requires both a write signal AND an explicit backend/api/auth signal.
    A task like "update affected tests" has write=True from the alias expansion
    of "update", but no backend signal — it should not trigger endpoint filtering.
    """
    return intent["write"] and (intent["backend"] or intent["api"] or intent["auth"])


def _path_tokens(file_path: str) -> Set[str]:
    return set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', file_path.lower()))


def _is_frontend_file(file_path: str) -> bool:
    path = f"/{file_path.lower()}"
    return (
        "/apps/web/" in path
        or "/web/" in path
        or "/pages/" in path
        or "/hooks/" in path
        or "/components/" in path
        or file_path.endswith(".tsx")
        or file_path.endswith(".jsx")
    )


def _is_backend_file(file_path: str) -> bool:
    path = f"/{file_path.lower()}"
    return (
        "/apps/api/" in path
        or "/api/" in path
        or "/server/" in path
        or "/routes/" in path
        or "/controllers/" in path
        or "/middleware/" in path
        or "/services/" in path
        or "/repositories/" in path
    )


def _is_tooling_file(file_path: str) -> bool:
    """Return True for files that are part of the token-miser tool itself.

    These files contain the same vocabulary as application tasks (auth, write,
    user, etc.) because they implement the selector logic, and should not be
    returned when the task is about a different application.
    """
    path = f"/{file_path.lower()}"
    return (
        "/token-miser/" in path
        or "/context-lens/" in path
        or "/.token-miser/" in path
        or "/.context-lens/" in path
    )


def _is_request_user_typing(unit: "CodeUnit") -> bool:
    text = f"{unit.file_path}\n{unit.signature}\n{unit.full_code}".lower()
    return (
        "express.d.ts" in unit.file_path.lower()
        or ("namespace express" in text and "user" in text)
        or ("interface request" in text and "user" in text)
    )


def _contains_any(text: str, needles: Set[str]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def _route_method(unit: "CodeUnit") -> str:
    """Extract HTTP method from route unit symbol/signature."""
    text = f"{unit.symbol_name} {unit.signature}".lower()
    for method in ("post", "put", "patch", "delete", "get"):
        if re.search(rf"\b{method}\b|^{method}_", text):
            return method
    return ""


def _route_expression_code(unit: "CodeUnit") -> str:
    """Return the route call expression without imported context prefix."""
    if unit.unit_type != "route":
        return unit.full_code
    return unit.full_code.rsplit("\n\n", 1)[-1]


def _is_public_auth_route(unit: "CodeUnit") -> bool:
    """Detect login/register auth routes that normally should not require auth.

    Only applies to explicitly typed route units — not to helper functions that
    happen to live in a routes/auth file.
    """
    if unit.unit_type != "route":
        return False
    text = f"{unit.file_path} {unit.symbol_name} {unit.signature}".lower()
    return "/routes/auth" in f"/{unit.file_path.lower()}" or "login" in text or "register" in text


def _framework_score(unit: "CodeUnit", intent: Dict[str, bool]) -> float:
    """Score framework-specific route/auth patterns."""
    text = f"{unit.signature}\n{unit.full_code}"
    lower = text.lower()
    score = 0.0

    route_methods = {method.lower() for method in ROUTE_CALL_RE.findall(text)}
    method = _route_method(unit)
    if method:
        route_methods.add(method)

    if intent["write"] and route_methods & WRITE_METHODS:
        score += 24
    elif intent["read"] and route_methods & READ_METHODS:
        score += 14
    elif route_methods and (intent["api"] or intent["backend"]) and not intent["write"]:
        score += 8

    if intent["auth"]:
        if "requireauth" in lower:
            score += 14
        if "req.user" in lower:
            score += 14
        if _contains_any(lower, {"verifytoken", "jwt", "bearer", "401", "403"}):
            score += 6
        if _is_request_user_typing(unit):
            score += 20

    if intent["write"] and _contains_any(lower, {"createdby", "created_by", "ownerid", "owner_id"}):
        score += 10

    return score


def _shares_task_tokens(unit: "CodeUnit", expanded_tokens: Set[str]) -> bool:
    tokens = _tokenize(f"{unit.symbol_name} {unit.signature}")
    meaningful = expanded_tokens - GENERIC_PATH_TOKENS - {"post", "get", "put", "patch", "delete"}
    return bool(tokens & meaningful)


def _is_similar_route_handler(unit: "CodeUnit", top_units: List["CodeUnit"], intent: Dict[str, bool]) -> bool:
    if not _is_route_unit(unit):
        return False

    method = _route_method(unit)
    if intent["write"] and method not in WRITE_METHODS:
        return False
    if intent["read"] and method not in READ_METHODS:
        return False

    for top in top_units:
        if not _is_route_unit(top):
            continue
        if top.file_path != unit.file_path:
            continue
        top_method = _route_method(top)
        if intent["write"] and top_method in WRITE_METHODS and method in WRITE_METHODS:
            return True
        if intent["read"] and top_method in READ_METHODS and method in READ_METHODS:
            return True
    return False


# ── Shared name token check (improvement #3) ──────────────────────────────────

def _shares_name_tokens(unit_a: "CodeUnit", unit_b: "CodeUnit") -> bool:
    """Check if two units share meaningful name tokens (e.g. get_task, update_task)."""
    parts_a = set(unit_a.symbol_name.lower().split("_")) - {"", "test"}
    parts_b = set(unit_b.symbol_name.lower().split("_")) - {"", "test"}
    # Remove very generic parts
    generic = {"get", "set", "do", "is", "has", "on", "to"}
    parts_a -= generic
    parts_b -= generic
    return bool(parts_a & parts_b)


# ── Test file matching (improvement #4) ───────────────────────────────────────

def _find_test_file_for(source_path: str) -> Set[str]:
    """
    Given a source file path, return possible test file name patterns.
    e.g. routes/tasks.py → {test_tasks, tasks_test, test_tasks.py}
    """
    import os
    basename = os.path.basename(source_path).replace(".py", "").replace(".js", "").replace(".ts", "")
    return {
        f"test_{basename}",
        f"{basename}_test",
        f"{basename}.test",
        f"{basename}.spec",
        f"test_{basename}.py",
        f"{basename}_test.py",
        f"test_{basename}.js",
        f"{basename}_test.js",
        f"test_{basename}.ts",
        f"{basename}_test.ts",
        f"{basename}.test.ts",
        f"{basename}.spec.ts",
    }


# ── Scoring ────────────────────────────────────────────────────────────────────

def _score_unit(
    unit: "CodeUnit",
    task_tokens: Set[str],
    expanded_tokens: Set[str],
    error_tokens: Set[str],
    file_path_hits: Set[str],
    intent: Dict[str, bool],
) -> Tuple[float, List[str]]:
    """
    Score a unit and return (score, reasons).
    Uses expanded tokens (with aliases) for matching.
    """
    score = 0.0
    reasons = []

    name_lower = unit.symbol_name.lower()
    name_parts = set(name_lower.split("_")) - {""}
    name_parts.add(name_lower)

    # Symbol name exact match against original task tokens
    name_task_match = name_parts & task_tokens
    if name_task_match:
        score += 10
        reasons.append(f"name matches task: {', '.join(name_task_match)}")

    # Symbol name match against expanded tokens (aliases)
    name_alias_match = name_parts & (expanded_tokens - task_tokens)
    if name_alias_match and not name_task_match:
        score += 7
        reasons.append(f"name matches alias: {', '.join(name_alias_match)}")

    # File path match. Ignore generic folder names so "middleware" does not
    # make every middleware file look relevant.
    path_parts = _path_tokens(unit.file_path) - GENERIC_PATH_TOKENS
    path_task_match = path_parts & expanded_tokens
    if path_task_match:
        score += 6
        reasons.append(f"file path matches: {', '.join(path_task_match)}")

    path_error_match = path_parts & error_tokens
    if path_error_match:
        score += 8
        reasons.append(f"file path in error log")

    if unit.file_path in file_path_hits:
        score += 6
        reasons.append(f"exact file path in error: {unit.file_path}")

    # Signature token overlap
    sig_tokens = _tokenize(unit.signature)
    sig_overlap = sig_tokens & expanded_tokens
    if sig_overlap:
        pts = min(5, len(sig_overlap) * 2)
        score += pts
        reasons.append(f"signature overlap: {', '.join(list(sig_overlap)[:5])}")

    sig_error_overlap = sig_tokens & error_tokens
    if sig_error_overlap:
        pts = min(4, len(sig_error_overlap) * 2)
        score += pts
        reasons.append(f"signature matches error tokens")

    # Code body overlap — raised cap so a function with many relevant tokens
    # scores meaningfully higher than one with just one or two.
    code_tokens = _tokenize(unit.full_code)
    code_overlap = code_tokens & expanded_tokens
    if code_overlap:
        pts = min(8, len(code_overlap) * 1.5)
        score += pts

    score += _framework_score(unit, intent)

    wants_write_endpoint = _task_wants_write_endpoint(intent)
    if _is_route_unit(unit):
        method = _route_method(unit)
        if wants_write_endpoint and method and method not in WRITE_METHODS:
            return 0.0, []
        if wants_write_endpoint and method in WRITE_METHODS:
            score += 18
            reasons.append(f"write route endpoint: {method.upper()}")
        elif "route" in expanded_tokens or "endpoint" in expanded_tokens:
            score += 8
            reasons.append("route endpoint")

        if intent["auth"] and method in WRITE_METHODS:
            route_expression = _route_expression_code(unit).lower()
            if "requireauth" not in route_expression:
                score += 8
                reasons.append("write route missing requireAuth")
            else:
                score += 3
                reasons.append("authenticated write route pattern")

        if "createdby" in expanded_tokens and "createdby" in unit.full_code.lower():
            score += 6
            reasons.append("route handles user attribution")

    if intent["backend"] or intent["api"]:
        lower_path = unit.file_path.lower()
        if wants_write_endpoint and "/repositories/" in f"/{lower_path}":
            score = 0.0
            reasons = []
        elif wants_write_endpoint and lower_path.endswith("/app.ts"):
            score = 0.0
            reasons = []
        elif wants_write_endpoint and "/lib/jwt" in f"/{lower_path}" and unit.symbol_name.lower() not in {"verifytoken", "verify_token"}:
            score = 0.0
            reasons = []
        elif _is_public_auth_route(unit) and not ({"login", "register"} & task_tokens):
            score = 0.0
            reasons = []
        elif _is_frontend_file(unit.file_path) and not intent["frontend"]:
            score *= 0.10
            if score > 0:
                reasons.append("deprioritized non-backend context")
        elif lower_path.startswith("packages/shared/") and not _is_request_user_typing(unit):
            score = 0.0
            reasons = []
        elif wants_write_endpoint and _is_tooling_file(unit.file_path):
            # Suppress indexer/query/storage internals when the task is about
            # application write endpoints — they only match because the tool
            # source contains the same vocabulary (auth, write, user, etc.)
            score = 0.0
            reasons = []

    # Suppress tooling files for any task that doesn't explicitly mention the tool.
    # This must run outside the backend/api block so it catches all intent types.
    if _is_tooling_file(unit.file_path) and not (task_tokens & {"miser", "selector", "indexer", "index", "scanner", "parser"}):
        score = 0.0
        reasons = []

    # Suppress private test helpers (e.g. _write_fixture, _setup_db).
    # These are not test functions — they're setup code that happens to contain
    # every domain keyword and inflates scores badly.
    if "test" in unit.file_path.lower() and unit.symbol_name.startswith("_"):
        score = 0.0
        reasons = []

    return score, reasons


# ── Main selector ──────────────────────────────────────────────────────────────

def select_units(
    db: "Database",
    task: str,
    error_log: Optional[str] = None,
    k: int = 10,
    include_neighbors: bool = True,
    include_tests: bool = True,
) -> SelectionResult:
    """
    Automatically select the most relevant units for a task.

    Returns a SelectionResult with units, confidence, coverage, and reasons.
    """
    all_units = db.get_all_units()
    if not all_units:
        return SelectionResult()

    # Tokenize
    task_tokens = _tokenize(task)
    expanded_tokens = _expand_aliases(task_tokens)
    intent = _detect_intent(task_tokens, expanded_tokens)
    error_tokens = _tokenize(error_log) if error_log else set()

    # Extract file paths from error log
    file_path_hits = set()
    if error_log:
        for match in re.finditer(r'["\']?([a-zA-Z0-9_/\\]+\.\w+)["\']?', error_log):
            file_path_hits.add(match.group(1))

    # ── Phase 1: Score all units ───────────────────────────────────────────
    scored = []
    for unit in all_units:
        score, reasons = _score_unit(unit, task_tokens, expanded_tokens, error_tokens, file_path_hits, intent)
        if score >= 1:
            scored.append(SelectedUnit(unit=unit, score=score, reasons=reasons))

    scored.sort(key=lambda s: -s.score)

    # ── Phase 2: Take top K ────────────────────────────────────────────────
    selected_ids = set()
    selected = []

    for su in scored[:k]:
        if su.unit.unit_id and su.unit.unit_id not in selected_ids:
            selected_ids.add(su.unit.unit_id)
            selected.append(su)

    # ── Phase 3: Stricter sibling selection (improvement #3) ───────────────
    top_units = [su.unit for su in selected]
    top_files = {u.file_path for u in top_units}

    for unit in all_units:
        if len(selected) >= int(k * 1.5):
            break
        if unit.unit_id in selected_ids:
            continue
        if unit.file_path not in top_files:
            continue
        if unit.unit_type == "constant":
            continue

        # Only add if: has a score OR shares name tokens with a top unit
        sib_score, sib_reasons = _score_unit(unit, task_tokens, expanded_tokens, error_tokens, file_path_hits, intent)
        shares_name = any(_shares_name_tokens(unit, top_u) for top_u in top_units)
        if _is_route_unit(unit):
            directly_related = (
                _shares_task_tokens(unit, expanded_tokens)
                or _is_similar_route_handler(unit, top_units, intent)
            )
        else:
            directly_related = (
                _shares_task_tokens(unit, expanded_tokens)
                or shares_name
            )

        if sib_score >= 3 and directly_related:
            sib_reasons.append("same-file sibling with relevance")
            selected_ids.add(unit.unit_id)
            selected.append(SelectedUnit(unit=unit, score=sib_score, reasons=sib_reasons))
        elif directly_related and _is_similar_route_handler(unit, top_units, intent):
            selected_ids.add(unit.unit_id)
            selected.append(SelectedUnit(
                unit=unit, score=1.0,
                reasons=["same-file related route handler"]
            ))

    # ── Phase 4: Depth-1 callee expansion only ────────────────────────────
    # We expand callees (what selected units call) but not callers.
    # Callers are rarely needed for a fix — they just add noise.
    if include_neighbors and selected_ids:
        callee_ids_all: Set[int] = set()
        placeholders = ",".join("?" * len(selected_ids))
        # Use db directly via a helper — get only outgoing edges (callees)
        callee_rows = db.conn.execute(
            f"SELECT DISTINCT callee_id FROM edges WHERE caller_id IN ({placeholders})",
            list(selected_ids)
        ) if hasattr(db, 'conn') else []
        for row in callee_rows:
            callee_ids_all.add(row[0] if isinstance(row, tuple) else row["callee_id"])
        callee_ids_all -= selected_ids

        callee_units = db.get_units_by_ids(list(callee_ids_all))
        for unit in callee_units:
            if len(selected) >= k + 4:
                break
            if unit.unit_id in selected_ids:
                continue
            n_score, n_reasons = _score_unit(unit, task_tokens, expanded_tokens, error_tokens, file_path_hits, intent)
            if _task_wants_write_endpoint(intent) and "/repositories/" in f"/{unit.file_path.lower()}":
                continue
            if n_score >= 1:
                n_reasons.append("call graph neighbor")
                selected_ids.add(unit.unit_id)
                selected.append(SelectedUnit(unit=unit, score=n_score, reasons=n_reasons))

    # ── Phase 5: Smarter test discovery (improvement #4) ───────────────────
    if include_tests:
        # Build set of test file patterns from selected source files
        source_files = {su.unit.file_path for su in selected if "test" not in su.unit.file_path.lower()}
        test_patterns = set()
        for sf in source_files:
            test_patterns.update(_find_test_file_for(sf))

        # Also collect domain words from task for matching test function names
        domain_words = task_tokens & expanded_tokens

        test_units = [u for u in all_units if "test" in u.file_path.lower() and u.unit_id not in selected_ids]

        for unit in test_units:
            if len(selected) >= k * 2:
                break

            test_reasons = []
            test_score = 0.0

            # Check if test file matches a source file
            basename = unit.file_path.lower().split("/")[-1]
            if any(pat in basename for pat in test_patterns):
                test_score += 5
                test_reasons.append(f"test file for {', '.join(source_files)}")

            # Check if test function name contains domain words
            test_name_parts = set(unit.symbol_name.lower().split("_")) - {"test", ""}
            domain_match = test_name_parts & expanded_tokens
            if domain_match:
                test_score += 3
                test_reasons.append(f"test name matches: {', '.join(domain_match)}")

            # Check if test code references selected function names
            selected_names = {su.unit.symbol_name.lower() for su in selected}
            code_lower = unit.full_code.lower()
            name_refs = [n for n in selected_names if n in code_lower]
            if name_refs:
                test_score += 4
                test_reasons.append(f"test references: {', '.join(name_refs)}")

            # Check if test code contains route strings
            route_patterns = re.findall(r'["\']/(api/[^"\']+)["\']', unit.full_code)
            route_task_match = any(
                any(t in route.lower() for t in task_tokens)
                for route in route_patterns
            )
            if route_task_match:
                test_score += 3
                test_reasons.append("test hits task-related route")

            if test_score > 0:
                selected_ids.add(unit.unit_id)
                selected.append(SelectedUnit(unit=unit, score=test_score, reasons=test_reasons))

    # ── Phase 6: Internal confidence bookkeeping ───────────────────────────
    coverage = {}
    wants_write_endpoint = _task_wants_write_endpoint(intent)

    # target_found: did we find a unit whose name directly matches the task?
    coverage["target_found"] = any(
        su.unit.symbol_name.lower() in task_tokens or
        set(su.unit.symbol_name.lower().split("_")) & task_tokens
        for su in selected
    )

    if wants_write_endpoint:
        coverage["write_endpoint_found"] = any(
            _is_route_unit(su.unit) and _route_method(su.unit) in {"post", "put", "patch", "delete"}
            for su in selected
        )

    # similar_pattern_found: did we find a same-file sibling with a shared name?
    coverage["similar_pattern_found"] = any(
        "same-file sibling" in r for su in selected for r in su.reasons
    )

    # dependency_found: did we include a call graph neighbor?
    coverage["dependency_found"] = any(
        "call graph neighbor" in r for su in selected for r in su.reasons
    )

    # test_found: did we include at least one test?
    coverage["test_found"] = any(
        "test" in su.unit.file_path.lower() for su in selected
    )

    # error_file_found: if error log provided, did we match the file?
    if error_log and file_path_hits:
        coverage["error_file_found"] = any(
            su.unit.file_path in file_path_hits for su in selected
        )
    elif error_log:
        coverage["error_file_found"] = False

    # Compute confidence from coverage
    confidence = 0.0
    top_score = scored[0].score if scored else 0

    if top_score >= 10:
        confidence += 0.35
    elif top_score >= 5:
        confidence += 0.20

    if coverage.get("target_found"):
        confidence += 0.20
    if coverage.get("write_endpoint_found"):
        confidence += 0.25
    if coverage.get("similar_pattern_found") or coverage.get("dependency_found"):
        confidence += 0.15
    if coverage.get("test_found"):
        confidence += 0.15
    if coverage.get("error_file_found", True):  # True if no error log
        confidence += 0.15

    confidence = min(confidence, 1.0)
    if wants_write_endpoint and not coverage.get("write_endpoint_found"):
        confidence = min(confidence, 0.55)

    if confidence >= 0.75:
        conf_label = "high"
    elif confidence >= 0.45:
        conf_label = "medium"
    else:
        conf_label = "low"

    # Sort by file path and line number
    selected.sort(key=lambda su: (su.unit.file_path, su.unit.start_line))

    return SelectionResult(
        units=selected,
        confidence=confidence,
        confidence_label=conf_label,
        coverage=coverage,
    )
