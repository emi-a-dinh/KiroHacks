# PRD: Context Lens — Signature-Level Indexing with On-Demand Expansion

## 1. Problem Statement

Coding agents today send entire file contents to LLMs for every request. For a repo with 500 files and 50k lines of code, this means stuffing 150k–200k tokens into context — most of which the model never uses. This wastes tokens, increases latency, hits context window limits, and drives up cost.

The root cause: agents have no lightweight way to understand what's in a codebase without reading all of it. They need a map of the repo, not a copy of it.

## 2. Proposed Solution

Build a local CLI tool with two commands that create and query a compressed, signature-level index of a codebase.

**Core idea:** Parse source files into an AST, extract only signatures (function names, parameters, return types, class outlines, method lists), and store them as a compact index. At query time, present this small index to the LLM so it can choose which functions to see in full. Then expand only those selected units. The result is a prompt that contains the full repo's structure but only the relevant code bodies — typically 10–15x fewer tokens than the naive approach.

## 3. Target User

- Developers building or extending coding agents / LLM-based dev tools.
- Hackathon context: judges evaluating a working demo on a real repo.

## 4. Commands

### 4.1 `context-index`

**Input:**
- `repo_path` — path to a local repository

**Behavior:**
1. Walk the file tree. Skip binary files, files over 500KB, and common non-source directories (`node_modules`, `.git`, `__pycache__`, `venv`, `dist`, `build`).
2. For each source file, compute a SHA-256 content hash.
3. Compare hash against the stored index. If unchanged, skip. If changed or new, re-parse. If the file was deleted from disk, remove its entries from the index.
4. **Detect moved/renamed files.** Before treating a deleted path as a true deletion and a new path as a brand-new file, check for moves:
   - Collect two sets: **orphaned paths** (in the DB but missing from disk) and **new paths** (on disk but not in the DB).
   - For each orphaned path, look for a new path with the **same content hash**. An identical hash means the file was moved or renamed without content changes.
   - When a match is found, update the `file_path` in the `files` table and all corresponding `units` rows to the new path. The `unit_id` values are preserved, so all edges pointing to/from those units remain valid. No re-parsing needed.
   - If an orphaned path's hash matches no new path, it's a genuine deletion — remove it. If a new path's hash matches no orphaned path, it's a genuinely new file — parse it.
   - If a file was both moved AND modified (different hash at the new path), it won't match. This is treated as a delete + create. Acceptable — the common case (pure rename/move via `git mv` or IDE refactor) preserves the hash.
5. Parse the file using tree-sitter (preferred) or Python's `ast` module (fallback for `.py` files).
5. Extract signature-level units:
   - **Functions:** name, parameters, return type annotation (if present), start line, end line
   - **Classes:** name, base classes, list of method signatures, start line, end line
   - **Methods:** name, parameters, return type, containing class
   - **Top-level assignments / constants** (name and type annotation only)
6. For each unit, store the full source code body alongside the signature so it can be expanded later without re-reading the file.
7. **Extract lightweight call edges (second pass).** After all files are parsed and all units are inserted, run a single pass over every unit's `full_code` to detect calls to other known symbols:
   - Build a lookup set of all `symbol_name` values in the `units` table.
   - For each unit, scan its `full_code` for identifiers that match a symbol in the set. Use simple pattern matching: `symbol_name(` for function calls, `self.symbol_name(` and `ClassName.symbol_name(` for method calls.
   - For each match, resolve to the target `unit_id`(s). If a symbol name is ambiguous (e.g., multiple functions named `validate` in different files), record edges to all matches — false positives are acceptable, false negatives are worse.
   - Insert a row into the `edges` table for each caller → callee pair.
   - **On incremental re-index:** after updating changed files' units, drop ALL rows from the `edges` table and rebuild edges from scratch. This is a full scan of `full_code` columns against the symbol name set — no file I/O, no parsing, just string matching against in-memory data. For 2k units this takes milliseconds and avoids stale edges from renamed or deleted symbols.
8. Detect language from file extension.
9. Write everything to a local SQLite database at `<repo_path>/.context-lens/index.db`.

