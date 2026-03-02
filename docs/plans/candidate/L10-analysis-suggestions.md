# L10 — `static/js/explorer/analysis-suggestions.js` — MODIFY

## Purpose
Add `?candidate=1` to suggestion API calls. Rewrite template creation, hostgroup creation, and edit application to use CandidateApi instead of mutating client-side staging state. All changes write to the candidate directory only — no live config mutation until Apply.

## Removal Audit
- `state.stagedCreations.push(...)` → REPLACED by `CandidateApi.createObject()`. Server writes to candidate directory.
- `state.pendingEdits.set(...)` → REPLACED by `CandidateApi.editObject()`. Server writes to candidate directory.
- `Explorer.saveStagedChanges()` → REMOVED. No client-side state to persist — all state is server-side in candidate directory.
- `state.selectedStagedIndices` management → REMOVED. No client-side staged index tracking.
- `Explorer.selectStagedCreationForEdit()` → REPLACED by selecting by stable key from CandidateApi.createObject() response.
- `generateUniqueId()` calls → REMOVED. Server assigns object identity.
- `state.stagedCreations.find(...)` duplicate check → REMOVED. Server returns 409 if duplicate exists in candidate.

Every removed function has a CandidateApi equivalent that performs the same user-facing operation. Audit logging is handled server-side by the candidate route handlers (L03-routes-candidate.md).

## Changes

**1. Add candidate suffix to suggestion API calls**:
```javascript
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
```
Apply to:
- `/api/smart-grouping/suggest` (line 234) → `/api/smart-grouping/suggest${suffix}`
- `/api/health-check` (line 146) → `/api/health-check${suffix}`
- `/api/templates/issues` (line 52) → `/api/templates/issues${suffix}`

These are read-only GET calls. The `?candidate=1` parameter tells the server to analyze the candidate config instead of the running config.

**2. Rewrite template creation action** (`showCreateTemplateDialog` callback, around line 358):
```javascript
// BEFORE: state.stagedCreations.push({...}); Explorer.saveStagedChanges();
// AFTER:
const templateAttrs = { ...suggestion.attributes, name: name, register: '0' };
const result = await CandidateApi.createObject(suggestion.type, templateAttrs, targetFile);
if (!result.success) {
    showToast(result.error || 'Failed to create template', 'error');
    return;
}

// If updating objects, apply edits to add 'use' and remove common attrs
if (updateObjects) {
    for (const obj of suggestion.objects) {
        const newAttrs = { ...obj.attributes };
        newAttrs.use = name;
        for (const key of Object.keys(suggestion.attributes)) {
            delete newAttrs[key];
        }
        const stableKey = Explorer.getObjectKey(obj);
        const editResult = await CandidateApi.editObject(stableKey, newAttrs, obj.attributes);
        if (!editResult.success) {
            showToast(`Failed to update ${Explorer.getObjectDisplayName(obj)}: ${editResult.error}`, 'error');
        }
    }
}

Explorer.closeDialog();
await Explorer.refreshAfterObjectChange();
await Explorer.refreshCandidateDiff();

// Select the newly created object by stable key from create response
if (result.data?.stable_key) {
    setTimeout(() => {
        Explorer.selectObjectByKey(result.data.stable_key);
    }, 50);
}

const msg = updateObjects
    ? `Created template "${name}" and updated ${suggestion.count} objects.`
    : `Created template "${name}".`;
showToast(msg, 'success');
```

Note: Toast messages change from "Staged template" to "Created template" for UI consistency in the candidate model. Visual appearance of dialogs and buttons remains identical (C2 — UI visual parity).

**3. Rewrite edit application** (around line 381):
```javascript
// BEFORE: state.pendingEdits.set(obj.global_index, {...});
// AFTER:
const stableKey = Explorer.getObjectKey(obj);
const editResult = await CandidateApi.editObject(stableKey, editedAttrs, obj.attributes);
if (!editResult.success) {
    showToast(editResult.error || 'Failed to apply edit', 'error');
    return;
}
await Explorer.refreshAfterObjectChange();
await Explorer.refreshCandidateDiff();
```

