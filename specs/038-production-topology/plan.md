# Implementation Plan: Production Topology Indexing

**Branch**: `038-production-topology` | **Date**: 2026-05-23 | **Spec**: [spec.md](spec.md)

## Summary

Parse `ProductionDefinition` XData in `Ens.Production` subclasses to extract component wiring,
emit `ProductionItem` nodes and `ROUTES_TO` edges that connect `SendRequestSync` callsites to
their target class entry points. Validate correctness by comparing static `ROUTES_TO` predictions
against live runtime message traffic via `iris_interop_query`.

## Technical Context

**Language/Version**: C11 (core pipeline), Python 3.x (E2E tests)
**Primary Dependencies**: tree-sitter ObjectScript UDL grammar (existing), SQLite (existing), iris Python API (E2E)
**Storage**: Existing SQLite graph DB — new node label `ProductionItem`, new edge type `ROUTES_TO`
**Testing**: `make -f Makefile.cbm test` (C unit) + `tests/test_production_topology.py` (E2E)
**Target Platform**: macOS/Linux
**Project Type**: Library/CLI extension of existing pipeline
**Performance Goals**: ≤50ms added indexing overhead per 20-item production class (SC-004)
**Constraints**: ≤200ms ROUTES_TO query latency (SC-005); no new external dependencies
**Scale/Scope**: hscore-30.0 (~30 production classes); generalizes to any Ensemble namespace

## Constitution Check

Key project conventions:
- Test-first: C unit tests in `test_extraction.c` before merge
- No new external dependencies: `$FIND`-based XML parsing (spec-021 precedent)
- Confidence values explicit on all edges (spec-037 precedent)
- E2E tests skip gracefully when IRIS unavailable (iris_dict pattern)

## Project Structure

### Documentation

```
specs/038-production-topology/
├── plan.md
├── research.md
├── data-model.md
├── contracts/
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```
internal/cbm/
├── extract_defs.c              -- extend xdata to parse ProductionDefinition XML
├── pass_production_topology.c  -- NEW: second-pass ROUTES_TO resolution
└── pass_production_topology.h  -- NEW

tests/
├── test_extraction.c           -- add ProductionDefinition unit tests
└── test_production_topology.py -- NEW: E2E via iris_interop_query
```

---

## Phase 0: Research

### R-001: ProductionDefinition XML structure

**Decision**: `$FIND`-based string extraction (same as spec-021 storage, spec-037 MessageMap).

Target XML:
```xml
<Production Name="HS.Sample.Production.Demo.Hub">
  <Item Name="HUB" ClassName="HS.Hub.HSWS.RemoteOperations" Enabled="true">
    <Setting Target="Host" Name="TargetConfigName">HUB</Setting>
    <Setting Target="Host" Name="PatientHost">PATIENT_HOST</Setting>
    <Setting Target="Host" Name="ConformanceOperation">HS.FHIR.Repository.Operations</Setting>
  </Item>
</Production>
```

Parse strategy:
1. Find all `<Item ` occurrences, extract `Name=`, `ClassName=`, `Enabled=` attributes
2. Within each Item block find `<Setting Target="Host" Name="TargetConfigName|PatientHost|ConformanceOperation">value`
3. Build `item_map[item_name] = {class_name, enabled, settings}`

### R-002: Detecting production classes

**Decision**: Trigger on XData named `ProductionDefinition` — more reliable than Super chain traversal.
`HS.Util.AbstractFlashProduction` → `HS.Util.AbstractProduction` → `Ens.Production` is 3 hops.
XData name is definitive and requires no ancestry lookup.

### R-003: SendRequestSync callsite detection

**Decision**: Scan `body_tokens` for `SendRequestSync`. Extract first argument via pattern matching on raw source text using two passes:

1. **Literal pattern** — `SendRequestSync\s*\(\s*"([^"]+)"` → capture group 1 is the item name → `confidence=0.95`
2. **Property pattern** — `SendRequestSync\s*\(\s*\.\.\s*([A-Za-z][A-Za-z0-9]*)` → capture group 1 is the property name → look up parent class for `Property PropName ... [ InitialExpression = "value" ]` → if value matches item name → `confidence=0.85`
3. **Anything else** (local variable, expression) → skip, no edge

Regex patterns are applied to the raw method source text (same as spec-021 storage parsing). Case-sensitive match against item names.

### R-004: Entry-point resolution order

**Decision**: `OnProcessInput > OnMessage > OnRequest > OnTask`.
If none found, target the Class node with `confidence -= 0.10`.

### R-005: E2E test via iris_interop_query

**Decision**: `tests/test_production_topology.py`:
1. Index hscore-30.0 sample production classes
2. Query CBM graph for all `ROUTES_TO` edges
3. For each edge, call `iris_interop_query(what=messages)` filtered to target item
4. Assert: edge↔message match OR edge has `InitialExpression` justification
5. `pytest.skip()` when careconnect-ivg-iris unavailable

---

## Phase 1: Design & Contracts

### Data Model

**ProductionItem node**:

| Property | Type | Source |
|----------|------|--------|
| `name` | string | `Item.Name` attribute |
| `qualified_name` | string | `{production_class}.{item_name}` |
| `label` | `"ProductionItem"` | fixed |
| `class_name` | string | `Item.ClassName` attribute |
| `enabled` | bool | `Item.Enabled` attribute |
| `production` | string | Parent production class name |
| `file_path` | string | Inherited from class file |

**ROUTES_TO edge**:

| Property | Type | Notes |
|----------|------|-------|
| `via` | string | `"TargetConfigName"`, `"PatientHost"`, `"ConformanceOperation"`, or `"literal"` |
| `production` | string | Production class name |
| `item_name` | string | Config item name targeted |
| `confidence` | float | 0.95 literal / 0.85 InitialExpression |
| `enabled` | bool | From target item |
| `version` | string | Supports cross-version diff (spec-024) |

**Source**: `Method` node (calling method)
**Target**: `Method` node (entry point) OR `Class` node if no entry point found

### Contracts: Query Interface

```cypher
-- What does FHIRService route to?
MATCH (m:Method)<-[:DEFINES_METHOD]-(c:Class {name:'HS.Flash.FHIRService'})
MATCH (m)-[r:ROUTES_TO]->(target)
RETURN m.name, r.item_name, r.via, r.confidence, target.name

-- What feeds into FHIROperations.DSTU2?
MATCH (src)-[:ROUTES_TO]->(tgt:Method)
WHERE tgt.qualified_name CONTAINS 'FHIROperations.DSTU2'
RETURN src.name, tgt.name
```

### E2E Test Functions

```python
def test_routes_to_edges_exist(hscore_project, careconnect_iris)
def test_routes_to_matches_runtime_messages(hscore_project, careconnect_iris)
def test_no_routes_to_for_runtime_only_config(hscore_project)
def test_production_item_nodes_indexed(hscore_project)
def test_disabled_item_routes_to_carries_enabled_false(hscore_project)
```

Fixtures:
- `hscore_project`: path to cached hscore-30.0 CBM graph DB
- `careconnect_iris`: iris connection to localhost:19720/HSLIB — `pytest.skip()` if unavailable

---

## Complexity Tracking

No violations. Additive feature following spec-021 and spec-037 patterns.
