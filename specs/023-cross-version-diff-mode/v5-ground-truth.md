# V5 ground truth — hand-verified by diffing 28.0 → 30.0

Paths abbreviated to `hscore/<ver>/databases/hslib/cls/HS/...`.

---

## Q1: New scheduled task in `Flash/`

**Class:** `HS.Flash.CachePurgeTask` at `hscore/30.0/.../HS/Flash/CachePurgeTask.cls:3` — extends `%SYS.Task.Definition`.

**What it does:** `OnTask` calls `DoPurge` (line 6-9). `DoPurge` (line 11-27) walks `^CacheTemp.HS.EdgeSession(...)` and kills entries whose `timeReceived` is older than 1 hour (`currTime - 3600`). It is the Edge-session cache cleanup task.

**Schedule registration:** `ClassMethod Schedule(pNS)` at line 29 creates/updates a `%SYS.Task` named "Edge Session Cache Purge Task" running daily, every hour.

**Caller that schedules it:** `HS.Util.Installer.FlashGateway::...` at `hscore/30.0/.../HS/Util/Installer/FlashGateway.cls:163`:
```
Set tSC=##class(HS.Util.SystemAPI).Invoke("ScheduleTask",pNamespace,"HS.Flash.CachePurgeTask",pNamespace)
```

**Full credit:** name `HS.Flash.CachePurgeTask`, mention `^CacheTemp.HS.EdgeSession` and the 1-hour cutoff, cite both `Flash/CachePurgeTask.cls:3` (or :11) and `Util/Installer/FlashGateway.cls:163`.

---

## Q2: `HS.Local.ZAUTHENTICATE` refactor

**(a) Parent change:** In 28.0, `HS.Local.ZAUTHENTICATE` extended `HS.Util.IAuthenticate` directly (`hscore/28.0/.../HS/Local/ZAUTHENTICATE.cls:1`). In 30.0, it extends a new intermediate base class `HS.Auth.Client.Custom.ZAUTHENTICATE` (`hscore/30.0/.../HS/Local/ZAUTHENTICATE.cls:7`). The new base class is defined at `hscore/30.0/.../HS/Auth/Client/Custom/ZAUTHENTICATE.cls:5` (it itself extends `HS.Util.IAuthenticate [Abstract]`).

**(b) The ~190 lines of OnBeforeAA/OnAfterAA/OnBeforeValidatePW/OnGetCredentials/...** in 28.0's `HS.Local.ZAUTHENTICATE` were moved up into the new `HS.Auth.Client.Custom.ZAUTHENTICATE` base. In 30.0, `HS.Local.ZAUTHENTICATE` itself is essentially empty — the comment block (lines 1-6) explicitly says "This SHOULD NEVER have methods present in it on a new install. ALL methods MUST only be defined in the super class."

**(c) Upgrade advantage:** Because customer code in `HS.Local.*` is "left unchanged" on upgrades (per the doc-comment), keeping the empty `HS.Local.ZAUTHENTICATE` shell and putting the actual default callback bodies in the InterSystems-shipped base class (`HS.Auth.Client.Custom.ZAUTHENTICATE`) means **default behaviour and new callback methods can be updated by InterSystems on upgrade without rewriting the customer's HS.Local class.** Only methods marked `@API.Overrideable` may be overridden in HS.Local; the rest stay in the shipped super.

**Full credit:** identifies new parent `HS.Auth.Client.Custom.ZAUTHENTICATE` at `HS/Auth/Client/Custom/ZAUTHENTICATE.cls`, notes 28.0's body methods moved up, and explains the upgrade-safety rationale (or quotes the doc comment).

---

## Q3: `Flash/Status.cls` — new property and `$$$FlashFHIRStatusListReady` gating

**New property:** `Property FHIRStatusList As array Of %Integer` at `hscore/30.0/.../HS/Flash/Status.cls:28`. Doc-comment (line 23-27) states each entry maps an ODS instance ID → FHIR status (Uninitialized/Ready/Error/Delete-in-progress). The legacy single-valued `FHIRStatus` property is now marked deprecated at line 20: "This property has been deprecated. Use FHIRStatusList instead."

**Macro `$$$FlashFHIRStatusListReady` gating:** In 30.0 `SetMRNStatus`, `SetFHIRStatus`, and `IsFHIRSynced` (Status.cls lines ~93, 122, 152), the code branches on `$$$FlashFHIRStatusListReady`:
- When **NOT** ready (`'$$$FlashFHIRStatusListReady`), the legacy single-valued `FHIRStatus` property is *also* updated/read alongside the new `FHIRStatusList` array (e.g. line 94: `if '$$$FlashFHIRStatusListReady { set tObj.FHIRStatus = $$$FlashStatusDeleted }`; line 152 `IsFHIRSynced` falls back to the old `obj.FHIRStatus = $$$FlashStatusReady` semantics).
- When **ready**, the code uses *only* `FHIRStatusList`.
- **Crucially**, `FHIRStatusList` is updated unconditionally regardless of macro state ("Devnote: Update FHIRStatusList regardless of the progress of the upgrade step. This ensures FHIRStatusList always has the most up-to-date statuses.").

