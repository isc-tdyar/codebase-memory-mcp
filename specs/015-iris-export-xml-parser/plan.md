# Plan: IRIS Export XML → UDL Transcoder

## Architecture

Single new module `internal/cbm/iris_export_xml.{h,c}` containing the transcoder.
No changes to the extraction pipeline beyond:
1. Language classifier: `CBM_LANG_OBJECTSCRIPT_EXPORT` constant
2. `discover.c`: recognize `<Export generator=` files as `CBM_LANG_OBJECTSCRIPT_EXPORT`
   instead of skipping them
3. `pass_definitions.c` + `pass_calls.c`: for EXPORT files, call transcoder first,
   then pass UDL strings to existing `cbm_extract_file`

## XML Parser Choice

**Hand-written recursive descent** — the Export format is simple enough:
- No XML namespaces
- No entity references except standard `&amp;` `&lt;` `&gt;` `&quot;`
- No attributes on most elements (only `<Parameter name="X" value="Y">` has two)
- CDATA sections (`<![CDATA[...]]>`) are the only multi-line content mechanism
- Nesting depth is fixed: Export > Class > Method/Property/etc. (3 levels max)

~300 lines of C. No external dependency.

## Transcoding Phases

### Phase 1: Classify
In `discover.c`: replace the `return CBM_LANG_COUNT` for Export files with
`return CBM_LANG_OBJECTSCRIPT_EXPORT`. New constant added to `CBMLanguage` enum
in `cbm.h` (or reuse UDL with a flag — TBD in implementation).

### Phase 2: Parse & transcode
`cbm_iris_export_to_udl()` — streaming XML parse, one pass:
- On `<Class name="X">`: start accumulating a new UDL string in a CBMArena buffer
- On `<Super>`: append `Extends Y` to class header
- On `<Abstract>1`: add `Abstract` modifier
- On `<Method name="M">`: start method block, collect children
- On `<ClassMethod>1`: set flag → emit `ClassMethod` prefix
- On `<FormalSpec>`: collect content → emit `(content)` in signature
- On `<ReturnType>`: collect content → emit `As content`
- On `<Implementation><![CDATA[...]]>`: emit `{\n content \n}`
- On `<Property name="P"><Type>T</Type>`: emit `Property P As T;`
- On `<Parameter name="N"><Default>V</Default>`: emit `Parameter N = "V";`
- On `<Index name="I"><Properties>F</Properties><Unique>1</Unique>`: emit
  `Index I On F [Unique];`
- On `<XData name="N"><Data><![CDATA[content]]>`: emit `XData N { content }`
- On `</Class>`: emit closing `}`, finalize UDL string

### Phase 3: Feed to existing pipeline
In pass_definitions.c and pass_calls.c: detect `CBM_LANG_OBJECTSCRIPT_EXPORT`,
call transcoder, feed each resulting UDL string to `cbm_extract_file(...,
CBM_LANG_OBJECTSCRIPT_UDL, ...)`. Use the original file path for rel_path
(so graph nodes have correct `file_path`).

## File Structure

```
internal/cbm/
  iris_export_xml.h      — public API: cbm_iris_export_to_udl()
  iris_export_xml.c      — XML parser + UDL emitter (~300 lines)
src/discover/
  language.c             — (modify) add CBM_LANG_OBJECTSCRIPT_EXPORT to enum/table
  discover.c             — (modify) classify Export files as EXPORT not SKIP
src/pipeline/
  pass_definitions.c     — (modify) transcode before extraction
  pass_calls.c           — (modify) transcode before extraction
  pass_parallel.c        — (modify) transcode in worker
```

## Key Edge Cases

1. **Multiple `<Class>` in one Export file** — iterate, produce N UDL strings
2. **Method with no `<Implementation>`** — emit empty body `{}`
3. **CDATA spanning multiple lines** — preserve newlines in body
4. **Entity refs in descriptions** — `&amp;` → `&` etc. (only needed for docstrings)
5. **`<FormalSpec>` with ByRef/Output** — passthrough as-is (UDL uses same syntax)
6. **Empty `<Super>`** — omit Extends clause
7. **`<Super>` with comma-separated list** — `Extends (A, B, C)` with parens

## Performance

- 41 XML files in hscommunity, avg ~5KB each = ~200KB total
- One-pass parse: O(n) in file size
- Arena allocation: no malloc/free per element
- Estimated overhead: < 5ms for all 41 files
- Parallel safe: transcoder is stateless, arena-per-file

## Testing Strategy

- Unit tests: feed known XML fragments, assert exact UDL output
- Integration tests: full extract on XML fixture, assert class/method/calls nodes
- Regression: existing `.cls` extraction stats unchanged
