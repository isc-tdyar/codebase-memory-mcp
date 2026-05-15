# Implementation Plan: IRIS %Dictionary Ingest Mode

**Feature**: 003-iris-dictionary-ingest
**Created**: 2026-05-14
**Status**: Ready for implementation

---

## Technical Context

- **CBM language**: C binary (`src/pipeline/`, `internal/cbm/`)
- **IRIS connector**: Python subprocess (`tools/iris_dict_extractor.py`) using `intersystems-iris` PyPI package
- **No IRIS-side installation** — read-only SQL queries only
- **No Atelier REST** — IRIS native protocol port 1972 only
- **No new C dependencies** — CBM uses `popen()` to spawn Python subprocess

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `tools/iris_dict_extractor.py` | New — Python script, 8 SQL queries, NDJSON output |
| `tools/requirements.txt` | New — `intersystems-iris>=3.0.0` |
| `src/pipeline/pass_iris_dict.c` | New — CBM pipeline pass, spawns Python, reads NDJSON |
| `src/pipeline/pass_iris_dict.h` | New — header |
| `src/pipeline/pipeline.c` | Modified — add `pass_iris_dict` to `full` + `dictionary` modes |
| `src/mcp/mcp.c` | Modified — add `iris_host`, `iris_port`, `iris_namespace`, `iris_username`, `iris_password`, `iris_package_filter` to `index_repository` tool params |
| `tests/test_iris_dict.py` | New — Python unit tests for the extractor script |

---

## Phase 1: Python extractor (`tools/iris_dict_extractor.py`)

The script:
1. Accepts `--host`, `--port`, `--namespace`, `--user`, `--pass`, `--package` CLI args
2. Connects via `iris.connect(host, port, namespace, user, password)`
3. Runs 8 SQL queries — one per `%Dictionary.*Definition` table
4. Streams NDJSON to stdout, one record per line
5. Exits 0 on success, 1 on connection failure (writes error JSON to stderr)

**Key SQL queries**: see research.md Decision 2.

**Output format**: see research.md Decision 3.

**Error handling**:
- Connection refused → `{"type":"error","message":"Connection refused to host:port"}` on stderr, exit 1
- Permission denied on a table → skip that table, emit warning, continue
- Encoding error in a field → replace with `<binary>`, continue

---

## Phase 2: CBM pipeline pass (`src/pipeline/pass_iris_dict.c`)

```c
// Core function
int pass_iris_dict_run(CBMPipelineCtx *ctx) {
    if (!ctx->iris_host || !ctx->iris_host[0]) return CBM_OK; // skip if no IRIS params
    
    // Build command: python3 tools/iris_dict_extractor.py --host ... 
    char cmd[CBM_SZ_4K];
    snprintf(cmd, sizeof(cmd),
        "python3 \"%s/tools/iris_dict_extractor.py\" "
        "--host \"%s\" --port %d --namespace \"%s\" "
        "--user \"%s\" --pass \"%s\" --package \"%s\"",
        ctx->cbm_dir, ctx->iris_host, ctx->iris_port,
        ctx->iris_namespace, ctx->iris_user, ctx->iris_pass,
        ctx->iris_package_filter ? ctx->iris_package_filter : "");
    
    FILE *pipe = popen(cmd, "r");
    if (!pipe) { /* log warning, return OK */ return CBM_OK; }
    
    char line[CBM_SZ_64K];
    while (fgets(line, sizeof(line), pipe)) {
        pass_iris_dict_process_line(ctx, line);
    }
    pclose(pipe);
    return CBM_OK;
}
```

`pass_iris_dict_process_line()` parses each NDJSON line and calls `cbm_store_upsert_node()` or `cbm_store_upsert_edge()` as appropriate.

**Merge logic**:
- `type="class"` → `cbm_store_upsert_node()` with label `Class` — enriches existing tree-sitter node or creates new one
- `type="method"` → `cbm_store_upsert_node()` with label `Method` — enriches with `FormalSpec`, `ReturnType`
- `type="parameter"` → `cbm_store_upsert_node()` with label `Variable`, `member_type=Parameter`
- `type="query"` → `cbm_store_upsert_node()` with label `Function`, `member_type=Query`
- `type="xdata"` → `cbm_store_upsert_node()` with label `XData`
- `type="trigger"` → `cbm_store_upsert_node()` with label `Trigger`
- `type="index"` → `cbm_store_upsert_node()` with label `Index`
- `type="storage"` → `cbm_store_upsert_node()` with label `Storage`
- INHERITS edges: emit for each `|`-separated parent in `super` field

---

## Phase 3: `index_repository` tool schema update (`src/mcp/mcp.c`)

Add to `index_repository` tool parameters:
```json
{
  "iris_host": "IRIS host for %Dictionary ingest (optional)",
  "iris_port": "IRIS superserver port, default 1972",
  "iris_namespace": "IRIS namespace, default USER",  
  "iris_username": "IRIS username, default _SYSTEM",
  "iris_password": "IRIS password",
  "iris_package_filter": "Only index classes starting with this prefix e.g. 'HS.FHIRServer'"
}
```

Add `mode="dictionary"` to the list of valid modes (dictionary-only, no tree-sitter pass).

---

## Phase 4: Pipeline integration (`src/pipeline/pipeline.c`)

Add `pass_iris_dict_run()` call:
- In `CBM_MODE_FULL`: run after `pass_definitions`, before `pass_semantic`
- In `CBM_MODE_DICTIONARY` (new): run `pass_iris_dict` only, skip tree-sitter

---

## Build & Verify

```bash
cd /Users/tdyar/ws/codebase-memory-mcp

# Test Python extractor standalone
python3 tools/iris_dict_extractor.py \
  --host localhost --port 11972 --namespace USER \
  --user _SYSTEM --pass SYS --package HS.FHIRServer \
  | head -20

# Build CBM with new pass
make -j16 -f Makefile.cbm cbm

# Run tests
make -j16 -f Makefile.cbm test
python3 -m pytest tests/test_iris_dict.py -v

# Full integration test
make -f Makefile.cbm install
# Restart OpenCode to pick up new binary
# Then: index_repository with iris params on fhir-017
```

---

## PR scope

This PR targets the upstream `main` branch (DeusData/codebase-memory-mcp).
It adds optional IRIS connectivity — zero breaking changes for existing users who don't pass `--iris-*` params.
New labels (`XData`, `Trigger`, `Index`, `Storage`) extend the graph schema without breaking existing queries.
