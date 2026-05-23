# Spec 039: WorkMgr Parallel Queue Dispatch Resolution

**Feature**: `039-workmgr-queue-dispatch`
**Created**: 2026-05-23
**Priority**: P1 — closes the final static analysis gap surfaced by V6 Q3
**Source**: V6 benchmark — `trace_path` terminates at `MakeMRNUpToDate` because
`tQueue.Queue("##class(HS.Flash.UpdateManager).populateCacheTask", ...)` is invisible

---

## Problem

IRIS `%SYSTEM.WorkMgr` (parallel job manager) dispatches background jobs via a
literal string `"##class(ClassName).MethodName"` as the first argument to `.Queue()`:

```objectscript
Set tQueue = $system.WorkMgr.Initialize("/multicompile=1", .tStatus)
Set tSC = tQueue.Queue("##class(HS.Flash.UpdateManager).populateCacheTask", args...)
Set tSC = tQueue.WaitForComplete()
```

Static CALLS extraction sees the `.Queue()` call but cannot resolve the string argument
to a class method. Result: `trace_path` from `MakeMRNUpToDate` dead-ends — it cannot
reach `populateCacheTask` → `processStreamlet`.

Five instances in hscore 30.0, all in the Flash subsystem:
- `HS/Flash/UpdateManager.cls:126` → `HS.Flash.UpdateManager.populateCacheTask`
- `HS/Flash/Sender.cls:200` → `HS.Flash.Sender.task`
- `HS/Flash/SessionCache.cls:126` → `HS.Flash.SessionCache.outputTask`
- `HS/Flash/SessionCache.cls:1016` → `HS.Flash.SessionCache.populateTask`
- `HS/Flash/SessionCache.cls:1504` → `HS.Flash.SessionCache.ApplyMRNConsent`

This is the direct analogue of `SendRequestSync("LiteralTarget", ...)` from spec-038:
a literal string encodes a fully-qualified dispatch target.

## Fix

During source scanning in `pass_ensemble_routing.c` (or a new helper), detect the
WorkMgr queue dispatch pattern via regex and emit a `CALLS` edge with
`confidence=0.90` (literal string, high confidence — same as spec-038 literal targets).

**Regex**: `\.Queue\s*\(\s*"##class\(([^)]+)\)\.([^"]+)"`
- Group 1: class name
- Group 2: method name

**Edge type**: `CALLS` (not `ROUTES_TO` — this is a direct method invocation, not
an Ensemble component routing hop)

**Confidence**: `0.90` — literal string in source, resolves unambiguously

**Where to implement**: Add a new scan in `pass_ensemble_routing.c`'s
`resolve_method_routes()` pass, running on every Method node's source file.
Alternatively, add a new dedicated helper `scan_workmgr_dispatch()` called from the
same predump pass.

## Acceptance Criteria

1. After indexing hscore-30.0, `trace_path(MakeMRNUpToDate, outbound, depth=3)` returns
   `populateCacheTask` at hop 1
2. `trace_path(populateCacheTask, outbound, depth=2)` returns `processStreamlet`
3. The full chain `MakeMRNUpToDate → populateCacheTask → processStreamlet` is visible
   in a single `trace_path(..., depth=3)` call
4. V6 Q3 answer is now complete from CBM alone (no file reads needed)
5. 2 new unit tests: one confirming the edge exists, one confirming no false positive
   on a non-dispatch `.Queue()` call (e.g., `Ens.Queue.GetCount(...)`)

## Scope

- Only `tQueue.Queue("##class(...)...")` pattern — WorkMgr parallel dispatch
- NOT `Ens.Queue` (message queue depth queries, not method dispatch)
- NOT `##class(X).Queue(...)` (static Queue method calls, not WorkMgr dispatch)
- Pattern: receiver is a variable (`.Queue`) AND first arg is `"##class(...).method"`
