# L10 — `static/js/explorer/analysis-issues.js` — MODIFY

## Purpose
Add `?candidate=1` to health-check call. Remove client-side staged creation references and replace with CandidateApi calls. Preserve all user-facing toast text.

## Removal Audit
- `Explorer.getStagedCreations()` / `Explorer.setStagedCreations()` → REMOVED. No client-side staged creations. Batch create calls `CandidateApi.createObject()` for each object.
- `Explorer.saveStagedChanges()` → REMOVED from this file. No client-side state to save; server handles persistence.
- `Explorer.computeStagedIssues()` → REMOVED from this file. In candidate mode, all issues come from the server health-check (which analyzes candidate objects). After batch create, call `loadIssues()` to refresh from server.
- `Explorer.stagedIssues` getter → REMOVED from usage in this file (getter itself removed in L10-badge-issues). Server health-check provides all issues.
- `Explorer.openNewObjectInEditor()` → KEPT but creates via CandidateApi.

## Changes

**1. Add candidate suffix to health-check fetch (line 36)**:
```javascript
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/health-check${suffix}`, { silent: true });
```

**2. Rewrite `filterIssues()` — Remove `Explorer.stagedIssues` merge (line 106)**:
```javascript
// BEFORE:
const combined = [...state.allIssues, ...Explorer.stagedIssues].filter(i => i.severity === 'error');
// AFTER:
const combined = state.allIssues.filter(i => i.severity === 'error');
```
Server health-check in candidate mode already includes all issues (candidate objects are analyzed server-side).

**3. Rewrite `executeBatchCreate()` — Replace client-side staging with CandidateApi calls**:
```javascript
async function executeBatchCreate(groups, targetFile) {
    Explorer.closeDialog();

    let created = 0;
    let failed = 0;

    for (const group of groups) {
        const issue = group.firstIssue;
        const isTemplate = issue.type === 'missing_template';
        const objectType = isTemplate ? issue.object_type : group.objectType;

        // Build attributes for this object
        const attributes = buildDefaultAttributes(objectType, group.missingName, isTemplate);

        try {
            // Create via candidate API
            const result = await CandidateApi.createObject(objectType, attributes, targetFile);
            if (result.success) {
                created++;
            } else {
                failed++;
                console.error('Failed to create object:', group.missingName, result.error);
            }
        } catch (e) {
            failed++;
            console.error('Failed to create object:', group.missingName, e);
        }
    }

    // Refresh UI from server
    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();
    Explorer.updateCommitUI();
    state.healthCheckData = null;
    loadIssues();

    if (failed === 0) {
        showToast(`Staged ${created} new object${created !== 1 ? 's' : ''} for creation`, 'success');
    } else {
        showToast(`Staged ${created} objects, ${failed} failed`, 'warning');
    }
}
```

**4. Rewrite `createObjectForIssue()` — Replace `computeStagedIssues()` with `loadIssues()`**:
```javascript
// BEFORE:
Explorer.computeStagedIssues();
loadIssues();
// AFTER:
loadIssues();
```
The `loadIssues()` call fetches fresh issues from the server, which in candidate mode already reflects the newly created object. No client-side issue computation needed.

**5. Add `?candidate=1` suffix to any other API calls in this file** that need candidate awareness (if any exist beyond the health-check call).

## Detailed Staging References

All staging references found via `grep -n stag analysis-issues.js`:

| Line(s) | Reference | Action |
|---------|-----------|--------|
| 104 | `// Combine server issues with staged issues` comment | REWORD → "Filter issues by severity" |
| 106 | `[...state.allIssues, ...Explorer.stagedIssues].filter(...)` | REPLACE → `state.allIssues.filter(...)` — server health-check includes all issues |
| 377 | `// Stage the creation (same as createObjectForIssue)` comment | REWORD → "Create the object via candidate API" |
| 391 | `// Add to staged creations` comment | REWORD → "Create via candidate API" |
| 400-403 | `Explorer.getStagedCreations()` / `.push(creation)` / `Explorer.setStagedCreations(staging)` | REPLACE → `CandidateApi.createObject()` call with `result.success` check |
| 405-406 | `state.allObjects.push(newObj)` — manual UI list mutation | REMOVE — `refreshAfterObjectChange()` reloads from server |
| 411 | `console.error('Failed to stage creation:', ...)` | REWORD → `'Failed to create object:'` |
| 416 | `Explorer.saveStagedChanges()` | REMOVE — server handles persistence |
| 417 | `Explorer.updateCommitUI()` | KEEP — still needed to update commit badge |
| 418 | `Explorer.buildTree()` | REMOVE — `refreshAfterObjectChange()` handles tree rebuild |
| 420 | `Explorer.computeStagedIssues()` | REMOVE — `loadIssues()` fetches fresh issues from server |
| 424 | `showToast('Staged ${created} new object${created !== 1 ? 's' : ''} for creation')` | **KEEP TEXT UNCHANGED** — UI visual parity (Commandment 2) |
| 426 | `showToast('Staged ${created} objects, ${failed} failed')` | **KEEP TEXT UNCHANGED** — UI visual parity (Commandment 2) |
| 566 | `// Open in editor so user can modify before staging` comment | REWORD → "before saving" |
| 569 | `showToast('Edit the ${objectType} and save to stage the creation', 'info')` | **KEEP TEXT UNCHANGED** — UI visual parity (Commandment 2) |
| 572 | `Explorer.computeStagedIssues()` | REMOVE — `loadIssues()` on next line fetches fresh issues |

