# L09 — `static/js/commit-dialog.js` — MODIFY

## Purpose
Rewrite commit dialog to use candidate diff data. Replace staging data processing with candidate diff rendering. Add apply+commit, apply-only, and discard flows. The Apply button in the commit dialog triggers writing candidate config over live config (Palo Alto candidate model). All user-facing text (button labels, dialog titles, toast messages) remains unchanged to preserve UI visual parity.

## Removal Audit
- `extractStagingArrays(staging)` → REMOVED. Candidate diff has its own structure (file-level changes, not operation-type arrays).
- `hasFileOperations(s)` → REMOVED. Candidate diff reports all changes uniformly.
- `hasGuiStagingChanges(s)` → REMOVED. Use `candidateDiff.totalCount > 0`.
- `getStagingCounts(staging)` → REPLACED by reading counts from `candidateDiff.counts`.
- `buildGlobalFileBasedChanges(pendingEdits, stagedMoves, ...)` → REPLACED. Candidate diff already provides file-based change list.
- `applyGuiStagingChanges()` calling `/api/staging/apply` → REPLACED by `CandidateApi.apply()`.
- `discardGlobalChanges()` calling `DELETE /api/staging` → REPLACED by `CandidateApi.clearSession()`.
- `autoGitCommitGlobal()` clearing staging → REPLACED by apply+commit flow.
- `diffDataHasGuiStaging()` → REMOVED. Check `candidateDiff.totalCount > 0`.

All data processing functions that decompose staging arrays are replaced by rendering the candidate diff directly, which already groups changes by file.

### Detailed Line-by-Line Staging References

**API endpoint references (7):**
| Line | Reference | Action |
|------|-----------|--------|
| 35 | `ApiClient.get('/api/staging/diff', { silent: true })` | REPLACE with `CandidateApi.getDiff()` |
| 36 | `ApiClient.get('/api/staging/analyze-references', { silent: true })` | REPLACE with `CandidateApi.analyzeReferences()` |
| 245 | `ApiClient.post('/api/staging/apply', { updateReferences, deferClear: true })` | REPLACE with `CandidateApi.apply()` |
| 688 | `ApiClient.del('/api/staging', { silent: true })` in `discardStagingAfterFailedCommit()` | REPLACE with `CandidateApi.clearSession()` |
| 1430 | `ApiClient.del('/api/staging', { silent: true })` in `discardGlobalChanges()` | REPLACE with `CandidateApi.clearSession()` |
| 1526 | `ApiClient.del('/api/staging', { silent: true })` in `autoGitCommitGlobal()` | REPLACE with `CandidateApi.clearSession()` |
| 260 | `baseState.diffData.staging` access in `diffDataHasGuiStaging()` | REMOVE entire function |

**`extractStagingArrays()` function and all call sites (6):**
| Line | Reference | Action |
|------|-----------|--------|
| 67-79 | `function extractStagingArrays(staging)` definition | REMOVE entire function |
| 261 | `extractStagingArrays(baseState.diffData.staging)` in `diffDataHasGuiStaging()` | REMOVE (function removed) |
| 313 | `extractStagingArrays(data.staging \|\| {})` in `buildGlobalCommitDialogHtml()` | REMOVE (replaced by candidate diff rendering) |
| 1395 | `baseState.diffData.staging` null check in `updateGlobalContextLines()` | REMOVE (replaced by candidate diff) |
| 1400 | `extractStagingArrays(baseState.diffData.staging)` in `updateGlobalContextLines()` | REMOVE (replaced by candidate diff) |

**`getStagingCounts()` function and call sites (2):**
| Line | Reference | Action |
|------|-----------|--------|
| 185-206 | `function getStagingCounts(staging)` definition | REMOVE entire function |
| 1425 | `getStagingCounts(staging)` call in `discardGlobalChanges()` | REPLACE with candidate diff count read |

**`buildGlobalFileBasedChanges()` function and call sites (3):**
| Line | Reference | Action |
|------|-----------|--------|
| 973-1025 | `function buildGlobalFileBasedChanges(pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, ...)` definition | REMOVE entire function |
| 320 | `buildGlobalFileBasedChanges(s.pendingEdits, s.stagedMoves, s.stagedCreations, s.stagedObjectDeletions, ...)` in `buildGlobalCommitDialogHtml()` | REMOVE (replaced by candidate diff) |
| 1404 | `buildGlobalFileBasedChanges(s.pendingEdits, s.stagedMoves, s.stagedCreations, s.stagedObjectDeletions, ...)` in `updateGlobalContextLines()` | REMOVE (replaced by candidate diff) |

