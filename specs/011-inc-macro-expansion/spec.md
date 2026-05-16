# Spec: .inc Macro Expansion for CALLS

**Feature**: 011-inc-macro-expansion
**Created**: 2026-05-16
**Priority**: P1 — highest remaining call graph gap
**References**: Builds on 004 (static calls) and 005 (macro name extraction)

---

## Problem

ObjectScript `$$$Macro` calls are currently extracted as literal callee names
(e.g., `$$$ISERR` appears as a CALLS edge target). This works for text search
but doesn't resolve the actual function being called. In Ensemble/HealthShare
code, `$$$` macros account for ~25% of all function-like invocations (25K+
in a typical depot).

Common patterns:
- `$$$ISERR(sc)` → expands to `$System.Status.IsError(sc)` → CALLS to `%SYSTEM.Status.IsError`
- `$$$ThrowStatus(sc)` → expands to `$$$GENERATE(...)` chain → complex
- `$$$HSCMDocumentActive` → expands to literal `1` → no call (constant)
- `$$$HSCMConfigGetSetting(x,y)` → expands to `$get(^HSCM.Config.Settings(x),y)` → global ref

## Scope

### In scope:
1. Parse `.inc` files to build a macro definition table (`name → expansion text`)
2. Locate `.inc` files by resolving `Include <name>` directives in `.cls` files
3. For macro invocations (`$$$Name(args)`), substitute the expansion
4. If the expansion contains a function/method call, emit that as the CALLS callee
5. Constant macros (expand to literals) produce no CALLS edge — correct behavior

### Out of scope:
- Nested macro expansion beyond 1 level (diminishing returns)
- System macros from IRIS itself (`%occStatus.inc`, `%occErrors.inc`) — these
  aren't in the customer depot. Provide a hardcoded table for the top ~20.
- Conditional compilation (`#if`, `#ifdef`) — treat all `#define` as active

## User Scenarios

### US1 — Local .inc expansion (P1)
Given a class `Include HSCM.Config.Include` and body using `$$$HSCMConfigGetSetting("key","default")`:
- CBM finds `HSCM/Config/Include.inc` (or `HSCM.Config.Include.inc`) in the repo
- Parses `#define HSCMConfigGetSetting(%setting,%default) $get($$$HSCMConfigSettings(%setting),%default)`
- Resolves `$$$HSCMConfigGetSetting` to its expansion
- Since expansion is `$get(...)` (intrinsic function), no CALLS edge — correct

### US2 — System macro table (P1)
Given a class using `$$$ISERR(sc)`:
- CBM looks up `ISERR` in the hardcoded system macro table
- Finds expansion → `$System.Status.IsError`
- Emits CALLS edge to `%SYSTEM.Status.IsError`

### US3 — Macro calls another class method (P2)
Given `.inc` with `#define MyCheck(%sc) ##class(MyApp.Utils).Validate(%sc)`:
- Expansion contains `##class(MyApp.Utils).Validate` → emit CALLS edge

## Acceptance Criteria

1. Total CALLS edges on HealthShare hscm depot increases by ≥ 5% over feature 010 baseline (45,391)
2. `$$$ISERR`, `$$$OK`, `$$$ThrowStatus` resolve to their %SYSTEM targets
3. Local `.inc` files are discovered via `Include` directives
4. No performance regression: index time increase < 10% (macro pass is fast)
5. Missing `.inc` files degrade gracefully — no crash, no false edges

## Technical Constraints

- `.inc` file format: `ROUTINE <name> [Type=INC]` header, then `#define Name(args) expansion`
- `Include` directive in UDL: `Include <dotted.name>` → find `<dotted/name>.inc` or `<dotted.name>.inc`
- Multiple includes: `Include (A, B, C)` → load all three
- Macro args: `%argname` in definition, positional substitution at call site
- Self-referential macros: `$$$HSCMDocumentActions` uses `$$$HSCMDocumentActionUpload` — need table populated before expansion
- System macros (hardcoded): ~20 entries covering `%occStatus`, `%occErrors`, `%occMessages`
