# Spec: Parameter Read Edges (READS_PARAM)

**Feature**: 020-parameter-read-edges  
**Created**: 2026-05-21  
**Priority**: P1 — caused hallucination in Michael's V3 benchmark Q3  
**Source**: Michael's V3 Q3: "Find every place that reads `..#VERSIONPROPERTY`"

---

## Problem

The graph tracks CALLS edges (`##class(X).Method()`) but has no concept of
**class parameter reads** (`..#PARAMETERNAME` or `$Parameter(cls, "NAME")`).

When the V3 benchmark asked "which classes read `VERSIONPROPERTY`?", the correct
answer was "nobody — zero readers". The hint arm fabricated callsites because the
graph showed CALLS edges but nothing about parameter reads. The agent assumed the
graph would contain the answer, found nothing, and hallucinated.

This is a real analysis question: "Is this parameter actually used?" is a common
code quality question that currently requires grepping every file for `..#PARAM`.

## What exists today

`CBMDefinition` has parameters (name, default, type). CALLS edges track method calls.
Nothing tracks `..#PARAM` reads or `$Parameter(class, "name")` calls.

## Scope

### In scope
- `..#PARAMETERNAME` reads within method bodies → `READS_PARAM` edge: Method → Parameter
- `$Parameter(classname, "PARAMETERNAME")` calls → same edge type
- Applies to UDL class parameters only

### Out of scope  
- System parameters (`%Library.*`) — noise, not useful
- Parameter writes (ObjectScript parameters are compile-time constants, can't be written)
- `##class(X).#PARAM` cross-class parameter reads (follow-up feature)

## User Scenarios

### US1 — Find all readers of a parameter (V3 Q3)
Query: `MATCH (m:Method)-[:READS_PARAM]->(p:Parameter {name:'VERSIONPROPERTY'}) RETURN m.qualified_name`  
Returns: empty set → **correct answer**: nobody reads it → decorative parameter

### US2 — Find unused parameters  
Query: `MATCH (p:Parameter) WHERE NOT EXISTS (()-[:READS_PARAM]->(p)) RETURN p.qualified_name`  
Returns: all parameters with zero readers — dead configuration

### US3 — Find all callers that depend on a parameter's value
Query: `MATCH (m:Method)-[:READS_PARAM]->(p:Parameter {name:'EXTENTSIZE'}) RETURN m.qualified_name`  
Tells you: if you change EXTENTSIZE, which methods are affected

## Acceptance Criteria

1. `HS.SDA3.Streamlet.Flash` methods that read `..#VERSIONPROPERTY` → `READS_PARAM` edge to the VERSIONPROPERTY Parameter node (if any exist)
2. If no readers: `MATCH ()-[:READS_PARAM]->({name:'VERSIONPROPERTY'})` returns empty — not null, empty
3. A method containing `if ..#MAXSIZE > 0 { ... }` gets a READS_PARAM edge to MAXSIZE
4. `$Parameter("HS.SDA3.Streamlet.Flash","VERSIONPROPERTY")` also generates the edge

## Implementation

In `extract_unified.c` or a new pass, scan method bodies for:

```
// Pattern 1: ..#PARAMETERNAME  
// AST: macro node with text starting with "..#"
// or: class_parameter_expression

// Pattern 2: $Parameter(classname, "PARAMETERNAME")
// AST: intrinsic_call with function_name="$Parameter"  
//       second arg is string literal = parameter name
```

When found, emit a `CBMCall` with `callee_name = "ClassName.ParameterName"` and a
special edge type `READS_PARAM` rather than `CALLS`.

The Parameter node must already exist in the graph (it does — feature 007 extracts
all Parameter members). The edge resolution happens in `pass_calls.c` by matching
`ClassName.ParameterName` against existing Parameter nodes.

## Grammar check needed

Verify with Hannah Kimura: does `..#PARAMETERNAME` parse as a `macro` node or a
separate `class_parameter_expression` node type in the UDL grammar? This determines
the extraction approach.