**`discardStagingAfterFailedCommit()` function (1):**
| Line | Reference | Action |
|------|-----------|--------|
| 679-693 | `function discardStagingAfterFailedCommit()` — calls `ApiClient.del('/api/staging')` | REPLACE with `CandidateApi.clearSession()` |

**10 staging data key references (across `extractStagingArrays` and `getStagingCounts`):**
| Line | Key | Action |
|------|-----|--------|
| 69 | `staging.pendingEdits` | REMOVE with function |
| 70 | `staging.stagedMoves` | REMOVE with function |
| 71 | `staging.stagedCreations` | REMOVE with function |
| 72 | `staging.stagedObjectDeletions` | REMOVE with function |
| 73 | `staging.stagedFileCreations` | REMOVE with function |
| 74 | `staging.stagedFileDeletions` | REMOVE with function |
| 75 | `staging.stagedFileMoves` | REMOVE with function |
| 76 | `staging.stagedFolderCreations` | REMOVE with function |
| 77 | `staging.stagedFolderDeletions` | REMOVE with function |
| 78 | `staging.stagedFolderMoves` | REMOVE with function |
| 187-196 | Same 10 keys read in `getStagingCounts()` | REMOVE with function |

**Staging UI text references — KEEP ALL USER-FACING TEXT UNCHANGED:**
| Line | Reference | Action |
|------|-----------|--------|
| 242 | `'Applying staged changes...'` in `applyGuiStagingChanges()` | KEEP text unchanged (UI visual parity) |
| 250 | `'Failed to apply staged changes'` error message | KEEP text unchanged |
| 1428 | `'Clearing staged changes...'` in `discardGlobalChanges()` | KEEP text unchanged |
| 1448 | `'All staged changes discarded'` success message | KEEP text unchanged |
| 1456 | `'Staging cleared.'` success message | KEEP text unchanged |
| 1492 | `'Apply staged changes'` command label in `showStagingResultPanel()` | KEEP text unchanged |

**"staging preserved" retry logic — KEEP ALL USER-FACING TEXT UNCHANGED:**
| Line | Reference | Action |
|------|-----------|--------|
| 638 | `// C-10: Add retry button if commit failed but staging was preserved` comment | UPDATE comment to reference candidate internally |
| 646 | `onclick="discardStagingAfterFailedCommit()"` button handler | REPLACE function name to `discardCandidateAfterFailedCommit()` |
| 676-693 | `discardStagingAfterFailedCommit()` function body | REPLACE `ApiClient.del('/api/staging')` with `CandidateApi.clearSession()` |
| 681 | `'Discard Staging?'` dialog title | KEEP text unchanged (UI visual parity) |
| 682 | `'Discarding staging will clear the staging state'` dialog message | KEEP text unchanged (UI visual parity) |
| 683 | `'Discard Staging'` confirm button text | KEEP text unchanged (UI visual parity) |
| 691 | `'Staging cleared'` toast message | KEEP text unchanged (UI visual parity) |
| 1598 | `// C-10: Show retry option if staging was preserved after apply` comment | UPDATE comment to reference candidate internally |
| 1601 | `'Staging preserved - you can retry the commit.'` info text | KEEP text unchanged (UI visual parity) |

**Helper functions that process staging arrays (REMOVE):**
| Line | Function | Action |
|------|----------|--------|
| 85-88 | `hasFileOperations(s)` | REMOVE |
| 93-97 | `hasGuiStagingChanges(s)` | REMOVE |
| 241-253 | `applyGuiStagingChanges()` | REPLACE with `CandidateApi.apply()` call |
| 259-263 | `diffDataHasGuiStaging()` | REMOVE |
| 846-851 | `buildEditsMap(pendingEdits)` | REMOVE (staging helper) |
| 857-902 | `processStagedMove(moveEntry, ...)` | REMOVE (staging helper) |
| 907-936 | `processPendingEdit(editEntry, ...)` | REMOVE (staging helper) |
| 941-949 | `processStagedCreation(creation, ...)` | REMOVE (staging helper) |
| 955-967 | `processStagedDeletion(globalIndex, ...)` | REMOVE (staging helper) |