**4. Rewrite hostgroup creation action** (`showCreateGroupDialog` callback, around line 472):
```javascript
// BEFORE: state.stagedCreations.push({...}); Explorer.saveStagedChanges();
// AFTER:
const result = await CandidateApi.createObject('hostgroup', {
    hostgroup_name: name,
    alias: name,
    members: suggestion.members.join(',')
}, targetFile);
if (!result.success) {
    showToast(result.error || 'Failed to create hostgroup', 'error');
    return;
}

Explorer.closeDialog();
await Explorer.refreshAfterObjectChange();
await Explorer.refreshCandidateDiff();

// Select the newly created object by stable key from create response
if (result.data?.stable_key) {
    setTimeout(() => {
        Explorer.selectObjectByKey(result.data.stable_key);
    }, 50);
}

showToast(`Created hostgroup "${name}".`, 'success');
```

Note: Toast message changes from "Staged hostgroup" to "Created hostgroup".

**5. Remove `state.selectedStagedIndices` management** — All `state.selectedStagedIndices.clear()`, `.add()` calls and `data-staged-index` queries are removed. Object selection after create uses `Explorer.selectObjectByKey(stableKey)` with the stable key from the CandidateApi response.

**6. Remove client-side duplicate checks that are now server-side**:
- Line 464-465: `const alreadyStaged = state.stagedCreations.find(...)` → REMOVE. Server returns 409 if object already exists in candidate.
- Line 466-468: `if (alreadyStaged) { showToast(...); return; }` → REMOVE. The `result.success` check after CandidateApi.createObject() handles this.
- Line 350-353: Existing-object check against `state.allObjects` → KEEP. This is a UX shortcut; the server also validates, but checking locally avoids an unnecessary API call.

**7. Remove `generateUniqueId()` calls** — Lines 359, 473: The server assigns stable keys and identity. No client-side ID generation needed.

## Detailed Staging References

All staging references found via `grep -n stag analysis-suggestions.js`:

| Line(s) | Reference | Action |
|---------|-----------|--------|
| 356 | `// Stage the template creation` comment | REWORD → "Create the template" |
| 358 | `state.stagedCreations.push({...})` (template creation) | REPLACE → `CandidateApi.createObject()` |
| 359 | `id: generateUniqueId()` | REMOVE — server assigns identity |
| 365 | `const newStagedIdx = state.stagedCreations.length - 1` | REMOVE — no client-side index tracking |
| 367 | `// If updating objects, stage edits` comment | REWORD → "If updating objects, apply edits" |
| 381 | `state.pendingEdits.set(obj.global_index, {...})` | REPLACE → `CandidateApi.editObject()` |
| 396 | `Explorer.saveStagedChanges()` | REMOVE — no client-side state to persist |
| 399 | `// Select the newly created staged item` comment | REWORD → "Select the newly created item" |
| 401 | `state.selectedStagedIndices.clear()` | REMOVE |
| 402 | `state.selectedStagedIndices.add(newStagedIdx)` | REMOVE |
| 403 | `Explorer.selectStagedCreationForEdit(newStagedIdx)` | REPLACE → `Explorer.selectObjectByKey(stableKey)` |
| 406 | `` document.querySelector(`[data-staged-index="${newStagedIdx}"]`) `` | REPLACE → select by stable key from create response |
| 413-416 | `showToast('Staged template...')` | REWORD → "Created template..." |
| 464-465 | `const alreadyStaged = state.stagedCreations.find(...)` (hostgroup duplicate check) | REMOVE — server returns 409 if object already exists in candidate |
| 467 | `showToast('...is already staged for creation', 'warning')` | REMOVE — handled by server error response |
| 471 | `// Stage the creation instead of immediately creating` comment | REWORD → "Create the hostgroup" |
| 472 | `state.stagedCreations.push({...})` (hostgroup creation) | REPLACE → `CandidateApi.createObject()` |
| 473 | `id: generateUniqueId()` | REMOVE — server assigns identity |
| 483 | `const newStagedIdx = state.stagedCreations.length - 1` | REMOVE |
| 486 | `Explorer.saveStagedChanges()` | REMOVE |
| 489 | `// Select the newly created staged item` comment | REWORD → "Select the newly created item" |
| 491 | `state.selectedStagedIndices.clear()` | REMOVE |
| 492 | `state.selectedStagedIndices.add(newStagedIdx)` | REMOVE |
| 493 | `Explorer.selectStagedCreationForEdit(newStagedIdx)` | REPLACE → `Explorer.selectObjectByKey(stableKey)` |
| 496 | `` document.querySelector(`[data-staged-index="${newStagedIdx}"]`) `` | REPLACE → select by stable key |
| 503 | `showToast('Staged hostgroup...')` | REWORD → "Created hostgroup..." |

