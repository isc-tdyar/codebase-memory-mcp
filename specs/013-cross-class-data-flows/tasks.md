# Tasks: Cross-Class DATA_FLOWS Edges

**Feature**: 013-cross-class-data-flows
**Total tasks**: 8

---

## Phase 1: Tests (TDD)

- [ ] T001 Add `objectscript_data_flows_class_method` test: `Do ##class(MyApp.Utils).Transform(input, "JSON")` → assert call has `arg_count=2`, `args[0].expr="input"`, `args[1].expr="\"JSON\""`
- [ ] T002 Add `objectscript_data_flows_instance_method` test: `Do adapter.ExecuteQuery(sql)` (type-inferred) → assert call has `arg_count=1`, `args[0].expr="sql"`
- [ ] T003 Register tests

**Phase gate**: Tests MUST FAIL.

## Phase 2: ObjectScript argument extraction

- [ ] T004 In `handle_calls` (extract_calls.c), after resolving an ObjectScript callee: find `method_args` child of the call node, iterate its named children (skip `bracket` nodes), extract each `expression` child text as positional argument → populate `call.args[]`
- [ ] T005 Handle both `class_method_call` args (already has `method_args` in grammar) and `instance_method_call` args (via `oref_method` → `method_args`)

**Phase gate**: Both tests MUST PASS.

## Phase 3: DATA_FLOWS edge emission

- [ ] T006 In `pass_calls.c` (or `pass_route_nodes.c` extension), when writing a CALLS edge that has `arg_count > 0`: also emit a `DATA_FLOWS` edge with `args` property formatted as `"0:expr0,1:expr1,..."`
- [ ] T007 Add integration test via CLI: index fixture, query `MATCH ()-[d:DATA_FLOWS]->() RETURN d.args`, verify arg strings present

**Phase gate**: Integration test MUST PASS.

## Phase 4: Polish

- [ ] T008 Full test suite, verify on hscm depot (≥10K DATA_FLOWS edges)

---

## Dependency Order

```
T001-T003 (tests) → T004-T005 (arg extraction) → T006-T007 (edge emission) → T008 (polish)
```
