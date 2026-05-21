# Spec: Storage Block XML Parsing

**Feature**: 021-storage-block-parsing  
**Created**: 2026-05-21  
**Priority**: P1 — caused wrong answer in Michael's V3 benchmark Q1  
**Source**: Michael's V3 Q1 + Q4. Research: docs.intersystems.com/GOBJ_storage, grongierisc/iris-persistence schema.py

---

## Research Findings (added after docs + Guillaume's code review)

### From ISC docs (GOBJ_storage)
The `Storage Default` block is the **authoritative runtime source** for storage metadata. The storage compiler reads `%Dictionary.StorageDefinition.ExtentSize`, not `%Dictionary.ClassDefinition.Parameter("EXTENTSIZE")`. The class parameter is cosmetic — it doesn't affect compilation or query optimization.

Fields in the Storage block XML:
- `<ExtentSize>` — optimizer row-count estimate (this is what the runtime uses)
- `<DataLocation>` — actual global for row data (`^ClassName.D`)
- `<IdLocation>` — ID counter global
- `<IndexLocation>` — index globals
- `<StreamLocation>` — stream data globals
- `<Type>` — storage adapter (`%Storage.Persistent`, `%Storage.Serial`)

### From grongierisc/iris-persistence (schema.py STORAGE_KEYS)
Guillaume's `STORAGE_KEYS` tuple confirms our field list. He reads them via `%Dictionary.StorageDefinition` at runtime. For source-only analysis, we parse the Storage XData XML.

Key from his `_insert_storage_sql_maps`: **`StorageSQLMapDefinition.Global`** is the actual global name used in SQL maps — the source of hash-truncated names like `^HS.SDA3.Strea2F54` (V3 Q4). Extracting this directly answers "what global does this SQL map actually use?" without live IRIS.

Also: Guillaume reads `StorageStrategy` to find the **active** storage block. A class can have multiple Storage blocks; only the one matching `StorageStrategy` (usually "Default") is the live one. We should only extract the "Default" storage block.

---

## Problem

`Storage Default` blocks in ObjectScript UDL contain structured XML with fields like
`<ExtentSize>`, `<DataLocation>`, `<IdLocation>`, `<IndexLocation>`, `<StreamLocation>`.
These are stored as `XData` nodes in the graph (name only) — the XML content is not
parsed.

The V3 Q1 trap: `Parameter EXTENTSIZE = 100000000` (100M) vs `<ExtentSize>10000000`
(10M) in the Storage block. The storage compiler uses the Storage block value, not
the class parameter. The agent saw the Parameter node with 100M and reported it as
authoritative — **wrong**. The Storage block's value (10M) is what IRIS actually uses.

## What exists today

Storage nodes are extracted with name ("Default") and label ("Storage") and
start/end lines. No XML content is parsed. The `%Dictionary` ingest (003) gets storage
names from `%Dictionary.StorageDefinition` but not the XML fields within.

## Scope

### In scope
- Parse `Storage Default` XData block XML
- Extract: `<ExtentSize>`, `<DataLocation>`, `<IdLocation>`, `<IndexLocation>`,
  `<StreamLocation>`, `<Type>` (the storage adapter class)
- **NEW from research**: Extract SQL map global names from `<SQLMap><Global>` elements → `sql_map_globals` property
- Store as properties on the Storage node: `extent_size`, `data_global`, `id_global`, 
  `index_global`, `stream_global`, `type`, `sql_map_globals` (space-separated)
- **Only extract the active "Default" storage block** (the one matching `StorageStrategy`, typically "Default")
- Applies to UDL `.cls` files and IRIS Export XML (`.xml`)

### Out of scope
- Full storage descriptor parse (subscript maps, extent queries)
- Custom storage adapters (non-default storage types)
- Deprecated storage formats (pre-Cache 2007)

## User Scenarios

### US1 — EXTENTSIZE mismatch detection (V3 Q1)
Query: `MATCH (c:Class {name:'HS.SDA3.Streamlet.Flash'})-[:DEFINES]->(s:Storage) RETURN s.extent_size`  
Returns: `10000000` — the compiled-authoritative value, not the class parameter value

Cross-check: `MATCH (c:Class {name:'HS.SDA3.Streamlet.Flash'})-[:DEFINES]->(p:Parameter {name:'EXTENTSIZE'}) RETURN p.default`  
Returns: `100000000` — they differ → the graph itself reveals the mismatch

### US2 — Find all classes where EXTENTSIZE parameter ≠ Storage block ExtentSize
```cypher
MATCH (c:Class)-[:DEFINES]->(p:Parameter {name:'EXTENTSIZE'}),
      (c)-[:DEFINES]->(s:Storage)
WHERE p.default <> s.extent_size
RETURN c.name, p.default as param_value, s.extent_size as storage_value
```

### US3 — Find classes sharing a global name (storage collision risk)
```cypher
MATCH (s1:Storage), (s2:Storage)
WHERE s1.data_global = s2.data_global AND s1 <> s2
RETURN s1.qualified_name, s2.qualified_name, s1.data_global
```

## Acceptance Criteria

1. `HS.SDA3.Streamlet.Flash` Storage node has `extent_size = 10000000`
2. The class's EXTENTSIZE Parameter node has `default = 100000000`  
3. The mismatch query (US2) returns Flash in its result set
4. `data_global` is populated for classes with explicit `<DataLocation>` in Storage
5. No regression on existing Storage name/line extraction

## Implementation

The Storage block in UDL parses as:

```
storage → storage_name + xdata_block
xdata_block → <Data><![CDATA[<Storage default="1"><Type>...</Type><DataLocation>...</DataLocation><ExtentSize>N</ExtentSize>...]]></Data>
```

The CDATA content is XML. After extracting the XData text (same as 015 iris_export_xml
does for `<Data>` content), parse the XML fields with the same hand-written element
content scanner we have in `iris_export_xml.c`.

Extract: `<ExtentSize>`, `<DataLocation>`, `<IdLocation>`, `<IndexLocation>`,
`<StreamLocation>` → store in `properties_json` on the Storage node.

Reuse `elem_content()` from `iris_export_xml.c` — or factor it into a shared
`cbm_xml_elem()` utility. The CDATA → XML parse is already working in 015.