**Other staging references:**
| Line | Reference | Action |
|------|-----------|--------|
| 209 | `resetFrontendAfterDiscard()` calls `Explorer.resetStagingState()` | REPLACE with candidate-aware reset |
| 214 | `Explorer.resetStagingState()` call | REPLACE |
| 326 | `stagedFilePaths` variable filtering git changes from staging preview | REMOVE (candidate diff already handles) |
| 329 | `!stagedFilePaths.has(fullPath) && !stagedFilePaths.has(gc.path)` | REMOVE |
| 349 | `buildFileAndFolderOperationsHtml(s.stagedFolderCreations, ...)` | REMOVE (candidate diff includes file ops) |
| 402 | `// (reference was already staged by the rename dialog)` comment | REMOVE comment |
| 1413 | `buildFileAndFolderOperationsHtml(s.stagedFolderCreations, ...)` | REMOVE |
| 1424 | `baseState.diffData && baseState.diffData.staging` access | REMOVE |
| 1439 | `showStagingDiscardResultPanel(...)` function name | RENAME to `showDiscardResultPanel` |
| 1440 | `'Clear staging data'` command label | KEEP text unchanged (UI visual parity) |
| 1490 | `showStagingResultPanel(...)` function name | RENAME to `showApplyFailedResultPanel` |
| 1500 | `clearStagingOnSuccess` parameter in `autoGitCommitGlobal()` | RENAME to `clearCandidateOnSuccess` |
| 1523-1527 | `// C-10: Only clear staging if commit was successful` + `ApiClient.del` | REPLACE with `CandidateApi.clearSession()` |

## Changes

**1. Rewrite `showGlobalCommitDialog()`** — Fetch structured diff + reference analysis:
```javascript
// BEFORE
const [diffResult, refResult] = await Promise.all([
    ApiClient.get('/api/staging/diff', { silent: true }),
    ApiClient.get('/api/staging/analyze-references', { silent: true })
]);
// AFTER
const [diffResult, refResult] = await Promise.all([
    CandidateApi.getDiffStructured(),
    CandidateApi.analyzeReferences()
]);
```

**2. Replace staging array processing** with structured diff rendering:
The structured diff response provides per-file, per-object change data:
```json
{
    "files": [
        {
            "path": "hosts.cfg",
            "status": "modified",
            "additions": [{"object_type": "host", "name": "web03", "attributes": {}}],
            "removals": [{"object_type": "host", "name": "old-host", "attributes": {}}],
            "modifications": [{"object_type": "host", "name": "web01", "changed_fields": [{"field": "address", "old_value": "10.0.0.1", "new_value": "10.0.0.2"}]}]
        }
    ],
    "counts": {"files_changed": 3, "objects_added": 1, "objects_removed": 1, "objects_modified": 2, "fields_changed": 5},
    "file_operations": {"files_created": [], "files_deleted": [], "files_moved": []}
}
```
Replace `buildGlobalFileBasedChanges()` with a function that renders this structure directly. The structured diff carries the same per-object, per-field detail that the staging arrays provided — the commit dialog's semantic diff view (Nagios `define { }` blocks with red/green field highlighting) is preserved.

**3. Rewrite commit flow** — Three buttons (same labels as current UI):
- **Apply & Commit**: `CandidateApi.apply({ updateReferences })` → git commit → done (candidate already cleared by apply). Apply = copy candidate config over live config (Palo Alto model). No changes written to disk until this button is clicked.
- **Apply Only**: `CandidateApi.apply({ updateReferences })` → done. Writes candidate to live config without git commit.
- **Discard**: `CandidateApi.clearSession()` (no apply, no disk writes)

The `updateReferences` flag comes from the "Update references" checkbox (see item 5).

**4. Remove `extractStagingArrays()`**, `hasFileOperations()`, `hasGuiStagingChanges()`, `getStagingCounts()`, `buildGlobalFileBasedChanges()`, and all helper functions that process staging arrays. Replace count displays with `diffResult.counts`.

**5. Keep** `buildReferenceChangesSection()`, `injectReferenceChanges()`, and the "Update references" checkbox — these work with the `analyzeReferences()` response which has the same format as the staging system. The checkbox value is passed to `apply({ updateReferences })`.

**6. Update discard flow** (internal API call changes only; user-facing text unchanged):
```javascript
// BEFORE
ApiClient.del('/api/staging', { silent: true })
// AFTER
CandidateApi.clearSession()
```

