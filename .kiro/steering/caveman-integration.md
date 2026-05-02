---
inclusion: manual
---

# Scope: Caveman Integration

## Goal

Integrate [caveman](https://github.com/juliusbrussee/caveman) with Context Lens to compress tokens on **both sides** of every LLM call:

| Layer | Tool | What it compresses | Savings |
|---|---|---|---|
| Input context | Context Lens | Sends signatures instead of full files | ~10–15x fewer tokens |
| Input context | caveman-compress | Compresses steering/memory files (README, CLAUDE.md, etc.) | ~46% |
| Output | caveman skill | Agent responds in compressed caveman-speak | ~65–75% |
| MCP tool descriptions | caveman-shrink | Compresses MCP tool/prompt/resource descriptions | varies |

Combined effect: a task that would cost ~180k tokens naive could realistically land under 5k.

---

## What Caveman Provides (relevant pieces)

- **caveman skill** — steering/system-prompt plugin that makes the agent respond tersely. Install: `npx skills add JuliusBrussee/caveman`. Trigger: `/caveman` or `"caveman mode"`. Levels: lite / full / ultra.
- **caveman-compress** — CLI that rewrites a context file (e.g. `CLAUDE.md`, steering `.md` files) into caveman-speak. Preserves code, URLs, paths byte-for-byte. Saves backup as `<file>.original.md`. Usage: `/caveman:compress <file>`.
- **caveman-shrink** — MCP stdio proxy that intercepts `tools/list` / `prompts/list` / `resources/list` and compresses description fields. Auto-registered by the installer. Wraps any MCP server including the Context Lens MCP server.

---

## Integration Tasks

### 1. Compress the Context Lens MCP tool descriptions

The three MCP tools (`context_index`, `context_query`, `context_expand`) have verbose `description` fields in `mcp_server.py`. Run caveman-compress on the descriptions or manually rewrite them in caveman-speak.

**Before:**
```python
"description": "Index a code repository. Parses source files, extracts function/class signatures, and stores them in a local SQLite database for fast querying. Supports incremental updates — only re-parses files that changed since last index."
```

**After (target):**
```python
"description": "Index repo. Parse files → extract signatures → store SQLite. Incremental: skip unchanged files."
```

Apply to all three tool descriptions and all parameter `description` fields in `mcp_server.py`.

### 2. Compress the signature map output format

The `query/formatter.py` signature map is the primary input token cost. Apply caveman-style compression to the static text scaffolding (headers, instructions, labels) while keeping symbol names, types, and line numbers exact.

**Before:**
```
## Repository Signature Map (1847 units, 623 call edges, across 312 files)

### api/routes.py
  [12] def get_users(page: int, page_size: int) -> Response        (lines 30–58)
       → calls: paginate [45], get_total_pages [46]
       ← called by: UserRouter.handle_request [14]

## Instruction
Select up to 10 unit IDs whose full source code is needed to complete the task.
The → and ← annotations show call relationships. Consider including callers and
callees of your selected units if they are relevant to the task.
```

**After (target):**
```
## Sig map (1847u 623e 312f)

### api/routes.py
[12] get_users(page:int,page_size:int)->Response L30-58 →[45,46] ←[14]

## Pick up to 10 IDs. →=calls ←=calledby. Include neighbors if relevant.
```

This alone can cut the signature map from ~8k tokens to ~3–4k for a 300-file repo.

### 3. Compress the expanded prompt scaffolding

In `query/expander.py`, the expanded prompt wraps each code unit with verbose headers and comments. Compress the static scaffolding; keep the actual source code untouched.

**Before:**
```
### api/pagination.py — paginate (lines 5–22)
# Called by: get_users [12], get_posts [87]
# Calls: (none)
```

**After:**
```
### api/pagination.py:paginate L5-22
# ←[12,87] →[]
```

### 4. Compress the selection prompt instruction block

The instruction text sent to the LLM in phase 1 of `context-query` is verbose. Rewrite it in caveman-speak.

**Before:**
```
Select up to K functions/methods whose full source code you need to see to complete this task. Return their unit_ids.
```

**After:**
```
Pick ≤K unit IDs need full code. Return list.
```

### 5. Wrap the Context Lens MCP server with caveman-shrink

When registering the MCP server in `.kiro/settings/mcp.json`, wrap it through `caveman-shrink` so description fields are compressed at the protocol level automatically.

**Before:**
```json
{
  "mcpServers": {
    "context-lens": {
      "command": "python",
      "args": ["/path/to/mcp_server.py"]
    }
  }
}
```

**After:**
```json
{
  "mcpServers": {
    "context-lens": {
      "command": "npx",
      "args": ["caveman-shrink", "python", "/path/to/mcp_server.py"]
    }
  }
}
```

### 6. Compress steering/memory files with caveman-compress

After the project's `README.md` and any `CLAUDE.md` / steering files are written, run:

```bash
/caveman:compress README.md
/caveman:compress CLAUDE.md
```

This cuts ~46% of input tokens on every session start where these files are loaded into context. Backups are saved automatically as `README.md.original.md`.

---

## Token Budget: Before vs After Integration

| Stage | Naive | Context Lens only | + Caveman |
|---|---|---|---|
| Input: full repo | ~180,000 | — | — |
| Input: signature map | — | ~8,000 | ~3,500 |
| Input: expanded units (10) | — | ~4,000 | ~4,000 (code unchanged) |
| Input: steering/README | ~2,000 | ~2,000 | ~1,100 |
| Output: agent response | ~1,200 | ~1,200 | ~300 |
| **Total** | **~183,000** | **~15,000** | **~9,000** |

~20x reduction end-to-end vs naive. Context Lens does the heavy lifting on input; caveman handles output and scaffolding.

---

## Implementation Notes

- Code bodies in `full_code` must **never** be compressed — only static scaffolding text (headers, labels, instructions).
- Symbol names, type annotations, line numbers, file paths must be preserved exactly.
- caveman-shrink wraps at the MCP protocol layer — no changes needed to `mcp_server.py` tool logic.
- The caveman skill affects agent output only — it does not change how Context Lens formats its prompts. Both are independent and additive.
- Test token counts before/after each change using `tiktoken` or the Claude API's usage response.
