# Feature Specification: Fix ObjectScript Class Definition Line Span

**Feature Branch**: `006-fix-class-line-span`
**Created**: 2026-05-15
**Status**: Draft
**Type**: Bug fix

---

## Context

All ObjectScript `class_definition` nodes have `start_line = end_line = last_line_of_file`.
For example, `HS.FHIRServer.Storage.JsonAdvSQL.Search` (3,690 lines) shows
`start_line=3690, end_line=3690`. Methods within the same class have correct spans.

Root cause: in `extract_class_def()` in `extract_defs.c`, the ObjectScript-specific
name extraction logic (finding `class_name` via `cbm_find_child_by_kind`) returns
the `class_name` alias node — a leaf — but the `node` passed to
`ts_node_start_point(node)` is the correct `class_definition` node. The positions
are correct in the tree-sitter AST. The issue is that `walk_defs` pushes the
`class_definition` node but something in the class-name resolution path is
corrupting or replacing `node` before `start_line`/`end_line` are written.

Verified: `search_graph` returns correct spans. `query_graph` Cypher returns
wrong spans. This is a display/storage issue in how the class node's positions
are persisted.

---

## User Scenarios & Testing

### User Story 1 — Class range queries work correctly (Priority: P1)

`MATCH (n:Class) WHERE n.name = 'HS.FHIRServer.Storage.JsonAdvSQL.Search' RETURN n.start_line, n.end_line`
should return `start_line=1, end_line=3690` — not `start_line=3690, end_line=3690`.

**Acceptance Scenarios**:
1. After indexing `objectscript-coder/cleaned-code`, all Class nodes have
   `start_line < end_line`.
2. `MATCH (n:Class) WHERE n.start_line = n.end_line RETURN count(n)` returns 0.
3. `(n.end_line - n.start_line)` for a known large class (≥100 lines) equals the
   actual line count ± 2.

---

## Requirements

- **FR-001**: Every `class_definition` node MUST have `start_line` set to the line
  of the `Class` keyword and `end_line` set to the line of the closing `}`.
- **FR-002**: The fix MUST NOT affect method line spans (currently correct).
- **FR-003**: All existing tests MUST pass.
- **FR-004**: A new test MUST verify `start_line < end_line` for a multi-line class.

---

## Success Criteria

- `MATCH (n:Class) WHERE n.start_line = n.end_line RETURN count(n)` returns 0
  after indexing any ObjectScript project with multi-line classes.
- All existing 3,553+ tests pass.

---

## Root Cause Investigation Required

Before implementing, verify exactly which code path sets `start_line`/`end_line`
for ObjectScript classes. Candidate locations:
1. `extract_class_def()` in `extract_defs.c` ~line 1968
2. `compute_class_qn()` in `extract_defs.c` (the static version in `walk_defs`)
3. The `cbm_gbuf_upsert_node` call with wrong node position

The `ts_node_start_point(node).row` for `class_definition` should be 0 (line 1
in 1-indexed). If it's returning the last line, the wrong `node` variable is
being passed. Check if `node` is being shadowed or replaced by the `class_name`
child during the ObjectScript-specific name extraction.
