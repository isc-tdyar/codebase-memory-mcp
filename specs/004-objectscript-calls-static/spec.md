# Feature Specification: ObjectScript CALLS Edges — Static Analysis

**Feature Branch**: `004-objectscript-calls-static`
**Created**: 2026-05-15
**Status**: Draft
**Depends on**: 001-objectscript-lang (grammar), 003-iris-dictionary-ingest (FormalSpec)

---

## Context

codebase-memory-mcp currently extracts 28 CALLS edges from a 1,112-class Ensemble
codebase (<3% coverage). The root cause is not the grammar — tree-sitter already
parses `class_method_call`, `instance_method_call`, `routine_tag_call`, and
`superclass_method_call` nodes correctly. The gap is in `extract_unified.c`:
`cbm_extract_call_node()` does not know how to extract the target class/method name
from ObjectScript's positional child structure (no `callee` field name, unlike
JavaScript/Python).

This feature wires ObjectScript call extraction into the existing CALLS pipeline.
It is split into two tiers delivered together:

**Tier 1 — Literal class calls (~40% coverage)**
`##class(HS.FHIRServer.Admin.API).GetParam()` — class name is a literal `class_name`
child of `class_ref`. Directly resolvable without type inference.

**Tier 2 — FormalSpec type resolution (+15% coverage)**
`Set x = ##class(Ens.Director).%New()` then `x.StartProduction()` — variable `x` has
a known type from the parent method call's return type (available from `%Dictionary`
FormalSpec). Requires `%Dictionary` ingest to have run (003).

Combined target: **~55% CALLS coverage** for ObjectScript codebases.
Remaining ~45% (dynamic `$classmethod`, runtime string dispatch) is unresolvable
by static analysis and is explicitly out of scope.

---

## User Scenarios & Testing

### User Story 1 — Literal ##class() call edges (Priority: P1)

A developer queries `MATCH (a)-[:CALLS]->(b) WHERE a.name = 'IndexTypeVector' RETURN b.name`
to find what methods `Indexer.IndexTypeVector()` calls. After this feature, the direct
`##class(X).Method()` calls appear as CALLS edges.

**Acceptance Scenarios**:
1. `MATCH (m:Method {name:'IndexTypeVector'})-[:CALLS]->(t) RETURN t.name` returns
   target method nodes for literal `##class(...)` call sites in the body.
2. A routine `.mac` file with `Do Format^Utils` produces a CALLS edge from the
   calling tag to `Format` in `Utils.mac`.
3. `Do ..Method()` (relative dot call) produces a CALLS edge from the caller to
   `Method` in the same class.
