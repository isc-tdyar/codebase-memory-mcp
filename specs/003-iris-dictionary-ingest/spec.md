# Feature Specification: IRIS %Dictionary Ingest Mode

**Feature Branch**: `003-iris-dictionary-ingest`
**Created**: 2026-05-14
**Status**: Draft

---

## Context

codebase-memory-mcp's tree-sitter pass extracts Classes and Methods well (~100%),
but misses 7 member types that live in `%Dictionary` inside every IRIS instance:
Parameters, Queries, XData blocks, Trigger definitions, Index definitions,
Storage definitions, and multi-parent Extends (inheritance beyond first parent).

These gaps are documented in the audit of 1,112-class Ensemble source (uncleaned-code):
- 1,677 Parameter definitions: 0% extracted
- 136 Query definitions: 0% extracted
- 543 XData blocks: 0% extracted
- 47 Trigger definitions: 0% extracted
- 153 Index definitions: 0% extracted
- 233 Storage definitions: 0% extracted

For internal ISC workspaces and customer IRIS installations, the code is already
compiled inside IRIS. `%Dictionary.ClassDefinition` is IRIS's own authoritative
structural model — more accurate than parsing .cls files because it includes
runtime-resolved types and fully-resolved multi-parent inheritance.

This feature adds a `--iris` ingest mode that connects to a live IRIS instance
via the Atelier REST API (already used by iris-dev MCP and the VSCode ObjectScript
extension) to pull `%Dictionary` data and merge it into the knowledge graph.
No new external dependencies. Works in air-gapped customer installations.
No code leaves the customer's network.

---

## User Scenarios & Testing

### User Story 1 — Index a live IRIS namespace (Priority: P1)

A developer runs:
```
index_repository(repo_path="/ws/fhir-017", mode="full",
                 iris_host="localhost", iris_port=64780,
                 iris_namespace="USER")
```
The tool performs the normal tree-sitter pass on .cls files on disk PLUS
fetches `%Dictionary` data from the live IRIS instance and merges the results.
After indexing, all 7 previously-missing member types appear in the graph.

**Acceptance Scenarios**:
1. `MATCH (n:Query) RETURN n.name, n.file_path` returns SQL Query definitions
2. `MATCH (n:Variable) WHERE n.member_type = 'Parameter' RETURN n.name` returns class Parameters
3. `MATCH (n:XData) RETURN n.name, n.file_path` returns XData blocks
4. `MATCH (a)-[:INHERITS]->(b) RETURN a.name, b.name` returns ALL base classes for multi-parent Extends

### User Story 2 — Dictionary-only mode for customer installations (Priority: P1)

A customer has their IRIS instance but no .cls source files on disk (code is only
compiled in the database). The tool connects to IRIS and builds a knowledge graph
from `%Dictionary` alone — no .cls files needed.

```
index_repository(repo_path=None, mode="dictionary",
                 iris_host="customer-iris.example.com", iris_port=52773,
                 iris_namespace="PROD", iris_username="admin", iris_password="...")
```

**Acceptance Scenarios**:
1. Graph contains Class, Method, Property, Parameter, Query, XData, Trigger, Index, Storage nodes
2. Works with no .cls files present — dictionary-only is sufficient
3. Namespace filter works: only classes from the target namespace are indexed

### User Story 3 — Namespace filter and package scoping (Priority: P2)

A developer wants to index only classes from a specific package (e.g., `HS.FHIRServer`)
without pulling the entire 10,000-class IRIS system library.

```
index_repository(..., iris_namespace="USER", iris_package_filter="HS.FHIRServer")
```

**Acceptance Scenarios**:
1. Only classes whose name starts with `HS.FHIRServer` are indexed
2. System classes (%Library.*, %Dictionary.*, etc.) are excluded by default
3. Filter is case-insensitive

### Edge Cases

