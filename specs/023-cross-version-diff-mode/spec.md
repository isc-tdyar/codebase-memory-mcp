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

## Implementation

### Step 1: version parameter in index_repository

In `mcp.c` `handle_index_repository`:
- Add `version` string parameter (optional)
- Pass to pipeline as `ctx->version_tag`
- All extracted nodes get `version_tag` stored in `properties_json`

In the glob expansion (`handle_glob_index`):
- When `project_name` is set (all versions in one DB), auto-derive version from path component
- e.g., path contains `28.0` → version tag = `28.0`
- Override with explicit `version` parameter

### Step 2: Version-aware node properties

In `extract_defs.c` and `pass_definitions.c`:
- Store `properties_json` field `"version":"28.0"` on every node when version tag is set
- No changes to graph schema — version is just a node property like `complexity`

### Step 3: pass_version_diff

New pipeline pass that runs after both versions are indexed:
- Query: find all (Class/Method/etc.) nodes grouped by name, look for name collisions across versions
- For each collision: compare structural_profile (already extracted for methods)
- For missing names: emit ADDED_IN or REMOVED_IN tags on the node itself (`"added_in":"30.0"` property)
- This is a pure-SQL pass on the existing DB — no re-extraction needed

### Step 4: diff_versions MCP tool

New entry in `TOOLS[]` array. Implementation calls:
1. `SELECT name FROM nodes WHERE properties_json LIKE '%"version":"NEW"%' AND name NOT IN (SELECT name FROM nodes WHERE properties_json LIKE '%"version":"OLD"%')`
2. Same inverted for removals
3. Structural profile comparison for changes

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
