# L10 — `static/js/explorer/analysis.js` — MODIFY

## Purpose
Add `?candidate=1` to health-check API calls when candidate session is active. Replace direct `state.pendingEdits` and `state.stagedObjectDeletions` mutations with CandidateApi calls.

No live configuration is mutated by the health-check calls themselves (they are read-only `GET` requests). The `?candidate=1` suffix directs the server to analyze the candidate directory rather than the running config. However, this module also contains deletion-staging functions that directly mutate `state.stagedObjectDeletions` and `state.pendingEdits` — these must be migrated to CandidateApi calls (Palo Alto model: copy config to candidate, edit candidate, apply candidate to live).

## Removal Audit

**`state.pendingEdits` references:**
| Line | Reference | Action |
|------|-----------|--------|
| 748 | `state.pendingEdits.delete(obj.global_index)` in cleanup delete handler | REPLACE with CandidateApi.deleteObject() |
| 1315 | `state.pendingEdits.get(serviceGlobalIndex)` in hostgroup link handler | REPLACE with CandidateApi.editObject() |
| 1329 | `state.pendingEdits.set(serviceGlobalIndex, edit)` in hostgroup link handler | REPLACE with CandidateApi.editObject() |

**`state.stagedObjectDeletions` references:**
| Line | Reference | Action |
|------|-----------|--------|
| 231 | `state.stagedObjectDeletions.has(obj.global_index)` skip in mapHealthCheckToState | REMOVE — in candidate mode, server health-check already excludes deleted objects |
| 315 | `state.stagedObjectDeletions.has(issue.global_index)` skip in notification analysis | REMOVE — same reason |
| 746-747 | `state.stagedObjectDeletions.has/add` in stageCleanupDelete single | REPLACE with CandidateApi.deleteObject() |
| 990 | `state.stagedObjectDeletions.add` in batch delete handler | REPLACE with CandidateApi.deleteObject() |
| 1052 | `state.stagedObjectDeletions.add` in stageCleanupDelete | REPLACE with CandidateApi.deleteObject() |
| 1173 | `state.stagedObjectDeletions.add` in keepDuplicateAndDeleteOthers | REPLACE with CandidateApi.deleteObject() |

**`Explorer.saveStagedChanges()` references:**
| Line | Reference | Action |
|------|-----------|--------|
| 753, 1001, 1053, 1178 | `Explorer.saveStagedChanges()` after staging operations | REMOVE — CandidateApi calls persist server-side |

**`Explorer.isObjectMarkedForDeletion()` references:**
| Line | Reference | Action |
|------|-----------|--------|
| 15 | `filterActiveSuggestions()` checks `isObjectMarkedForDeletion` | KEEP — this helper will be updated in state-management (L07) to check candidate state |

## Changes

