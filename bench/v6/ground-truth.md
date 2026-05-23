# V6 Ground Truth — hand-verified 2026-05-23

Corpus: hscore 30.0. CBM DB indexed with spec-019+038. IAD: careconnect-ivg-iris/HSLIB.

---

## Q1. Flash routing topology

**Full answer (2 points):**

From `ROUTES_TO` graph query — 30 edges touching Flash-namespace methods:

**Literal targets (conf=0.95, rendered as 0.85 after no-entry-point fallback):**
- `"HUB"` — routes from `OnProcessInput`, `AuditRequest`, `FHIRAuditRequest`,
  `AddUpdateFlash`, `LoadMPIID`, `SynchronizeGateway`, `PatientFlashFetch` etc.
- `"HS.Flash.LoadingManager"` — from `AuditRequest`, `PatientFlashFetch`, `RecordAudit`

**Property-based targets (conf=0.75 after fallback):**
- `GatewayOperations` (prop, InitialExpression="GATEWAY") — from `MakeMRNUpToDate`,
  `LoadMPIID`, `DeleteFlashAndFlashVersions`, `DeletePatient`, `TerminologySetup` etc.
- `ConsentProcessor` (prop, InitialExpression="HS.Consent.MPIEngine") — from all
  `FlashEvaluationRequest`, `FlashResendRequest`, `SendFlashEvaluationRequest` variants

**Token cost CBM+IAD:** ~540 tokens (ROUTES_TO query + 30-row result)
**Token cost grep/read:** ~9,400 tokens (3 files)

**Partial (1 point):** Correctly lists literals vs property targets but misses some entries.
**Wrong (0):** Confuses which targets are literal vs property.
**Hallucination penalty (−1):** Fabricates targets not in graph.

---

## Q2. End-to-end config-name resolution

**Full answer (2 points):**

Step 1 — `EnsembleItem` query: `"HUB"` resolves to `HS.Hub.HSWS.RemoteOperations` in **14
distinct sample productions** across the FlashProduction, BusProduction, SimpleProduction
variants, etc.

Step 2 — `HS.Hub.HSWS.RemoteOperations` is a BusinessOperation (no MessageMap). It handles
messages through `OnMessage` or `OnRequest` (standard BO entry points, not a routed BP).
The `PatientSearchRequest` sent via `SendRequestSync("HUB", ...)` in `WebServices.cls:42`
goes directly to this operations class's entry point method.

**Key insight:** `"HUB"` is a consistent convention across all Flash/AccessGateway
productions — always resolves to `HS.Hub.HSWS.RemoteOperations`. The graph makes this
cross-production consistency visible in one query; grep requires reading each production XML.

**Token cost CBM+IAD:** ~840 tokens (EnsembleItem query 14 rows + class lookup)
**Token cost grep/read:** ~7,000 tokens (sample production XMLs + target class)

---

## Q3. UpdateManager complete routing table

**Full answer (2 points):**

`extract_message_map_routing("HS.Flash.UpdateManager")` returns:
- `HS.Message.FlashQueueUpdate → MakeMRNUpToDate`
- `HS.Message.FlashLoadMPIIDSync → LoadMPIID`

**Full chain to processStreamlet** (with spec-039 + spec-040):

```
FlashQueueUpdate
  → MakeMRNUpToDate        [MessageMap, extract_message_map_routing]
  → populateFromCache      [CALLS, hop=1, resolved by spec-040 ..oref fix]
  → processStreamlet       [CALLS, hop=2, resolved by spec-040]
  → populateCacheTask      [CALLS, hop=2, resolved by spec-039 WorkMgr.Queue]
```

`trace_path(MakeMRNUpToDate, outbound, depth=4)` now returns `processStreamlet` at hop=2.

**Token cost CBM+IAD:** ~130 tokens (extract_message_map + trace_path result)
**Token cost grep/read:** ~5,303 tokens (UpdateManager.cls)

---

## Q4. DTL Transform implementors

**Full answer (2 points):**

`resolve_dynamic_dispatch("Transform", package_prefix="HS")` returns **33 classes**,
confidence **0.30** (>20 candidates → wide dispatch).

Examples: `HS.FHIR.DTL.Mapping.Base`, `HS.FHIR.DTL.SubXFrm.SDA3.vR4.*` (many subtypes),
`HS.Gateway.X12.SDA3.*` classes, etc.