**Output (to stdout):**
```
Files scanned:    312
Files skipped:    188  (unchanged)
Files moved:        2  (path updated, units preserved)
Files updated:     12
Units extracted: 1847
Call edges:       623
Index path:      /path/to/repo/.context-lens/index.db
Index time:      2.3s
```

**Database schema:**

```sql
CREATE TABLE files (
    file_path    TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL,
    language     TEXT,
    last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE units (
    unit_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path    TEXT NOT NULL REFERENCES files(file_path) ON DELETE CASCADE,
    symbol_name  TEXT NOT NULL,
    unit_type    TEXT NOT NULL,  -- 'function', 'class', 'method', 'constant'
    parent_class TEXT,           -- NULL unless unit_type is 'method'
    signature    TEXT NOT NULL,  -- compact one-liner: "def foo(x: int, y: str) -> bool"
    start_line   INTEGER NOT NULL,
    end_line     INTEGER NOT NULL,
    full_code    TEXT NOT NULL
);

CREATE TABLE edges (
    caller_id    INTEGER NOT NULL REFERENCES units(unit_id) ON DELETE CASCADE,
    callee_id    INTEGER NOT NULL REFERENCES units(unit_id) ON DELETE CASCADE,
    PRIMARY KEY (caller_id, callee_id)
);

CREATE INDEX idx_units_file ON units(file_path);
CREATE INDEX idx_units_symbol ON units(symbol_name);
CREATE INDEX idx_edges_caller ON edges(caller_id);
CREATE INDEX idx_edges_callee ON edges(callee_id);
```

The `edges` table is a simple join table. No graph database needed. To get "what does function X call," query `SELECT callee_id FROM edges WHERE caller_id = X`. To get "what calls function X," query `SELECT caller_id FROM edges WHERE callee_id = X`. Both queries are indexed and fast.

### 4.2 `context-query`

**Input:**
- `task` — a natural language task description (required)
- `--error` — an optional error log or traceback string
- `--k` — max number of full code units to include (default: 10)
- `--index` — path to index database (default: `.context-lens/index.db` in current directory)

**Behavior:**
1. Load the signature index from SQLite.
2. Build a **signature map**: a compact text block listing every file and its unit signatures, grouped by file. This is the "table of contents" for the repo.
3. Construct a **selection prompt** containing:
   - The task description
   - The error log (if provided), truncated to 80 lines
   - The full signature map
   - An instruction: "Select up to K functions/methods whose full source code you need to see to complete this task. Return their unit_ids."
4. The selection prompt is the primary output. It is designed to be sent to any LLM by the caller. This tool does NOT call an LLM itself — it produces the prompt.
5. Accept a second invocation with the selected unit IDs to produce the **expanded prompt**: the task + error summary + full source code of only the selected units.

**Output — Phase 1 (selection prompt):**
```
## Task
Fix the off-by-one error in pagination for the /users endpoint.

## Error
Traceback (most recent call last):
  File "api/routes.py", line 42, in get_users
    ...
IndexError: list index out of range

## Repository Signature Map (1847 units, 623 call edges, across 312 files)

### api/routes.py
  [12] def get_users(page: int, page_size: int) -> Response        (lines 30–58)
       → calls: paginate [45], get_total_pages [46]
       ← called by: UserRouter.handle_request [14]
  [13] def get_user_by_id(user_id: str) -> Response                (lines 60–78)
       → calls: User.to_dict [72]
  [14] class UserRouter                                             (lines 10–78)

### api/pagination.py
  [45] def paginate(items: list, page: int, size: int) -> list     (lines 5–22)
       ← called by: get_users [12], get_posts [87]
  [46] def get_total_pages(total: int, size: int) -> int           (lines 24–31)
       ← called by: get_users [12]

### models/user.py
  [71] class User                                                   (lines 1–35)
  [72]   def to_dict(self) -> dict                                  (lines 28–35)
       ← called by: get_user_by_id [13], get_users [12]
...

## Instruction
Select up to 10 unit IDs whose full source code is needed to complete the task.
The → and ← annotations show call relationships. Consider including callers and
callees of your selected units if they are relevant to the task.
```

