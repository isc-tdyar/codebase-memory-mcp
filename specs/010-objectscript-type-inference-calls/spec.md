# Feature Specification: ObjectScript Type Inference for CALLS Edges

**Feature Branch**: `010-objectscript-type-inference-calls`
**Created**: 2026-05-16
**Status**: Draft
**Depends on**: 004 (basic CALLS), 007 (property extraction)

---

## Context

Feature 004 extracts CALLS edges from literal `##class(X).Method()` patterns —
achieving ~45% call-edge-to-method ratio on HealthShare code (1,984 CALLS / 4,409
methods). The remaining ~55% are calls through typed variables, properties, and
return values that LOOK dynamic but are actually statically resolvable because
ObjectScript uses `As <Type>` annotations on all API boundaries.

This feature adds **local type inference** — tracking the declared type of variables
through assignment patterns and resolving `instance_method_call` nodes on typed
receivers. No whole-program analysis, no interprocedural dataflow — just intraprocedural
type tracking within a single method body.

**Coverage target**: ~45% → ~75-80% (only true dynamic dispatch remains unresolvable).

---

## The Four Type Resolution Patterns

### Pattern 1: `%New()` constructor type (highest frequency)
```objectscript
Set adapter = ##class(EnsLib.SQL.OutboundAdapter).%New()
Do adapter.ExecuteQuery(sql)
;; → adapter has type EnsLib.SQL.OutboundAdapter
;; → CALLS edge: current method → EnsLib.SQL.OutboundAdapter.ExecuteQuery
```
**Resolution**: When `Set <var> = ##class(<ClassName>).%New()` is seen, record
`var → ClassName` in a local type map. When `<var>.Method()` is seen later,
resolve to `ClassName.Method`.

### Pattern 2: Method parameter types (from `As` clause)
```objectscript
Method ProcessMessage(request As Ens.Request, adapter As EnsLib.SQL.OutboundAdapter)
{
    Do adapter.ExecuteQuery(sql)
    ;; → adapter declared As EnsLib.SQL.OutboundAdapter
    ;; → CALLS edge: ProcessMessage → EnsLib.SQL.OutboundAdapter.ExecuteQuery
}
```
**Resolution**: Parse method `FormalSpec` (available from tree-sitter `arguments` node
or from `%Dictionary.MethodDefinition.FormalSpec`). Build type map from parameter
declarations at method entry.

### Pattern 3: Property types (from `As` clause)
```objectscript
Property Adapter As EnsLib.SQL.OutboundAdapter;

Method Run()
{
    Do ..Adapter.ExecuteQuery(sql)
    ;; → ..Adapter has type EnsLib.SQL.OutboundAdapter (from Property declaration)
    ;; → CALLS edge: Run → EnsLib.SQL.OutboundAdapter.ExecuteQuery
}
```
**Resolution**: For `..PropertyName.Method()` calls, look up the Property's type
from the class's Variable nodes (already extracted by 007). The type is in the
`prop_type` field of `properties_json`.

### Pattern 4: Return type from method calls
```objectscript
Set adapter = ..GetAdapter()
Do adapter.SendRequest(msg)
;; → GetAdapter() has ReturnType = "EnsLib.SQL.OutboundAdapter" (from %Dictionary)
;; → CALLS edge: current method → EnsLib.SQL.OutboundAdapter.SendRequest
```
**Resolution**: When `Set <var> = ..Method()` or `Set <var> = ##class(X).Method()`,
look up the target method's `ReturnType` from `%Dictionary` (feature 003) or from
the `return_type` property on the Method node. Requires the target method to be
already indexed.

---

## User Scenarios & Testing

### User Story 1 — Resolve %New() typed variables (Priority: P1)

```
MATCH (m:Method {name:'ProcessMessage'})-[:CALLS]->(t) RETURN t.name
```
Returns `ExecuteQuery` when the method body contains
`Set adapter = ##class(EnsLib.SQL.OutboundAdapter).%New()` followed by
`Do adapter.ExecuteQuery(...)`.

**Acceptance Scenarios**:
1. `Set x = ##class(A.B).%New()` then `x.Foo()` → CALLS edge to `A.B.Foo`
2. `Set x = ##class(A.B).%New()` then `x.Bar().Baz()` → CALLS edge to `A.B.Bar` only (chained calls are single-hop)
3. Multiple `Set` to same variable: last assignment wins

### User Story 2 — Resolve parameter types (Priority: P1)

A method with typed parameters produces CALLS edges for calls on those parameters.

**Acceptance Scenarios**:
1. `Method Run(req As Ens.Request)` with body `Do req.Send()` → CALLS edge to `Ens.Request.Send`
2. Untyped parameters (`arg`) produce no CALLS edge for `arg.Method()` — silently skipped

### User Story 3 — Resolve property types (Priority: P2)

`Do ..Adapter.Method()` resolves via the Property's declared type.

