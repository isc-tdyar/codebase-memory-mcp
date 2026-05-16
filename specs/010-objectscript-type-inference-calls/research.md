# Research: ObjectScript Type Inference for CALLS

## Decision 1: Where to implement — extract_calls.c
The type map is built and consumed entirely within the ObjectScript case of
`extract_callee_lang_specific()`. When an `instance_method_call` node is encountered
whose receiver is a variable (not a literal ##class()), look it up in the type map.

The type map is populated from:
- `command_set` nodes containing `##class(X).%New()` or `##class(X).%OpenId()`
- Method `arguments` node (parameter declarations with `As <Type>`)
- Property types (from same-class Variable nodes in the graph)

## Decision 2: Type map data structure — static array on stack
```c
typedef struct {
    const char *var_name;
    const char *class_name;
} os_type_entry_t;

#define OS_TYPE_MAP_CAP 64
```
64 entries per method is more than sufficient (typical method has 3-8 typed variables).
Stack-allocated to avoid heap pressure. Overflows silently — no crash.

## Decision 3: AST node identification for Set statements
From the routine grammar parse of `Set x = ##class(A.B).%New()`:
- `command_set` node
- Child: `assignment` → `lvn` (variable name) + `expression` → `class_method_call`
- The `class_method_call` has `class_ref` → `class_name` = target type
- The method name is `%New` or `%OpenId` (type-preserving factory)

For parameter types (from method signature):
- `arguments` node → `method_arg` children with `typename` child containing the type

## Decision 4: instance_method_call node structure
```
(instance_method_call [row, col]
  (expression → lvn → objectscript_identifier = receiver var name)
  (oref_method → method_name → identifier = called method name))
```
OR in UDL:
```
Do <var>.<Method>()
```
The receiver is the first child expression, the method is in `oref_method`.

## Decision 5: Property type resolution for ..Prop.Method()
`..Adapter.ExecuteQuery()` parses as `relative_dot_method` → `oref_method`.
The `..` prefix means self — look up `Adapter` in same-class Variable nodes.
Variable nodes have `prop_type` in `properties_json` (from 007 extraction).
At call extraction time, the current class's properties are NOT in the type map
yet. Solution: pre-populate type map with `..Property` entries from the class's
field_node_types extraction (same pass, earlier in the walk).

Actually simpler: during the cursor walk, when we encounter a `property` node
(which is a sibling of `method`/`classmethod` in `class_body`), add it to the
type map as `..PropertyName → PropertyType`. This naturally happens before
method bodies are walked (properties are declared before methods in UDL).
