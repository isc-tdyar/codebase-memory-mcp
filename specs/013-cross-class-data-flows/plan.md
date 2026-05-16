# Plan: Cross-Class DATA_FLOWS Edges

## Architecture

Extends the existing CALLS extraction in `handle_calls` (extract_calls.c). When an
ObjectScript `instance_method_call` or `class_method_call` is resolved to a callee,
also extract the argument expressions and emit them as `CBMCallArg` entries. The
existing pipeline (`pass_calls.c` → `pass_route_nodes.c`) already knows how to write
DATA_FLOWS edges from call args — we just need ObjectScript to populate `call.args[]`.

## File Structure

```
internal/cbm/
  extract_calls.c        — (modify) add ObjectScript arg extraction in handle_calls
src/pipeline/
  pass_calls.c           — (modify) emit DATA_FLOWS for ObjectScript calls with args
```

## Implementation Phases

### Phase 1: Extract ObjectScript call arguments
- In `handle_calls`, after resolving an ObjectScript callee (static or type-inferred):
  - Find the `method_args` child of the call node
  - Walk its children (skipping brackets), extract each argument expression text
  - Populate `call.args[0..N]` with `{expr, index}`

### Phase 2: Emit DATA_FLOWS edges in pass_calls
- Already exists for HTTP routes. Extend: if a CALLS edge has `arg_count > 0`,
  also emit a DATA_FLOWS edge with `args` property containing the mapping
- Format: `"0:varName,1:literal,2:expr"` (matches existing convention)

### Phase 3: Callee parameter name resolution (optional enrichment)
- If the callee's definition node exists in the graph with `properties_json`
  containing parameter names, enrich the DATA_FLOWS edge:
  `"0:sql→pQuery,1:timeout→pTimeout"`
- This is best-effort — if callee params unknown, just use positional indices

## Performance Budget

- Phase 1: Zero additional passes — piggybacks on existing extraction
- Phase 2: One additional edge per CALLS edge with args (~45K edges) = ~50ms write time
- Phase 3: One graph query to load param names = ~20ms
- Total: < 100ms additional

## Key Insight

ObjectScript method_args structure in the UDL grammar:
```
(method_args
  (bracket)          — opening paren
  (expression ...)   — arg 0
  (expression ...)   — arg 1
  (bracket))         — closing paren
```

Filter out `bracket` nodes, keep `expression` nodes → those are the positional args.