**Acceptance Scenarios**:
1. Class has `Property Adapter As EnsLib.SQL.OutboundAdapter;` and method body has `Do ..Adapter.ExecuteQuery()` → CALLS edge to `EnsLib.SQL.OutboundAdapter.ExecuteQuery`
2. `Do ..UntypedProp.Method()` produces no CALLS edge — silently skipped

### User Story 4 — Resolve return types (Priority: P3)

`Set x = ..GetAdapter()` resolves via GetAdapter's declared ReturnType.

**Acceptance Scenarios**:
1. With `%Dictionary` data available (003): `Set x = ..Factory()` where `Factory() As SpecificClass` → CALLS from `x.Method()` resolve to `SpecificClass.Method`
2. Without `%Dictionary`: silently skipped (Pattern 4 is optional enrichment)

---

### Edge Cases

- Variable reassignment: `Set x = ##class(A).%New() ... Set x = ##class(B).%New()` → use last assignment for subsequent calls
- Variable used before assignment: no type info → skip
- `$this` / implicit self (`..Method()`): already resolved by 004 as same-class call
- `$Get(var)` / `$Select(cond:var)`: unresolvable — skip
- Nested method calls: `Do ##class(A).%New().Method()` — `%New()` returns type A, `.Method()` resolves to `A.Method` (single expression, no variable)
- `%OpenId()` returns same class as `%New()`: treat identically

---

## Requirements

### Functional Requirements

- **FR-001**: Within a method body, `Set <var> = ##class(<ClassName>).%New()` MUST record `var → ClassName` in a local type map for that method scope.
- **FR-002**: `Set <var> = ##class(<ClassName>).%OpenId(id)` MUST also record type (same as `%New`).
- **FR-003**: `<var>.Method()` where `var` has a known type MUST produce a CALLS edge to `<Type>.Method`.
- **FR-004**: Method parameters declared `As <Type>` in the method signature MUST be added to the type map at method entry.
- **FR-005**: `..PropertyName.Method()` MUST resolve the property type from the class's Variable nodes and produce a CALLS edge to `<PropertyType>.Method`.
- **FR-006**: `Set <var> = ..Method()` or `Set <var> = ##class(X).Method()` where the target method has a known `ReturnType` MUST record `var → ReturnType`.
- **FR-007**: Type resolution MUST be intraprocedural (within one method body) — no cross-method dataflow analysis.
- **FR-008**: When type cannot be resolved, the call MUST be silently skipped — no error, no stub node.
- **FR-009**: Feature MUST work standalone (without 003 %Dictionary data). Pattern 4 (ReturnType) is enhanced when 003 data is available but degraded gracefully when not.
- **FR-010**: All existing CALLS edges from 004/005 MUST be preserved — this adds edges, never removes.

### Performance Requirements

- **PR-001**: Type inference per method MUST complete in O(n) where n = number of statements in the method body. No backtracking, no fixpoint iteration.
- **PR-002**: Total CALLS extraction time MUST remain under 2× the current pass_calls duration.

### Out of Scope

- Cross-method dataflow (e.g. tracking types through method return values across call chains)
- `$classmethod(variable, "name")` where variable is not a literal string
- `Xecute` / indirection (`@var`)
- Polymorphic dispatch resolution (abstract method → concrete subclass)
- `%Super` calls (already handled as same-class by 004)

---

## Implementation Approach

**Where**: `internal/cbm/extract_calls.c` in the ObjectScript call extraction path.

**Data structure**: Per-method `type_map` — simple array of `{var_name, class_name}`
pairs, allocated from the arena. Max ~50 entries per method (typical).

**Algorithm**:
1. Before extracting calls from a method body, scan all `Set` statements to build the type map
2. For each `instance_method_call` node, check if the receiver variable is in the type map
3. If found, emit `ClassName.MethodName` as the callee
4. Also check method parameters (from `arguments` node) for `As <Type>` declarations

**Integration with existing pipeline**: This runs inside `handle_calls()` during the
existing unified cursor walk. The type map is built on-the-fly as `Set` nodes are
encountered, then consulted when `instance_method_call` nodes are encountered.
No separate pass needed.

---

## Success Criteria

- **SC-001**: On hscommlib (1,888 .cls), CALLS edges increase from 1,984 to ≥ 3,000 after type inference.
- **SC-002**: Pattern 1 (`%New()`) resolves correctly on test fixture — verified by unit test.
- **SC-003**: Pattern 2 (parameter types) resolves correctly — verified by unit test.
- **SC-004**: All existing 3,567+ tests pass.
- **SC-005**: CALLS extraction time on hscommlib remains under 5 seconds total.

---

## Assumptions

- ObjectScript's `Set var = ##class(X).%New()` pattern is the dominant type-introducing statement (covers >60% of typed variables in HealthShare code).
- Property types are available from the same file's Variable nodes (no cross-file lookup needed for `..Property.Method()` resolution — the property is in the same class).
- Method `FormalSpec` is parseable from the tree-sitter `arguments` node which contains `<param> As <Type>` patterns.
- The type map does not need SSA form — last assignment to a variable determines its type for all subsequent uses in the same method.