**Output — Phase 2 (expanded prompt, after selection):**
```
## Task
Fix the off-by-one error in pagination for the /users endpoint.

## Error Summary
IndexError in api/routes.py:42 — list index out of range during get_users call.

## Selected Code

### api/pagination.py — paginate (lines 5–22)
# Called by: get_users [12], get_posts [87]
# Calls: (none)
def paginate(items: list, page: int, size: int) -> list:
    start = page * size
    end = start + size
    return items[start:end]

### api/routes.py — get_users (lines 30–58)
# Called by: UserRouter.handle_request [14]
# Calls: paginate [45], get_total_pages [46]
def get_users(page: int, page_size: int) -> Response:
    users = db.query(User).all()
    page_data = paginate(users, page, page_size)
    ...
```

**Token budget comparison (example):**
| Approach | Tokens |
|---|---|
| Naive: paste all files | ~180,000 |
| Signature map only | ~8,000 |
| Signature map + 10 expanded units | ~12,000 |

## 5. Supported Languages (MVP)

| Language | Parser | Priority |
|---|---|---|
| Python | tree-sitter or `ast` stdlib fallback | P0 |
| JavaScript / TypeScript | tree-sitter | P0 |
| Go | tree-sitter | P1 (stretch) |

Use the `tree-sitter-languages` package for pre-built grammars to avoid compilation issues.

If tree-sitter fails for a file, fall back to a regex-based extractor that finds `def`, `class`, `function`, `const`, `export` patterns. This will be lossy but ensures every file gets at least partial coverage.

## 6. Distribution: Kiro Power

Context Lens is distributed as a **Kiro Power** — a bundled MCP server + documentation + steering files that users install in one click from the Kiro Powers panel. No terminal, no `pip install`, no manual `mcp.json` editing.

### 6.1 Why a Power over pip

| | Kiro Power | pip + manual MCP config |
|---|---|---|
| Install | One click in Powers panel | `pip install`, edit `mcp.json`, restart Kiro |
| MCP config | Bundled inside the Power | User writes it manually |
| Auto-index on workspace open | Via steering file, automatic | User must remember to run CLI |
| Updates | Managed by Kiro | User re-runs pip |
| Demo story | "Install from panel, start chatting" | "Let me show you the terminal first" |

The core Python logic is identical either way. The Power is just a better delivery wrapper.

### 6.2 Power Structure

```
context-lens-power/
├── POWER.md                  # Shown in the Powers panel — description, keywords, usage
├── mcp.json                  # MCP server config bundled with the Power
├── steering/
│   └── context-lens.md       # Tells Kiro when and how to use the tools automatically
└── src/
    ├── mcp_server.py         # MCP server entry point
    ├── indexer/
    │   ├── scanner.py
    │   ├── parser_treesitter.py
    │   ├── parser_python.py
    │   ├── parser_regex.py
    │   ├── edge_builder.py
    │   └── models.py
    ├── storage/
    │   └── db.py
    └── query/
        ├── formatter.py
        └── expander.py
```

### 6.3 `POWER.md`

```markdown
# Context Lens

Index your codebase once. Query it fast. Context Lens builds a signature-level
map of your repo — every function, class, and method with their call relationships
— so your agent can find the relevant code without reading every file.

## What it does
- Indexes source files into a local SQLite database (Python, JS/TS supported)
- Extracts function/class signatures and lightweight call edges
- Handles incremental updates — only re-parses changed files
- Detects moved/renamed files and preserves their index entries
- Returns compact signature maps and expanded code blocks on demand

## Tools
- context_index — index or re-index a repository
- context_query — get the signature map + selection prompt for a task
- context_expand — expand selected unit IDs into full source code

## Keywords
index, codebase, context, tokens, signatures, functions, classes, call graph
```

### 6.4 `mcp.json` (bundled)

```json
{
  "mcpServers": {
    "context-lens": {
      "command": "uvx",
      "args": ["context-lens@latest"],
      "disabled": false,
      "autoApprove": ["context_index", "context_query", "context_expand"]
    }
  }
}
```