## Error Handling
- `CandidateApi.createObject()` failures are caught in both the `result.success` check (API-level errors) and the `try/catch` (network/unexpected errors).
- Failed creations increment the `failed` counter and log the error with `console.error`.
- The toast message reports both created and failed counts so the user knows what happened.
- `loadIssues()` failure is handled by its existing error display in the container.

## Audit Logging
- All `CandidateApi.createObject()` calls go through the candidate routes on the backend, which log each creation via `audit_service.py`. No additional client-side audit logging is needed; the backend handles it.

## Linting
- All changes must pass `npm run lint:js` (ESLint) before committing.
- No new lint exceptions introduced.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Add `?candidate=1` suffix to health-check fetch in `loadIssues()` | [ ] |
| 2 | Remove `Explorer.stagedIssues` from `filterIssues()` combined array | [ ] |
| 3 | Rewrite `executeBatchCreate()` to use `CandidateApi.createObject()` | [ ] |
| 4 | Remove `Explorer.getStagedCreations()` / `setStagedCreations()` calls | [ ] |
| 5 | Remove `state.allObjects.push(newObj)` manual list mutation | [ ] |
| 6 | Remove `Explorer.saveStagedChanges()` call | [ ] |
| 7 | Remove `Explorer.buildTree()` call (handled by `refreshAfterObjectChange`) | [ ] |
| 8 | Remove `Explorer.computeStagedIssues()` calls (lines 420, 572) | [ ] |
| 9 | Add `await Explorer.refreshAfterObjectChange()` and `await Explorer.refreshCandidateDiff()` | [ ] |
| 10 | Update console.error text from "stage creation" to "create object" | [ ] |
| 11 | Reword code comments (lines 104, 377, 391, 566) | [ ] |
| 12 | Preserve all toast text unchanged (lines 424, 426, 569) | [ ] |
| 13 | Verify `npm run lint:js` passes | [ ] |

## Verification
- Issues tab shows candidate-aware issues (health-check uses `?candidate=1`)
- Batch create works in candidate mode (CandidateApi.createObject per object)
- Toast messages remain unchanged: "Staged N new objects for creation", "Staged N objects, M failed", "Edit the ${objectType} and save to stage the creation"
- Single-object create via `resolveGroupedError` works and refreshes issues
- No console errors
- `npm run lint:js` passes

## Playwright Validation
- **Issues tab load**: Navigate to Issues tab in candidate mode, verify issues load from server health-check
- **Batch create**: Click "Create All" for a missing object type, confirm dialog appears, submit, verify toast shows correct count and objects appear in tree
- **Single create**: Click "Create" on a single missing object, verify dialog opens, submit, verify object appears
- **Error handling**: If creation fails (e.g., invalid target file), verify toast reports failure count

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | PASS | All creates go through `CandidateApi.createObject()` which writes to candidate dir only; nothing touches live config until Apply |
| 2 | UI visual parity | PASS | All toast text preserved verbatim: "Staged N new objects for creation", "Staged N objects, M failed", "Edit the ${objectType} and save to stage the creation" |
| 3 | Full audit logging | PASS | `CandidateApi.createObject()` routes through backend candidate endpoints which log via `audit_service.py` |
| 4 | Proper error handling | PASS | Both `result.success` check and `try/catch` for each create; failed count reported in toast; `loadIssues()` has its own error display |
| 5 | Dead code deletion | PASS | `getStagedCreations`/`setStagedCreations` calls removed; `saveStagedChanges` call removed; `computeStagedIssues` calls removed; `state.allObjects.push` manual mutation removed; `buildTree` call removed (handled by refresh) |
| 6 | Full functionality migration | PASS | Batch create, single create, issue resolution all migrated to CandidateApi equivalents; `loadIssues` refreshes from server; `refreshAfterObjectChange` rebuilds tree |
| 7 | Palo Alto candidate model | PASS | Creates go to candidate directory via CandidateApi; health-check analyzes candidate state; Apply promotes to live |
| 8 | Change tracking document | PASS | Change tracking table with 13 items included above |
| 9 | Complete planning before implementation | PASS | This plan is complete; all line-level changes documented before any code changes |
| 10 | Linting enforcement | PASS | Plan requires `npm run lint:js` pass before commit |
| 11 | Playwright validation | PASS | Playwright test scenarios documented for issues tab load, batch create, single create, and error handling |