4. On the cleaned-code project (6,004 files), CALLS edges from `.cls` files increase
   from 28 to at least 5,000 (covering all literal ##class() sites).

---

### User Story 2 — FormalSpec type resolution (Priority: P2)

A developer queries call chains through typed variables:
`Set conn = ##class(EnsLib.SQL.OutboundAdapter).%New()` then `conn.ExecuteQuery(...)`.
After this feature, the `conn.ExecuteQuery` call resolves to
`EnsLib.SQL.OutboundAdapter.ExecuteQuery`.

**Acceptance Scenarios**:
1. A method body containing `Set x = ##class(A.B).%New() ... Do x.Foo()` produces
   a CALLS edge to `A.B.Foo` when `A.B` is in the graph.
2. When `%Dictionary` FormalSpec data is not available (003 not run), this tier is
   silently skipped — no error, no crash.
3. At least 500 additional CALLS edges appear on the cleaned-code project vs Tier 1
   alone (validated by before/after count query).

---

### Edge Cases

- `##class(%Persistent).%Save()` — system class not in graph: emit CALLS edge with
  unresolved target (callee_name set, target node not created).
- `##class(@dynamicVar).Method()` — dynamic class name: skip, not resolvable.
- `Do ..Method()` — relative call: resolve to enclosing class (known from enclosing
  Class node in graph).
- `Do method^ROUTINE` — routine tag call: resolve to tag `method` in file `ROUTINE.mac`.
- Multi-chained: `obj.Prop.Method()` — resolve only first segment, mark rest unresolved.
- Empty FormalSpec string: treat as unresolved, no crash.
- Class exists in call but not in graph (external dependency): emit CALLS edge,
  create a stub node for the target class.

---

## Requirements

### Functional Requirements

- **FR-001**: `cbm_extract_call_node()` in `extract_unified.c` MUST extract the
  callee class and method name from `class_method_call` nodes for
  `CBM_LANG_OBJECTSCRIPT_UDL` by reading `class_ref → class_name` (target class)
  and `method_name → identifier` (method name).
- **FR-002**: Routine tag calls (`Do Format^Utils`, `$$Format^Utils`) MUST be
  extracted from `routine_tag_call` nodes for `CBM_LANG_OBJECTSCRIPT_ROUTINE`.
- **FR-003**: Relative dot calls (`Do ..Method()`) MUST be extracted as calls to
  the method on the enclosing class.
- **FR-004**: `instance_method_call` nodes where the receiver type can be resolved
  via `%Dictionary` FormalSpec MUST produce a CALLS edge to the resolved target.
  When type is unresolvable, the call is silently skipped (no stub node, no error).
- **FR-005**: All extracted ObjectScript CALLS edges MUST flow through the existing
  `pass_calls.c` resolution pipeline unchanged — no new pipeline pass needed.
- **FR-006**: All existing CALLS edge tests MUST continue to pass (zero regressions).
- **FR-007**: The feature MUST work without `%Dictionary` ingest (003) — Tier 1
  (literal calls) works standalone; Tier 2 is gated on FormalSpec data being present.

### Performance Requirements

- **PR-001**: CALLS extraction for 6,004 `.cls` files MUST complete within the
  existing `pass_calls` time budget (< 2× current wall-clock time for that pass).
- **PR-002**: FormalSpec lookup (Tier 2) MUST use the in-memory `cbm_gbuf` node
  properties rather than re-querying SQLite per call site.

### Out of Scope

- `$classmethod(dynamicVar, methodName)` — runtime string dispatch: unresolvable.
- `$$$Macro` calls — deferred to 005.
- `.INT` intermediate file parsing — deferred to 005.
- Cross-namespace calls — not tracked.

---

## Success Criteria

- **SC-001**: On cleaned-code (6,004 .cls files, 10,496 methods): `MATCH ()-[:CALLS]->() RETURN count(*)`
  returns ≥ 5,000 after this feature (vs 28 today). Verified by before/after query.
- **SC-002**: `Do Format^Utils` in a `.mac` file produces a resolvable CALLS edge.
- **SC-003**: All existing tests pass (3,553+ passing).
- **SC-004**: `pass_calls` wall-clock time on cleaned-code does not exceed 2× its
  current duration.

---

## Key Technical Decisions

- **Where to add ObjectScript call extraction**: `extract_unified.c` in
  `cbm_extract_call_node()` — same place as ObjC/Swift/Python special cases.
- **call_node_types already registered**: `class_method_call`, `instance_method_call`,
  `routine_tag_call`, `superclass_method_call` are already in the lang_spec.
  The pipeline fires for them — the missing piece is the name extractor.
- **Tier 2 FormalSpec lookup**: After `cbm_gbuf_upsert_node` runs for dictionary
  nodes, `properties_json` contains `"formal_spec":"..."`. Parse this at call
  resolution time to extract the return type of `%New()` / factory methods.

---

## Assumptions

- tree-sitter `class_name` nodes in `class_ref` are leaf aliases (same as in
  `class_definition`) — their text IS the class name. Confirmed from grammar.
- `routine_tag_call` has two named children: the tag name and the routine name
  (separated by `^`). Verify against grammar node-types.json before implementing.
- FormalSpec format from `%Dictionary`: `"paramName As TypeClass"` — the return
  type is the type after `As ` in the last formal spec parameter, or the method's
  `ReturnType` field (simpler: use `ReturnType` from the dictionary ingest).
