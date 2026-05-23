# Specification Quality Checklist: Production Topology Indexing

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-23
**Feature**: [spec.md](../spec.md)
**Focus**: Graph correctness, E2E validation contract, scope boundary enforcement

---

## Requirement Completeness

- [ ] CHK001 - Are all three topology-bearing setting names (`TargetConfigName`, `PatientHost`, `ConformanceOperation`) explicitly listed in FR-008, or is the list acknowledged as open-ended? [Completeness, Spec §FR-008]
- [ ] CHK002 - Is the entry-point method resolution order (`OnProcessInput` > `OnMessage` > `OnRequest` > `OnTask`) justified — what happens if a class defines none of these? [Completeness, Spec §FR-006]
- [ ] CHK003 - Are `ProductionItem` node properties fully enumerated (`item_name`, `class_name`, `enabled`, `production`)? Are any attributes from the `<Item>` XML (e.g. `PoolSize`, `Category`) intentionally excluded? [Completeness, Spec §Key Entities]
- [ ] CHK004 - Is the behavior specified when two different productions define items with the same `Name` but different `ClassName`? [Completeness, Edge Cases]
- [ ] CHK005 - Are requirements defined for the case where `SendRequestSync` passes a variable (not a literal and not a direct property reference)? The spec says "out of scope" but it is not in the scope boundary section. [Completeness, Gap]

---

## Requirement Clarity

- [ ] CHK006 - Is "property whose `InitialExpression` matches a known `ProductionItem.item_name`" unambiguous? Does this require exact string match or substring? Case-sensitive? [Clarity, Spec §FR-004]
- [ ] CHK007 - Is `confidence=0.85` for settings-derived targets and `confidence=0.95` for literal targets defined relative to each other — i.e. is the scale documented? [Clarity, Spec §FR-003, FR-004]
- [ ] CHK008 - What constitutes an "actively-used route" in SC-003? Is there a minimum message count threshold, or is one message sufficient? [Clarity, Spec §SC-003]
- [ ] CHK009 - In FR-007, "at least one corroborating runtime message OR has a valid `InitialExpression` default as justification" — is "as justification" a sufficient substitute for runtime evidence, or does it weaken the correctness claim? [Clarity, Spec §FR-007]
- [ ] CHK010 - Is "first match wins" in FR-006 clearly defined: first match in the target class's own methods, or including inherited methods? [Clarity, Spec §FR-006]

---

## Requirement Consistency

- [ ] CHK011 - SC-001 says "100% of production classes in hscore-30.0 test corpus" but FR-003/FR-004 are conditional (only when item names match). Are these consistent — could SC-001 fail for classes with no matching items? [Consistency, Spec §SC-001 vs FR-003]
- [ ] CHK012 - The Edge Cases section says `Enabled="false"` items get a `ROUTES_TO` edge with `enabled=false`. FR-005 lists `enabled` as a property. Is there a requirement that agents/queries should be able to filter by `enabled=false`? [Consistency, Spec §Edge Cases vs FR-005]
- [ ] CHK013 - Assumptions state `iris_interop_query` returns 24h history. SC-002 and SC-003 rely on message archive coverage. If the production is idle, the assumption fallback ("use `InitialExpression` matching instead") changes the correctness signal — is this fallback explicitly captured in FR-007? [Consistency, Spec §Assumptions vs FR-007]

---

## Acceptance Criteria Quality

- [ ] CHK014 - SC-004 specifies "less than 50ms added indexing overhead for a production class with 20 items." Is this measurable in the existing test harness, or does it require a new benchmark? [Measurability, Spec §SC-004]
- [ ] CHK015 - SC-002 says "zero false-positive ROUTES_TO edges" — is this verified per-corpus (hscore-30.0 sample productions) or as a universal guarantee? A universal claim is untestable. [Measurability, Spec §SC-002]
- [ ] CHK016 - US-1 Independent Test references `HS.Sample.Production.EdgeGateway.SimpleProduction` — does that production's XML contain a `TargetConfigName` setting with `InitialExpression`? This should be confirmed before it becomes a test anchor. [Acceptance Criteria, Spec §US-1]

---

## Scenario Coverage

- [ ] CHK017 - Is there a scenario covering the demo path specifically: index → `query_graph(ROUTES_TO)` → `iris_interop_query` → compare? The spec has US-2 for E2E validation but the combined demo flow (US-1 static + US-2 runtime) is not a single acceptance scenario. [Coverage, Gap]
- [ ] CHK018 - Is there a scenario for upgrading an existing indexed corpus — e.g. re-indexing after a production is modified adds/removes `ROUTES_TO` edges correctly? [Coverage, Gap]
- [ ] CHK019 - Are requirements defined for the `mode=cross_service` trace path behavior after ROUTES_TO edges exist? US-3 mentions it but FR-* do not enumerate how `trace_path` uses these edges. [Coverage, Spec §US-3 vs FR-*]

---

## Edge Case Coverage

- [ ] CHK020 - FR-010 says indexing a missing/malformed `ProductionDefinition` XData MUST complete without error. Is "without error" sufficient, or should the spec say "emitting a warning to the indexing log"? [Edge Cases, Spec §FR-010]
- [ ] CHK021 - The circular routing edge case is listed but no requirement enforces it. Is cycle detection required, or only that cycles don't cause infinite loops? These have different implementation implications. [Edge Cases, Gap]
- [ ] CHK022 - What happens when the `ClassName` in an `<Item>` does not exist as a compiled class in the indexed corpus? Is it a warning, a skipped edge, or an error? [Edge Cases, Gap]

---

## Non-Functional Requirements

- [ ] CHK023 - SC-005 defines a 200ms query latency target for `ROUTES_TO` queries. Is this under what load/corpus size? A bare latency number without corpus size is not reproducible. [Non-Functional, Spec §SC-005]
- [ ] CHK024 - Are storage requirements for `ProductionItem` nodes and `ROUTES_TO` edges estimated? For large HealthShare deployments with hundreds of production items, graph size growth should be bounded. [Non-Functional, Gap]

---

## Dependencies & Assumptions

- [ ] CHK025 - The spec assumes spec-021 (storage block XML parsing) and spec-013 (DATA_FLOWS) are merged and available. Is this stated as a hard dependency in the spec? [Dependency, Assumption]
- [ ] CHK026 - The E2E test depends on careconnect-ivg-iris being up and having recent message traffic. Is the test designed to degrade gracefully (skip, not fail) when the container is unavailable? [Dependency, Assumption]
- [ ] CHK027 - The spec assumes `Ens.Production` detection via `Super LIKE '%Ens.Production%'`. Is this reliable for abstract production base classes (e.g. `HS.Util.AbstractFlashProduction`)? [Assumption]
