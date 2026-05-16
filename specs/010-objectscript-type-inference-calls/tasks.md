# Tasks: ObjectScript Type Inference for CALLS Edges

**Feature**: 010-objectscript-type-inference-calls
**Created**: 2026-05-16
**Total tasks**: 12

---

## Phase 1: Setup — type map data structure

- [X] T001 Define `os_type_entry_t` and `os_type_map_t` structs in `internal/cbm/extract_calls.c` (static, file-scoped): `{var_name, class_name}` pairs, `OS_TYPE_MAP_CAP=64`, stack-allocated
- [X] T002 Add `os_type_map_t os_type_map` field to `WalkState` in `internal/cbm/extract_unified.c` and reset it to zero when `push_scope(SCOPE_FUNC)` fires for ObjectScript languages

---

## Phase 2: Tests (TDD — write failing tests first)

- [X] T003 [P] [US1] Add `objectscript_udl_calls_typed_new` test in `tests/test_extraction.c`: source with `Set x = ##class(A.B).%New()` then `Do x.Foo()` → assert CALLS callee contains `A.B.Foo`
- [X] T004 [P] [US2] Add `objectscript_udl_calls_typed_param` test in `tests/test_extraction.c`: source with `Method Run(req As Ens.Request) { Do req.Send() }` → assert CALLS callee contains `Ens.Request.Send`
- [X] T005 [P] [US3] Add `objectscript_udl_calls_typed_property` test in `tests/test_extraction.c`: source with `Property Adapter As Ens.Adapter;` and method body `Do ..Adapter.Execute()` → assert CALLS callee contains `Ens.Adapter.Execute`
- [X] T006 Register T003-T005 tests with `RUN_TEST()` in `tests/test_extraction.c`

**Phase gate**: All 3 new tests MUST FAIL before T007 (confirming they test the right thing).

---

## Phase 3: US1 — %New() constructor type resolution (P1)

- [X] T007 [US1] In `internal/cbm/extract_calls.c`, add `os_type_map_add()` helper: appends `{var_name, class_name}` to map if not full
- [X] T008 [US1] In `internal/cbm/extract_unified.c`, add `handle_objectscript_set_type()`: when visiting a `command_set` node in ObjectScript, check if RHS contains `class_method_call` with method name `%New` or `%OpenId` — if yes, extract LHS variable name and RHS class name, call `os_type_map_add()`
- [X] T009 [US1] In `internal/cbm/extract_calls.c`, modify ObjectScript case of `extract_callee_lang_specific()`: for `instance_method_call` nodes, extract receiver variable name, look up in `state->os_type_map`, if found return `"ClassName.MethodName"`

**Phase gate**: `objectscript_udl_calls_typed_new` test MUST PASS.

---

## Phase 4: US2 — Method parameter type resolution (P1)

- [X] T010 [US2] In `internal/cbm/extract_unified.c`, when entering method scope (`push_scope(SCOPE_FUNC)` for ObjectScript), parse the method's `arguments` node for typed parameters (`<name> As <Type>` pattern) and populate `os_type_map` with each typed param

**Phase gate**: `objectscript_udl_calls_typed_param` test MUST PASS.

---

## Phase 5: US3 — Property type resolution (P2)

- [X] T011 [US3] In `internal/cbm/extract_unified.c`, when visiting `property` nodes in ObjectScript class body (before method bodies in document order), extract property name and `typename` child text, add to type map as `..PropertyName → Type`

**Phase gate**: `objectscript_udl_calls_typed_property` test MUST PASS.

---

## Phase 6: Polish

- [X] T012 Build, run full test suite (`make -j16 -f Makefile.cbm test`), sign and install (`cbm-install`), push to fork

---

## Dependency Order

```
T001 → T002 → T003-T006 (parallel, tests)
  → T007 → T008 → T009 (US1 — %New type)
    → T010 (US2 — param types)
      → T011 (US3 — property types)
        → T012 (polish)
```

## Implementation Strategy

**MVP = T001-T009** (US1 only — %New() constructor resolution). This alone covers the highest-frequency type pattern in HealthShare code. US2 and US3 are incremental additions that share the same type map infrastructure.

**Verification shortcut** (before writing tests):
```bash
# Create test fixture, index, check CALLS
cat > /tmp/type_test/Caller.cls << 'CLS'
Class MyApp.Caller Extends %RegisteredObject
{
Method Run() As %Status
{
    Set adapter = ##class(EnsLib.SQL.OutboundAdapter).%New()
    Do adapter.ExecuteQuery("SELECT 1")
    Quit $$$OK
}
}
CLS
cbm-install && codebase-memory-mcp cli index_repository '{"repo_path":"/tmp/type_test","mode":"full"}'
# Check: CALLS should include adapter → EnsLib.SQL.OutboundAdapter.ExecuteQuery
```
