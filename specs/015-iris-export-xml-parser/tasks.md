# Tasks: IRIS Export XML → UDL Transcoder

**Feature**: 015-iris-export-xml-parser
**Total tasks**: 13

---

## Phase 1: Setup

- [ ] T001 Add `CBM_LANG_OBJECTSCRIPT_EXPORT` to `CBMLanguage` enum in `cbm.h`
- [ ] T002 Create `internal/cbm/iris_export_xml.h` with public API:
  `cbm_iris_export_to_udl(CBMArena*, const char* xml, int len, int* class_count) → char**`
- [ ] T003 Add `iris_export_xml.c` to `Makefile.cbm` EXTRACTION_SRCS

## Phase 2: Tests (TDD — write BEFORE implementation)

- [ ] T004 [P] Test `iris_export_xml_simple_class`: minimal Export with one method,
  assert UDL contains class name, method name, method body, Extends clause
- [ ] T005 [P] Test `iris_export_xml_classmethod`: `<ClassMethod>1</ClassMethod>` →
  UDL emits `ClassMethod` keyword, `FormalSpec` → correct args
- [ ] T006 [P] Test `iris_export_xml_property_parameter_index`: Property with Type+MAXLEN,
  Parameter with Default, Index with Unique → correct UDL syntax for each
- [ ] T007 [P] Test `iris_export_xml_calls_extracted`: full extract of XML fixture
  where method body calls `##class(X).Method()` → CALLS edge to X.Method exists
- [ ] T008 [P] Test `iris_export_xml_multi_class`: Export with two `<Class>` blocks →
  `class_count == 2`, both class names present in respective UDL strings
- [ ] T009 Register T004-T008 in test runner

**Phase gate**: all 5 tests MUST FAIL before proceeding.

## Phase 3: Transcoder implementation

- [ ] T010 Implement `iris_export_xml.c`:
  - CDATA scanner (`<![CDATA[` ... `]]>`)
  - Element content scanner (reads between `<Tag>` and `</Tag>`)
  - Attribute extractor (for `name="X"` and `value="Y"`)
  - Class-level UDL builder (header, modifiers, closing brace)
  - Method UDL builder (signature from FormalSpec + ReturnType, body from Implementation)
  - Property UDL builder (name, type, MAXLEN/parameters)
  - Parameter UDL builder (name, default)
  - Index UDL builder (name, fields, Unique/PrimaryKey)
  - XData UDL builder (name, CDATA content)
  - Multi-class iteration

**Phase gate**: T004-T006 and T008 MUST PASS. T007 (CALLS) still expected to fail.

## Phase 4: Pipeline integration

- [ ] T011 In `discover.c`: change Export file classification from `CBM_LANG_COUNT`
  (skip) to `CBM_LANG_OBJECTSCRIPT_EXPORT`
- [ ] T012 In `pass_definitions.c`, `pass_calls.c`, `pass_parallel.c`: for
  `CBM_LANG_OBJECTSCRIPT_EXPORT` files, call `cbm_iris_export_to_udl()`, then
  call `cbm_extract_file()` for each resulting UDL string with
  `CBM_LANG_OBJECTSCRIPT_UDL`

**Phase gate**: ALL 5 tests MUST PASS. Run full suite — zero regressions.

## Phase 5: Verify on real depot

- [ ] T013 Re-index hscommunity, confirm:
  - 41 new XML-backed classes appear (previously 0)
  - 212+ new Method nodes
  - CALLS edges from their method bodies
  - Non-Export XML files (dfi/ pivot/dashboard files) still correctly skipped
  - Total index time increase < 5%

---

## Dependency Order

```
T001-T003 (setup) → T004-T009 (failing tests) → T010 (transcoder) →
phase gate → T011-T012 (pipeline wiring) → phase gate → T013 (depot verify)
```
