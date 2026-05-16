# Spec: Cross-Class DATA_FLOWS Edges

**Feature**: 013-cross-class-data-flows
**Created**: 2026-05-16
**Priority**: P2 — enables impact analysis
**References**: Depends on 010 (resolved CALLS), uses existing DATA_FLOWS infrastructure

---

## Problem

CBM already produces `DATA_FLOWS` edges for some languages (Go, TypeScript) that
track argument-to-parameter binding. ObjectScript has none. When a developer asks
"if I change this parameter's format, what breaks?" — the answer requires knowing
which callers pass data into that parameter.

Example:
```objectscript
Do adapter.ExecuteQuery(mySql)
```
After 010, we know this calls `EnsLib.SQL.OutboundAdapter.ExecuteQuery`. But we
don't track that `mySql` flows into ExecuteQuery's first parameter. DATA_FLOWS
would give us: `Run.mySql → ExecuteQuery.pQuery` (arg position 0).

## Scope

### In scope:
1. For resolved CALLS edges in ObjectScript, emit DATA_FLOWS edges from each
   actual argument expression to the callee's formal parameter (by position)
2. Track variable names at call sites (what flows in)
3. Support both positional args and named args (rare in ObjectScript)

### Out of scope:
- Intra-method data flow (tracking `Set x = y` chains within a method)
- Cross-method return value flow (caller receives return → uses it)
- Global variable flow (`Set ^Temp = x` → read elsewhere)
- Side-effect tracking (method mutates ByRef parameter)

## User Scenarios

### US1 — Argument to parameter binding (P1)
```objectscript
Method Run() {
    Set sql = "SELECT * FROM Patient"
    Do ..Adapter.ExecuteQuery(sql)
}
```
Produces: `DATA_FLOWS` edge from `Run` to `ExecuteQuery` with `args: ["sql→pQuery"]`
(or positional: `args: ["0:sql"]`).

### US2 — Multiple arguments (P1)
```objectscript
Do ##class(MyApp.Utils).Transform(input, output, "JSON")
```
Produces: `DATA_FLOWS` with `args: ["0:input", "1:output", "2:\"JSON\""]`

### US3 — Impact query (P1)
A developer wants to know: "what data flows into ExecuteQuery's first parameter?"
```cypher
MATCH (caller)-[d:DATA_FLOWS]->(callee)
WHERE callee.name = 'ExecuteQuery'
RETURN caller.name, d.args
```

## Acceptance Criteria

1. Resolved ObjectScript CALLS edges produce companion DATA_FLOWS edges
2. Argument position is tracked (0-indexed)
3. Variable names (not just positions) are captured in edge properties
4. Literal arguments are captured as-is (quoted strings, numbers)
5. ≥ 10,000 DATA_FLOWS edges on hscm depot (proportional to CALLS)
6. Query works: `MATCH ()-[d:DATA_FLOWS]->() WHERE d.args CONTAINS 'varname' RETURN ...`

## Technical Approach

The existing `extract_call_args()` function in `extract_calls.c` already extracts
argument text for some languages. For ObjectScript, extend it to:
1. Walk the `method_args` child of the call node
2. Extract each positional argument's text
3. Store in `CBMCall.args` (already exists — `call_arg_t` array)

The pipeline's `pass_calls` already writes args to edge properties when present.
The work is primarily in making `extract_call_args` handle ObjectScript's
`method_args` → `bracket` → expressions structure.

## Edge Properties

```json
{
  "type": "DATA_FLOWS",
  "from": "caller_qn",
  "to": "callee_qn",
  "args": "0:sql,1:timeout",
  "arg_count": 2
}
```
