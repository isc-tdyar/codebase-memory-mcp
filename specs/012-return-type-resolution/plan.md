# Plan: Return Type Resolution (Second Pass)

## Architecture

New pipeline pass `pass_return_types` runs AFTER `pass_calls` completes. It:
1. Queries all Method definition nodes, extracts `return_type` from their properties
2. Builds a lookup table: `ClassName.MethodName → ReturnType`
3. Scans CALLS edges where the callee is a `##class(X).Method()` pattern (not %New/%Open)
4. For each such call, looks up the return type → infers the variable's type
5. Re-scans the same file's unresolved instance_method_calls → emits new CALLS edges

## File Structure

```
src/pipeline/
  pass_return_types.c    — second-pass pipeline: read graph, infer, emit edges
  pass_return_types.h    — pass entry point declaration
internal/cbm/
  extract_defs.c         — (modify) store return_type in properties_json for methods
```

## Implementation Phases

### Phase 1: Store return types during definition extraction
- In `extract_defs.c`, when extracting method definitions for ObjectScript UDL,
  find the `return_type` → `typename` child and store it in `properties_json`
- Format: `"return_type":"ClassName"` added to existing JSON props

### Phase 2: Build return type lookup from graph
- After indexing, query: `SELECT properties_json FROM nodes WHERE label='Method'`
- Parse each node's `return_type` field
- Build hash table: `qualified_callee_name → return_type_string`
- Filter out scalar types (`%String`, `%Integer`, `%Status`, etc.)

### Phase 3: Resolve deferred type assignments
- For each file with ObjectScript code:
  - Find `Set var = ##class(X).Method()` calls where Method ≠ %New/%Open
  - Look up `X.Method` in return type table
  - If found and non-scalar, infer `var` has type = return type
  - Find subsequent `var.OtherMethod()` calls → resolve to `ReturnType.OtherMethod`
  - Emit new CALLS edges

## Performance Budget

- Phase 1: Zero cost (piggybacks on existing extraction)
- Phase 2: ~48K method nodes × JSON parse = ~50ms
- Phase 3: Scan ~13K files × pattern match = ~200ms
- Total: < 500ms additional pipeline time

## Risks

1. Return type not declared (body-inferred only) — we skip these, explicit `As Type` only
2. Polymorphic returns — factory methods returning different subclasses — we use declared type
3. Circular dependencies — A.Method() returns B, B.Method() returns A — one pass is enough
