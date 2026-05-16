# Feature Specification: Exclude IRIS Studio XML Export Files from ObjectScript Indexing

**Feature Branch**: `009-exclude-iris-xml-exports`
**Created**: 2026-05-16
**Status**: Draft
**Type**: Bug fix

---

## Context

HealthShare P4 depot contains `.xml` files (IRIS Studio XML export format) alongside
`.cls` files in the same `cls/` directory. These `.xml` files are class definitions
exported as XML (e.g., `<Class name="HSPTest.UI.CSSIssue">`) — they're deployment
artifacts, not source code.

CBM maps `.xml` to `CBM_LANG_XML` and the XML grammar's extraction layer treats XML
elements (`<Class>`, `<Method>`, `<Property>`) as structural nodes. This produces
527 false-positive Class nodes (named `Export`, `Class`, `Method`, `Description`)
in a 1,888-file HealthShare project. Of these, 289 have `start_line = end_line`
(single-line XML elements), appearing as "broken" classes in audits.

**Zero `.cls` files** produce false-positive Class nodes — the issue is exclusively
`.xml` files being parsed as XML when they're actually IRIS class export artifacts.

---

## User Scenarios & Testing

### User Story 1 — Clean indexing of HealthShare workspaces (Priority: P1)

A developer indexes a HealthShare P4 workspace that contains both `.cls` source files
and `.xml` Studio export files. After this fix, only the `.cls` files produce
ObjectScript Class/Method/Variable nodes — the `.xml` files are either skipped or
produce no ObjectScript-labeled nodes.

**Acceptance Scenarios**:
1. `MATCH (n:Class) WHERE n.start_line = n.end_line RETURN count(n)` returns 0
   (no broken-span classes from XML false positives).
2. `MATCH (n:Class) WHERE n.name IN ['Export','Class','Method','Description','Implementation'] RETURN count(n)` returns 0 (no XML element names as class nodes).
3. Real `.cls` classes (e.g., `HSPTest.UI.CSSIssue`) still appear correctly.
4. Total Class count drops from 2,350 to ~1,823 (only .cls-sourced classes).

---

## Requirements

- **FR-001**: `.xml` files matching the IRIS Studio XML export format (`<?xml...><Export generator="Cache"...>`) MUST be excluded from ObjectScript-style extraction. They MAY still be indexed as generic XML if useful, but MUST NOT produce Class, Method, or Variable label nodes.
- **FR-002**: The exclusion MUST be content-based (check first line for `<?xml`), not just extension-based — `.xml` files in non-IRIS projects should still be indexed normally by the XML grammar.
- **FR-003**: Alternative approach: skip `.xml` files entirely when the project contains `.cls` files (heuristic: if a project has ObjectScript, its `.xml` files are likely export artifacts).
- **FR-004**: All existing tests MUST pass. No regression on non-IRIS XML projects.

---

## Possible Approaches

### Approach A: Skip `.xml` when `.cls` present in same directory
In `discover.c`, if a directory contains any `.cls` file, skip `.xml` files in that directory. Simple heuristic, handles the HealthShare case, low risk.

### Approach B: Content-sniff `.xml` for IRIS export format
Like `.cls` disambiguation, read first 1KB of `.xml` files. If they contain `<Export generator="Cache"` or `<Export generator="IRIS"`, skip them (or classify as `CBM_LANG_NONE`).

### Approach C: Filter in post-processing
After extraction, remove any nodes from `.xml` files that have Class/Method/Variable labels. Most conservative — no discovery changes.

**Recommended**: Approach B — content-sniff. Matches the existing `.cls` disambiguation pattern, doesn't affect non-IRIS XML files, minimal code.

---

## Success Criteria

- **SC-001**: Re-indexing hscommlib produces exactly 0 Class nodes from `.xml` files.
- **SC-002**: Total Class count = only `.cls`-sourced classes (~1,823).
- **SC-003**: All existing tests pass.
- **SC-004**: Non-IRIS XML projects (e.g., Maven pom.xml, Kubernetes manifests) still index normally.

---

## Assumptions

- IRIS Studio XML exports always start with `<?xml` followed by `<Export generator="Cache"` or `<Export generator="IRIS"`.
- No legitimate ObjectScript source code uses `.xml` extension.
- The fix is safe to submit upstream — it's a pure false-positive reduction with no loss of real data.