Note: Lines 464-496 (hostgroup creation) mirror the template creation block at lines 358-406. Both get the same rewrite pattern.

## Error Handling

Every CandidateApi call checks `result.success` and shows a user-visible toast with the server error message on failure. No silent failures.

| Operation | Failure Behavior |
|-----------|-----------------|
| `CandidateApi.createObject()` (template) | `showToast(result.error \|\| 'Failed to create template', 'error')` and early return |
| `CandidateApi.editObject()` (template update) | `showToast('Failed to update <name>: <error>', 'error')` — continues loop for remaining objects |
| `CandidateApi.editObject()` (edit suggestion) | `showToast(result.error \|\| 'Failed to apply edit', 'error')` and early return |
| `CandidateApi.createObject()` (hostgroup) | `showToast(result.error \|\| 'Failed to create hostgroup', 'error')` and early return |
| Duplicate hostgroup (server 409) | Server error message displayed via the `!result.success` check |
| `refreshAfterObjectChange()` failure | Handled by existing refresh error handling in data-loading.js |

## Audit Logging

All CandidateApi calls route to server-side candidate endpoints (L03-routes-candidate.md) which log every operation through both `audit_service.py` (structured JSONL) and the application logger. This file does not add any client-side logging because it performs no direct mutations — all mutations go through CandidateApi to the server.

Operations logged server-side for this file's actions:
- `candidate.object.create` — template creation, hostgroup creation
- `candidate.object.edit` — template update edits, edit suggestion application
- Each log entry includes: session_id, user identity, stable_key, operation type, timestamp

## UI Visual Parity

All dialog layouts, button labels, input fields, and visual elements remain unchanged. The only user-visible text changes are:
- "Staged template" → "Created template" in toast notifications
- "Staged hostgroup" → "Created hostgroup" in toast notifications
- "is already staged for creation" → removed (server 409 error message replaces)
- "Use Commit to apply." → removed from toast suffix (no longer needed — changes are already in candidate)

Dialog appearance, suggestion list rendering, filter sliders, and confidence badges are untouched.

## Linting

All changes must pass `npm run lint:js` before committing. No new ESLint warnings or errors introduced.

## Playwright Validation

Playwright tests should cover the following user flows after this migration:

| Test | Steps | Expected |
|------|-------|----------|
| Template creation from suggestion | 1. Open analysis tab 2. Click template suggestion 3. Fill name, select file, click Create | Template appears in tree, toast shows "Created template" |
| Template creation with object updates | Same as above with "Update objects" checked | Template created, objects updated with `use` directive, common attrs removed |
| Hostgroup creation from suggestion | 1. Open analysis tab 2. Click grouping suggestion 3. Fill name, select file, click Create | Hostgroup appears in tree, toast shows "Created hostgroup" |
| Duplicate hostgroup creation | Attempt to create hostgroup with name that already exists | Error toast displayed (409 from server) |
| Edit suggestion application | 1. Open analysis tab 2. Apply an edit suggestion | Object updated in editor, change reflected in diff |
| Candidate suffix on API calls | Open analysis tab in candidate mode, verify network requests | API calls include `?candidate=1` parameter |