**7. Add audit logging** for all three operations:
```javascript
// After successful apply
AuditLogger.log('candidate_apply', { updateReferences, fileCount: diffResult.counts.files_changed });

// After successful commit
AuditLogger.log('candidate_commit', { commitHash, fileCount: diffResult.counts.files_changed });

// After successful discard
AuditLogger.log('candidate_discard', { changeCount });
```
The backend `CandidateApi.apply()` and `CandidateApi.clearSession()` endpoints must also write to the audit log (see L03/L04 plans). The frontend logging here is supplementary — the backend is the audit source of truth.

**8. Error handling** for apply and commit failures:
- If `CandidateApi.apply()` fails: show error in result panel with the existing "Apply staged changes" retry button. Candidate session is preserved (no partial writes — apply is atomic).
- If git commit fails after successful apply: show the existing retry/discard buttons. The "Discard Staging?" confirmation dialog appears with its current text. `discardCandidateAfterFailedCommit()` calls `CandidateApi.clearSession()`.
- If `CandidateApi.clearSession()` fails during discard: show toast error, do not close dialog.

## UI Text Parity Guarantee

The following user-facing strings are explicitly preserved unchanged. Only internal function names, variable names, API calls, and code comments change.

| Current Text | Location | Status |
|---|---|---|
| `'Applying staged changes...'` | Running panel | UNCHANGED |
| `'Failed to apply staged changes'` | Error message | UNCHANGED |
| `'Clearing staged changes...'` | Running panel | UNCHANGED |
| `'All staged changes discarded'` | Success message | UNCHANGED |
| `'Staging cleared.'` | Success message | UNCHANGED |
| `'Apply staged changes'` | Command label | UNCHANGED |
| `'Discard Staging?'` | Dialog title | UNCHANGED |
| `'Discarding staging will clear the staging state'` | Dialog message | UNCHANGED |
| `'Discard Staging'` | Confirm button | UNCHANGED |
| `'Staging cleared'` | Toast message | UNCHANGED |
| `'Staging preserved - you can retry the commit.'` | Info text | UNCHANGED |
| `'Clear staging data'` | Command label | UNCHANGED |

## Change Tracking

| What Changed | Before (Staging) | After (Candidate) |
|---|---|---|
| Diff data source | `/api/staging/diff` | `CandidateApi.getDiffStructured()` |
| Reference analysis | `/api/staging/analyze-references` | `CandidateApi.analyzeReferences()` |
| Apply action | `ApiClient.post('/api/staging/apply')` | `CandidateApi.apply()` |
| Discard action | `ApiClient.del('/api/staging')` | `CandidateApi.clearSession()` |
| Diff rendering | `extractStagingArrays()` + `buildGlobalFileBasedChanges()` | Direct rendering of structured candidate diff |
| Count display | `getStagingCounts()` | `diffResult.counts` |
| Frontend reset | `Explorer.resetStagingState()` | Candidate-aware reset |
| Internal fn name | `discardStagingAfterFailedCommit()` | `discardCandidateAfterFailedCommit()` |
| Internal fn name | `showStagingDiscardResultPanel()` | `showDiscardResultPanel()` |
| Internal fn name | `showStagingResultPanel()` | `showApplyFailedResultPanel()` |
| Internal param | `clearStagingOnSuccess` | `clearCandidateOnSuccess` |
| User-facing text | All dialog/toast/label text | **NO CHANGES** |

## Dead Code Deletion Inventory

All of the following functions are removed entirely (not replaced with stubs):

| Function | Lines | Reason |
|---|---|---|
| `extractStagingArrays(staging)` | 67-79 | Staging array decomposition; candidate diff is pre-structured |
| `hasFileOperations(s)` | 85-88 | Staging array check; candidate diff reports uniformly |
| `hasGuiStagingChanges(s)` | 93-97 | Staging array check; replaced by `totalCount > 0` |
| `getStagingCounts(staging)` | 185-206 | Staging array counting; replaced by `diffResult.counts` |
| `diffDataHasGuiStaging()` | 259-263 | Staging data check; replaced by candidate diff check |
| `buildEditsMap(pendingEdits)` | 846-851 | Staging helper for edit processing |
| `processStagedMove(moveEntry, ...)` | 857-902 | Staging helper for move processing |
| `processPendingEdit(editEntry, ...)` | 907-936 | Staging helper for edit rendering |
| `processStagedCreation(creation, ...)` | 941-949 | Staging helper for creation rendering |
| `processStagedDeletion(globalIndex, ...)` | 955-967 | Staging helper for deletion rendering |
| `buildGlobalFileBasedChanges(...)` | 973-1025 | Staging array aggregator; candidate diff is pre-aggregated |

