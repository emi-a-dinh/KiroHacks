# Kiro Hackathon — Writeup Responses

## 1. Vibe Coding

**How did you structure your conversations with Kiro to build your project?**

The project had two major components — Token Miser (an MCP-based context-selection engine) and a benchmark tool to measure its effectiveness — and I used very different conversation styles for each.

For Token Miser, I started with a long exploratory conversation where I described the problem space: "AI coding agents dump entire repos into context, costing ~180K tokens. I want to build something that indexes a codebase into signatures and call graphs, then surgically selects only the relevant code units for a given task." I iterated on the architecture in chat — two-phase design (signature map → selective expansion), parser cascade (tree-sitter → Python AST → regex fallback), SQLite storage — before asking Kiro to start building. Each subsequent conversation tackled one subsystem: the indexer, the selector algorithm, the MCP server, the CLI.

For the benchmark tool, I switched to spec-driven development (more on that below), but the initial problem framing was still conversational: "Kiro routes through AWS, not Anthropic directly, so I can't get raw token counts. But the event stream has credit usage values that are proportional to tokens. I need a proxy to intercept those."

The most productive pattern was giving Kiro a concrete error or output and asking it to work backward. For example, when the mitmproxy addon wasn't capturing anything, I had Kiro add raw response logging, then pasted the binary event stream output back into chat. Kiro identified the Amazon Event Stream binary format and rewrote the parser to handle it — that was probably the most impressive single generation. It went from "I see binary garbage" to a working struct-based event stream parser in one turn.

**What was the most impressive code generation Kiro helped you with?**

The v2 selector algorithm in `token-miser/src/query/selector.py`. I described six improvements I wanted — fixed camelCase tokenizer, domain alias expansion (20+ alias groups like "auth" → "jwt"/"session"/"permission"), stricter sibling selection, smarter test discovery, coverage-based confidence scoring, and explainable selection with per-unit reasons — and Kiro produced a complete, working rewrite. The alias table alone had 20+ domain groups that were contextually accurate. The coverage-based confidence system (5 weighted signals: target_found, similar_pattern, dependency, test, error_file) replaced my crude top-score threshold and immediately produced better selections.

---

## 2. Agent Hooks

**What specific workflows did you automate with Kiro hooks?**

I set up six hooks that formed an automated development loop:

1. **Token Miser re-index on save/delete** (`miser-reindex-on-save`, `miser-reindex-on-delete`) — Every time I saved or deleted a source file (`.py`, `.ts`, `.js`, `.go`, `.rs`, `.java`, `.rb`), the hook ran `python token-miser/src/cli.py index .` to incrementally update the SQLite index. This meant the MCP tools always had a fresh view of the codebase without me ever running a manual index command.

2. **Context Lens re-index on save** (`auto-reindex-on-save`) — Same pattern for the earlier Context Lens prototype, running `.venv/bin/python cli.py context-index . --quiet`.

3. **Auto-commit on agent stop** (`commit-helper`) — After every agent interaction, this hook checked `git status --porcelain`, staged changes with `git add -A`, inspected the diff, crafted a conventional commit message (feat/fix/refactor/docs/test/chore), and committed. This gave me a granular commit history without ever thinking about it.

4. **Memory consolidator** (`memory-consolidator`) — Also fires on `agentStop`. It reviewed what happened in the session and appended a structured summary to `.kiro/memory.md` with sections for what changed, decisions made, issues encountered, and open items. This created a persistent project journal that survived context window resets.

5. **Run tests after spec task** (`test-after-task`) — After each spec task was marked complete, this hook ran `pytest tests/ -x -q` in fast-fail mode. This caught regressions immediately during the benchmark tool's spec-driven implementation.

**How did these hooks improve your development process?**

The re-index hooks were the backbone of the Token Miser workflow. Without them, every `miser_fix` or `miser_ask` call would have operated on a stale index. With them, the index was always current — I'd save a file, and the next MCP tool call would already see the changes.

The memory consolidator was unexpectedly valuable. The project spanned a full day of intense development across many conversations. When context got compacted or I started a new chat, `.kiro/memory.md` had the full history: what was tried, what failed, what decisions were made. The entry about "MCP server fails through proxy — need NO_PROXY=localhost,127.0.0.1" saved me from re-debugging the same issue twice.

The auto-commit hook created 30+ granular commits over the day. Each one had a meaningful message generated from the actual diff. When I needed to reset `flask_project/src/flask/app.py` to its buggy state between benchmark runs, I could `git checkout` confidently because every intermediate state was committed.

---

## 3. Spec-Driven Development

**How did you structure your spec for Kiro to implement?**

I used specs for the benchmark tool — a complex, multi-module system with strict correctness requirements. The spec had three layers:

**Requirements** (`requirements.md`) — 7 requirements for the initial benchmark tool (session script generation, proxy interception, run orchestration, usage measurement, results storage, comparison report, run configuration), each with numbered acceptance criteria. Later, I added a second spec for automated benchmark testing with 10 requirements covering the automation driver, power management, prompt delivery, response detection, and error recovery.

**Design** (`design.md`) — System architecture diagrams, component interfaces with method signatures, data model definitions (dataclasses with field types), algorithm pseudocode (session script generation, proxy interception flow, run orchestration state machine), and a property-based test strategy mapping each correctness property to a Hypothesis test.