`uvx` downloads and runs the package via `uv` — no separate install step for the user. If `uv` is not installed, the Power's `POWER.md` links to the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

### 6.5 Steering File (`steering/context-lens.md`)

The steering file tells Kiro to use Context Lens automatically without the user having to ask:

```markdown
---
inclusion: auto
---

# Context Lens — Usage Guidelines

When the user opens a workspace or asks to work on code in a repository:
1. Call `context_index` with the workspace root path if no index exists yet,
   or if files have changed since the last index.
2. When the user describes a task involving code (fixing a bug, adding a feature,
   understanding a function), call `context_query` with the task description to
   get the signature map.
3. Review the signature map and call `context_expand` with the most relevant
   unit IDs. Use `include_neighbors: true` if the task involves tracing a bug
   through multiple functions.
4. Use the expanded code as context for your response. Do not read full files
   unless the signature map indicates the entire file is relevant.

This keeps token usage low and responses fast.
```

### 6.6 MCP Tools

The server exposes three tools:

#### `context_index`

```json
{
  "name": "context_index",
  "description": "Index a code repository. Parses source files, extracts function/class signatures and call edges, and stores them in a local SQLite database. Supports incremental updates — only re-parses changed files. Detects moved/renamed files and preserves their index entries.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "repo_path": {
        "type": "string",
        "description": "Absolute or relative path to the repository root."
      }
    },
    "required": ["repo_path"]
  }
}
```

**Returns:** `{ files_scanned, files_skipped, files_moved, files_updated, units_extracted, call_edges, index_path, index_time_seconds }`

#### `context_query`

```json
{
  "name": "context_query",
  "description": "Generate a signature map of the indexed repository. The map lists every function, class, and method with their call relationships — compact enough to fit in context. Use it to identify which units to expand for a given task.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "task": {
        "type": "string",
        "description": "Natural language description of the task or question."
      },
      "error_log": {
        "type": "string",
        "description": "Optional error traceback or log output related to the task."
      },
      "k": {
        "type": "integer",
        "description": "Maximum number of code units to select for expansion. Default: 10.",
        "default": 10
      },
      "index_path": {
        "type": "string",
        "description": "Path to the index database. Default: .context-lens/index.db in the repo root."
      }
    },
    "required": ["task"]
  }
}
```

**Returns:** The signature map as a formatted string with unit IDs, signatures, and call edge annotations.

#### `context_expand`

```json
{
  "name": "context_expand",
  "description": "Expand selected code units into their full source code. Each unit is prefixed with its call edges (what it calls, what calls it). Optionally include 1-hop neighbors for tracing bugs across function boundaries.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "unit_ids": {
        "type": "array",
        "items": { "type": "integer" },
        "description": "List of unit IDs to expand (from the signature map)."
      },
      "task": {
        "type": "string",
        "description": "The original task description (included in the expanded prompt for context)."
      },
      "error_summary": {
        "type": "string",
        "description": "Optional short error summary to include in the expanded prompt."
      },
      "include_neighbors": {
        "type": "boolean",
        "description": "If true, also expand direct callers and callees of the selected units (1-hop). Default: false.",
        "default": false
      },
      "index_path": {
        "type": "string",
        "description": "Path to the index database."
      }
    },
    "required": ["unit_ids"]
  }
}
```

**Returns:** Full source code of selected units (and neighbors if requested), each prefixed with `# Called by:` and `# Calls:` comments.

### 6.7 Agent Workflow (via Power)

```
User opens workspace in Kiro
  │
  ▼
Steering file triggers → Kiro calls context_index(repo_path=".")
  → "1847 units, 623 edges indexed in 2.3s"  [silent, no user prompt needed]
  │
User: "Fix the pagination bug in the /users endpoint"
  │
  ▼
Kiro calls context_query(task="Fix the pagination bug...")
  → Signature map (~8k tokens) with call edge annotations
  │
  ▼
Kiro reviews map, selects unit_ids [12, 45, 46]
  │
  ▼
Kiro calls context_expand(unit_ids=[12, 45, 46], include_neighbors=true)
  → Full source of 3 functions + their direct callers/callees (~3k tokens)
  │
  ▼
Kiro writes the fix
  Total tokens: ~11k instead of ~180k
```

