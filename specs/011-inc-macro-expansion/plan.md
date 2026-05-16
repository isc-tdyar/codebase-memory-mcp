# Plan: .inc Macro Expansion

## Architecture

New pipeline pass `pass_inc_macros` runs BEFORE `pass_calls` (between `pass_definitions` and the parallel extract phase). It:
1. Discovers `.inc` files in the repo
2. Parses `#define` directives into a macro table
3. Resolves `Include` directives in `.cls` files to determine which macros apply
4. The macro table is attached to `CBMExtractCtx` so `handle_calls` can expand `$$$Macro` invocations

## File Structure

```
internal/cbm/
  macro_table.h          — CBMMacroEntry, CBMMacroTable structs + API
  macro_table.c          — parse_inc_file(), expand_macro(), system_macro_table[]
src/pipeline/
  pass_inc_macros.c      — pipeline pass: discover .inc, parse, attach to ctx
```

## Implementation Phases

### Phase 1: Macro table data structure
- `CBMMacroEntry`: `{name, param_count, param_names[], expansion_text}`
- `CBMMacroTable`: flat array, max 4096 entries, arena-allocated
- System macro table: hardcoded ~20 entries for `%occStatus`/`%occErrors`

### Phase 2: .inc file parser
- Line-by-line: skip `ROUTINE` header, skip `#;` comments
- Parse `#define Name expansion` (no-arg) and `#define Name(%a,%b) expansion` (with args)
- Store in `CBMMacroTable`

### Phase 3: Include resolution
- During file discovery (or early in extraction), scan `.cls` files for `Include` directives
- Map `Include HSCM.Config.Include` → find `HSCM/Config/Include.inc` or `HSCM.Config.Include.inc`
- Build per-file include chain (transitive: if A includes B which includes C)

### Phase 4: Macro expansion in call extraction
- In `extract_callee_lang_specific`, when we have a `macro` node with `$$$Name(args)`:
  - Look up `Name` in the macro table
  - Substitute args positionally
  - If expansion contains `##class(X).Method(...)`, emit that as the callee
  - If expansion is a literal or intrinsic (`$get`, `$select`), emit nothing (correct)

## Performance Budget

- .inc file parsing: ~210 files × ~50 lines each = ~10K lines, trivial
- Macro table lookup: linear scan of ~500 entries per call site (worst case 50µs)
- Total pass time target: < 100ms on hscm depot

## Risks

1. Self-referential macros: `$$$A` uses `$$$B` — need table fully populated before expansion
2. Conditional compilation: `#if` guards — we ignore them (treat all defines as active)
3. Missing system .inc files — hardcoded table covers the critical ones
