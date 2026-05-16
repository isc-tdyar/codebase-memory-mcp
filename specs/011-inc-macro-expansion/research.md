# Research: .inc Macro Expansion

## Decision 1: Where does the macro table live?

On `CBMExtractCtx` as a pointer to a shared table (arena-allocated, built once per project).
The table is populated by `pass_inc_macros` before extraction starts, then read-only
during the parallel extract phase. Thread-safe since it's immutable after build.

## Decision 2: .inc file discovery strategy

Two-pass approach:
1. During file discovery, collect all `.inc` files found in the repo tree
2. For each `.cls` file's `Include` directive, resolve the name to a discovered `.inc` path

Name resolution: `Include HSCM.Config.Include` tries:
- `HSCM/Config/Include.inc` (slash-separated)
- `HSCM.Config.Include.inc` (dot-preserved)
- Case-insensitive match if exact match fails

If not found in repo, check system macro table (hardcoded).

## Decision 3: #define parsing grammar

No tree-sitter needed. Line-by-line text parsing:
```
#define NAME expansion_text
#define NAME(%arg1,%arg2) expansion_text_with_%arg1_and_%arg2
```

Rules:
- Skip lines starting with `#;` (comments)
- Skip `ROUTINE ... [Type=INC]` header
- `#define` followed by identifier, optional `(params)`, then rest of line is expansion
- Multi-line continuations: not standard in ObjectScript .inc (each #define is one line)

## Decision 4: Expansion → callee extraction

After substituting args into expansion text, scan for:
- `##class(ClassName).MethodName` → callee = `ClassName.MethodName`
- `$$Label^Routine` → callee = `Label^Routine` (routine tag call)
- `$System.Cls.Method` → callee = `%SYSTEM.Cls.Method`

If none found, expansion is a value expression (no CALLS edge).

## Decision 5: System macro hardcoded table

Top ~20 from %occStatus.inc and %occErrors.inc:
```c
{"OK",       0, "$$$OK",                   NULL},          // literal 1 — no call
{"ISERR",    1, "$System.Status.IsError",  "%SYSTEM.Status.IsError"},
{"ISOK",     1, "$System.Status.IsOK",     "%SYSTEM.Status.IsOK"},
{"ThrowStatus", 1, NULL,                   "%SYSTEM.Status.ThrowStatus"},
{"ERROR",    1, NULL,                      "%SYSTEM.Status.Error"},
{"ADDSC",    2, NULL,                      "%SYSTEM.Status.AppendStatus"},
```

Only populate the `callee` column — the expansion text is optional context.