Total: ~180 lines of dead code removed.

## Linting

After implementation, run:
```bash
npx eslint static/js/commit-dialog.js
```
Ensure zero errors and zero warnings. All new code must follow the existing eslint configuration. No `eslint-disable` comments permitted for new code.

## Verification
- Commit dialog opens and shows candidate diff with correct layout
- Apply & Commit → changes written to disk + git commit created
- Apply Only → changes written to disk, no git commit
- Discard → candidate session cleared, no disk writes
- All dialog text matches current UI exactly (see UI Text Parity table)
- Error handling: apply failure shows retry panel; commit failure shows retry/discard
- Audit log entries created for apply, commit, and discard operations
- No console errors
- `npx eslint static/js/commit-dialog.js` passes clean

## Playwright Test Plan

The commit dialog is an excellent Playwright test target due to its multi-step flows and user-visible state changes.

**Test file:** `tests/e2e/test_commit_dialog.spec.js`

**Test cases:**

1. **Dialog opens with diff summary** — Make an edit, open commit dialog, verify change count and file list are displayed.
2. **Apply & Commit flow** — Open dialog, click Apply & Commit, verify success panel, verify git log shows new commit, verify candidate session is cleared.
3. **Apply Only flow** — Open dialog, click Apply Only, verify changes written to disk, verify no git commit created, verify candidate session is cleared.
4. **Discard flow** — Open dialog, click Discard, verify "Discard Staging?" confirmation dialog appears with correct text, confirm, verify "Staging cleared" toast appears, verify no disk changes.
5. **Apply failure handling** — Mock apply endpoint to return error, verify error panel with "Apply staged changes" retry button appears.
6. **Commit failure after apply** — Mock git commit to fail, verify retry/discard buttons appear, verify "Staging preserved - you can retry the commit." text displayed.
7. **Discard after failed commit** — From commit failure state, click discard, verify "Discard Staging?" dialog, confirm, verify "Staging cleared" toast.
8. **Update references checkbox** — Make a rename, open dialog, verify "Update references" checkbox present, verify checkbox value is passed to apply call.
9. **Empty diff** — Open dialog with no changes, verify appropriate empty state.

## Commandments Compliance

- [x] **C1: No live config mutation until Apply.** The Apply button in the commit dialog triggers `CandidateApi.apply()` which copies candidate over live config. No disk writes occur until Apply is clicked. Discard clears the candidate session without touching disk.
- [x] **C2: UI visual parity.** All user-facing text is explicitly preserved unchanged: "Applying staged changes...", "Discard Staging?", "Discard Staging", "Staging cleared", "Staging preserved", "Clear staging data", and all other dialog/toast/label strings. See the "UI Text Parity Guarantee" table. Only internal function names, variable names, API calls, and code comments change.
- [x] **C3: Full audit logging.** Apply, commit, and discard operations all produce audit log entries. Backend endpoints are the source of truth; frontend logging is supplementary. See Change 7.
- [x] **C4: Proper error handling.** Apply failure shows retry panel. Commit failure after apply shows retry/discard buttons with candidate session preserved. Discard failure shows toast error without closing dialog. See Change 8.
- [x] **C5: Dead code deletion.** 11 functions (~180 lines) removed entirely. Full inventory in "Dead Code Deletion Inventory" section. No stubs left behind.
- [x] **C6: Full functionality migration.** All current capabilities preserved: apply+commit flow, apply-only flow, discard flow, reference analysis, "Update references" checkbox, retry after failure, discard after failed commit, diff rendering with per-object/per-field detail.
- [x] **C7: Palo Alto candidate model.** Apply = copy candidate config over live config. Candidate session is the working copy; live config is untouched until explicit Apply.
- [x] **C8: Change tracking document.** "Change Tracking" section provides before/after mapping for every data source, API call, function name, and parameter that changed. User-facing text explicitly marked as NO CHANGES.
- [x] **C9: Complete planning before implementation.** Full line-by-line removal audit, structured diff format specification, all three commit flows defined, error handling paths specified, UI text parity table, dead code inventory, and Playwright test plan all completed before implementation.
- [x] **C10: Linting enforcement.** Explicit `npx eslint` command in Linting section. Zero errors/warnings required. No `eslint-disable` in new code.
- [x] **C11: Playwright validation.** Full test plan with 9 test cases covering dialog open, all three flows (apply+commit, apply-only, discard), error handling (apply failure, commit failure), discard after failed commit, reference checkbox, and empty state.
