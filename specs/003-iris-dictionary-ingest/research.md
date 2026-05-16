# Research: IRIS %Dictionary Ingest Mode

## Decision 1: Connection mechanism — Python subprocess
- **Decision**: CBM spawns `python3 cbm_iris_dict.py` as a subprocess, passes connection params as CLI args, reads newline-delimited JSON records from stdout.
- **Rationale**: `intersystems-iris` is MIT-licensed, on PyPI, zero IRIS-side installation. Python script is independently testable. C codebase stays clean.
- **Alternatives**: libirisnative C SDK (requires platform-specific .so bundling), Go/Rust sidecar (more build complexity), JDBC/JVM (too heavy).
- **Dependency**: `pip install intersystems-iris` — version 3.x+ for IRIS 2019.1+.

## Decision 2: SQL queries — 8 bulk SELECTs
Confirmed working against IRIS USER namespace via `iris.connect('localhost', 11972, ...)`:

```sql
-- 1. Classes
SELECT Name, Super, Abstract, Description
FROM %Dictionary.ClassDefinition
WHERE Name NOT LIKE '$%' AND Name NOT LIKE '%%SYS%'
-- filtered by package prefix param

-- 2. Methods
SELECT parent, Name, ReturnType, ClassMethod, FormalSpec, Description
FROM %Dictionary.MethodDefinition
WHERE parent IN (...)  -- or WHERE parent %STARTSWITH ?

-- 3. Properties
SELECT parent, Name, Type, Collection, Description
FROM %Dictionary.PropertyDefinition WHERE parent IN (...)

-- 4. Parameters
SELECT parent, Name, Type, Default, Description
FROM %Dictionary.ParameterDefinition WHERE parent IN (...)

-- 5. Queries
SELECT parent, Name, SqlName, Type, FormalSpec, Description
FROM %Dictionary.QueryDefinition WHERE parent IN (...)

-- 6. Indexes
SELECT parent, Name, Properties, Unique, Type
FROM %Dictionary.IndexDefinition WHERE parent IN (...)

-- 7. XData
SELECT parent, Name, MimeType, SchemaSpec, Data
FROM %Dictionary.XDataDefinition WHERE parent IN (...)

-- 8. Triggers
SELECT parent, Name, Event, Foreach, Code, Description
FROM %Dictionary.TriggerDefinition WHERE parent IN (...)
```

## Decision 3: Output format — newline-delimited JSON (NDJSON)
Each record is one JSON line on stdout:
```
{"type":"class","name":"HS.FHIRServer.Admin.API","super":"%CSP.REST","abstract":false}
{"type":"method","class":"HS.FHIRServer.Admin.API","name":"GetParam","return_type":"%String","class_method":true,"formal_spec":"name:%String"}
{"type":"xdata","class":"HS.FHIRServer.Admin.API","name":"UrlMap","mime_type":"application/json"}
{"type":"done","count":1247}
```
CBM reads stdout line by line, upserts into graph as stream (no buffering full output in memory).

## Decision 4: Graph label mapping
| %Dictionary type | Graph label | Notes |
|---|---|---|
| ClassDefinition | Class | existing |
| MethodDefinition | Method | existing — enriched with FormalSpec |
| PropertyDefinition | Variable | existing — member_type="Property" |
| ParameterDefinition | Variable | new — member_type="Parameter" |
| QueryDefinition | Function | new — member_type="Query" |
| IndexDefinition | new label "Index" | or Variable with member_type="Index" |
| XDataDefinition | new label "XData" | |
| TriggerDefinition | new label "Trigger" | |

## Decision 5: Package filter — default exclude system classes
Default: exclude classes starting with `%`. User can pass `--package HS.FHIRServer` to narrow scope. Python script accepts `--exclude-system` flag (on by default).

## Decision 6: Merge strategy with tree-sitter
- If tree-sitter already created a Class node: enrich it with FormalSpec, ReturnType, etc.
- If %Dictionary has a class not on disk (compiled-only): create new nodes
- Tree-sitter line numbers take priority — %Dictionary has no line info for class members

## Decision 7: Script location in CBM repo
`tools/iris_dict_extractor.py` — lives in the CBM repo, distributed alongside the binary.
CBM looks for it at: `$(dirname $argv[0])/tools/iris_dict_extractor.py`, then `$PATH`.

## Confirmed data counts (USER namespace, los-iris container)
| Member type | Count |
|---|---|
| MethodDefinition | 45,078 |
| PropertyDefinition | 21,167 |
| ParameterDefinition | 9,750 |
| QueryDefinition | 654 |
| IndexDefinition | 582 |
| XDataDefinition | 1,324 |
| TriggerDefinition | 154 |
| StorageDefinition | 681 |

## Decision 8: JSON parsing in C pass — yyjson (already vendored)
- **Decision**: Use `yyjson_read()` / `yyjson_obj_get()` to parse each NDJSON line in `pass_iris_dict.c`.
- **Rationale**: yyjson is already included in CBM (`src/ui/http_server.c` uses it). Zero new dependencies.
- **Usage**: `yyjson_doc *doc = yyjson_read(line, strlen(line), 0)` per line, then `yyjson_obj_get(root, "type")` etc.

## Decision 9: Super field delimiter is COMMA not pipe
- **Decision**: `%Dictionary.ClassDefinition.Super` uses `,` to separate multiple parents.
- **Evidence**: Live query confirmed — `%AI.MCP.Service` has `Super = "%CSP.REST,%CSP.WebSocket"`.
- **Fix applied**: Python extractor splits `super.split(',')`, not `super.split('|')`.
