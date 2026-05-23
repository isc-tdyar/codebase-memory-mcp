# Feature Specification: Production Topology Indexing

**Feature Branch**: `038-production-topology`
**Created**: 2026-05-23
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Trace a cross-component call chain end-to-end (Priority: P1)

An agent or developer asks: "What does `HS.Flash.FHIRService.dispatchToProduction` ultimately call?"
Today, `trace_path` returns a dead end at `SendRequestSync` because the target is a config name, not a class.
With this feature, `trace_path` follows the `ROUTES_TO` edge to `HS.Flash.FHIROperations.DSTU2.OnProcessInput`
and continues from there — giving a complete, unbroken call chain across production components.

**Why this priority**: The single most common question about an Ensemble production is "what talks to what."
Without this, every cross-component trace terminates prematurely.

**Independent Test**: Index `HS.Sample.Production.EdgeGateway.SimpleProduction` (which exists in hscore-30.0),
then run `trace_path("dispatchToProduction")` — it should cross at least one component boundary via `ROUTES_TO`.

**Acceptance Scenarios**:

1. **Given** a production class with `<Item Name="HUB" ClassName="HS.Hub.HSWS.RemoteOperations">` indexed,
   **When** a method in another class calls `..SendRequestSync("HUB", ...)`,
   **Then** a `ROUTES_TO` edge exists from that method to `HS.Hub.HSWS.RemoteOperations.OnMessage` (or `OnRequest`)

2. **Given** `HS.Flash.FHIRService` has property `TargetConfigName` with `InitialExpression` matching a production item name,
   **When** `dispatchToProduction` calls `..SendRequestSync(..TargetConfigName, ...)`,
   **Then** a `ROUTES_TO` edge exists with `confidence=0.85` and `via="TargetConfigName"`

3. **Given** a `SendRequestSync("LiteralTarget", ...)` call with a literal string,
   **When** "LiteralTarget" matches an `Item.Name` in any indexed production,
   **Then** a `ROUTES_TO` edge exists with `confidence=0.95`

---

### User Story 2 — Validate static topology against runtime evidence (Priority: P1)

An agent or developer asks: "Are the `ROUTES_TO` edges accurate — do they reflect what actually runs?"
The E2E test queries `iris_interop_query` against a live IRIS production's message archive and checks that
every `ROUTES_TO` edge predicted by the static graph corresponds to at least one real message that transited
that route in production.

**Why this priority**: Without runtime validation, the static topology is unverified. The `iris_interop_query`
test is what transforms this from a graph curiosity into a trusted signal. This is the correctness proof.

**Independent Test**: With careconnect-ivg-iris running, run the E2E test suite — it should find at least one
`ROUTES_TO` edge and at least one matching message in the archive for that route.

**Acceptance Scenarios**:

1. **Given** the static graph has a `ROUTES_TO` edge from `HS.Flash.FHIRService` → `HS.Flash.FHIROperations.*`,
   **When** `iris_interop_query` is called with `what=messages` filtered to that target,
   **Then** at least one message record exists confirming the route has been exercised

2. **Given** the E2E test suite runs against careconnect-ivg-iris (localhost:19720, HSLIB),
   **When** all tests complete,
   **Then** zero `ROUTES_TO` edges exist for component pairs with no message traffic AND no `InitialExpression` default

3. **Given** `iris_interop_query` returns messages showing flow `A → B`,
   **When** the static graph is queried for `ROUTES_TO` between the classes backing items A and B,
   **Then** a `ROUTES_TO` edge exists (no false negatives for actively-used routes)

---

### User Story 3 — Query production topology directly (Priority: P2)

A developer asks: "Which production items in this production send to this business operation?"
The graph now contains `ProductionItem` nodes and `ROUTES_TO` edges queryable via `query_graph` / `trace_path`.

**Why this priority**: Once topology is indexed, direct topology queries become possible — "show me everything
that feeds into HS.Flash.FHIROperations.DSTU2" — without reading production XML.

**Independent Test**: Index a production class, then run:
`MATCH (src)-[:ROUTES_TO]->(tgt) WHERE tgt.name CONTAINS 'FHIROperations' RETURN src.name, tgt.name`
— should return at least one row.

**Acceptance Scenarios**:

1. **Given** `HS.Sample.Production.Demo.Hub` is indexed,
   **When** `query_graph` runs `MATCH (p:ProductionItem) RETURN p.name, p.class_name LIMIT 10`,
   **Then** at least one `ProductionItem` node is returned with correct `class_name`

2. **Given** a production with 3 items wired via `TargetConfigName` settings,
   **When** `trace_path` is called with `mode=cross_service` on the sending class,
   **Then** all 3 downstream classes appear in the result

---

### Edge Cases