### 6.8 Demo Angle

1. Open Kiro Powers panel → install Context Lens (one click).
2. Open any repo. The steering file triggers auto-indexing silently.
3. Say: "Fix the pagination bug in the /users endpoint."
4. Kiro calls all three tools automatically. Show the token counts in the tool call log.
5. Kiro produces a correct fix using ~11k tokens instead of ~180k.

No terminal. No config files. No explaining what MCP is.

## 7. Non-Goals (for MVP)

- **No embedded LLM calls.** The tool produces prompts. The steering file and agent handle the LLM calls.
- **No semantic search or embeddings.** The LLM does the relevance judgment from the signature map.
- **No full type-resolved call graph.** The edges are name-based matches, not type-checked. Ambiguous names produce duplicate edges. This is a deliberate tradeoff — good enough for navigation, not a compiler.
- **No cross-editor support at launch.** The Power is Kiro-specific. The underlying MCP server can be used standalone by other agents, but the one-click install and steering file are Kiro-only.
- **No remote/cloud storage.** Local SQLite only.

## 8. Design Decisions and Rationale

| Decision | Rationale |
|---|---|
| Signatures, not keywords | Keywords are noisy and miss semantic relevance. Signatures are compact, human-readable, and give the LLM enough to judge relevance. |
| LLM picks relevant code, not a scoring formula | Any static scoring formula will be worse than the LLM at understanding task relevance. Offload the hard problem to the thing that's good at it. |
| Two-phase query (select then expand) | Keeps the selection prompt small. The caller controls the LLM call and can use any model. |
| Lightweight call edges via name matching | A bug in function A is often caused by function B calling it with bad arguments. Without edges, the LLM has to guess which functions are related. Name-based matching is imprecise but cheap — it catches 80% of real call relationships with zero type resolution overhead. |
| Edges in a side table, not columns | A unit can call many others and be called by many. A join table (`edges`) with two foreign keys is the natural relational model. Avoids JSON arrays in columns, keeps queries simple (`WHERE caller_id = X`), and cascading deletes handle cleanup automatically. |
| Full edge rebuild on incremental index | Edges are cross-file, so changing one file can invalidate edges in other files. Rebuilding all edges from the `full_code` column (no file I/O) is fast enough (<100ms for 2k units) that surgical updates aren't worth the complexity. |
| Hash-based move detection | File renames and moves are common (IDE refactors, `git mv`, directory restructuring). Without detection, a move looks like a delete + create: old unit IDs are destroyed, edges break, and the file gets fully re-parsed for no reason. Matching orphaned DB paths to new disk paths by content hash is O(n) on the smaller set and catches the common case (pure move, no content change) with zero parsing cost. |
| SQLite | Zero setup, single file, fast enough for repos up to ~10k files. |
| tree-sitter over regex | Real AST parsing handles edge cases (decorators, async, nested classes). Regex fallback exists for resilience. |
| Store full_code in the DB | Avoids re-reading source files during expansion. Also enables edge extraction without file I/O. Trades ~2x disk for faster query and rebuild. |

## 9. Success Metrics (Hackathon Demo)

