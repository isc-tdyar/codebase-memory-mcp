# Spec: Trigger Body Text Extraction

**Feature**: 019-trigger-body-text  
**Created**: 2026-05-21  
**Priority**: P1 — caused -1 hallucination penalty in Michael's V3 benchmark Q2  
**Source**: Michael's benchmark V3 Q2: "Does `OnDeleteSQL` actually cascade?"

---

## Problem

`Trigger` nodes are extracted with name, label, start_line, end_line — but the body
text is NOT stored. When an agent queries the graph for what a trigger does, it gets
no content. This caused the V3 Q2 failure: the agent could not verify the trigger
body was just `Quit`, so it either guessed or hallucinated.

Doc comment: "cascade-delete linked resource streamlets"  
Actual trigger body: `Quit` (empty, does nothing)  
Graph says: nothing about body content

The correct answer ("the doc comment lies — body is just Quit") requires reading the
body. The graph should make this answerable without opening the file.

## What exists today

`CBMDefinition.body_tokens` exists and is populated for Method/Function nodes via
`extract_func_def()`. Trigger nodes go through a different code path in
`push_method_def` for UDL class members — they only store `name`, `label`,
`start_line`, `end_line`. No body.

## Scope

### In scope
- Extract trigger body text from UDL `.cls` files
- Store as `body_tokens` (identifier tokens, same as methods) on Trigger nodes
- Store the raw body as a queryable node property (for "what does this trigger do" queries)

### Out of scope
- Macro trigger definitions (those are different node types)
- Non-UDL trigger syntax (not applicable in ObjectScript)

## User Scenarios

### US1 — Verify trigger body (V3 Q2 benchmark question)
Query: `MATCH (t:Trigger {name:'OnDeleteSQL'}) RETURN t.body_tokens`  
Returns: `"Quit"` — immediately reveals empty/no-op trigger  
Without this: agent opens the file, reads it — or hallucinates

### US2 — Find all no-op triggers across a codebase
Query: `MATCH (t:Trigger) WHERE t.body_tokens = 'Quit' OR t.body_tokens = '' RETURN t.qualified_name`  
Returns: all ghost triggers — impossible with grep without reading every trigger body

### US3 — Find triggers that call specific methods
Query: `MATCH (t:Trigger) WHERE t.body_tokens CONTAINS 'DeleteId' RETURN t.qualified_name`

## Acceptance Criteria

1. `HS.ODS.FHIR.ODSSession` trigger `OnDeleteSQL` has `body_tokens = 'Quit'` in graph
2. Trigger with real body has meaningful token content
3. Query `MATCH (t:Trigger) WHERE t.body_tokens CONTAINS 'Quit'` returns correct set
4. No regression on existing trigger name/line extraction

## Implementation

In `extract_defs.c`, the UDL member extraction for `trigger` nodes currently just
stores name and label. Extend it to:

1. Find the `trigger_definition` child
2. Find the `implementation` child inside it (same as method body)
3. Call `extract_body_ident_tokens(ctx, impl_node)` and store in `mdef.body_tokens`
4. Store raw body text as a `properties_json` field `"trigger_body":"..."` for exact
   content queries (not just token search)

The grammar already parses trigger bodies — `trigger` → `trigger_definition` →
`implementation` → `<![CDATA[...]]>` just like methods.