- Production class with no `ProductionDefinition` XData: no `ProductionItem` nodes emitted, no error
- `Item.Name` in `SendRequestSync` that does not match any production item: no `ROUTES_TO` edge, no error
- Same item name used in multiple productions: `ROUTES_TO` edges created for each production separately, `production` property distinguishes them
- `TargetConfigName` property with no `InitialExpression` (set at runtime via admin UI): no `ROUTES_TO` edge created — runtime-only config is explicitly out of scope
- Circular routing (item A sends to item B which sends back to A): both edges indexed without infinite loop
- Production item `Enabled="false"`: indexed but `ROUTES_TO` edge carries `enabled=false` property

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST parse `ProductionDefinition` XData in any class extending `Ens.Production` and emit `ProductionItem` nodes for each `<Item>` element
- **FR-002**: Each `ProductionItem` node MUST carry `item_name` (the `Name` attribute) and `class_name` (the `ClassName` attribute)
- **FR-003**: The system MUST create `ROUTES_TO` edges when a method body contains `SendRequestSync` with a literal quoted string first argument that matches a known `ProductionItem.item_name`. A "literal" is a double-quoted string constant in the source text, matched via the pattern `SendRequestSync\s*\(\s*"([^"]+)"`. Variables, expressions, and unquoted identifiers are NOT literals and MUST NOT produce edges.
- **FR-004**: The system MUST create `ROUTES_TO` edges when a method's `SendRequestSync` first argument is a property accessor of the form `..PropName`, AND the parent class defines `Property PropName` with an `InitialExpression` value matching a known `ProductionItem.item_name`. Confidence for such edges is `0.85`.
- **FR-005**: `ROUTES_TO` edges MUST carry properties: `via` (setting name or "literal"), `production` (production class name), `item_name`, `confidence` (0.85 or 0.95), `enabled` (from the `Item` element)
- **FR-006**: The system MUST connect `ROUTES_TO` to the receiving class's own entry-point method (not inherited) using the resolution order: `OnProcessInput`, `OnMessage`, `OnRequest`, `OnTask` — first own method found wins. If no own entry-point method is found, the edge targets the Class node directly with `confidence -= 0.10`.
- **FR-007**: The E2E test suite MUST query the IRIS Interoperability message archive (via the iris Python native API against localhost:19720/HSLIB) and assert that every `ROUTES_TO` edge in the test corpus has at least one corroborating runtime message in the archive OR the edge was derived from an `InitialExpression` property (not runtime config). When the IRIS instance is unavailable the tests MUST skip gracefully.
- **FR-008**: HS-specific topology settings (`PatientHost`, `ConformanceOperation`) MUST be treated identically to `TargetConfigName` — same edge type, same confidence rules. Unit tests MUST cover at least one HS-specific setting explicitly.
- **FR-009**: The feature MUST NOT index runtime-only config (settings with no `InitialExpression` and no literal `SendRequestSync` callsite)
- **FR-010**: Indexing a production class MUST complete without error when the `ProductionDefinition` XData is absent or malformed. On malformed XML, all valid `<Item>` elements parsed before the error MUST still be emitted; parsing stops at the first malformed element with a warning in the indexing log.

### Key Entities

- **ProductionItem**: Represents one `<Item>` in a production. Attributes: `item_name`, `class_name`, `enabled`, `production` (parent production class name)
- **ROUTES_TO edge**: Connects a sending method to a receiving method across a production component boundary. Properties: `via`, `production`, `item_name`, `confidence`, `enabled`
- **ProductionDefinition**: The XData block in an `Ens.Production` subclass that defines the component wiring

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `trace_path` successfully crosses at least one component boundary (via `ROUTES_TO`) on 100% of the following test corpus production classes from hscore-30.0: `HS.Sample.Production.Demo.Hub`, `HS.Sample.Production.EdgeGateway.SimpleProduction`, `HS.Sample.Production.Demo.AccessGateway`. These classes MUST contain at least one topology setting with an `InitialExpression`.
- **SC-002**: Zero false-positive `ROUTES_TO` edges — every edge either has a matching runtime message in `iris_interop_query` OR has a traceable `InitialExpression` link; validated by E2E test
- **SC-003**: Zero false-negative `ROUTES_TO` edges for routes with active runtime traffic — every source→target pair seen in `iris_interop_query` message archive maps to a `ROUTES_TO` edge in the graph; validated by E2E test
- **SC-004**: Indexing overhead for a production class with 20 items adds less than 50ms to total index time, as measured by a benchmark test against a synthetic 20-item production fixture
- **SC-005**: `query_graph("MATCH (src)-[:ROUTES_TO]->(tgt) RETURN src, tgt")` returns correct results for all sample productions within 200ms, measured against the hscore-30.0 test corpus on the CI machine

---

## Assumptions

- `iris_interop_query` with `what=messages` returns sufficient history (at least 24h) on careconnect-ivg-iris for E2E validation; if the production is idle, the E2E test uses `InitialExpression` matching as the correctness signal instead
- Only `TargetConfigName`, `PatientHost`, and `ConformanceOperation` are in scope for HS-specific settings; other deployment-time settings are deferred
- The receiving class's entry-point method is resolved in priority order: `OnProcessInput` > `OnMessage` > `OnRequest` > `OnTask`; if none exists, the `ROUTES_TO` edge targets the class node directly
- Production XML parsing reuses the `$FIND`-based string extraction pattern from spec-021 (storage block) — no new XML parser required
- `Ens.Production` subclass detection uses `Super LIKE '%Ens.Production%'` pattern, same as `find_subclass_implementations`
- Cross-version behavior (spec-024): `ROUTES_TO` edges carry the `version` tag of the containing class, enabling diff queries
