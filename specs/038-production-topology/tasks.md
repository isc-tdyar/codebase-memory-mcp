# Tasks: Production Topology Indexing (038)

**Input**: `specs/038-production-topology/`
**Prerequisites**: plan.md ✓, spec.md ✓

**Organization**: US1 = cross-component trace; US2 = runtime validation; US3 = topology queries

---

## Phase 1: Setup

- [ ] T001 Create `internal/cbm/pass_production_topology.h` with struct and function declarations for `ProductionItemMap` and `cbm_resolve_production_routes()`
- [ ] T002 Create `internal/cbm/pass_production_topology.c` skeleton (includes, empty function stubs)
- [ ] T003 Create `tests/test_production_topology.py` skeleton with pytest fixtures `hscore_project` and `careconnect_iris` (skip logic when IRIS unavailable)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: ProductionDefinition XML parsing and item map — required by all three user stories

- [ ] T004 Write unit test in `tests/test_extraction.c`: `TEST(objectscript_udl_production_def_parses_items)` — asserts that indexing a minimal production class emits `ProductionItem` nodes for each `<Item>` element with correct `name`, `class_name`, `enabled`
- [ ] T004b Write unit test in `tests/test_extraction.c`: `TEST(objectscript_udl_production_def_hs_specific_settings)` — asserts `PatientHost` and `ConformanceOperation` settings are extracted and stored on `ProductionItem` nodes identically to `TargetConfigName` (FR-008)
- [ ] T005 Write unit test in `tests/test_extraction.c`: `TEST(objectscript_udl_production_def_extracts_settings)` — asserts `TargetConfigName`, `PatientHost`, `ConformanceOperation` settings are stored on `ProductionItem` nodes
- [ ] T006 Write unit test in `tests/test_extraction.c`: `TEST(objectscript_udl_production_def_absent_no_error)` — asserts class without `ProductionDefinition` XData indexes cleanly with zero `ProductionItem` nodes
- [ ] T007 Extend `extract_defs.c` XData block: detect XData named `ProductionDefinition`, call `cbm_parse_production_xdata(ctx, body_node, class_qn)` from `pass_production_topology.c`
- [ ] T008 Implement `cbm_parse_production_xdata()` in `pass_production_topology.c`: `$FIND`-based scan of raw XData text, extract `<Item Name=... ClassName=... Enabled=...>` and `<Setting Target="Host" Name="TargetConfigName|PatientHost|ConformanceOperation">value` entries; emit `ProductionItem` nodes via `cbm_defs_push`
- [ ] T009 Build and run `make -f Makefile.cbm test` — T004/T004b/T005/T006 must pass green
- [ ] T010 [P] Index `HS.Sample.Production.Demo.Hub` from hscore-30.0 and verify `ProductionItem` nodes in the graph DB via sqlite query

---

## Phase 3: US1 — Cross-Component Trace (P1)

**Story goal**: `trace_path` crosses component boundaries via `ROUTES_TO` edges
**Phase gate**: `test_routes_to_edges_exist` passes; `trace_path` on `dispatchToProduction` returns a cross-component result

- [ ] T011 [US1] Write unit test `TEST(production_routes_to_literal_target)` in `tests/test_extraction.c`: class with `SendRequestSync("HUB", ...)` + production defining item `HUB` → assert `ROUTES_TO` edge exists with `confidence=0.95`, `via="literal"`
- [ ] T012 [US1] Write unit test `TEST(production_routes_to_property_target)` in `tests/test_extraction.c`: class with property `TargetConfigName [ InitialExpression = "HUB" ]` + `SendRequestSync(..TargetConfigName, ...)` + production defining item `HUB` → assert `ROUTES_TO` edge with `confidence=0.85`, `via="TargetConfigName"`
- [ ] T013 [US1] Write unit test `TEST(production_routes_to_disabled_item)` in `tests/test_extraction.c`: item with `Enabled="false"` → `ROUTES_TO` edge has `enabled=false`
- [ ] T014 [US1] Write unit test `TEST(production_routes_to_no_edge_for_variable)` in `tests/test_extraction.c`: `SendRequestSync(tHost, ...)` where `tHost` is a local variable → zero `ROUTES_TO` edges
- [ ] T015 [US1] Implement `cbm_resolve_production_routes()` in `pass_production_topology.c`: scan all Method nodes for `SendRequestSync` in `body_tokens`; for each hit, apply literal pattern `SendRequestSync\s*\(\s*"([^"]+)"` (confidence=0.95) and property pattern `SendRequestSync\s*\(\s*\.\.\s*([A-Za-z][A-Za-z0-9]*)` (confidence=0.85, requires InitialExpression lookup) per plan.md R-003; match against item map; resolve target class own entry point (`OnProcessInput > OnMessage > OnRequest > OnTask`); emit `ROUTES_TO` edge via `cbm_gbuf_upsert_edge()`
- [ ] T016 [US1] Register `pass_production_topology` as a second-pass step in `pipeline.c` (after definitions pass, before enrichment)
- [ ] T017 [US1] Build and run `make -f Makefile.cbm test` — T011–T014 must pass green
- [ ] T018 [US1] Add `test_routes_to_edges_exist()` to `tests/test_production_topology.py`: index `HS.Sample.Production.EdgeGateway.SimpleProduction`, query graph for `ROUTES_TO` edges, assert at least one exists
- [ ] T019 [US1] Run E2E test — `test_routes_to_edges_exist` passes (phase gate)
- [ ] T020 [US1] Verify `trace_path(function_name="dispatchToProduction", project="hscore-30.0", mode="cross_service")` returns a result crossing a component boundary

