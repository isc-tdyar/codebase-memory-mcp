# Tasks: IRIS %Dictionary Ingest Mode

**Feature**: 003-iris-dictionary-ingest
**Created**: 2026-05-14
**Total tasks**: 14

---

## Phase 1: Python extractor — write failing tests first

- [ ] T001 Create `tools/` directory and `tools/requirements.txt` with `intersystems-iris>=3.0.0`
- [ ] T002 [US1] [US2] Write `tests/test_iris_dict.py` with 5 tests:
  - `test_ndjson_output_format` — mock iris.connect, verify each record type emits valid JSON
  - `test_class_filter` — `--package HS.FHIRServer` excludes `%Library.*` classes
  - `test_connection_failure` — unreachable host exits 1 and emits error JSON to stderr
  - `test_multi_parent_extends` — `Super = "A|B|C"` emits 3 separate records
  - `test_all_member_types` — fixture class with method/property/parameter/query/xdata/trigger/index produces correct record types
- [ ] T007 Add `pytest` and `intersystems-iris>=3.0.0` to `tools/requirements.txt`; verify `python3 -m pytest tests/test_iris_dict.py --collect-only` shows 5 tests

**Phase gate**: `python3 -m pytest tests/test_iris_dict.py -v` — ALL 5 tests MUST FAIL (no implementation yet).

---

## Phase 2: Implement Python extractor

- [ ] T003 [P] [US1] [US2] Write `tools/iris_dict_extractor.py`:
  - argparse: `--host`, `--port`, `--namespace`, `--user`, `--pass`, `--package`, `--exclude-system` (default on)
  - `iris.connect()` with error handling → exit 1 + stderr on failure
  - 8 SQL queries (see research.md Decision 2) using `WHERE parent %STARTSWITH ?` filter
  - Stream NDJSON to stdout: one JSON record per line
  - Handle multi-parent Super field: split on `,`, emit separate `inherits` records
  - Handle encoding errors: replace binary content with `"<binary>"`, continue
  - Final `{"type":"done","count":N}` record

**Phase gate**: `python3 -m pytest tests/test_iris_dict.py -v` — ALL 5 tests MUST PASS.
**Integration check**: `python3 tools/iris_dict_extractor.py --host localhost --port 11972 --namespace USER --user _SYSTEM --pass SYS | head -5` — outputs valid NDJSON.

---

## Phase 3: CBM pipeline pass (C)

- [ ] T004 [US1] [US2] Add IRIS connection fields to `CBMPipelineCtx` in `src/pipeline/pipeline.h`:
  `char *iris_host`, `int iris_port`, `char *iris_namespace`, `char *iris_user`, `char *iris_pass`, `char *iris_package_filter`.
  Write `src/pipeline/pass_iris_dict.h` declaring `int pass_iris_dict_run(CBMPipelineCtx *ctx)`.

- [ ] T005 [US1] [US2] Write `src/pipeline/pass_iris_dict.c`:
  - `pass_iris_dict_run()`: build command string, `popen()`, read NDJSON line-by-line
  - `pass_iris_dict_process_line()`: parse JSON, dispatch to `cbm_store_upsert_node()` / `cbm_store_upsert_edge()`
  - Label mapping per research.md Decision 4
  - No-op if `ctx->iris_host` is NULL or empty
  - Log warning (not error) if Python not found or subprocess fails
  - INHERITS edges for all parents from `inherits` records

**Phase gate**: `make -j16 -f Makefile.cbm cbm` — must compile with zero errors.

---

## Phase 4: Tool schema + pipeline integration

- [ ] T006 [US1] [US2] [US3] Modify `src/mcp/mcp.c`:
  - Add `iris_host`, `iris_port`, `iris_namespace`, `iris_username`, `iris_password`, `iris_package_filter` to `index_repository` tool JSON schema
  - Parse new params from tool call and populate `CBMPipelineCtx`
  - Add `"dictionary"` as valid mode value

- [ ] T008 Modify `src/pipeline/pipeline.c`:
  - Add `#include "pass_iris_dict.h"`
  - In `CBM_MODE_FULL`: call `pass_iris_dict_run(ctx)` after `pass_definitions`
  - Add `CBM_MODE_DICTIONARY` case: call only `pass_iris_dict_run(ctx)`
  - Add `CBM_LANG_OBJECTSCRIPT_DICTIONARY` or handle dictionary-mode classes with no file_path

**Phase gate**: `make -j16 -f Makefile.cbm test` — all existing tests pass + new pass compiles.

---

## Phase 5: Integration test

- [ ] T009 [US1] Integration test using live los-iris container:
  ```bash
  make -f Makefile.cbm install
  # In new session after restart:
  # index_repository fhir-017 with iris_host=localhost iris_port=11972 iris_namespace=USER
  # Verify:
  # MATCH (n:XData) RETURN count(n) > 0
  # MATCH (n:Variable) WHERE n.member_type = 'Parameter' RETURN count(n) > 0
  # MATCH (a)-[:INHERITS]->(b) RETURN count(a) as multi_parent WHERE ... > single parent count
  ```

- [ ] T010 [US3] Test package filter: `iris_package_filter="%Library"` returns only %Library.* classes

- [ ] T011 [US2] Test dictionary-only mode: `mode="dictionary"` with no repo_path indexes successfully

- [ ] T012 [US4] Test IRIS connection failure: unreachable host → tree-sitter pass completes normally, warning logged, no crash

---

## Phase 6: Polish

- [ ] T013 Update `README.md` / tool documentation to describe `--iris-*` parameters
- [ ] T014 `make -f Makefile.cbm install` — sign + install — verify binary works

---

## Dependency Order

```
T001 (tools dir)
  → T002 (write failing tests)
    → T003 (implement extractor — tests now pass)
      → T004 (C header)
        → T005 (C implementation)
          → T006 (tool schema)
            → T008 (pipeline integration)
              → T009-T012 (integration tests)
                → T013-T014 (polish)
```

T003 and T004 are independent and can be done in parallel.

## Verification shortcut

Before writing any C code, verify the Python extractor works end-to-end:
```bash
pip install intersystems-iris
python3 tools/iris_dict_extractor.py \
  --host localhost --port 11972 --namespace USER \
  --user _SYSTEM --pass SYS \
  | python3 -c "import sys,json; [print(json.loads(l)['type']) for l in sys.stdin]" \
  | sort | uniq -c | sort -rn
```
Expected output: method, property, parameter counts dominating.
