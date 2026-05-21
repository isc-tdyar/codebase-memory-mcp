# V5 — five cross-version (28.0 → 30.0) change questions

The two source trees live at:
- `/Users/mriadzak/Perforce/mriadzak_ws1/healthshare/hscore/28.0/databases/hslib/cls/HS/`
- `/Users/mriadzak/Perforce/mriadzak_ws1/healthshare/hscore/30.0/databases/hslib/cls/HS/`

Both trees are read-only. You may use `diff`, `grep`, `find`, file reads, or any indexed tooling.

---

Q1. A new scheduled task class was added to `HS/Flash/` in 30.0 that did not exist in 28.0. Name the class, summarize what it does (target of the cleanup), and identify the installer/method that schedules it. Cite both the class definition and the schedule call site by file:line.

Q2. The class `HS.Local.ZAUTHENTICATE` was substantially restructured between 28.0 and 30.0. Describe (a) what the parent class changed to and where that new parent class is defined, (b) what happened to the ~190 lines of `OnBefore*/OnAfter*/OnGetCredentials/...` methods that lived in 28.0's `HS.Local.ZAUTHENTICATE`, and (c) what advantage this refactor gives customers on upgrade (hint: read the doc-comment added to the new 30.0 `HS.Local.ZAUTHENTICATE`). Cite file:line for each claim.

Q3. In `HS/Flash/Status.cls`, a new property was added in 30.0 that supersedes `FHIRStatus`. Name the new property and its type. Then explain the role of the macro `$$$FlashFHIRStatusListReady` — specifically: what does the code do differently when the macro is true vs. false, and why does this gating exist? Cite file:line.

Q4. The class `HS.Hub.Auth.Strategy` exists in 28.0 but is gone in 30.0. (a) Identify the single hscore caller of `HS.Hub.Auth.Strategy` in 28.0 and explain how 30.0's equivalent file dispatches authentication instead (i.e., what class hierarchy/method replaced it). (b) Confirm via grep that no class in hscore 30.0 still references `HS.Hub.Auth.Strategy`. Cite file:line for both versions.

Q5. In `HS/ODS/FHIR/ODSSession.cls::MakeFHIRSession`, two lines (`do ret.ExtendExpiration(...)` and `do ret.%Save()`) moved between 28.0 and 30.0. Read both versions of the method. Describe precisely the behavioural difference this causes when callers retrieve an *existing* (not newly created) session. Is this a bug, a fix, or an intentional behaviour change? Justify your answer by reading what `ExtendExpiration` does in the same file. Cite file:line.