**1. Add candidate suffix to health-check calls** (lines 66, 785, 1369):
```javascript
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/health-check${suffix}`);
```

**2. Replace `stageCleanupDelete()` single-object deletion** (line 745-758):
```javascript
// BEFORE: state.stagedObjectDeletions.add(obj.global_index); state.pendingEdits.delete(...)
// AFTER:
const stableKey = Explorer.getObjectKey(obj);
const result = await CandidateApi.deleteObject(stableKey);
if (result.success) {
    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();
}
```

**3. Replace batch delete handler** (lines 986-993):
```javascript
// BEFORE: loop adding to state.stagedObjectDeletions
// AFTER: loop calling CandidateApi.deleteObject() for each object
```

**4. Replace `stageCleanupDelete()` at line 1052**:
Same pattern as Change 2 — use CandidateApi.deleteObject().

**5. Replace `keepDuplicateAndDeleteOthers()` deletion logic** (lines 1170-1176):
```javascript
// BEFORE: state.stagedObjectDeletions.add(obj.global_index)
// AFTER: await CandidateApi.deleteObject(Explorer.getObjectKey(obj))
```

**6. Replace hostgroup link handler** (lines 1314-1329):
```javascript
// BEFORE: state.pendingEdits.get/set to modify service attributes
// AFTER:
const stableKey = Explorer.getObjectKey(serviceObj);
const edited = { ...serviceObj.attributes };
delete edited.host_name;
edited.hostgroup_name = hostgroupName;
const result = await CandidateApi.editObject(stableKey, edited, serviceObj.attributes);
```

**7. Remove `state.stagedObjectDeletions.has()` guard in `mapHealthCheckToState()`** (line 231):
In candidate mode, server health-check already excludes deleted objects from analysis.

**8. Remove `state.stagedObjectDeletions.has()` guard in notification analysis** (line 315):
Same reason as Change 7.

**9. Remove all `Explorer.saveStagedChanges()` calls** (lines 753, 1001, 1053, 1178):
No client-side staging state to save — CandidateApi persists changes server-side.

## UI Visual Parity

The following UI elements must remain visually identical after migration:

- **Suggestions tab layout**: Same subtabs (Issues, Cleanup, Grouping, Templates, Notifications), same structure.
- **Cleanup suggestion cards**: Same card layout, same "Delete" and "Delete All" buttons.
- **Toast notifications**: Same messages after deletion actions.
- **Section badges**: Same badge rendering for cleanup count, notification count, etc.

No CSS classes are added, removed, or renamed. No DOM structure changes.

## Audit Logging

Health-check calls are read-only (`GET /api/health-check`) and do not require audit logging. The deletion and edit operations migrated to CandidateApi will be audit-logged by the backend candidate routes (covered in L04-routes-objects.md).

## Error Handling

All existing error handling is preserved:

| Function | Error Handling | Status |
|----------|---------------|--------|
| `loadAllSuggestions()` | `try/catch` with `showToast('Analysis failed: ...')` | PRESERVED |
| `loadCleanupSuggestions()` | `try/catch` with container error message | PRESERVED |
| `loadNotificationSuggestions()` | `try/catch` with container error message | PRESERVED |
| `analyzeAll()` | `try/catch` with `showToast('Analysis failed: ...')` | PRESERVED |

New CandidateApi calls will check `result.success` before proceeding — failures display via toast.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Add `?candidate=1` suffix to `loadAllSuggestions()` health-check call (line 66) | [ ] |
| 2 | Add `?candidate=1` suffix to `loadCleanupSuggestions()` health-check call (line 785) | [ ] |
| 3 | Add `?candidate=1` suffix to `loadNotificationSuggestions()` health-check call (line 1369) | [ ] |
| 4 | Replace `stageCleanupDelete()` single-delete (line 745-758) with CandidateApi.deleteObject() | [ ] |
| 5 | Replace batch delete handler (lines 986-993) with CandidateApi.deleteObject() loop | [ ] |
| 6 | Replace `stageCleanupDelete()` at line 1052 with CandidateApi.deleteObject() | [ ] |
| 7 | Replace `keepDuplicateAndDeleteOthers()` deletion (lines 1170-1176) with CandidateApi.deleteObject() | [ ] |
| 8 | Replace hostgroup link handler (lines 1314-1329) with CandidateApi.editObject() | [ ] |
| 9 | Remove `state.stagedObjectDeletions.has()` guard in `mapHealthCheckToState()` (line 231) | [ ] |
| 10 | Remove `state.stagedObjectDeletions.has()` guard in notification analysis (line 315) | [ ] |
| 11 | Remove `Explorer.saveStagedChanges()` calls (lines 753, 1001, 1053, 1178) | [ ] |
| 12 | Remove `state.pendingEdits.delete()` call (line 748) | [ ] |
| 13 | `npm run lint:js` passes | [ ] |
| 14 | Playwright validation passes (see below) | [ ] |

## Verification
- Analysis tab loads in candidate mode
- Shows analysis of candidate objects, not running config
- Cleanup deletion stages via CandidateApi, not client-side state
- Hostgroup link suggestion stages edit via CandidateApi
- No references to `state.pendingEdits` or `state.stagedObjectDeletions` remain
- `npm run lint:js` passes
- `python3 -m ruff check` passes (no Python in this file, verify no cross-file breakage)
- No console errors in browser devtools

## Playwright Validation

**Test: Analysis tab loads in candidate mode**
1. Navigate to explorer page
2. Start a candidate session
3. Switch to Suggestions tab
4. Assert analysis subtabs render with data

**Test: Cleanup deletion works in candidate mode**
1. Navigate to explorer page with candidate session
2. Switch to Cleanup subtab
3. Click delete on a cleanup suggestion
4. Assert toast notification appears
5. Assert object is removed from suggestions list

**Test: No console errors on analysis load**
1. Navigate to explorer page
2. Wait for full load
3. Assert no `console.error` messages related to analysis

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Health-check calls are read-only. Deletion/edit operations go through CandidateApi, which writes to candidate directory only. |
| 2 | UI visual parity | COMPLIANT | Same suggestions tab layout, card design, badges, and toast messages. No CSS or DOM changes. See "UI Visual Parity" section. |
| 3 | Full audit logging | COMPLIANT | Read-only calls need no audit logging. Mutation operations via CandidateApi are logged by backend routes. See "Audit Logging" section. |
| 4 | Proper error handling | COMPLIANT | All existing try/catch blocks preserved. New CandidateApi calls check result.success. See "Error Handling" section. |
| 5 | Dead code deletion | COMPLIANT | Direct `state.stagedObjectDeletions` and `state.pendingEdits` mutations removed — dead code in candidate mode. |
| 6 | Full functionality migration | COMPLIANT | All deletion and edit operations migrated from client-side staging to CandidateApi calls. No functionality dropped. |
| 7 | Palo Alto candidate model | COMPLIANT | `?candidate=1` suffix on health-check reads candidate directory. Mutations go through CandidateApi (edit candidate, apply to live). |
| 8 | Change tracking document | COMPLIANT | See "Change Tracking" section with 14 items. |
| 9 | Complete planning before implementation | COMPLIANT | This plan fully specifies all changes, removals, and migrations before any code changes. |
| 10 | Linting enforcement | COMPLIANT | `npm run lint:js` required in verification and change tracking (item 13). |
| 11 | Playwright validation | COMPLIANT | Three Playwright test scenarios defined in "Playwright Validation" section. |