---

## Phase 4: US2 — Runtime Validation (P1)

**Story goal**: `ROUTES_TO` edges are confirmed correct by querying the IRIS message archive
**Phase gate**: `test_routes_to_matches_runtime_messages` passes OR skips gracefully when IRIS unavailable

- [ ] T021 [US2] Implement `careconnect_iris` pytest fixture in `tests/test_production_topology.py`: connect to localhost:19720/HSLIB via iris Python native API; `pytest.skip("careconnect-ivg-iris unavailable")` if connection fails
- [ ] T022 [US2] Add `seed_fhir_request()` helper to `tests/test_production_topology.py`: sends a minimal FHIR GET request through the careconnect production via the iris Python API to ensure at least one message exists in the archive before validation runs; skips if production is stopped
- [ ] T023 [US2] Implement `test_routes_to_matches_runtime_messages()`: call `seed_fhir_request()`, then for each `ROUTES_TO` edge in the graph query the IRIS `Ens.MessageHeader` table filtered by target config item name; assert at least one message found OR edge has `InitialExpression` justification (stored in edge properties as `derived_from=InitialExpression`)
- [ ] T024 [US2] Implement `test_no_routes_to_for_runtime_only_config()`: assert zero `ROUTES_TO` edges exist for `TargetConfigName` properties without `InitialExpression` (runtime-only config)
- [ ] T025 [US2] Run full E2E suite with careconnect-ivg-iris available — `test_routes_to_matches_runtime_messages` must pass; zero unexpected failures
- [ ] T026 [US2] Run full E2E suite with careconnect-ivg-iris stopped — all careconnect tests must skip gracefully, none fail

---

## Phase 5: US3 — Direct Topology Queries (P2)

**Story goal**: `ProductionItem` nodes and `ROUTES_TO` edges are queryable via `query_graph` and `trace_path`
**Phase gate**: `test_production_item_nodes_indexed` and the US3 acceptance scenario queries return correct results

- [ ] T027 [US3] Implement `test_production_item_nodes_indexed()` in `tests/test_production_topology.py`: assert `ProductionItem` nodes exist with correct `name` and `class_name` after indexing a production
- [ ] T028 [US3] Implement `test_disabled_item_routes_to_carries_enabled_false()`: assert `enabled=false` is present on `ROUTES_TO` edges for disabled items
- [ ] T029 [P] [US3] Verify Cypher query: `MATCH (p:ProductionItem) RETURN p.name, p.class_name LIMIT 10` returns results against hscore-30.0 graph
- [ ] T030 [P] [US3] Verify Cypher query: `MATCH (src)-[:ROUTES_TO]->(tgt) WHERE tgt.name CONTAINS 'FHIROperations' RETURN src.name, tgt.name` returns expected FHIRService→FHIROperations topology
- [ ] T031 [US3] Run `test_production_item_nodes_indexed` and `test_disabled_item_routes_to_carries_enabled_false` — both pass (phase gate)

---

## Phase 6: Polish & Cross-Cutting

- [ ] T032 [P] Add `ROUTES_TO` and `ProductionItem` to `get_graph_schema()` output in `mcp.c` schema description
- [ ] T033 [P] Update `trace_path` handler in `mcp.c` to include `ROUTES_TO` in `mode=cross_service` edge traversal
- [ ] T034 [P] Update `spec.md` Status to `Implemented`
- [ ] T035 Write benchmark test in `tests/test_extraction.c`: `TEST(production_topology_indexing_overhead)` — index a synthetic 20-item production fixture, assert elapsed time ≤50ms (SC-004)
- [ ] T036 Write benchmark test in `tests/test_production_topology.py`: `test_routes_to_query_latency()` — run `MATCH (src)-[:ROUTES_TO]->(tgt) RETURN src, tgt` against hscore-30.0 graph, assert elapsed ≤200ms (SC-005)
- [ ] T037 Run full test suite `make -f Makefile.cbm test` — all tests green including T035
- [ ] T038 Run `cbm-install` to install new binary

---

## Dependencies

```
Phase 1 (Setup)
  └── Phase 2 (Foundational: parse ProductionDefinition XML)
        ├── Phase 3 (US1: ROUTES_TO edges + C unit tests + basic E2E)
        │     └── Phase 4 (US2: iris message archive validation)
        │           └── Phase 5 (US3: topology query verification)
        │                 └── Phase 6 (Polish + benchmarks)
        └── Phase 5 can start in parallel after Phase 2 ✓
```

## Parallel Opportunities

- T003 (test skeleton) can run in parallel with T001/T002
- T010 (manual index verify) can run in parallel with T009
- T022/T023 (US2 test impl) can be written in parallel with T015–T020 (US1 impl)
- T029, T030, T032, T033, T034, T036 are all independent and can run in parallel in Phase 5/6

## MVP Scope

**US1 alone (T001–T020)** delivers the core value: `trace_path` crosses component boundaries.
US2 (runtime validation) and US3 (direct topology queries) are additive polish.

Suggested delivery order: Phase 1 → 2 → 3 (US1 ships) → 4 (US2 validation) → 5/6 (cleanup + benchmarks).
