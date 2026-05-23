# Upstream PR Portfolio — ISC + Michael Riadzak contributions

**Repo**: `DeusData/codebase-memory-mcp`
**Our fork**: `isc-tdyar/codebase-memory-mcp`
**Michael's fork**: `isc-mriadzak/codebase-memory-mcp`
**Date**: 2026-05-23

---

## PR Strategy

Three tiers:

1. **Tier 1 — General (submit immediately)**: Language support and bug fixes that benefit all users.
2. **Tier 2 — Interoperability pattern (submit with framing)**: Ensemble/production topology features,
   framed as an "interoperability production pipeline" extension pattern generalizable to other
   workflow orchestration systems.
3. **Tier 3 — ISC-specific (hold or submit separately)**: IRIS %Dictionary ingest, IRIS Studio XML
   parser — valuable but require IRIS runtime to demonstrate.

---

## PR 1: ObjectScript / IRIS ObjectScript Language Support (Tier 1)

**Branch**: `isc-tdyar:objectscript-language-support`
**Commits**: specs 001-017 (merged to main from their feature branches)

### What it does
Full ObjectScript UDL and MAC routine language support: 40 node types extracted (Class, Method,
Property, Parameter, Index, Trigger, XData, Storage, ...), CALLS edge resolution via `##class()`,
`$$$macro`, `.INT` intermediate, type inference, macro expansion, return-type tracking, cross-class
DATA_FLOWS, parallel pipeline wiring. Plus IRIS Studio XML export transcoder.

### Why upstream wants it
ObjectScript is the language of InterSystems IRIS/Caché, used by thousands of enterprise
customers. It's a significant installed base with no current MCP code intelligence tool.
The implementation follows all existing patterns (tree-sitter grammar, lang_spec, extract_calls).

### Test coverage
~400 new tests in `test_extraction.c`. Benchmark: hscore-30.0 (1,162 classes, 4,153 methods,
3,349 CALLS edges after spec-040).

### Files changed
- `internal/cbm/lang_specs.c` — ObjectScript UDL + routine lang specs
- `internal/cbm/extract_defs.c` — 40 class member types
- `internal/cbm/extract_calls.c` — `##class()`, `$$$macro`, oref resolution
- `internal/cbm/extract_unified.c` — ObjectScript type map
- `internal/cbm/grammar_objectscript_udl.c/.h`, `grammar_objectscript_routine.c/.h`
- `internal/cbm/iris_export_xml.c/.h` — Studio XML transcoder
- `src/pipeline/pass_iris_dict.c/.h` — IRIS %Dictionary ingest (needs IRIS — Tier 3)
- `tests/test_extraction.c` — 400+ tests

---

## PR 2: ObjectScript oref self-call resolution (`..Method()`) (Tier 1) ⭐ HIGH IMPACT

**Branch**: `isc-tdyar:objectscript-oref-selfcall`
**Key commit**: `481189f feat(040): ObjectScript oref self-call resolution (..Method())`

### What it does
Two-line fix: adds `"relative_dot_method"` to `objectscript_udl_call_types[]` and resolves
`..Method(args)` as `{enclosing_class}.Method` using the existing `WalkState.enclosing_class_qn`.

### Impact (measured on hscore-30.0)
**CALLS edges: 957 → 3,349 (3.5× increase)**

This single fix unlocks 4,023 previously invisible self-calls across the hscore codebase, including
all `..SendRequestSync()` / `..SendRequestAsync()` Ensemble dispatch calls, all `..processStreamlet()`
data processing calls, and all property accessor methods.

### Why this matters for all ObjectScript users
`..Method()` is THE standard call pattern in ObjectScript — it's how every method calls
another method on the same class. Without it, CALLS analysis for ObjectScript is structurally
incomplete. This is not a niche pattern; it's ~80% of all ObjectScript method calls.

### Files
- `internal/cbm/lang_specs.c` — 1 line
- `internal/cbm/extract_calls.c` — 20 lines

---

## PR 3: Trigger body text extraction (Tier 1)

**Branch**: `isc-tdyar:objectscript-trigger-body`
**Key commit**: `467c491 feat(019): trigger body text extraction`

### What it does
Extracts `Trigger` body text as `trigger_body` property on Trigger nodes, and adds
`objectscript_identifier` + `identifier_segment_immediate` to `extract_body_ident_tokens`
(benefits all ObjectScript method extraction, not just triggers).

### Why upstream wants it
Trigger bodies were visible in the node list but empty — `trigger_body` was always NULL.
Agents querying "what does this trigger do?" had to read the source file. Now it's a 30-token
graph query. Demonstrated in V6 benchmark: closes a known hallucination trap from V3-Q2.

### Files
- `internal/cbm/extract_defs.c` — trigger body extraction + objectscript_identifier node types

---

