# Spec: Return Type Resolution (Second Pass)

**Feature**: 012-return-type-resolution
**Created**: 2026-05-16
**Priority**: P2 — incremental improvement over 010
**References**: Depends on 010 (type inference), builds on existing CALLS edges

---

## Problem

Feature 010 resolves types from `%New()`, parameters, and properties. But this
pattern remains unresolved:

```objectscript
Set result = ##class(MyApp.Service).GetAdapter()
Do result.Execute()  // What type is result?
```

`GetAdapter()` returns `EnsLib.SQL.OutboundAdapter` (declared in its `As` clause),
but CBM doesn't know that because the return type lives in a different class's
definition — possibly in a different file.

## Scope

### In scope:
1. After all files are indexed and CALLS edges exist, run a second pass
2. For each unresolved `instance_method_call` (variable with no type in the map):
   - Check if there's a `Set var = ##class(X).Method()` where Method is NOT `%New/%Open`
   - Look up `X.Method` in the graph → find its definition node → read `return_type` from properties
   - If return type found, resolve `var.OtherMethod()` to `ReturnType.OtherMethod`
3. Store return type info in method definition nodes' `properties_json`

### Out of scope:
- Chained returns (`a.Get().Transform().Send()` — multiple hops)
- Runtime-dependent return types (polymorphic dispatch)
- Return types not declared in source (inferred from body)

## User Scenarios

### US1 — Factory method return type (P1)
```objectscript
Set adapter = ##class(Ens.Host).GetAdapter()
Do adapter.ExecuteQuery("SELECT 1")
```
After indexing: `GetAdapter` definition node has `return_type: "EnsLib.SQL.OutboundAdapter"`.
Second pass resolves `adapter.ExecuteQuery` → `EnsLib.SQL.OutboundAdapter.ExecuteQuery`.

### US2 — Static method with typed return (P2)
```objectscript
Set obj = ##class(%SYSTEM.Status).OK()  // returns %Status (scalar, not object)
```
`%Status` is a scalar type — no instance methods. No CALLS edge should be emitted.
The system must recognize scalar types and skip them.

## Acceptance Criteria

1. Method definition nodes include `return_type` in properties_json when declared
2. Second pass resolves ≥ 500 additional CALLS edges on hscm depot
3. No false positives for scalar return types (`%String`, `%Integer`, `%Status`, `%Boolean`)
4. Second pass runs in < 2 seconds for 48K method nodes
5. No regression on existing type inference (010 tests still pass)

## Technical Approach

**Phase 1**: During definition extraction (pass_definitions), store `return_type`
in method node `properties_json` by parsing the `return_type` → `typename` child.

**Phase 2**: New pipeline pass `pass_return_types` runs after `pass_calls`:
- Query all method definition nodes with non-null `return_type`
- Build a lookup table: `ClassName.MethodName → ReturnType`
- For each `Set var = ##class(X).Method()` call where Method is NOT %New/%Open:
  - Look up `X.Method` → get return type
  - Add to a "deferred type map" for that file
- Re-resolve unresolved instance_method_call nodes using the deferred map
- Emit additional CALLS edges

## Scalar Types (No Object Methods)

These return types should NOT generate instance method CALLS:
`%String`, `%Integer`, `%Float`, `%Double`, `%Boolean`, `%Status`,
`%Numeric`, `%Date`, `%Time`, `%TimeStamp`, `%Binary`, `%Text`
