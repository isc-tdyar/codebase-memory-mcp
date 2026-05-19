# Research: IRIS Export XML Parser

## Decision 1: Parse XML with what?

**Chosen: Hand-written recursive descent.**

The Export format is simple enough to parse with a 300-line scanner:
- Fixed 3-level nesting (Export > Class > Member)
- Only elements we care about — unknown elements are skipped
- CDATA is the only complex construct
- No DTD, no namespaces, no processing instructions

Alternatives considered:
- **expat** (vendored in some CBM paths): adds a dependency; callback model is
  harder to reason about than a recursive descent for this fixed schema
- **yyjson** (already vendored): JSON-only, not applicable
- **libxml2**: too heavy, not vendored

## Decision 2: New language constant vs reuse

**Chosen: New `CBM_LANG_OBJECTSCRIPT_EXPORT` constant.**

Why not reuse `CBM_LANG_OBJECTSCRIPT_UDL` with a flag:
- The pipeline needs to distinguish Export files from UDL files in the extraction
  pass so it knows to call the transcoder
- A separate constant makes the classification explicit and grep-able
- Cost: one enum value, one string in language.c

## Decision 3: Transcoder output — temp file vs in-memory string

**Chosen: Arena-allocated in-memory string.**

Writing to a temp file would require file I/O, path management, and cleanup.
Arena allocation is CBM's standard pattern. The UDL for a typical Export class
is 2–20KB — trivially fits in the per-file arena.

## Decision 4: rel_path for transcoded classes

**Use original `.xml` file path with the class name appended.**

Example: `HSPTest/Reporting/Utils.xml → HSPTest.Reporting.Utils`

For multi-class exports (rare), use `file.xml[0]`, `file.xml[1]` etc.
This ensures `file_path` on graph nodes is meaningful and traceable back to
the source file, while also being unique per class.

## Decision 5: FormalSpec passthrough vs re-parse

**Passthrough as-is.**

The `<FormalSpec>` element in Export XML uses the same syntax as UDL FormalSpec:
`pArg:%Type=default,pArg2:ByRef %Type`. No translation needed. Wrap in parens
and feed to the UDL grammar directly.

## Decision 6: Storage, Projection elements

**Skip for now.**

`<Storage>` in Export XML has a complex nested structure (global maps, StreamLocation
etc.) that doesn't map cleanly to a UDL `Storage { ... }` block. Since Storage
is already extracted via %Dictionary ingest (PR 003), we'd just be adding noise.

`<Projection>` is rare and not useful for call graph analysis. Skip.

## CDATA Extraction Pattern

CDATA sections in Export XML always follow this pattern:
```xml
<Implementation><![CDATA[
    ... multi-line ObjectScript code ...
]]></Implementation>
```

The scanner looks for `<![CDATA[` literal, then reads until `]]>`. The content
between them is the method body verbatim. No entity substitution inside CDATA.

## Class Modifier Mapping

| XML element | UDL keyword |
|-------------|-------------|
| `<Abstract>1</Abstract>` | `Abstract` |
| `<Final>1</Final>` | `Final` |
| `<Deprecated>1</Deprecated>` | `Deprecated` |
| `<System>4</System>` | (skip — internal IRIS class type) |
| `<GeneratedBy>X</GeneratedBy>` | (skip — generated class metadata) |
| `<ProcedureBlock>0</ProcedureBlock>` | `[ ProcedureBlock = 0 ]` class pragma |

## Property Type Mapping

`<Type>%String</Type><Parameter name="MAXLEN" value="1000"/>` → `As %String(MAXLEN = 1000)`

Multiple `<Parameter>` children → comma-separated in parens.
`<Parameter name="X"/>` (no value) → omit from parens (default/reset).

## Index Mapping

```xml
<Index name="NameIDX">
  <Properties>Name</Properties>
  <Unique>1</Unique>
</Index>
```
→ `Index NameIDX On Name [ Unique ];`

`<PrimaryKey>1</PrimaryKey>` → `[ PrimaryKey, Unique ]`
