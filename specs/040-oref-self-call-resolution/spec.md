# Spec 040: ObjectScript Oref Self-Call Resolution

**Feature**: `040-oref-self-call-resolution`
**Created**: 2026-05-23
**Priority**: P0 — 4,023 unresolved CALLS in hscore; closes the V6 Q3 chain

## Problem

ObjectScript `..Method(args)` (relative dot method) is the standard way to call
another method on the same class. All 4,023 such calls in hscore-30.0 were
invisible to static analysis.

The grammar node type `relative_dot_method` was not in `objectscript_udl_call_types[]`.

## Fix

Two-line change:
1. `lang_specs.c`: add `"relative_dot_method"` to `objectscript_udl_call_types[]`
2. `extract_calls.c`: in `handle_calls()`, detect `relative_dot_method` and resolve
   callee as `{state->enclosing_class_qn}.{method_name}`

## Impact

- CALLS edges in hscore-30.0: **957 → 3,349** (3.5× increase)
- `MakeMRNUpToDate → populateFromCache → processStreamlet` chain now fully visible
- All 220 `..SendRequestSync` / `..SendRequestAsync` self-calls now create CALLS edges
- Closes V6 Q3 completely: chain traceable without any file reads
