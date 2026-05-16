# Tasks: .inc Macro Expansion

**Feature**: 011-inc-macro-expansion
**Total tasks**: 14

---

## Phase 1: Setup — macro table structure

- [ ] T001 Create `internal/cbm/macro_table.h` with `CBMMacroEntry` (name, param_count, param_names[4], expansion) and `CBMMacroTable` (entries[4096], count) structs
- [ ] T002 Create `internal/cbm/macro_table.c` with `cbm_macro_table_add()`, `cbm_macro_table_find()`, and hardcoded `system_macro_table[]` (~20 entries)
- [ ] T003 Add `CBMMacroTable *macro_table` pointer to `CBMExtractCtx` in `cbm.h`
- [ ] T004 Add `macro_table.c` to `Makefile.cbm` source list

## Phase 2: Tests (TDD)

- [ ] T005 [P] Add `objectscript_macro_expand_system` test: source with `$$$ISERR(sc)` → assert CALLS contains `%SYSTEM.Status.IsError`
- [ ] T006 [P] Add `objectscript_macro_expand_local` test: provide .inc content defining `#define MyCheck(%sc) ##class(MyApp.Utils).Validate(%sc)`, source using `$$$MyCheck(sc)` → assert CALLS contains `MyApp.Utils.Validate`
- [ ] T007 [P] Add `objectscript_macro_constant_no_call` test: .inc defines `#define MyConst 42`, source uses `$$$MyConst` → assert NO new CALLS edge from it
- [ ] T008 Register T005-T007 tests

**Phase gate**: Tests MUST FAIL.

## Phase 3: .inc file parser

- [ ] T009 Implement `cbm_parse_inc_file(arena, file_content, table)` in `macro_table.c`: line-by-line `#define` parsing with arg extraction
- [ ] T010 Implement `cbm_macro_expand(arena, table, macro_name, args[], arg_count)` → returns expanded text with arg substitution

## Phase 4: Include resolution + macro pass

- [ ] T011 Create `src/pipeline/pass_inc_macros.c`: discover `.inc` files, parse `Include` directives from `.cls` files, build per-project macro table
- [ ] T012 Wire `pass_inc_macros` into pipeline (in `pipeline.c`) before parallel extract phase

## Phase 5: Call extraction integration

- [ ] T013 In `extract_calls.c` ObjectScript `macro` case: look up macro in `ctx->macro_table`, expand, scan expansion for `##class(X).Method` or `$$Label^Routine`, emit resolved callee

**Phase gate**: All 3 tests MUST PASS.

## Phase 6: Polish

- [ ] T014 Full test suite, build, install, verify on hscm depot (CALLS ≥ 47,600)
