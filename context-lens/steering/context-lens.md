---
inclusion: auto
---

# Context Lens — Usage Guidelines

When working with code in a repository, use Context Lens to minimize token usage:

1. **Index first.** Call `context_index` with the workspace root path if:
   - No index exists yet (`.context-lens/index.db` is missing)
   - The user explicitly asks to re-index
   - You suspect files have changed significantly since the last index

2. **Query for tasks.** When the user describes a task involving code (fixing a bug, 
   adding a feature, understanding a function), call `context_query` with the task 
   description to get the signature map. This shows every function and class with 
   their call relationships.

3. **Expand selectively.** Review the signature map and call `context_expand` with 
   only the most relevant unit IDs. Use `include_neighbors: true` if the task 
   involves tracing a bug through multiple functions or understanding how a 
   function is used.

4. **Avoid full file reads.** Use the expanded code as context for your response. 
   Do not read full files unless the signature map indicates the entire file is 
   relevant or the user explicitly asks for it.

This keeps token usage low and responses fast. A typical task needs 10-15k tokens 
of context instead of 150-200k.