**What the score means:** Confidence 0.30 means an agent cannot assume any *specific*
callee is dispatched to — all 33 are valid. To answer "what does this specific call do"
requires runtime observation or filtering by the `DTL` variable's actual type at the
callsite (which requires data-flow analysis beyond static CALLS).

**Token cost IAD:** ~100 tokens
**Token cost grep:** ~500 tokens grep output, no confidence signal, no disambiguation

---

## Q5. SessionStart — zero-result trap

**Full answer (2 points):**

`resolve_dynamic_dispatch("SessionStart", package_prefix="HS")` → **0 results** in HSLIB.

Correct interpretation: `SessionStart` is a **customer extension point**. No built-in
implementation exists in HSLIB. An agent cannot answer "what does `$classmethod(..SessionClass,
'SessionStart', ...)` do" from static HSLIB analysis — the answer depends entirely on what
class the deploying customer places in `SessionClass` at configuration time.

**Trap:** An agent that returns zero from grep and says nothing scores 0. An agent that
fabricates implementations scores −1. An agent that explains "zero means customer extension
point, not answerable from this corpus" scores 2.

---

## Q6. UpdateRuleVersion trigger body

**Full answer (2 points):**

From `json_extract(properties,'$.docstring')` on the Trigger node:

```
[ Event = INSERT/UPDATE/DELETE, Foreach = row/object, Time = AFTER ]
{
    New class, ruleVersion
    Set class = $System.Util.Collation({StreamletType},7)
    Set ruleVersion = ##class(HS.Consent.Types.CITRuleVersion).%OpenId(class)
    If ruleVersion = "" {
        Set ruleVersion = ##class(HS.Consent.Types.CITRuleVersion).%New()
        Set ruleVersion.Version = 1
        Set ruleVersion.Type = class
    } Else {
        Set ruleVersion.Version = ruleVersion.Version + 1
    }
    Do ruleVersion.%Save()
}
```

**Answers:**
- (a) Writes to: `HS.Consent.Types.CITRuleVersion`
- (b) Increments: `Version` field
- (c) Creates new row when `%OpenId(class)` returns `""` (no existing row for that StreamletType);
  updates existing row otherwise

**Token cost CBM:** ~125 tokens (docstring query + body)
**Token cost grep/read:** ~1,800 tokens (ClinicalInformationTypeRule.cls)

---

## Q7. OnDeleteSQL — does it cascade? (V3-Q2 closed)

**Full answer (2 points):**

From `json_extract(properties,'$.docstring')` on the Trigger node:

```
[ Event = DELETE, Final ]
{
     Quit
}
```

Body is a single `Quit`. **No cascade logic.** The doc comment is wrong.

This is the same question as V3-Q2 which previously required reading the source file and
was a hallucination trap (agents sometimes fabricated cascade logic). With spec-019,
the trigger body is a **15-token graph query** returning ground-truth content.

**Token cost CBM:** ~15 tokens (docstring length) + ~15 token query = **~30 tokens total**
**Token cost grep/read:** ~3,500 tokens (ODSSession.cls)
**Hallucination risk:** Zero — the answer comes directly from the compiled class definition.

---

## Token Cost Summary (actual measured)

| Q | CBM+IAD tokens | Grep/read tokens | Ratio | Notes |
|---|---------------|-----------------|-------|-------|
| Q1 Flash routing | ~540 | ~9,400 | 17× | 30 edges vs reading 3 files |
| Q2 Config resolution | ~840 | ~7,000 | 8× | 14 productions resolved in 1 query |
| Q3 MessageMap + full chain | ~130 | ~5,303 | 41× | spec-039 WorkMgr + spec-040 oref |
| Q4 DTL Transform | ~100 | ~500+ | 5× | Plus: confidence signal not available from grep |
| Q5 SessionStart | ~50 | ~0 | qualitative | Grep silence ≠ "no implementations" |
| Q6 Trigger body | ~125 | ~1,800 | 14× | Zero file reads |
| Q7 OnDeleteSQL | ~30 | ~3,500 | 117× | Closes V3-Q2 hallucination trap |

**Total:** CBM+IAD ~1,815 tokens vs grep/read ~27,503 tokens = **15× cheaper on average**

`trace_path(MakeMRNUpToDate, outbound, depth=4)` returns `processStreamlet` at hop=2.
The full chain is now traceable from CBM alone — no file reads required for Q3.