**Tasks** (`tasks.md`) — Ordered implementation tasks with explicit dependencies. Each task referenced specific requirements for traceability. Checkpoints between major phases ensured tests passed before moving on. Optional tasks (property-based tests) were marked with `*` for faster MVP.

The key structural decision was including **correctness properties** in the design doc — formal statements like "For any RunRecord r, sum(turn.total for turns in session) == session.total" — that mapped directly to Hypothesis property-based tests. This gave Kiro unambiguous acceptance criteria.

**How did the spec-driven approach improve your development process?**

The benchmark tool had 7 modules, 15+ dataclasses, and complex interactions (proxy subprocess management, binary event stream parsing, multi-run orchestration). Without the spec, I would have been constantly re-explaining context. With it, each task was self-contained: Kiro could read the task, check the design doc for the interface, and implement it correctly.

The `postTaskExecution` hook running pytest after each task caught issues early. When Task 4 (proxy interception) broke a model assumption from Task 1, the test failure surfaced immediately rather than compounding.

**How did this compare to vibe coding?**

Vibe coding was faster for exploratory work — the Token Miser core (indexer, selector, MCP server) came together in a few long conversations. But it required me to hold the full architecture in my head and course-correct when Kiro drifted.

Spec-driven was slower to start (writing requirements and design took real effort) but paid off for the benchmark tool's complexity. The automated benchmark testing spec had 10 requirements, 12 correctness properties, and touched 5 files — that's the kind of scope where vibe coding would have produced inconsistencies. The spec kept everything aligned.

My takeaway: vibe code the prototype, spec the production system.

---

## 4. Steering Docs

**How did you leverage steering to improve Kiro's responses?**

I had two steering files:

1. **`token-miser.md`** (auto-included) — This was the most impactful. It contained strict rules: "NEVER use Read file(s), Searched workspace, or any native file reading tool. NEVER read line ranges directly. NEVER search the workspace for symbols — use miser_context instead." It defined the only allowed sequence: `miser_context` → `miser_read` → make the edit. And it included a fallback: "If Token Miser tools are not available, stop and tell the user."

2. **`caveman-integration.md`** (manual inclusion) — A detailed integration plan for compressing Token Miser's output format using the caveman compression library. This was a future roadmap document that I could pull into context when working on that specific feature, without it cluttering every conversation.

**Was there a particular strategy that made the biggest difference?**

The `inclusion: auto` on the Token Miser steering file was critical. Without it, Kiro would default to its native file-reading tools, bypassing the MCP power entirely. The steering file essentially rewired Kiro's behavior: instead of `readFile` → edit, it became `miser_context` → `miser_read` → edit. This was the mechanism that made Token Miser actually get used.

The negative rules ("NEVER use Read file(s)") were more effective than positive rules alone. Kiro has strong defaults toward its built-in tools, and the steering file had to explicitly override those defaults. Without the "NEVER" rules, Kiro would occasionally fall back to native reads, especially for quick lookups.

The manual inclusion strategy for `caveman-integration.md` was also a good pattern. It was a 200-line document with detailed before/after examples and token budget tables. Auto-including it would have wasted context on every conversation. Manual inclusion meant it was available when needed but invisible otherwise.

---

## 5. MCP

**How did extending Kiro's capabilities help you build your project?**

Token Miser is itself an MCP server — the entire project is an MCP extension for Kiro. It exposes three tools:

- **`miser_context`** — Takes a task description, indexes the repo (incrementally), runs the multi-signal selector (token matching, intent detection, call graph traversal, test inclusion), and returns signatures of the most relevant code units.
- **`miser_read`** — Takes a symbol name and returns its full source code. Used after `miser_context` to expand specific units the agent needs to edit or understand.

These replaced Kiro's default behavior of reading entire files. Instead of dumping 180K tokens of raw source, the agent gets ~15K tokens of targeted context: signatures for orientation, full source only for the units it needs.

**What sort of features or workflow improvements did MCP enable that otherwise would have been difficult or impossible?**

Three things MCP made possible that couldn't be done with steering alone:

1. **Persistent state across conversations.** The SQLite index at `.token-miser/index.db` persists between conversations. The first call indexes the repo; subsequent calls are incremental (only re-parsing changed files, detected via SHA-256 hashes). This is impossible with steering files, which are stateless text.

2. **Algorithmic context selection.** The selector uses token matching with alias expansion, call graph traversal, intent detection, and coverage-based confidence scoring. This is computation that needs to run as code, not instructions in a prompt. MCP let me put that logic in Python and expose the result as a tool.

3. **Call graph awareness.** When the agent asks about a function, Token Miser doesn't just return that function — it follows the call graph to include callers and callees. If you ask about `dispatch_request`, you also get `ensure_sync`, `full_dispatch_request`, and the route handlers that call it. This graph traversal is what makes the context selection "surgical" rather than keyword-based.

The benchmark results showed that on a Flask-sized project (~15K lines), the Power actually costs more tokens than baseline — the multi-step MCP flow (index → query → expand) adds overhead that exceeds the savings on a small codebase. But the qualitative benefit was clear: the Power consistently identified the right files and functions, while baseline Kiro sometimes wandered. The Power's value scales with project size — on a 100K+ line codebase where full-file reads push context to 50%+, the 10-15x reduction target becomes achievable.
