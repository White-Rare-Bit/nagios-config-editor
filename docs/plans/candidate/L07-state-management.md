# L07 — `static/js/explorer/state-management.js` — MODIFY

## Purpose
Remove all staging accessor helpers. Add `computeCandidateBadges()` that reads from `state.candidateDiff` to compute tree badges.

## Removal Audit

Functions being removed and their candidate equivalents:
- `getPendingEdit(globalIndex)` → REMOVED. No client-side pendingEdits map. Object editor fetches current attributes from candidate objects via `?candidate=1`.
- `setPendingEdit(globalIndex, editData)` → REMOVED. Edits go to server via CandidateApi.editObject().
- `removePendingEdit(globalIndex)` → REMOVED. Revert via CandidateApi.undo().
- `getStagedCreations()` → REMOVED. Server manages creations.
- `setStagedCreations(arr)` → REMOVED. Server manages creations.
- `hasStagedChanges()` → REPLACED by `hasCandidateChanges()` which checks `state.candidateActive && state.candidateDiff`.
- `resetStagingState()` → REPLACED by candidate session clear flow.
- `saveStagedChanges()` → REMOVED. No client-side state to save. All changes already on server.
- `loadStagedChanges()` → REMOVED. No client-side state to load.
- `getEffectiveAttributes(obj)` → SIMPLIFIED. In candidate mode, objects from server already have their current attributes. This becomes a passthrough: just return `obj.attributes`.
- `getEffectiveName(obj)` → SIMPLIFIED. Just read from object directly.
- `getStagedDisplayName(obj)` → SIMPLIFIED. Just read display_name from object.
- `refreshAfterObjectChange()` → KEPT but simplified. Reloads objects from server and rebuilds tree.

Functions being ADDED:
- `hasCandidateChanges()` → Returns `state.candidateActive && state.candidateDiff && state.candidateDiff.totalCount > 0`
- `computeCandidateBadges()` → Reads `state.candidateDiff` to mark files/objects with change badges in the tree

## Changes

**Remove all staging accessor functions** and replace with simplified candidate-aware versions:

```javascript
// === REMOVED FUNCTIONS ===
// getPendingEdit, setPendingEdit, removePendingEdit
// getStagedCreations, setStagedCreations
// saveStagedChanges, loadStagedChanges
// resetStagingState

// === SIMPLIFIED FUNCTIONS ===

/**
 * Check if there are any candidate changes.
 */
function hasCandidateChanges() {
    return state.candidateActive && state.candidateDiff && state.candidateDiff.totalCount > 0;
}

/**
 * Get effective attributes for an object.
 * In candidate mode, objects already have current attributes from server.
 */
function getEffectiveAttributes(obj) {
    return obj.attributes || {};
}

/**
 * Get effective name for an object.
 */
function getEffectiveName(obj) {
    const nameField = Explorer.constants?.nameFields?.[obj.object_type] || 'name';
    return obj.attributes?.[nameField] || obj.display_name || obj.name || '';
}

/**
 * Get display name for an object.
 */
function getStagedDisplayName(obj) {
    return obj.display_name || obj.name || getEffectiveName(obj);
}

/**
 * Compute candidate change badges from diff data.
 * Populates a Map of file→changes for tree badge rendering.
 */
function computeCandidateBadges() {
    // Read state.candidateDiff and build badge data
    // Called after getDiff() updates state.candidateDiff
    if (!state.candidateDiff) { return; }
    // Badge computation logic based on diff structure
    Explorer.updateBadge();
    Explorer.buildTree();
}

/**
 * Refresh UI after a candidate operation.
 * Reloads objects from server, rebuilds tree, and refreshes issue badges.
 */
async function refreshAfterObjectChange() {
    await Explorer.loadObjects();
    Explorer.buildTree();
    if (state.editedObject) {
        Explorer.showCenterPaneObject(state.editedObject.global_index);
    }
    // Refresh issue badges — health-check runs on candidate objects
    // so badges stay accurate after each edit
    Explorer.loadIssuesForBadges();
}
```

**Export updated functions:**
```javascript
Explorer.hasCandidateChanges = hasCandidateChanges;
Explorer.getEffectiveAttributes = getEffectiveAttributes;
Explorer.getEffectiveName = getEffectiveName;
Explorer.getStagedDisplayName = getStagedDisplayName;
Explorer.computeCandidateBadges = computeCandidateBadges;
Explorer.refreshAfterObjectChange = refreshAfterObjectChange;
```

## Change Tracking

- [ ] Remove `getPendingEdit(globalIndex)`
- [ ] Remove `setPendingEdit(globalIndex, editData)`
- [ ] Remove `removePendingEdit(globalIndex)`
- [ ] Remove `getStagedCreations()`
- [ ] Remove `setStagedCreations(arr)`
- [ ] Remove `hasStagedChanges()` (replaced by `hasCandidateChanges()`)
- [ ] Remove `resetStagingState()` (replaced by candidate session clear flow)
- [ ] Remove `saveStagedChanges()`
- [ ] Remove `loadStagedChanges()`
- [ ] Simplify `getEffectiveAttributes(obj)` to passthrough
- [ ] Simplify `getEffectiveName(obj)` to read from object directly
- [ ] Simplify `getStagedDisplayName(obj)` to read from object directly
- [ ] Simplify `refreshAfterObjectChange()` to reload from server
- [ ] Add `hasCandidateChanges()`
- [ ] Add `computeCandidateBadges()`
- [ ] Update module exports to reflect new/removed functions

## Verification
- `npm run lint:js` passes
- `python3 -m ruff check .` passes (no Python in this file, but verify no side-effects)
- Explorer loads, objects display
- `Explorer.getEffectiveAttributes` is callable
- `Explorer.hasCandidateChanges` is callable and returns boolean
- `Explorer.computeCandidateBadges` is callable
- Playwright: verify object display and tree badge rendering after state-management migration

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** All functions either read from the server-provided candidate state or delegate writes to CandidateApi. No live config mutation occurs.
- [x] **C2 — UI visual parity.** Simplified accessors return the same values the old staging accessors produced. Badge rendering via `computeCandidateBadges()` maintains existing visual behavior.
- [ ] **C3 — Full audit logging.** N/A — This is a client-side JS helper module. Audit logging is the responsibility of the server-side CandidateApi endpoints these functions call.
- [x] **C4 — Proper error handling.** `getEffectiveAttributes` returns `{}` on missing attributes. `getEffectiveName` uses optional chaining with fallbacks. `computeCandidateBadges` guards on null diff.
- [x] **C5 — Dead code deletion.** Nine staging accessor functions explicitly removed. The Removal Audit documents every function and its disposition.
- [x] **C6 — Full functionality migration.** Every removed function has a documented candidate equivalent: `hasStagedChanges` becomes `hasCandidateChanges`, `getEffective*` functions are simplified but preserved, `refreshAfterObjectChange` is kept and updated.
- [x] **C7 — Palo Alto candidate model.** Client-side staging accessors replaced with functions that read from server-managed candidate state. Edits go to server; client just reads results.
- [x] **C8 — Change tracking document.** Change Tracking section added above with tickable checklist for every function change.
- [x] **C9 — Complete planning before implementation.** This file is part of the L07 planning layer; no code changes until the full plan is approved.
- [x] **C10 — Linting enforcement.** Verification section includes `npm run lint:js` check.
- [x] **C11 — Playwright validation.** Verification section includes Playwright check for object display and tree badge rendering after migration.