- IRIS instance unreachable: graceful fallback to tree-sitter-only pass, warning logged
- Class exists in %Dictionary but not on disk (compiled-only): Dictionary nodes created, no line numbers
- Class on disk but not compiled: tree-sitter nodes created, no %Dictionary enrichment
- Multi-parent Extends `(A, B, C)`: all three INHERITS edges created
- XData with embedded XML/JSON content > 100KB: content stored as truncated text, full hash stored
- %Dictionary not accessible (insufficient privileges): warning + skip, no crash
- Namespace contains 50,000+ classes: batched in pages of 500

---

## Requirements

### Functional Requirements

- **FR-001**: `index_repository` MUST accept optional parameters `iris_host`, `iris_port`, `iris_namespace`, `iris_username`, `iris_password` to connect to a live IRIS instance via Atelier REST API.
- **FR-002**: When IRIS connection params are provided, the indexer MUST fetch ALL of: Methods, Properties, Parameters, Queries, Indices, XDatas, Triggers, Storages from `%Dictionary.ClassDefinition` for each class in the namespace.
- **FR-003**: Parameters MUST be indexed as `Variable` label nodes with `member_type = "Parameter"` to distinguish from Properties.
- **FR-004**: SQL Query definitions MUST be indexed as `Function` label nodes with `member_type = "Query"` — they are callable entry points equivalent to methods.
- **FR-005**: XData blocks MUST be indexed as a new `XData` label node with properties: `name`, `mime_type`, `schema_spec`, `file_path`.
- **FR-006**: Trigger definitions MUST be indexed as a new `Trigger` label node.
- **FR-007**: Index definitions MUST be indexed as a new `Index` label node with `is_unique`, `is_bitmap`, `index_type` properties.
- **FR-008**: Storage definitions MUST be indexed as a new `Storage` label node.
- **FR-009**: Multi-parent `Extends (A, B, C)` MUST create an INHERITS edge for EACH parent, not just the first.
- **FR-010**: When both tree-sitter and %Dictionary data are available for the same class, they MUST be merged: tree-sitter provides line numbers and method bodies; %Dictionary provides member types, type signatures, Parameters, Queries, XDatas, Triggers, Indexes, Storage.
- **FR-011**: A `mode="dictionary"` index mode MUST work without any .cls files on disk.
- **FR-012**: An optional `iris_package_filter` parameter MUST limit indexing to classes whose name starts with the given prefix. Default: exclude system classes (those starting with `%`).
- **FR-013**: The feature MUST work with IRIS Community Edition and HealthConnect/HealthShare enterprise editions. No ISC-internal-only APIs.
- **FR-014: The feature MUST connect via the IRIS native protocol (superserver port 1972) using standard SQL queries against %Dictionary.* tables — the same protocol used by the intersystems-iris Python driver and JDBC. No custom code installed on IRIS. No Atelier REST required. No web server required on the IRIS instance.

### Non-Functional Requirements

- **NFR-001**: Dictionary ingest for 1,000 classes MUST complete in under 60 seconds over a local network connection.
- **NFR-002**: Credentials MUST NOT be stored in the knowledge graph or logged.
- **NFR-003**: If the IRIS connection is unavailable, the indexer MUST complete the tree-sitter pass normally and log a warning — no crash.
- **NFR-004**: The feature MUST NOT require changes to the IRIS instance (no new classes to install, no IPM packages).

### Out of Scope

- Method body extraction from IRIS (bodies are in .INT compiled form, not source)
- Macro resolution ($$$) — deferred to separate spec
- CALLS edge extraction from %Dictionary — %Dictionary has no call graph
- Support for Caché (pre-IRIS) — IRIS 2019.1+ only
- Authentication via Kerberos or OAuth2 — username/password only in this scope

---

## Success Criteria

