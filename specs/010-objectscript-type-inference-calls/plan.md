# Implementation Plan: ObjectScript Type Inference for CALLS

**Feature**: 010-objectscript-type-inference-calls
**Created**: 2026-05-16

---

## Technical Context

- **File to modify**: `internal/cbm/extract_calls.c` — the ObjectScript case in `extract_callee_lang_specific()`
- **Depends on**: 004 (basic CALLS extraction already in place)
- **No new files**: all changes in one function + a helper struct

---

## Architecture

```
handle_calls() [existing — fires for every call_node_type match]
  → extract_callee_name()
    → extract_callee_lang_specific()
      → ObjectScript case:
         if (class_method_call) → literal resolution [004, already works]
         if (instance_method_call) → TYPE MAP LOOKUP [NEW - this feature]
         if (macro) → macro name [005, already works]
```

The type map is populated DURING the same cursor walk, from earlier nodes:
1. Property declarations (`property` nodes in `class_body`) → `..PropName → Type`
2. Method parameter declarations (`arguments` → `method_arg` with `typename`) → `param → Type`
3. `Set var = ##class(X).%New()` assignments → `var → X`

---

## Data Structure

```c
typedef struct {
    const char *var_name;
    const char *class_name;
} os_type_entry_t;

typedef struct {
    os_type_entry_t entries[OS_TYPE_MAP_CAP];
    int count;
} os_type_map_t;

#define OS_TYPE_MAP_CAP 64
```

Stored in `WalkState` (the per-walk state struct in `extract_unified.c`).
Reset when entering a new method scope.

---

## Implementation Steps

### Step 1: Add type_map to WalkState

In `internal/cbm/extract_unified.c`, add `os_type_map_t` field to `WalkState`.
Reset it when `push_scope(SCOPE_FUNC)` is called (new method entered).

### Step 2: Populate type map from Set statements

In `handle_calls()` (or a new `handle_objectscript_type_tracking()` called from
the main walk loop), when visiting a `command_set` node in ObjectScript:
- Check if RHS is `##class(X).%New()` or `##class(X).%OpenId(...)`
- If yes: extract variable name from LHS, class name from RHS
- Add to type map: `{var_name, class_name}`

### Step 3: Populate from method parameters

When entering a method scope (SCOPE_FUNC push), parse the method's `arguments`
node for `<param> As <Type>` patterns. Add each typed param to the type map.

### Step 4: Populate from property types

When visiting `property` nodes in `class_body` (before method bodies), extract
`property_name` and the type from `typename` child. Add as `..PropertyName → Type`.

### Step 5: Resolve instance_method_call via type map

In `extract_callee_lang_specific()` for ObjectScript, when node type is
`instance_method_call` (or the UDL equivalent `oref_method` within an expression):
- Extract receiver variable name from the first child expression
- Look up in type map
- If found: return `"ClassName.MethodName"`
- If not found: return NULL (unresolved, silent)

---

## Files to Modify

| File | Change |
|------|--------|
| `internal/cbm/extract_calls.c` | Add type map struct, populate from Set/%New, resolve instance calls |
| `internal/cbm/extract_unified.c` | Add `os_type_map_t` to `WalkState`, reset on method entry, populate from params/properties |
| `tests/test_extraction.c` | 3 new tests: %New type, param type, property type |

---

## Tests

1. `objectscript_udl_calls_typed_new` — `Set x = ##class(A).%New()` then `x.Foo()` → CALLS to `A.Foo`
2. `objectscript_udl_calls_typed_param` — `Method Run(req As Ens.Request)` then `req.Send()` → CALLS to `Ens.Request.Send`
3. `objectscript_udl_calls_typed_property` — `Property Adapter As Ens.Adapter;` then `..Adapter.Execute()` → CALLS to `Ens.Adapter.Execute`