**Why:** This is an upgrade/migration gate. Existing rows haven't yet had their `FHIRStatusList` populated by the V29/V30 upgrade step. Until the upgrade flips the macro/registry flag indicating the population is complete, the code dual-writes to keep the old `FHIRStatus` column authoritative for reads. After the flag is on, only the new array is read.

**Full credit:** name `FHIRStatusList As array Of %Integer` at line 28, explain dual-write/legacy-fallback semantics, mention upgrade-migration motivation. Bonus: catch that `FHIRStatusList` is *always* written (per the devnote), only reads/writes of legacy `FHIRStatus` are gated.

---

## Q4: `HS.Hub.Auth.Strategy` removal

**(a) 28.0 caller:** Single hscore caller is `HS.Hub.RESTHandler::AuthenticationStrategy` at `hscore/28.0/.../HS/Hub/RESTHandler.cls:6-9`:
```
ClassMethod AuthenticationStrategy() As %Dictionary.CacheClassname
{ Return ##class(HS.Hub.Auth.Strategy).%ClassName(1) }
```
The class itself is at `hscore/28.0/.../HS/Hub/Auth/Strategy.cls:5`, extending `HSMOD.REST.Auth.Default.Strategy` and overriding `RouteToResourceMap`.

**(b) 30.0 replacement:** `HS.Hub.RESTHandler` no longer extends `HS.REST.Handler` — it now extends `HS.RESTBase.UIHandler` (`hscore/30.0/.../HS/Hub/RESTHandler.cls:5`). The `AuthenticationStrategy()` method is gone; the class instead overrides `IsPublic(pUrl, pMethod)` (line 16) and `CheckHSResourcePermitted(resourceClass)` (line 24). The auth-strategy plumbing is now inherited from the new `HS.RESTBase.UIHandler` superclass rather than locally pointing at `HS.Hub.Auth.Strategy`.

**(c) Confirm no lingering refs:** `grep -rn "HS.Hub.Auth.Strategy" hscore/30.0` returns **zero hits** in 30.0 (only 28.0 has them). Class itself is deleted.

**Full credit:** identifies the 28.0 callsite at `Hub/RESTHandler.cls:6-9`, explains 30.0 changed the parent class to `HS.RESTBase.UIHandler` instead of locally defining a strategy, and confirms no remaining references.

---

## Q5: `MakeFHIRSession` / `GetSessionForPatient` `ExtendExpiration` move

In 28.0 (`hscore/28.0/.../HS/ODS/FHIR/ODSSession.cls:57-58`), the calls
```
do ret.ExtendExpiration(expirationTimout)
do ret.%Save()
```
sit **outside** the `if '$isobject(ret) { ... }` "session-not-found" block — so they run for **both** newly-created sessions AND reused-existing sessions.

In 30.0 (`hscore/30.0/.../HS/ODS/FHIR/ODSSession.cls:56-57`), those two lines moved **inside** the `if '$isobject(ret) { ... }` block — they only run when a brand-new session is created.

**Effect on reused sessions:** `ExtendExpiration` (line 183) sets `..Expires = tNow + extendBySecs`. In 28.0, every successful retrieval (including hitting an existing matching row) refreshed the expiry. In 30.0, an existing reused session keeps whatever `Expires` was previously set — so a session that was about to expire is no longer kept alive by activity. The session will expire at the originally-set time even if a caller is actively using it.

**Bug or fix?** Most likely an unintentional regression. The function returns the session and the caller proceeds to use it; reusing a session whose expiry isn't refreshed defeats the point of the `expirationTimout` parameter when reuse occurs. There's no comment justifying the change. The diff is also a brace-rebalance ("moved inside the if" plus a stray empty line), which has the smell of a cleanup that overlooked the wider scope. (A defensible counter-argument: maybe they intentionally only extend on creation to prevent a stale session being kept alive forever — but that doesn't match the doc/usage pattern, since `expirationTimout` is passed every call and `isNew` is reported back to the caller.)

**Full credit:** (a) identifies the in/out-of-block move, (b) concretely names the behaviour change for *reused* sessions (no expiry refresh), (c) takes a position on bug-vs-intent with reasoning. Hallucination penalty if the agent fabricates a comment, ticket, or unrelated rationale.

---

Scoring rubric: 2 = full, 1 = partial, 0 = wrong-but-cautious, −1 = confidently fabricated.
