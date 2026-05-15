# Feature Specification: ObjectScript CALLS Edges — .INT Parsing + Macro Resolution

**Feature Branch**: `005-objectscript-calls-deep`
**Created**: 2026-05-15
**Status**: Draft
**Depends on**: 004-objectscript-calls-static (baseline CALLS infrastructure)

---

## Context

Feature 004 delivers ~55% CALLS coverage via tree-sitter static analysis. The
remaining ~45% consists of two distinct gaps:

**Gap A: `$$$` macro calls (~25%)**
`$$$ISERR(sc)`, `$$$ThrowStatus(e)`, `$$$ERROR(code)` — these are the most common
"function calls" in Ensemble code (25,403 invocations across 75% of uncleaned-code).
They expand to ObjectScript expressions via `.inc` include files. Without resolving
them, the call graph is incomplete for all Ensemble production code.

**Gap B: Dynamic dispatch via `.INT` (~15% additional)**
IRIS compiles `.cls` files to `.INT` intermediate routines. `.INT` files contain:
- All macro expansions already substituted
- Inherited method bodies inlined
- `$classmethod(varName, "MethodName")` calls where varName is sometimes a literal
  string that tree-sitter could not see in the `.cls` source

These two gaps require different infrastructure:
- Gap A: `.inc` preprocessor + macro expansion table
- Gap B: A grammar for `.INT` format OR using `%Dictionary` to read `.INT` text

---

## User Scenarios & Testing

### User Story 1 — Macro call resolution (Priority: P1)

A developer sees `$$$ISERR(sc)` throughout Ensemble code and wants to understand
the dependency chain. After this feature, `$$$ISERR` resolves to the ObjectScript
expression `$$$ISERR` expands to, and the underlying function call (if any) is
tracked. At minimum, the macro name itself appears in the call graph so text search
works.

**Acceptance Scenarios**:
1. `MATCH (m:Method)-[:CALLS]->(t {name:'ISERR'}) RETURN m.name` returns methods
   that invoke `$$$ISERR`.
2. `$$$ThrowStatus(sc)` resolves to a CALLS edge to `%SYSTEM.Error.ThrowStatus`
   (or equivalent) when the `.inc` expansion is known.
3. On uncleaned-code (75% macro-heavy): total CALLS edges increase by ≥ 10,000
   vs feature 004 baseline.

---

### User Story 2 — .INT file CALLS extraction (Priority: P2)

IRIS instances that have code compiled but no `.cls` source (customer installations)
can still have call graphs extracted from `.INT` files. After this feature,
`index_repository` with `.int` files in scope extracts CALLS edges from the
compiled intermediate representation.

**Acceptance Scenarios**:
1. An `.int` file from a compiled class produces CALLS edges equivalent to what
   `.cls` source analysis would produce (validated against a known class).
2. `$classmethod("ClassName", "MethodName")` in `.int` files where both args are
   string literals produces a CALLS edge.
3. Dynamic `$classmethod(varName, ...)` where varName is a variable produces no
   CALLS edge and no crash.

---

### Edge Cases

- `.inc` file not available: skip macro resolution for that macro, no crash.
- Recursive macro expansion: limit expansion depth to 3 levels.
- `.INT` file format varies by IRIS version: handle both old (label+routine) and
  new (UDL-compiled with `#; Generated from ClassName.cls`) formats.
- `$$$OK`, `$$$YES`, `$$$NO` (constant macros, not function calls): skip as they
  resolve to literal values, not calls.

---

## Requirements

### Functional Requirements

**Gap A — Macro resolution**:
- **FR-001**: The indexer MUST parse `.inc` files in the repository to build a
  macro expansion table: `{MacroName → expansion text}`.
- **FR-002**: During call extraction, `macro` AST nodes in method bodies MUST be
  looked up in the expansion table and the expanded call target (if a function call)
  extracted as a CALLS edge.
- **FR-003**: Macro names that expand to non-call expressions (literals, conditions)
  MUST be silently skipped — no error.
- **FR-004**: When no `.inc` files are present, macro resolution is skipped entirely
  — no error, Tier 1/2 calls from feature 004 still appear.

**Gap B — .INT parsing**:
- **FR-005**: The `objectscript_routine` grammar (already vendored from 001) MUST
  be used to parse `.int` files (same grammar, different extension — already handled).
- **FR-006**: `$classmethod("ClassName", "MethodName")` patterns in `.int` source
  where both arguments are string literals MUST produce a CALLS edge.
- **FR-007**: Variable-argument `$classmethod` MUST be silently skipped.
- **FR-008**: `.INT` extraction MUST deduplicate with `.cls` extraction — if both
  source forms are indexed, CALLS edges from `.cls` take priority and `.int`
  duplicates are not added.

### Performance Requirements

- **PR-001**: `.inc` macro table build MUST complete in < 5 seconds for a typical
  repository (≤ 500 `.inc` files, each ≤ 50KB).
- **PR-002**: Macro lookup per call site MUST be O(1) via hash table.

### Out of Scope

- Full macro preprocessor (C-style `#define` arithmetic, conditionals) — only
  function-call macros are extracted.
- Runtime `$classmethod` where variable is not a string literal.
- XECUTE string analysis (arbitrary dynamic code execution).

---

## Success Criteria

- **SC-001**: On uncleaned-code: total CALLS edges increase from 004 baseline by
  ≥ 10,000 after macro resolution.
- **SC-002**: An `.int` file from a compiled class produces the same CALLS edges
  as its `.cls` source (verified on a known test class).
- **SC-003**: All existing tests pass (zero regressions from 004 baseline).
- **SC-004**: `.inc` macro table build for uncleaned-code (863 macro-heavy files)
  completes in < 30 seconds.

---

## Key Technical Decisions (TBD in research phase)

- **Macro expansion table**: Build during the structure pass, store in `cbm_registry`
  alongside import mappings. Size: ~200 macros per `.inc` file × typical 20 files.
- **`.INT` parsing**: Already handled by `objectscript_routine` grammar (.int is a
  registered extension from feature 001). No new grammar needed — the pass_calls
  infrastructure already handles it if call extraction works for routine files.
- **`$classmethod` pattern**: In the routine grammar, this appears as a
  `class_method_call` or `function_call` node. Verify exact node type from `.int`
  parse output before implementing.

---

## Assumptions

- `.inc` files in the repository follow standard IRIS macro format:
  `#define MACRONAME expression`. Multi-line macros use `##continue`.
- The `objectscript_routine` grammar handles `.int` files correctly (same syntax
  as `.mac` — confirmed from feature 001 extension mapping).
- Macro resolution is best-effort: missing `.inc` files degrade gracefully.
