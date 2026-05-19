# Spec: IRIS Studio Export XML → ObjectScript UDL Transcoding

**Feature**: 015-iris-export-xml-parser
**Created**: 2026-05-19
**Priority**: P1 — real code being silently skipped in every HealthShare depot

---

## Problem

IRIS Studio XML export files (`<Export generator="Cache">`) contain complete
ObjectScript class definitions — methods, properties, parameters, indexes, XData,
triggers — in a well-defined XML format. CBM currently detects these files and
**skips them entirely** (PR 009 fix) to avoid false-positive class nodes from XML
element names. This means every method implementation inside these files is
invisible to the graph.

In hscommunity alone: **41 XML files, 212 methods** skipped.

---

## What the format looks like

```xml
<Export generator="Cache" version="25">
  <Class name="HSPTest.Reporting.Utils">
    <Super>%RegisteredObject</Super>
    <Description>Utility methods...</Description>

    <Parameter name="CubeList">
      <Default>ACTIVATIONEVENT,ENROLLMENT,...</Default>
    </Parameter>

    <Property name="Status">
      <Type>%String</Type>
      <Parameter name="MAXLEN" value="50"/>
    </Property>

    <Method name="RunAllCrawlers">
      <ClassMethod>1</ClassMethod>
      <FormalSpec>pResetOnly:%Boolean=0,pEnsMode:%Boolean=1</FormalSpec>
      <ReturnType>%Status</ReturnType>
      <Description>...</Description>
      <Implementation><![CDATA[
        Set tSC = ..ResetBaseData(pResetOnly, pEnsMode)
        Quit tSC
      ]]></Implementation>
    </Method>
  </Class>
</Export>
```

Every element maps 1:1 to a UDL construct.

---

## Approach: XML → UDL Transcoder

**Do not write a new extraction path.** Instead, transcode the XML to UDL text
and feed it to the existing UDL grammar + extraction pipeline. All existing
extraction logic (CALLS, DATA_FLOWS, type inference, macro expansion) works
automatically — no duplication.

UDL equivalent of the above:
```
Class HSPTest.Reporting.Utils Extends %RegisteredObject
{

Parameter CubeList = "ACTIVATIONEVENT,ENROLLMENT,...";

Property Status As %String(MAXLEN = 50);

/// Utility methods...
ClassMethod RunAllCrawlers(pResetOnly As %Boolean = 0, pEnsMode As %Boolean = 1) As %Status
{
    Set tSC = ..ResetBaseData(pResetOnly, pEnsMode)
    Quit tSC
}

}
```

The transcoder is ~200 lines of C. The existing 1,800-line UDL extraction path
handles everything else.

---

## Scope

### In scope:
- `<Class>`, `<Method>`, `<ClassMethod>`, `<Property>`, `<Parameter>`,
  `<Index>`, `<XData>`, `<Trigger>`, `<Storage>`, `<Query>`, `<Projection>`
- `<FormalSpec>`, `<ReturnType>`, `<Super>`, `<Description>` → docstring
- `<Implementation><![CDATA[...]]>` → method body
- Multiple `<Class>` blocks in one `<Export>` (split into separate virtual files)
- `<Abstract>`, `<Final>`, `<Deprecated>`, `<System>` class modifiers
- `<ClassMethod>1</ClassMethod>` → `ClassMethod` keyword in UDL

### Out of scope:
- `<Storage>` transcoding to UDL (Storage is already extracted via %Dictionary;
  UDL representation of Storage is complex and not needed for CALLS analysis)
- Validating XML against a schema
- Handling malformed / incomplete Export files (skip gracefully)
- CSP files embedded in Export (different format, separate feature)

---

## User Scenarios