1. **Token reduction ratio:** Demonstrate ≥10x reduction vs. naive full-file inclusion on a real open-source repo (e.g., Flask, FastAPI, or a mid-size project).
2. **Index speed:** Under 5 seconds for a repo with 500 files.
3. **Incremental re-index speed:** Under 1 second when fewer than 10 files changed.
4. **Signature map readability:** The map should be immediately understandable to a human reading it — no encoded blobs or opaque formats.
5. **End-to-end demo:** Show a task → signature map → LLM selection → expanded prompt → correct answer, with token counts at each step.

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| tree-sitter grammar setup fails or is slow to compile | Blocks all parsing | Use `tree-sitter-languages` (pre-built). Fall back to Python `ast` for .py files. Regex fallback for others. |
| Signature map exceeds context window for very large repos | Can't fit map in one prompt | Truncate to top-level signatures only (no method bodies). Or split by directory and query in stages. Flag this as a known limitation. |
| LLM selects wrong units | Bad expanded prompt | This is inherent to the approach but still better than keyword scoring. Show that even imperfect selection beats full-file inclusion on token count. |
| Name-based edge matching produces false positives | Noisy call edges (e.g., common names like `get`, `run`, `process` match everywhere) | Filter out edges to symbols with very high in-degree (>20 callers). Optionally qualify matches with file-path proximity or class scope. Accept some noise — the LLM can ignore irrelevant edges. |
| Edge annotations bloat the signature map | Reduces the token savings | Cap edge annotations to 5 callers/callees per unit in the signature map. Show `← called by: get_users [12], get_posts [87], ... (+3 more)`. Full edge lists available via expand. |
| File moved AND modified in same commit | Move detection fails, treated as delete + create | This is the correct fallback — the file needs re-parsing anyway since content changed. Unit IDs change but edges rebuild from scratch. Only pure moves (same hash) get the fast path. |
| Hash collision on move detection (two different files with same hash) | Wrong file matched as a move | SHA-256 collisions are astronomically unlikely. As a safety check, only match if exactly one orphaned path maps to one new path with that hash. If multiple candidates exist, treat all as delete + create. |
| SQLite write contention if run in parallel | Index corruption | Single-writer assumption is fine for a single-user Power. Document it. |
| `uv`/`uvx` not installed on user's machine | Power fails to start | POWER.md links to the uv install guide. Fallback: document a `python mcp_server.py` invocation for users who prefer manual setup. |
| Steering file triggers index on every workspace open | Slow startup if repo is large | Steering file checks whether an index already exists and whether any files changed before calling `context_index`. If nothing changed, the call returns in <100ms. |

## 11. Time Budget

| Block | Hours | Deliverable |
|---|---|---|
| Project setup + tree-sitter integration + Python `ast` fallback | 1.5 | Parser that extracts signatures from .py and .js/.ts files |
| Signature extraction logic (functions, classes, methods) | 1.0 | Structured unit data from AST nodes |
| Call edge extraction (name matching, edge table, rebuild logic) | 0.5 | `edges` table populated, rebuild on incremental index |
| SQLite storage + incremental indexing (hash check, move detection, insert/update/delete) | 1.0 | Working indexer core |
| Query formatter — signature map with edges + selection prompt + expansion | 2.0 | Working query + expand logic with edge annotations |
| MCP server + Kiro Power packaging (POWER.md, mcp.json, steering file) | 1.0 | Installable Power with auto-index steering |
| Demo prep — install Power, open real repo, run end-to-end, capture token counts | 0.5 | Demo script and numbers |

**Total: 7.5 hours.** Dropping the standalone CLI saves 0.5h — the MCP server is the entry point, not a wrapper around a CLI.

## 12. File Structure

```
context-lens-power/
├── POWER.md                      # Power description, keywords, usage — shown in Powers panel
├── mcp.json                      # Bundled MCP server config (uvx command, autoApprove)
├── steering/
│   └── context-lens.md           # Auto-included steering: when/how Kiro uses the tools
└── src/
    ├── mcp_server.py             # MCP server entry point — exposes 3 tools
    ├── indexer/
    │   ├── __init__.py
    │   ├── scanner.py            # File walking, filtering, hashing, move detection
    │   ├── parser_treesitter.py  # tree-sitter based extraction
    │   ├── parser_python.py      # Python ast fallback
    │   ├── parser_regex.py       # Regex fallback for unsupported languages
    │   ├── edge_builder.py       # Name-based call edge extraction + rebuild
    │   └── models.py             # Dataclasses for FileInfo, CodeUnit, Edge
    ├── storage/
    │   ├── __init__.py
    │   └── db.py                 # SQLite operations (create, upsert, delete, query, edges)
    └── query/
        ├── __init__.py
        ├── formatter.py          # Signature map builder with edge annotations
        └── expander.py           # Unit ID → full code lookup, neighbor expansion
```
