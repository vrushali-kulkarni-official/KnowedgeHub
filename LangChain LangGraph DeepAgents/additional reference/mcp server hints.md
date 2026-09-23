**These are optional tool annotations (hints) in the Model Context Protocol (MCP).** They appear in a tool’s definition (returned by `tools/list`) and describe the tool’s intended behavior so clients/hosts can make smarter decisions about confirmation dialogs, auto-approval, retries, and risk assessment.

They are **hints only** — not enforceable guarantees. A server can claim anything; clients should treat them as untrusted unless the server itself is trusted. Defaults are deliberately conservative/pessimistic.

### Summary of the four hints

| Hint              | Meaning                                                                 | Default | Main client use |
|-------------------|-------------------------------------------------------------------------|---------|-----------------|
| **readOnlyHint**  | Tool does **not** modify its environment (pure reads/queries/searches) | `false` | Safe to auto-approve / skip confirmation |
| **destructiveHint** | Tool may make irreversible / hard-to-undo changes (vs. purely additive) | `true`  | Show stronger warnings / require confirmation (only relevant when `readOnlyHint` is false) |
| **idempotentHint** | Calling the tool repeatedly with the **same arguments** has no additional effect | `false` | Safe to retry on failure/timeout (only relevant when `readOnlyHint` is false) |
| **openWorldHint** | Tool may interact with an “open world” of external entities (network, web APIs, email, etc.) vs. a closed/local domain | `true`  | Reason about data exfiltration, scrutinize outputs, flag trust-boundary crossings |

There is also an optional human-readable `title` field for UI display.

### Detailed meanings

- **readOnlyHint**  
  `true` → The tool only reads data and has no side effects beyond using compute (e.g., file readers, search, weather lookup, database queries).  
  `false` (or omitted) → The tool may write, create, update, or delete.  
  This is the most important hint for auto-approval UX.

- **destructiveHint**  
  Only meaningful when the tool is **not** read-only.  
  `true` → May perform destructive/irreversible operations (delete, overwrite, etc.).  
  `false` → Only additive/non-destructive changes (create new files, append to logs, upsert, etc.).  
  Clients often use this to escalate the confirmation prompt.

- **idempotentHint**  
  Only meaningful when the tool is **not** read-only.  
  `true` → Calling it multiple times with identical arguments produces the same end state as calling it once (classic examples: “set value”, “upsert”, “delete if exists”).  
  `false` → Repeated calls accumulate effects (append, increment, create-another, etc.).  
  Useful for deciding whether a failed call can be safely retried.

- **openWorldHint**  
  `true` → The tool can reach outside a closed, well-defined domain (web search, external APIs, sending email, etc.).  
  `false` → The tool operates in a closed world (local filesystem within allowed directories, in-memory store, internal database, etc.).  
  Helps clients think about data leaving the environment or untrusted content coming back.

### Example combinations
- Read-only web search → `readOnlyHint: true`, `openWorldHint: true`
- Local file delete → `readOnlyHint: false`, `destructiveHint: true`, `idempotentHint: true`, `openWorldHint: false`
- Append-to-log → `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: false`
- Set a preference / upsert → `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`

These annotations live on the tool definition itself (not on individual call results) so a client can decide *before* invoking the tool.
