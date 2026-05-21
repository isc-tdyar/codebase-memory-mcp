# Spec: Macro Conditional Guard Edges

**Feature**: 022-macro-guard-edges  
**Created**: 2026-05-21  
**Priority**: P2 — caused missed answer in Michael's V3 benchmark Q7  
**Source**: Michael's V3 Q7: "Under what condition is the hub-validator trigger enforced?"

---

## Problem

Feature 011 added `$$$Macro` to `call_node_types` — when a macro expands to a
method call, we emit a CALLS edge. But we don't track when a macro appears as a
**conditional guard**: `If ($$$InAContainer) { ... }`.

The V3 Q7 answer: the validator trigger only fires inside containers because the
entire body is wrapped in `If ($$$InAContainer) { ... }`. A model querying the graph
sees the CALLS edges inside the if-block but has no way to know they're conditional.
It reports the trigger fires unconditionally — wrong.

## What exists today

`$$$InAContainer` currently emits a CALLS edge to `%SYSTEM.Process.IsContainer` (or
similar). There is no edge type for "this call only happens when X macro is true".

## Scope

### In scope
- Detect `If ($$$MacroName) { ... }` pattern in method/trigger bodies
- Emit a `GUARDED_BY` edge: Method/Trigger node → Macro node
- The macro name becomes a queryable annotation on the code block
- Most valuable macros: `$$$InAContainer`, `$$$IsEnsemble`, `$$$ISOK`, `$$$ISERR`

### Out of scope
- Full conditional branch coverage (too complex, too noisy)
- Nested conditions more than 1 level deep
- `While`, `For` guards — only `If` at the outermost method/trigger scope
- Guard semantics (we store the guard name, not its logical meaning)

## User Scenarios

### US1 — Find deployment-conditional code (V3 Q7)
Query:
```cypher
MATCH (t:Trigger {name:'ValidateNotAuditRepo'})-[:GUARDED_BY]->(m)
RETURN m.name
```
Returns: `InAContainer` → "this trigger only fires in containerized deployments"

### US2 — Find all code paths gated on container deployment
```cypher
MATCH (n)-[:GUARDED_BY]->(m {name:'InAContainer'})
RETURN n.qualified_name, labels(n)
```
Returns: all methods and triggers that only execute in containers

### US3 — Find methods with no guard (unconditional execution)
```cypher
MATCH (m:Method) WHERE NOT EXISTS ((m)-[:GUARDED_BY]->())
AND m.qualified_name CONTAINS 'Validate'
RETURN m.qualified_name
```

## Acceptance Criteria

1. `HS.Util.Installer.Hub::ValidateNotAuditRepo` trigger has `GUARDED_BY` edge to
   an `InAContainer` macro node
2. Query US1 returns `InAContainer`
3. A method with no `If ($$$X)` guard has no `GUARDED_BY` edges
4. Non-macro `If` conditions (e.g., `If x > 0`) do NOT generate GUARDED_BY edges
5. No regression on existing CALLS edges from macro expansion

## Implementation

In `extract_unified.c`, extend `handle_objectscript_type_map` (or add a new handler
`handle_objectscript_guards`) to detect:

```
command_if
  └── expression / predicate
      └── macro { text = "$$$InAContainer" }
```

When the topmost `If` condition of a method body contains only a `macro` node (no
other conditions), emit a guard annotation: store `$$$MacroName` stripped of `$$$`
as a `GUARDED_BY` edge target.

Implementation: in `extract_unified.c`, when walking `command_if` nodes:
1. Check if the condition is a single `macro` node
2. If yes, record `guard_macro_name = strdup(macro_text + 3)` (strip `$$$`)
3. In `handle_calls`, when emitting edges within that `command_if` body,
   also emit a `GUARDED_BY` call from the enclosing function to the macro name

Alternative simpler approach: just store `guard_macros` as a space-separated string
in `properties_json` of the Method/Trigger node. Avoids a new edge type.
`"guard_macros":"InAContainer IsEnsemble"` → queryable with `CONTAINS`.
This is P2 — the simpler approach is preferred.

## Note on Prioritization

This is P2 because the V3 hint arm missed Q7 due to over-relying on the graph.
The guard information is answerable by reading the source (3 lines). The graph
enhancement removes the need to read the file — but it's not a hallucination trap
like Q1-Q3. Implement after 019-021.
