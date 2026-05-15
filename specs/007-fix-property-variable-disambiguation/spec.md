# Feature Specification: Fix Variable Node Overcounting — Property/Local Disambiguation

**Feature Branch**: `007-fix-property-variable-disambiguation`
**Created**: 2026-05-15
**Status**: Draft
**Type**: Bug fix + enhancement

---

## Context

The uncleaned-code audit found 5,075 Variable nodes vs 3,850 actual Property
definitions in the source. The overcounting has two causes:

1. **Local variables in method bodies** are being extracted as class-level Variable
   nodes. The `field_node_types` for ObjectScript UDL includes `property` and
   `parameter`, but `extract_class_fields()` in `extract_defs.c` may be walking
   into method bodies and picking up local variable assignments as "fields".

2. **Missing member_type disambiguation**: Properties, Parameters, Queries, Indexes,
   Triggers, and Storage are all `class_statement` children (per grammar). The
   current extraction uses `property` and `parameter` in `field_node_types`, but
   the `class_statement` unwrapping introduced in feature 001 may be matching more
   nodes than intended.

Additionally, `Query`, `Index`, `Trigger`, `Storage`, and `XData` class members
are NOT extracted from `.cls` source files (only available via `%Dictionary` in
feature 003). These should be extractable from UDL source directly since the
tree-sitter grammar has all their node types as `class_statement` children.

---

## User Scenarios & Testing

### User Story 1 — Accurate Property counts (Priority: P1)

After indexing the uncleaned-code project, Variable node count should match
actual Property + Parameter definitions, not exceed them.

**Acceptance Scenarios**:
1. `MATCH (n:Variable) RETURN count(n)` returns a count ≤ actual Properties
   + Parameters in source (within 5% of `%Dictionary` count for same namespace).
2. Local variables inside method bodies do NOT appear as Variable nodes.
3. `MATCH (n:Variable) WHERE n.member_type = 'Property' RETURN n.name, n.file_path`
   returns only class-level properties, not local method variables.

---

### User Story 2 — Complete class member extraction from source (Priority: P2)

All UDL class member types extractable from `.cls` source without needing a live
IRIS connection. After this feature, `class_statement` children produce nodes for
their respective types: Query → Function, Index → Index, Trigger → Trigger,
XData → XData, Storage → Storage.

**Acceptance Scenarios**:
1. A `.cls` file with `Query FindAll(name As %String) As %Query { ... }` produces
   a `Function` node named `FindAll` with `member_type=Query`.
2. A `.cls` file with `Index NameIdx On Name;` produces an `Index` node.
3. A `.cls` file with `XData UrlMap { ... }` produces an `XData` node.

---

## Requirements

- **FR-001**: Local variables (assignments within method bodies) MUST NOT be
  extracted as Variable nodes. Only `property` and `parameter` nodes that are
  **direct children of `class_statement` → direct children of `class_body`** should
  produce Variable nodes.
- **FR-002**: All 12 `class_statement` child types MUST be extracted from `.cls`
  source: `classmethod`, `method`, `property`, `parameter`, `query`, `index`,
  `xdata`, `trigger`, `storage`, `foreignkey`, `projection`, `relationship`.
- **FR-003**: Label mapping from `class_statement` child type to graph label:
  - `property`, `parameter` → `Variable` (with `member_type` in properties_json)
  - `query` → `Function` (with `member_type=Query`)
  - `index` → `Index`
  - `xdata` → `XData`
  - `trigger` → `Trigger`
  - `storage` → `Storage`
  - `foreignkey` → `Variable` (with `member_type=ForeignKey`)
  - `projection`, `relationship` → `Variable` (with appropriate `member_type`)
- **FR-004**: All existing tests MUST pass. Variable node count on existing test
  fixtures MUST NOT increase (only decrease or stay same for Properties/Parameters).

---

## Success Criteria

- `MATCH (n:Variable) RETURN count(n)` on uncleaned-code decreases from 5,075
  to within 5% of the `%Dictionary` count for the same namespace.
- All 12 class member types produce the correct graph label.
- All existing 3,553+ tests pass.
- New tests cover at least: property extraction, query extraction, index extraction,
  local-variable non-extraction.
