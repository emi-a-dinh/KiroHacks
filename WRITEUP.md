# Token Miser — Project Writeup

## What It Is

Token Miser is a context-selection engine for AI coding agents. Its core problem: when an agent needs to work on a codebase, naively dumping all source files into the context window costs ~180,000 tokens for a medium-sized repo. Token Miser reduces that to ~9,000 tokens — a ~20x reduction — by indexing the codebase once and then surgically selecting only the code relevant to the current task.

It exposes three MCP tools (`miser_fix`, `miser_ask`, `miser_plan`) that an agent calls instead of reading files directly. The agent describes what it needs in plain English; Token Miser returns the relevant code.

---

## How It Works

### Phase 1: Indexing

When first called on a repo, Token Miser walks the directory tree (skipping `node_modules`, `.git`, `__pycache__`, etc.) and parses every source file it finds. Supported languages: Python, JavaScript/TypeScript, Go, Rust, Java, Ruby, PHP, C/C++.

Each file is parsed into **code units** — individual functions, methods, classes, and constants. The parser pipeline tries three strategies in order:

1. **tree-sitter** — fast, accurate AST parsing for all supported languages
2. **Python AST** — used as a fallback for `.py` files when tree-sitter isn't available
3. **Regex** — last resort, handles edge cases and unusual syntax

After the general parsers run, a supplemental pass extracts **route handlers** (Express/Flask/FastAPI route registrations) and **test functions** that general parsers often miss.

For each code unit, the indexer stores:
- File path, symbol name, type (`function`/`class`/`method`/`constant`)
- Parent class (for methods)
- A compact one-line signature
- Start/end line numbers
- The full source code of the unit

All of this goes into a **SQLite database** at `.token-miser/index.db` in the repo root.

After extracting units, the indexer builds a **call graph** by scanning each unit's source code for references to other indexed symbols. This produces directed edges: `caller_id → callee_id`.

Subsequent runs are **incremental**: files are hashed (SHA-256), and only changed files are re-parsed. Deleted files are removed from the index. Renamed/moved files are detected by matching content hashes and their paths are updated without re-parsing.

The index is kept fresh automatically via **Kiro hooks** — every time a source file is saved or deleted, the CLI re-indexes the affected file.

---

### Phase 2: Selection

When an agent calls `miser_fix`, `miser_ask`, or `miser_plan`, Token Miser runs a multi-signal selection algorithm to pick the most relevant code units (up to K, default 8–15 depending on the command).

The selector scores every unit in the index using several signals:

**Token matching** — The task description is tokenized (stop words removed, camelCase/snake_case split). Each token is matched against symbol names, file paths, and signatures. Exact matches score higher than partial matches. A curated alias table expands terms: `"auth"` also matches `"jwt"`, `"session"`, `"permission"`, etc.

**Intent detection** — The task is classified as read-heavy or write-heavy based on keywords (`get`/`list`/`fetch` vs. `post`/`put`/`delete`/`create`). This boosts route handlers that match the detected HTTP method.

**Call graph neighbors** — Once an initial set of high-scoring units is identified, their direct callers and callees are added to the selection. This ensures the agent sees the full call chain, not just isolated functions.

**Test inclusion** — For `miser_fix` and `miser_plan`, test files matching the selected source files are included automatically.

**Weak selection detection** — If the selection looks thin (fewer than 5 units, no tests, all from one file, no call graph neighbors), a **Nearby Map** is appended: a compact listing of all symbols in the same directories as the selected units. This gives the agent a map to navigate if it needs more context, without dumping full file contents.

---

### Phase 3: Output

The tool returns a structured text block containing:

1. **Task** — the original task description
2. **Error** (if provided) — truncated error log/traceback
3. **Selected Code** — full source of each selected unit, with a header showing file path, symbol name, and line range, plus inline comments listing callers and callees
4. **Nearby Map** (if weak selection) — `file.py: symbol1 symbol2 symbol3` lines for adjacent files
5. **Instructions** — mode-specific directives telling the agent what to do next (implement the fix / answer the question / write a plan)

The agent is instructed not to read additional files after receiving this output. If the context is insufficient, it should say what's missing rather than opening more files.

---

## The Three Commands

| Command | K | Tests | Neighbors | Purpose |
|---|---|---|---|---|
| `miser_fix` | 12 | yes | yes | Bug fix or implementation |
| `miser_ask` | 8 | no | yes | Answer a question about the code |
| `miser_plan` | 15 | yes | yes | Write an implementation plan |

All three auto-index if the database doesn't exist yet, and retry with a fresh index if the selection returns no units.

---

## Token Budget

| Stage | Naive | With Token Miser |
|---|---|---|
| Full repo dump | ~180,000 | — |
| Signature map | — | ~8,000 |
| Expanded units (10) | — | ~4,000 |
| Steering/README | ~2,000 | ~2,000 |
| Agent output | ~1,200 | ~1,200 |
| **Total** | **~183,000** | **~15,000** |

The planned Caveman integration (see `.kiro/steering/caveman-integration.md`) would compress the scaffolding text further, targeting ~9,000 tokens total.

---

## Project Structure

```
token-miser/
  src/
    mcp_server.py        # MCP server — exposes miser_fix, miser_ask, miser_plan
    cli.py               # CLI entry point (miser index / fix / ask / plan / tree)
    indexer/
      core.py            # Orchestrates indexing: scan → parse → store → build edges
      scanner.py         # File system walk, language detection, hash computation
      models.py          # CodeUnit, FileInfo, Edge, IndexResult dataclasses
      parser_python.py   # Python AST parser
      parser_treesitter.py # tree-sitter parser (all languages)
      parser_regex.py    # Regex fallback parser
      parser_routes.py   # Supplemental: route handlers and test functions
      edge_builder.py    # Call graph construction
    storage/
      db.py              # SQLite schema, CRUD, edge queries
    query/
      selector.py        # Multi-signal unit selection algorithm
      smart.py           # run_fix / run_ask / run_plan — combines all phases
      formatter.py       # Signature map builder (used in phase-1 prompts)
      expander.py        # Full-code expander (used in phase-2 prompts)
      tree_view.py       # Tree view for the CLI
.kiro/
  hooks/                 # Auto-reindex on save/delete, memory consolidator, commit helper
  steering/              # Agent instructions (token-miser.md, caveman-integration.md)
  settings/mcp.json      # MCP server registration
```

---

## Key Design Decisions

**SQLite as the index store.** Simple, zero-dependency, fast enough for repos up to tens of thousands of units. The schema stores units, files, edges, and metadata. Incremental updates are handled by hashing files and only re-parsing what changed.

**Parser cascade.** tree-sitter is accurate but requires native binaries. The Python AST fallback handles the most common case. Regex handles everything else. Supplemental parsers layer on top to catch domain-specific patterns (routes, tests) that general parsers miss.

**Selection over retrieval.** Rather than embedding-based semantic search, Token Miser uses deterministic token matching + call graph traversal. This is fast, requires no embedding model, and produces explainable selections. The alias table handles vocabulary mismatch (e.g., `"auth"` → `"jwt"`).

**Nearby Map as a safety valve.** When selection confidence is low, the agent gets a symbol map of adjacent files instead of nothing. This lets it navigate to missing context without reading full files.

**MCP integration.** The three tools are exposed via the MCP protocol, making Token Miser a drop-in context provider for any MCP-compatible agent (Kiro, Claude Desktop, etc.).
