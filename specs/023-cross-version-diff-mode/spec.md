# Spec: Cross-Version Diff Mode

**Feature**: 023-cross-version-diff-mode  
**Created**: 2026-05-21  
**Priority**: P1 — V5 benchmark revealed this as the dominant real-world use case for HealthShare developers  
**Source**: Michael's V5 benchmark — all 5 questions were cross-version diff questions that grep beat the graph on

---

## Problem

Michael's V5 benchmark indexed both hscore 28.0 and 30.0 as separate projects (or the same project at two paths). Every question was of the form "what changed between 28.0 and 30.0?":

- Q1: "What class was ADDED in 30.0 that didn't exist in 28.0?"
- Q2: "How was class X RESTRUCTURED between versions?"
- Q3: "What property was ADDED and what macro GUARDS new behavior?"
- Q4: "What class was DELETED and what REPLACED it?"
- Q5: "What behavioral change occurred when these two lines MOVED?"

The graph currently treats 28.0 and 30.0 as separate projects with no connection. `grep` + `diff` wins because the filesystem naturally provides the answer through `find`/`diff`/`grep -rn` on two paths.

**grep wins here not because the graph is weak but because the graph has no diff semantics.** With diff semantics, the graph would be dramatically better — it can answer "what changed structurally" across ALL classes simultaneously in one query, whereas grep requires knowing what to look for first.

## What a Graph Diff Provides That grep Cannot

| Question | grep approach | Graph diff approach |
|----------|--------------|---------------------|
| "What NEW classes exist in 30.0?" | `diff <(ls 28.0) <(ls 30.0)` — only works for flat dirs | `MATCH (n:Class) WHERE n.version='30.0' AND NOT EXISTS { MATCH (m:Class {name:n.name, version:'28.0'}) } RETURN n.name` |
| "What methods MOVED between versions?" | grep + manual compare | `MATCH (m:Method {name:'MakeFHIRSession', version:'28.0'}), (n:Method {name:'MakeFHIRSession', version:'30.0'}) WHERE m.body_tokens <> n.body_tokens` |
| "What were ALL behavioral changes (not just ones I know to look for)?" | Impossible without knowing where to look | `MATCH (m:Method) WHERE m.version='30.0' AND EXISTS { MATCH (o:Method {name:m.name}) WHERE o.version='28.0' AND o.structural_profile <> m.structural_profile }` |
| "What classes changed parent class?" | `grep -r "Extends" in both, diff` — messy | `MATCH (a:Class {version:'28.0'}), (b:Class {name:a.name, version:'30.0'}) WHERE a.base_classes <> b.base_classes RETURN a.name, a.base_classes, b.base_classes` |

The graph answer to Q1-Q5 would be **one Cypher query each**, answerable in <1ms, without knowing what to look for in advance.

## Scope

### In scope

**Step 1: Version-tagged indexing**
- `index_repository` accepts a `version` parameter
- All nodes get a `version` property: `"version":"28.0"`
- Multiple versions can exist in the same project (same DB)
- `project_name` + `version` together identify a corpus

**Step 2: Diff edge generation (new pass)**
- After indexing both versions, a new pass `pass_version_diff` compares nodes with matching names across versions
- Emit `ADDED_IN` edge: node exists in new version, not in old
- Emit `REMOVED_IN` edge: node exists in old version, not in new
- Emit `CHANGED_IN` edge: node exists in both, structural_profile differs
- Store diff metadata on the edge: `from_version`, `to_version`, `change_type`

**Step 3: MCP tool `diff_versions`**
- New MCP tool: `diff_versions(project, from_version, to_version)`
- Returns: added classes, removed classes, changed methods (by structural profile delta)
- Optional `label` filter: diff only classes, or only methods, etc.

### Out of scope
- Line-level textual diff (that's `git diff`'s job)
- Semantic diff (understanding *why* something changed)
- Three-way merges

## User Scenarios

### US1 — Find all new classes in 30.0 (V5 Q1)
```cypher
MATCH (n:Class)
WHERE n.version = '30.0'
  AND NOT EXISTS {
    MATCH (m:Class) WHERE m.name = n.name AND m.version = '28.0'
  }
RETURN n.name, n.file_path
ORDER BY n.name
```
Returns: `HS.Flash.CachePurgeTask` among others. File path tells you where it is.

### US2 — Find all classes that changed parent class (V5 Q2)
```cypher
MATCH (a:Class {version:'28.0'}), (b:Class {version:'30.0'})
WHERE a.name = b.name AND a.base_classes <> b.base_classes
RETURN a.name, a.base_classes as old_parent, b.base_classes as new_parent
```
Returns: `HS.Local.ZAUTHENTICATE: HS.Util.IAuthenticate → HS.Auth.Client.Custom.ZAUTHENTICATE`

### US3 — Find all methods with changed structural profiles (V5 Q5)
```cypher
MATCH (a:Method {version:'28.0'}), (b:Method {version:'30.0'})
WHERE a.qualified_name = b.qualified_name
  AND a.structural_profile <> b.structural_profile
RETURN a.qualified_name, a.lines as old_lines, b.lines as new_lines
ORDER BY abs(b.lines - a.lines) DESC
```
Returns: `HS.ODS.FHIR.ODSSession.MakeFHIRSession` with changed profile.

