# hscore Benchmark V6 — CBM + IAD Capability Showcase

**Module under test**: `hscore/databases/hslib/cls/HS/`
**CBM binary**: current HEAD (spec-019 trigger bodies, spec-037 dynamic dispatch, spec-038 Ensemble routing)
**IAD version**: iris-agentic-dev current (resolve_dynamic_dispatch, extract_message_map_routing, find_subclass_implementations)
**IRIS instance**: careconnect-ivg-iris localhost:19720/HSLIB
**Designed by**: Tom Dyar, 2026-05-23

## Purpose

V6 benchmarks specifically the *new* capabilities added since V5:
- **spec-019**: trigger body text queryable from graph
- **spec-037**: dynamic dispatch resolution via live IRIS %Dictionary
- **spec-038**: Ensemble production topology (ROUTES_TO edges)

Each question includes explicit token-cost comparison between the CBM+IAD approach
and the naive grep/file-read approach, making the efficiency argument concrete.

## Scoring rubric (same as V3-V5)
- 2 = full correct answer
- 1 = partial (right direction, missing detail)
- 0 = wrong but cautious ("I'm not sure")
- −1 = confidently fabricated

## Questions

---

### Section A — Ensemble Production Routing (spec-038)

**Q1. Flash component routing topology**

In the Flash subsystem, three business components (`HS.Flash.WebServices`,
`HS.Flash.UpdateManager`, `HS.Flash.FetchManager`) route messages to downstream targets.
For each component:
(a) List every `SendRequestSync`/`SendRequestAsync` target and the message type that triggers it.
(b) Identify which targets are hardcoded literal strings vs. runtime-configured `ConfigName`
    properties — and for the property-based ones, give the `InitialExpression` default.

**Token budget — CBM+IAD approach**: ~300 tokens (ROUTES_TO query + extract_message_map_routing x2)
**Token budget — grep/read approach**: ~9,400 tokens (read WebServices.cls + UpdateManager.cls + FetchManager.cls)

---

**Q2. End-to-end config-name resolution**

`HS.Flash.WebServices` routes a `PatientSearchRequest` synchronously to the literal target
`"HUB"`. Using the indexed production definitions (not source file reads):
(a) Which class does the config name `"HUB"` resolve to in the sample Flash production?
(b) What entry-point method on that class handles the incoming message?

**Token budget — CBM+IAD approach**: ~200 tokens (EnsembleItem query + extract_message_map_routing)
**Token budget — grep/read approach**: ~7,000 tokens (read sample production XML + target class)

---

### Section B — MessageMap Routing (spec-037)

**Q3. UpdateManager complete routing table**

List every message type handled by `HS.Flash.UpdateManager`'s `XData MessageMap` block
and the method each routes to. Then: which message type ultimately triggers
`processStreamlet`, and what is the one-hop method chain?

**Token budget — CBM+IAD approach**: ~150 tokens (extract_message_map_routing)
**Token budget — grep/read approach**: ~5,303 tokens (read UpdateManager.cls)

---

### Section C — Dynamic Dispatch (spec-037)

**Q4. DTL Transform implementors**

`HS.ODS.FHIR.Transform.SDA3ToFHIR` calls `$classmethod(DTL, "Transform", ...)` where
`DTL` is a runtime string variable.
(a) How many distinct classes in HSLIB define `Transform` as their own (non-inherited)
    classmethod?
(b) What confidence score does `resolve_dynamic_dispatch` assign, and what does that
    score tell an agent about how safely it can assume a specific callee?

**Token budget — CBM+IAD approach**: ~100 tokens (resolve_dynamic_dispatch)
**Token budget — grep/read approach**: ~500 tokens grep output + manual disambiguation

---

**Q5. SessionClass dispatch — the zero-result trap**

`HS.Flash.FHIRService` has a `SessionClass As %Dictionary.CacheClassname` property and
calls `$classmethod(..SessionClass, "SessionStart", ...)`.
Using `resolve_dynamic_dispatch("SessionStart")` against HSLIB:
(a) How many classes implement `SessionStart` as their own method?
(b) What does this result tell you about whether an agent can answer "what does this
    call do" purely from static HSLIB analysis?

**Token budget — CBM+IAD approach**: ~100 tokens
**Token budget — grep approach**: ~0 tokens but gives wrong signal (silence ≠ "no implementations")

---

### Section D — Trigger Bodies (spec-019)

**Q6. What does UpdateRuleVersion actually do?**

The trigger `UpdateRuleVersion` fires on INSERT/UPDATE/DELETE on
`HS.Consent.Types.ClinicalInformationTypeRule`.
Using only the CBM graph (no file reads):
(a) What class/table does it write to?
(b) What field does it increment?
(c) Under what condition does it create a new row vs. update an existing one?

**Token budget — CBM+IAD approach**: ~100 tokens (trigger_body property query)
**Token budget — grep/read approach**: ~1,800 tokens (read ClinicalInformationTypeRule.cls)

---

**Q7. OnDeleteSQL trigger — does it cascade? (closes V3-Q2 without file reads)**

V3 Q2 required reading `HS.ODS.FHIR.ODSSession.cls` to determine whether its
`OnDeleteSQL` trigger actually cascades deletes as the doc comment claims.
Using only the CBM graph:
(a) What is the complete body of the `OnDeleteSQL` trigger?
(b) Does it cascade anything?

**Token budget — CBM+IAD approach**: ~80 tokens (trigger_body property query)
**Token budget — grep/read approach**: ~3,500 tokens (read ODSSession.cls)
**Note**: This is the same question as V3-Q2 which was a hallucination trap. With spec-019,
it is now answerable from the graph with ground-truth accuracy.
