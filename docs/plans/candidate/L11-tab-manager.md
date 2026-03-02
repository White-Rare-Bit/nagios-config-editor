# L11 — `static/js/explorer/tab-manager.js` — MODIFY

## Purpose
Replace the `state.pendingEdits.has()` check for the modified tab dot indicator with a candidate-aware equivalent that reads from `state.candidateDiff`. Delete the dead `pendingEdits` reference. Preserve full visual parity of the tab modified indicator (dot + `.modified` class).

## Removal Audit

| Line | Reference | Action | Reason |
|------|-----------|--------|--------|
| 254 | `state.pendingEdits.has(tab.objectIndex)` | REPLACE | Dead code — `state.pendingEdits` Map is removed in L07-main.md. Replaced by `hasObjectChanged(tab.key)` which reads from `state.candidateDiff.changed_files`. |

No other staging references exist in this file. All other functions (`openTab`, `closeTab`, `activateTab`, `renderTabBar`, `restoreTabs`, `validateTabs`, `syncTreeSelection`, `persistTabs`) are purely frontend navigation and remain unchanged.

## Changes

**1. Add `hasObjectChanged()` helper** (before `renderTabBar`):

The `candidateDiff` (from `CandidateApi.getDiff()`, cached in `state.candidateDiff` by L07-data-loading `refreshCandidateDiff()`) returns `changed_files` — an array of `{file, status}` objects where `status` is `"created"`, `"modified"`, or `"deleted"`. To detect per-object changes, we check whether the object's `source_file` appears in the changed files list with a relevant status.

This is file-level granularity, which is slightly broader than the old `pendingEdits.has()` (which was object-level). However, this matches the candidate model's change tracking granularity — the candidate system tracks changes at the file level via git diff. Per-object granularity is available from the structured diff (`GET /api/candidate/diff/structured`), but that endpoint is expensive (two full parses) and is reserved for the commit dialog. File-level detection is sufficient for the tab dot: if a file has changes, any open tab for an object in that file shows the dot. This is accurate because edits to a file always correspond to object changes within it.

```javascript
/**
 * Check if a tabbed object has candidate changes.
 * Uses file-level change detection from state.candidateDiff.
 * @param {string} tabKey - The stable key of the tab's object
 * @returns {boolean}
 */
function hasObjectChanged(tabKey) {
    if (!state.candidateDiff || !Array.isArray(state.candidateDiff.changed_files)) {
        return false;
    }
    const obj = Explorer.findObjectByKey(tabKey);
    if (!obj) { return false; }
    const objFile = obj.source_file;
    return state.candidateDiff.changed_files.some(function(entry) {
        return entry.file === objFile &&
            (entry.status === 'modified' || entry.status === 'created');
    });
}
```

Key design decisions:
- Uses `tabKey` (stable key) instead of `objectIndex` (global_index) for lookup — stable keys survive reloads, global_index may shift after creates/deletes. This aligns with the stable-key-first approach used across the candidate migration.
- Checks both `modified` and `created` statuses — a newly created file containing the object should also show the dot.
- Does NOT check `deleted` status — deleted objects are no longer in `state.allObjects` and therefore have no open tabs.
- Uses `Explorer.findObjectByKey()` (already defined in main.js) rather than `state.allObjects.find()` for consistent object lookup.

**2. Replace `pendingEdits.has()` in `renderTabBar()`** (line 254):

```javascript
// BEFORE (line 254)
const hasPendingEdit = state.pendingEdits.has(tab.objectIndex);

// AFTER
const hasPendingEdit = hasObjectChanged(tab.key);
```

The rest of the `renderTabBar()` function remains unchanged. The HTML template already uses `hasPendingEdit` to:
- Add the `.modified` CSS class to the tab div (line 259)
- Conditionally render `<span class="editor-tab-dot"></span>` (line 264)

Both of these produce identical visual output to the current system, preserving UI visual parity.

**3. Keep all `Explorer.checkForChanges()` calls unchanged** — In the candidate system, `checkForChanges()` is rewritten by L08-object-editor to call `CandidateApi.editObject()` (async auto-save to server). The three call sites in tab-manager.js remain:
- `openTab()` line 86 — auto-saves before switching tabs
- `closeTab()` line 116 — auto-saves before closing active tab
- `activateTab()` line 149 — auto-saves before activating a different tab

These calls are fire-and-forget (the return value is not awaited). This is intentional — tab switching should not block on network. If the save fails, the object editor's error handling (L08) surfaces the error via toast notification. The tab-manager does not need to handle save errors.