- **SC-001**: After indexing an IRIS namespace with 1,112 classes (uncleaned-code equivalent), the graph contains nodes for Parameters, Queries, XData blocks — verified by `MATCH (n:XData) RETURN count(n)` returning > 0.
- **SC-002**: Multi-parent inheritance: a class with `Extends (A, B, C)` produces 3 INHERITS edges — verified by test.
- **SC-003**: Dictionary-only mode produces a usable graph with no .cls files present — verified by test with an in-memory IRIS fixture.
- **SC-004**: IRIS connection failure causes graceful fallback, not crash — verified by test with unreachable host.
- **SC-005**: All existing tests continue to pass (zero regressions).
- **SC-006**: `make -f Makefile.cbm install` succeeds on macOS with new code.

---

## Assumptions

- The Atelier REST API is available at `http[s]://<host>:<port>/api/atelier/v1/<namespace>/`
  on any IRIS instance that has a web server enabled (true for all modern IRIS installs).
- `%Dictionary.ClassDefinition` is readable by any user with READ permission on the namespace
  (standard for developers; may need %DB_<namespace> role for restricted installations).
- The tree-sitter pass continues to run first; %Dictionary enriches/extends the results.
- For customer installations where only compiled code exists: dictionary-only mode
  provides enough structural data for navigation and search use cases.
- iris-dev MCP server is NOT required at runtime — CBM calls Atelier REST directly.
  iris-dev and CBM independently connect to the same IRIS instance.

---

## Appendix: CALLS Edge Improvement via %Dictionary

### What %Dictionary contributes to call graph quality

`%Dictionary` does NOT contain a call graph. However it contributes to CALLS edge
resolution in two ways:

**1. Literal class name calls (already works in tree-sitter, just not wired):**
`##class(HS.FHIRServer.Admin.API).GetParam()` — tree-sitter produces a
`class_method_call` AST node with a literal class name. CBM already has these
in `call_node_types` but the pipeline pass does not walk method bodies to emit
CALLS edges from them. This is a CBM pipeline gap, not a grammar gap.

**2. Type-resolved variable calls (new with %Dictionary):**
`set obj = ##class(Ens.Director).%New()` then `obj.StartProduction()` — tree-sitter
can't resolve `obj`'s type. But `%Dictionary.MethodDefinition.FormalSpec` knows the
declared return type of `%New()` is the class itself. A post-processing pass can
resolve typed variables to concrete classes and emit CALLS edges.

### Coverage estimate with both

| Call pattern | Coverage today | With pipeline fix | + %Dictionary types |
|---|---|---|---|
| Literal `##class(X).M()` | 0% (not wired) | ~80% | ~80% |
| `Do ..Method()` (relative) | 0% (not wired) | ~90% | ~90% |
| `Do tag^ROUTINE` | 0% (not wired) | ~95% | ~95% |
| Typed variable calls | 0% | 0% | ~30% |
| `$$$Macro` calls | 0% | 0% | 0% (needs macro resolution) |
| Dynamic `$ClassMethod` | 0% | 0% | 0% (truly dynamic) |

**Primary fix is in CBM's pipeline** — walk `class_method_call` and
`instance_method_call` nodes in method bodies during the definitions pass.
This is tracked as a separate issue. %Dictionary type resolution is a
secondary enhancement layered on top.

### FR addition: CALLS edges from literal class method calls

- **FR-015**: The `%Dictionary` ingest pass MUST emit CALLS edges for
  `##class(X).Method()` patterns where X is a literal class name resolvable
  against the indexed namespace. This is more reliable than tree-sitter's
  call extraction because %Dictionary confirms the target class exists.

---

## Clarifications

### Session 2026-05-14

- Q: How does CBM (a C binary) connect to IRIS native protocol for %Dictionary SQL? → A: Python subprocess — CBM invokes `python3 cbm_iris_dict.py --host ... --port ... --namespace ... --user ... --pass ...`, reads newline-delimited JSON on stdout. Uses `intersystems-iris` PyPI package (MIT, no IRIS-side installation). CBM passes credentials via CLI args (not stored). Python script is independently testable.
