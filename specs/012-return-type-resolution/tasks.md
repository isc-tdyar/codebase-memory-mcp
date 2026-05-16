# Tasks: Return Type Resolution

**Feature**: 012-return-type-resolution
**Total tasks**: 10

---

## Phase 1: Store return types in definition nodes

- [ ] T001 In `extract_defs.c` ObjectScript method extraction, parse `return_type` → `typename` child and add `"return_type":"ClassName"` to `properties_json`
- [ ] T002 Add test: extract method with `As EnsLib.SQL.OutboundAdapter` → verify `return_type` in properties_json

**Phase gate**: Method definition nodes must carry return_type.

## Phase 2: Tests (TDD)

- [ ] T003 Add `objectscript_calls_return_type_resolution` test: two classes in same extraction — Class A has `Method GetAdapter() As EnsLib.SQL.OutboundAdapter`, Class B has `Set x = ##class(A).GetAdapter()` then `Do x.Execute()` → assert CALLS to `EnsLib.SQL.OutboundAdapter.Execute`
- [ ] T004 Add `objectscript_calls_return_type_scalar_skip` test: `Method GetName() As %String`, `Set n = ##class(X).GetName()`, `Do n.Something()` → assert NO CALLS edge (scalar types don't have methods)
- [ ] T005 Register tests

**Phase gate**: Tests MUST FAIL.

## Phase 3: Return type lookup table

- [ ] T006 Create `src/pipeline/pass_return_types.c`: query all Method nodes from graph, parse properties_json for return_type, build `{callee_qn → return_type}` hash table
- [ ] T007 Define scalar type skip list: `%String`, `%Integer`, `%Float`, `%Boolean`, `%Status`, `%Numeric`, `%Date`, `%Time`, `%TimeStamp`, `%Binary`

## Phase 4: Second-pass resolution

- [ ] T008 In `pass_return_types`, iterate CALLS edges where callee matches `##class(X).Method` (not %New/%Open): look up return type, infer variable type, re-scan file for unresolved instance calls, emit new CALLS edges
- [ ] T009 Wire `pass_return_types` into pipeline after `pass_calls`

**Phase gate**: Both tests MUST PASS.

## Phase 5: Polish

- [ ] T010 Full test suite, verify on hscm depot (≥500 new CALLS edges from return types)