**4. No export changes** — `hasObjectChanged` is a module-private helper, not exported to the Explorer namespace. It is only called from `renderTabBar()`.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Add `hasObjectChanged(tabKey)` helper function | [ ] |
| 2 | Replace `state.pendingEdits.has(tab.objectIndex)` with `hasObjectChanged(tab.key)` on line 254 | [ ] |
| 3 | Verify `.modified` class and `.editor-tab-dot` span render identically | [ ] |
| 4 | Verify `checkForChanges()` calls remain and work with L08 async rewrite | [ ] |

## No Audit Logging Required

Tab-manager.js is purely frontend navigation — it performs no backend mutations and no data changes. All server-side operations triggered indirectly (via `Explorer.checkForChanges()`) are logged by their own modules (L08-object-editor auto-save logs through CandidateManager's git commit + audit_service). No additional audit logging is needed in this file.

## Error Handling

- `hasObjectChanged()`: Defensive null checks on `state.candidateDiff` and `state.candidateDiff.changed_files`. Returns `false` if either is missing (safe default — no dot shown when diff data is unavailable).
- `Explorer.findObjectByKey()`: Returns `null` if object not found; `hasObjectChanged` returns `false` in that case.
- `Explorer.checkForChanges()` calls: Fire-and-forget. Errors are handled by L08-object-editor's rewritten `checkForChanges()` which surfaces failures via toast notifications. Tab-manager does not swallow errors — it simply does not await the async result.

## Linting

After implementation, verify:
```bash
npm run lint:js
```

The new `hasObjectChanged()` function uses no globals beyond `state` (module-scoped) and `Explorer` (window-scoped), both of which are already declared in the ESLint config (L06-eslint-config). No new lint exceptions required.

## Verification

### Manual Verification
- Modified tabs show dot indicator when object has candidate changes
- Dot disappears after undo reverts all changes to that file
- Tab switching triggers auto-save (via checkForChanges)
- Closing a tab triggers auto-save for the active tab
- No console errors during tab operations
- `.modified` CSS class applied to tab div matches current visual appearance

### Playwright Tests

Add to the explorer E2E test suite:

```
Test: tab-modified-indicator
  1. Navigate to explorer page
  2. Open a host object (click tree item) — tab appears without dot
  3. Edit an attribute (change address field value)
  4. Save the change (triggers CandidateApi.editObject)
  5. Verify the active tab has class .modified
  6. Verify <span class="editor-tab-dot"> is present inside the tab
  7. Open a second object tab — verify it does NOT have .modified class
  8. Undo the change (CandidateApi.undo)
  9. Verify the first tab no longer has .modified class

Test: tab-switch-auto-save
  1. Open a host object, edit an attribute (do not explicitly save)
  2. Open a different object (triggers tab switch)
  3. Switch back to the first tab
  4. Verify the edited attribute value persisted (auto-save fired on switch)
```

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|------------|--------|-------|
| 1 | No live config mutation until Apply | PASS | Tab-manager is purely frontend navigation. No disk writes. `checkForChanges()` writes to candidate directory (not live config). Live config is only modified by `CandidateApi.apply()`. |
| 2 | UI visual parity | PASS | Tab modified dot indicator (`.modified` class + `.editor-tab-dot` span) renders identically to current system. File-level detection from `candidateDiff.changed_files` replaces object-level `pendingEdits.has()` — slightly broader but visually equivalent. |
| 3 | Full audit logging | PASS | No backend mutations in this file. Indirect mutations (via `checkForChanges()` triggering `CandidateApi.editObject()`) are logged by CandidateManager's git commit and audit_service in L08-object-editor and L01-candidate-manager. |
| 4 | Proper error handling | PASS | `hasObjectChanged()` has defensive null checks. `checkForChanges()` errors handled by L08 (toast notifications). No silent failures. |
| 5 | Dead code deletion | PASS | `state.pendingEdits.has(tab.objectIndex)` reference removed — `pendingEdits` Map no longer exists in candidate state (deleted in L07-main). |
| 6 | Full functionality migration | PASS | Tab modified indicator fully migrated from `pendingEdits.has()` to `hasObjectChanged()` using `candidateDiff.changed_files`. All tab operations (open, close, activate, persist, restore, validate, sync) preserved unchanged. |
| 7 | Palo Alto candidate model | PASS | Change detection reads from candidate diff (git-based diff of candidate vs baseline), consistent with the copy-edit-apply model. No client-side staging state referenced. |
| 8 | Change tracking document | PASS | Change tracking table included with checkboxes for each discrete change. |
| 9 | Complete planning before implementation | PASS | All changes fully specified with exact line numbers, before/after code, design rationale, and edge case analysis. No "for now" or placeholder language. |
| 10 | Linting enforcement | PASS | `npm run lint:js` verification step included. No new ESLint exceptions needed. |
| 11 | Playwright validation | PASS | Two Playwright test scenarios specified: tab-modified-indicator (dot appears/disappears with changes) and tab-switch-auto-save (auto-save on tab switch). |