### US4 — Find all deleted classes (V5 Q4)
```cypher
MATCH (n:Class {version:'28.0'})
WHERE NOT EXISTS {
  MATCH (m:Class) WHERE m.name = n.name AND m.version = '30.0'
}
RETURN n.name, n.file_path
```
Returns: `HS.Hub.Auth.Strategy`.

### US5 — MCP tool: full diff summary
```
diff_versions(project="hscore-compare", from_version="28.0", to_version="30.0")
```
Returns:
```json
{
  "added_classes": 12,
  "removed_classes": 3, 
  "changed_methods": 847,
  "added_classes_list": ["HS.Flash.CachePurgeTask", ...],
  "removed_classes_list": ["HS.Hub.Auth.Strategy", ...],
  "top_changed_files": ["HS/ODS/FHIR/ODSSession.cls", ...]
}
```

## Implementation — USE IVG (not SQLite)

**After discovering `Graph/KG/TemporalIndex.cls` in IVG, the implementation approach changes entirely.** IVG already has production-quality temporal graph infrastructure:

```
^KG("tout", timestamp, source, predicate, target) = weight  ← outbound temporal edges
^KG("tin",  timestamp, target, predicate, source) = weight  ← inbound temporal edges
^KG("bucket", bucket, source)                              ← 5-min velocity buckets
^KG("tagg", bucket, source, pred, {count/sum/min/max/hll}) ← bucket aggregates + HLL
^KG("edgeprop", ts, source, pred, target, key)             ← edge attributes
```

`TemporalIndex.InsertEdge` + `QueryWindow` are exactly what we need. Instead of building new SQLite version-diff logic, CBM should export to IVG temporal edges.

### CBM → IVG version export

After indexing each version:
```
// 28.0 indexing complete → export to IVG
timestamp_28 = unix_epoch_for("28.0")
for each class C in 28.0:
    InsertEdge(C.name, "EXISTS_IN", "hscore/28.0", timestamp=timestamp_28, attrs={base_classes, lines, methods_count})
    for each method M in C:
        InsertEdge(M.qualified_name, "METHOD_OF", C.name, timestamp=timestamp_28, attrs={structural_profile, lines})

// 30.0 indexing complete → export to IVG
timestamp_30 = unix_epoch_for("30.0")
// same pattern
```

### V5 queries become IVG temporal queries

```objectscript
// Q1: Classes in 30.0 not in 28.0
Set new28 = ##class(Graph.KG.TemporalIndex).QueryWindow("", "EXISTS_IN", ts28, ts28)
Set new30 = ##class(Graph.KG.TemporalIndex).QueryWindow("", "EXISTS_IN", ts30, ts30)
// set difference → new classes

// Q4: Classes deleted between 28.0 and 30.0  
// same, inverted

// Q2: Classes where base_classes edge attribute changed
// Compare attrs from QueryWindow for same class name between ts28 and ts30
```

### Why IVG is better than new SQLite pass

1. **Already implemented** — `TemporalIndex.cls` is production code with HLL, bucketing, velocity
2. **Time-travel queries** — "what did the graph look like at timestamp T?" is native
3. **Velocity/burst detection** — `FindBursts` finds which classes changed most between releases
4. **Streaming ingest** — `BulkInsert` handles large version exports efficiently
5. **Cross-version joins** are natural temporal window queries, not special-cased diff logic

### Revised spec for CBM side

CBM needs only:
1. `export_to_ivg` parameter on `index_repository` — triggers post-index export to IVG temporal graph
2. Version tag derived from path or explicit `version` parameter  
3. A `diff_versions` tool that queries IVG via the Bolt endpoint

The heavy lifting is entirely in IVG. CBM is the source; IVG is the temporal query engine.

## Acceptance Criteria

1. `index_repository(repo_path=".../hscore/28.0/...", project_name="hscore-compare", version="28.0")` works
2. `index_repository(repo_path=".../hscore/30.0/...", project_name="hscore-compare", version="30.0")` works
3. Both versions queryable in same project
4. `MATCH (n:Class) WHERE n.version='30.0'` returns only 30.0 classes
5. US1-US4 Cypher queries return correct results for the hscore test case
6. `diff_versions` MCP tool returns correct added/removed/changed counts
7. V5 Q1 ("new class in Flash/") answerable via graph in one query

## Why This Beats grep for V5

grep answers: "here's what I find when I look for X in path Y"
Graph diff answers: "here's everything that changed — organized by type, queryable by any property, without knowing what to look for"

Q1 with grep: find . -name "*.cls" in both dirs, diff the lists  
Q1 with graph: one Cypher query returns all new classes with file paths, complexity, line counts, call counts — immediate context for triage

Q4 with grep: `grep -rn "HS.Hub.Auth.Strategy"` in both dirs  
Q4 with graph: query returns the deleted class AND its callers AND what replaced them — one structured result

The graph doesn't win on Q1-Q5 individually. It wins on "answer ALL 5 questions for ALL versions simultaneously, ranked by impact, in <10ms" — the upgrade impact summary that a senior engineer currently needs a full day to produce manually.