These tests validate that the migrated functionality works identically to the pre-migration behavior from the user's perspective.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Add `?candidate=1` suffix to `/api/smart-grouping/suggest` | [ ] |
| 2 | Add `?candidate=1` suffix to `/api/health-check` | [ ] |
| 3 | Add `?candidate=1` suffix to `/api/templates/issues` | [ ] |
| 4 | Rewrite `showCreateTemplateDialog` callback to use `CandidateApi.createObject()` | [ ] |
| 5 | Rewrite template object updates to use `CandidateApi.editObject()` | [ ] |
| 6 | Add error handling for template create failure | [ ] |
| 7 | Add error handling for each template edit failure | [ ] |
| 8 | Rewrite edit suggestion application to use `CandidateApi.editObject()` | [ ] |
| 9 | Add error handling for edit suggestion failure | [ ] |
| 10 | Rewrite `showCreateGroupDialog` callback to use `CandidateApi.createObject()` | [ ] |
| 11 | Add error handling for hostgroup create failure | [ ] |
| 12 | Remove `state.stagedCreations.push(...)` (template, line 358) | [ ] |
| 13 | Remove `state.stagedCreations.push(...)` (hostgroup, line 472) | [ ] |
| 14 | Remove `state.pendingEdits.set(...)` (line 381) | [ ] |
| 15 | Remove `Explorer.saveStagedChanges()` calls (lines 396, 486) | [ ] |
| 16 | Remove `state.selectedStagedIndices` management (lines 401-402, 491-492) | [ ] |
| 17 | Remove `Explorer.selectStagedCreationForEdit()` calls (lines 403, 493) | [ ] |
| 18 | Remove `data-staged-index` queries (lines 406, 496) | [ ] |
| 19 | Remove `generateUniqueId()` calls (lines 359, 473) | [ ] |
| 20 | Remove client-side staged duplicate check (lines 464-468) | [ ] |
| 21 | Replace post-create selection with `Explorer.selectObjectByKey(stableKey)` | [ ] |
| 22 | Update toast messages from "Staged" to "Created" | [ ] |
| 23 | Verify `npm run lint:js` passes | [ ] |
| 24 | Run Playwright tests for template/hostgroup creation flows | [ ] |

## Verification
- Template suggestions load in candidate mode
- Creating template from suggestion works
- Applying edit suggestion works
- Hostgroup creation from suggestion works
- Duplicate creation attempt shows server error (409)
- All CandidateApi failures show user-visible toast errors
- No `state.stagedCreations`, `state.pendingEdits`, or `state.selectedStagedIndices` references remain
- Toast messages say "Created" not "Staged"
- `npm run lint:js` passes with no new warnings
- No console errors

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | All CandidateApi calls write to candidate directory only. Live config untouched until user clicks Apply in commit dialog. |
| 2 | UI visual parity | COMPLIANT | Dialog layouts, buttons, suggestion lists, filter sliders, confidence badges all unchanged. Only toast text changes ("Staged" → "Created"). |
| 3 | Full audit logging | COMPLIANT | All mutations route through CandidateApi to server endpoints that log via audit_service.py (JSONL) and app logger. No client-side mutations to log. |
| 4 | Proper error handling | COMPLIANT | Every CandidateApi call checks `result.success` and shows user-visible toast on failure. No silent failures. Edit loop continues on per-object failure with individual error toasts. |
| 5 | Dead code deletion | COMPLIANT | All staging state mutations (`stagedCreations.push`, `pendingEdits.set`, `saveStagedChanges`, `selectedStagedIndices`, `selectStagedCreationForEdit`, `generateUniqueId`, staged duplicate checks) are removed. |
| 6 | Full functionality migration | COMPLIANT | Template creation, template-update edits, edit suggestion application, hostgroup creation, duplicate detection, post-create selection — all migrated to CandidateApi equivalents. |
| 7 | Palo Alto candidate model | COMPLIANT | Changes are written to candidate config directory via CandidateApi. Applied to live only via explicit Apply. |
| 8 | Change tracking document | COMPLIANT | 24-item change tracking checklist included in this plan. |
| 9 | Complete planning before implementation | COMPLIANT | All changes, error handling, removal audit, and line-level references fully specified before implementation. |
| 10 | Linting enforcement | COMPLIANT | Plan requires `npm run lint:js` pass before commit. Tracked as change #23. |
| 11 | Playwright validation | COMPLIANT | Six Playwright test scenarios specified covering template creation, hostgroup creation, duplicate detection, edit application, and candidate suffix verification. |