### US1 — Method extraction from XML class (P1)
Given `HSPTest.Reporting.Utils.xml` with `<Export generator="Cache">`:
- CBM recognizes it as an IRIS export (not skipped)
- Transcodes to UDL in memory (no temp files)
- Feeds to existing UDL grammar
- Graph contains `HSPTest.Reporting.Utils` class with all methods
- `RunAllCrawlers` CALLS `ResetBaseData`, `ResetMPISearchData` etc. → CALLS edges

### US2 — Multiple classes in one Export (P2)
Given a file containing two `<Class>` elements:
- Each is transcoded independently to its own UDL string
- Each goes through extraction separately
- Both appear as Class nodes in the graph

### US3 — Property/Parameter/Index extraction (P1)
Given a class with `<Property>`, `<Parameter>`, `<Index>` children:
- Transcoded to UDL `Property`, `Parameter`, `Index` syntax
- Variable/Index/Parameter nodes created in graph same as `.cls` files

---

## Acceptance Criteria

1. All 41 XML-backed classes in hscommunity are extracted (currently 0)
2. The 212 methods within them appear as Method nodes
3. CALLS edges are produced for method bodies (same quality as UDL)
4. No regression: existing `.cls` extraction unaffected
5. Zero false-positive class nodes from XML element names (009 behavior preserved
   for non-Export XML files — only `<Export generator="Cache">` is parsed)
6. Performance: transcoding 41 files adds < 50ms to total index time

---

## Technical Design

### File classification (discover.c)

Change: instead of returning `CBM_LANG_COUNT` (skip) for Export files, return a
new language tag `CBM_LANG_OBJECTSCRIPT_EXPORT` (or reuse `CBM_LANG_OBJECTSCRIPT_UDL`
with a pre-processing hook).

Simpler: reuse `CBM_LANG_XML` but add a transcoding step in `pass_definitions.c`
and `pass_calls.c` that converts Export XML → UDL string before calling
`cbm_extract_file`.

### Transcoder: `internal/cbm/iris_export_xml.h` / `.c`

```c
// Returns arena-allocated UDL string(s) for each <Class> in the Export.
// caller_count set to number of classes found.
// Returns NULL if not an Export file or parse fails.
char **cbm_iris_export_to_udl(CBMArena *arena, const char *xml_src,
                               int xml_len, int *class_count);
```

Internally uses yyjson (already vendored) — but XML is not JSON. Use a simple
hand-written recursive-descent XML parser (Export format is simple enough: no
namespaces, no attributes on most elements, CDATA sections are the only escape
mechanism). Alternatively use the vendored expat or a 200-line recursive descent.

**Transcoding rules** (XML element → UDL fragment):

| XML | UDL |
|-----|-----|
| `<Class name="X"><Super>Y</Super>` | `Class X Extends Y` |
| `<Abstract>1</Abstract>` | `Abstract` keyword |
| `<ClassMethod>1</ClassMethod>` | `ClassMethod` prefix |
| `<FormalSpec>p As T</FormalSpec>` | `(p As T)` |
| `<ReturnType>T</ReturnType>` | `As T` |
| `<Implementation><![CDATA[code]]>` | method body `{ code }` |
| `<Property name="P"><Type>T</Type>` | `Property P As T;` |
| `<Parameter name="N"><Default>V</Default>` | `Parameter N = "V";` |
| `<Index name="I"><Properties>F</Properties>` | `Index I On F;` |
| `<XData name="N"><Data><![CDATA[...]]>` | `XData N { ... }` |

### Integration point

In `pass_definitions.c` and `pass_calls.c`, before calling `cbm_extract_file`
for a `CBM_LANG_OBJECTSCRIPT_EXPORT` file:

```c
int class_count = 0;
char **udl_strings = cbm_iris_export_to_udl(arena, src, slen, &class_count);
for (int i = 0; i < class_count; i++) {
    CBMFileResult *r = cbm_extract_file(udl_strings[i], strlen(udl_strings[i]),
                                        CBM_LANG_OBJECTSCRIPT_UDL, ...);
    // process r normally
}
```

No changes to extraction logic, graph schema, or Cypher layer.