## PR 4: Storage block XML parsing + version tag + diff_versions (Tier 1)

**Branch**: `isc-tdyar:objectscript-storage-version-diff`
**Key commits**: `3faf437`, `693a96a`, `a0c0be0`

### What it does
Three related features:
1. **Storage block parsing** (spec-021): Extracts `<ExtentSize>`, `<Value>`, subscript names
   from the Storage XData block — enables graph queries about persistence shape
2. **Version tags** (spec-024): Adds `version` property to all nodes via `index_repository(version=)`
   parameter, enabling the same codebase indexed twice at different versions to coexist in one DB
3. **`diff_versions` MCP tool** (spec-025): Returns added/removed/changed nodes between two
   version tags — "what classes changed between v28.0 and v30.0?"

### Why upstream wants it
Version-tagged indexing + diff is a general capability useful for any multi-version codebase
(e.g., index `main` and a feature branch, then `diff_versions` to see impact). Not ObjectScript-specific.

### Files
- `internal/cbm/extract_defs.c` — Storage XData parsing
- `src/pipeline/pass_definitions.c`, `pass_parallel.c`, `pipeline.c` — version tag propagation
- `src/mcp/mcp.c` — `diff_versions` tool registration + handler

---

## PR 5: Ensemble production topology / ROUTES_TO edges (Tier 2)

**Branch**: `isc-tdyar:ensemble-production-routing`
**Key commits**: `04624ea`, `d2e2cf4`, `dd78b3a`

### What it does
New predump pass `pass_ensemble_routing.c` that:
1. Parses `ProductionDefinition` XData (Ensemble's production component wiring XML)
2. Emits `EnsembleItem` nodes for each production component
3. Emits `ROUTES_TO` edges from `SendRequestSync("LiteralTarget", ...)` callsites to
   the receiving component's entry-point method
4. WorkMgr parallel dispatch: `$system.WorkMgr .Queue("##class(X).method", ...)` → CALLS edges

### Framing for upstream
The general pattern is: **production/pipeline topology indexing** — any workflow orchestration
system (Celery, Airflow, AWS Step Functions, etc.) has the same pattern: a string config name
routes to a class/handler. The `ROUTES_TO` edge type and the production XML parser are specific
to Ensemble, but the pattern is worth upstreaming as it demonstrates how to add domain-specific
routing topology to the graph.

### Benchmark result (V6)
29 `EnsembleItem` nodes, 289 `ROUTES_TO` edges in hscore-30.0. Combined with oref fix (PR 2),
the full `FlashQueueUpdate → MakeMRNUpToDate → processStreamlet` chain is traceable without
any file reads.

### Files
- `src/pipeline/pass_ensemble_routing.c/.h` — new predump pass
- `src/pipeline/pipeline.c`, `pipeline_internal.h` — wiring
- `tests/test_workmgr_dispatch.py` — integration tests

---

## PR 6: LSP cross-file shared registry + O(1) lookups (from Michael Riadzak) (Tier 1)

**Branch**: `isc-mriadzak:lsp-shared-registry`
**Commits**: `0a70f77`, `758b216`
**Author**: Michael Riadzak (isc-mriadzak)

### What it does
Performance improvement to `pass_lsp_cross`:
1. **O(1) registry lookups**: replaces linear scan with hash buckets in `type_registry.c`
2. **Shared per-language registry**: stdlib + cross-file defs built once per language
   (not once per file), eliminating the dominant CPU cost on large C/C++ codebases
3. **C-LSP OOB fix**: bounds check in `c_lsp.c` that was causing crashes on large header files

### Why upstream wants it
These are pure performance and correctness improvements to the existing LSP resolver infrastructure.
No new API surface. The shared registry pattern is architecturally clean.

### Status
Cherry-picked onto our `040-oref-self-call-resolution` branch. All 3653 tests pass.
Michael should PR this directly to upstream or through our fork.

---

## PR Submission Order (recommended)

1. **PR 2** (oref self-call) first — smallest, highest impact, zero ISC-specific content
2. **PR 1** (ObjectScript language) — largest, but well-tested, established pattern
3. **PR 3** (trigger body) — small, clean
4. **PR 6** (Michael's LSP perf) — let Michael submit directly or co-author
5. **PR 4** (storage/version/diff) — after core language support is merged
6. **PR 5** (Ensemble routing) — last, most ISC-specific, needs the most discussion

---

## What NOT to upstream (hold for ISC-internal use)

- `specs/` directory — ISC internal spec workflow
- `bench/v6/` — ISC HealthShare-specific benchmark
- `src/pipeline/pass_iris_dict.c` — requires live IRIS container to be useful
- `internal/cbm/iris_export_xml.c` — ISC Studio-specific format
- `tests/test_production_topology.py` — depends on careconnect-ivg-iris container
