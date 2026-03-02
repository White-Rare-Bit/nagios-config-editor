# L11 — `static/js/explorer/app.js` — MODIFY

## Purpose
Replace client-side staging state references in tree rendering with candidate diff data. Preserve ALL visual indicators (creation badges, deletion styling, move arrows, staged counts) by sourcing them from `state.candidateBadges` (populated by `computeCandidateBadges()` in L07-state-management.md) instead of from client-side Maps/Sets.

## Visual Parity Requirements (Commandment 2)

The following visual indicators MUST be preserved with identical appearance. Only the data source changes:

| Visual indicator | Current data source | New data source |
|-----------------|--------------------|--------------------|
| Green `+` badge on created objects | `state.stagedCreations` array | `state.candidateBadges.created` Set (stable keys from structured diff `additions`) |
| `staged-creation` CSS class (green tint) | Presence in `stagedCreations` | `state.candidateBadges.created.has(key)` |
| Red `−` badge + strikethrough on deleted objects | `state.stagedObjectDeletions` Set | `state.candidateBadges.deleted` Map (stable key -> display info from structured diff `removals`) |
| `staged-for-deletion` CSS class | `stagedObjectDeletions.has(index)` | `state.candidateBadges.deleted.has(key)` |
| Undo button on deleted objects | `Explorer.unstageObjectDeletion(index)` | `Explorer.undoLastAction()` (candidate undo) |
| `→` badge on moved objects | `state.stagedMoves` Map | `state.candidateBadges.moved` Set (stable keys where source_file changed between baseline and HEAD) |
| `staged` CSS class (move tint) | `stagedMoves.has(key)` | `state.candidateBadges.moved.has(key)` |
| `(+N)` staged count on folders | `staged.length` from `stagedByFile` grouping | `state.candidateBadges.createdByFile[file].length` |
| Staged count in nav/commit button | Sum of all staging Maps/Sets | `state.candidateDiff?.totalCount \|\| 0` |

**Key architectural change**: Created objects that exist only in the candidate (not in baseline) now appear in `state.allObjects` from the server — they are real parsed objects. But they MUST still be visually distinguished with the green `+` badge and `staged-creation` class. The `computeCandidateBadges()` function (L07-state-management.md) identifies these objects by comparing the structured diff against `allObjects` using stable keys.

**Deleted objects**: Objects removed from the candidate do NOT appear in `state.allObjects` (the server only returns candidate objects). However, the structured diff `removals` list provides their identity. Deleted objects MUST still be rendered as ghost tree items with strikethrough, the `−` badge, and an Undo button — just like today. The data source is `state.candidateBadges.deleted` instead of `state.stagedObjectDeletions`.

## Dependencies

- **L07-state-management.md**: Must define `state.candidateBadges` structure and `computeCandidateBadges()` that populates:
  - `state.candidateBadges.created` — Set of stable keys for created objects
  - `state.candidateBadges.deleted` — Map of stable key -> `{object_type, display_name, source_file, global_index_hint}` for deleted objects
  - `state.candidateBadges.moved` — Set of stable keys for moved objects
  - `state.candidateBadges.modified` — Set of stable keys for modified objects
  - `state.candidateBadges.createdByFile` — Map of file path -> array of created object info (for folder count badges)
  - `state.candidateBadges.deletedByFile` — Map of file path -> array of deleted object info (for ghost rendering)
- **L07-data-loading.md**: `refreshCandidateDiff()` must call `computeCandidateBadges()` after updating `state.candidateDiff`, and must also call `CandidateApi.getDiffStructured()` to get per-object data (or the diff endpoint must be enhanced to include object-level data).

**Note on performance**: The structured diff (`getDiffStructured()`) does two full config parses and is expensive for large configs. Two options:
1. **Option A (recommended)**: Enhance `get_diff()` in L01-candidate-manager.md to include a lightweight object summary (created/deleted/moved stable keys) without full field-level diffs. This avoids the double-parse cost for polling.
2. **Option B**: Call `getDiffStructured()` on every poll but cache aggressively (skip if `lastModified` unchanged). Only recommended if Option A is infeasible.

The choice affects L01 and L03, not this file. This plan assumes `state.candidateBadges` is populated by the time `buildTree()` runs.

## Removal Audit

### Functions REMOVED (dead code — visual functionality migrated to new implementations)
| Lines | Function | Reason | Visual migration |
|-------|----------|--------|-----------------|
| 549-567 | `renderStagedCreationTreeItem()` | Created objects now in `allObjects` | Visual badges migrated to `renderTreeItem()` via `candidateBadges.created` |
| 569-600 | `handleStagedItemClick()` | Created objects use normal click handler | Normal `handleItemClick()` handles all objects |
| 602-615 | `updateStagedSelection()` | No separate staged selection | Normal selection handles all objects |
| 620-643 | `selectStagedCreationForEdit()` | Created objects use normal editor | Normal `showCenterPaneObject()` handles all objects |
| 645-676 | `handleStagedContextMenu()` | Created objects use normal context menu | Normal `handleContextMenu()` handles all objects |
| 678-701 | `handleStagedDragStart()` | Created objects use normal drag | Normal drag handlers handle all objects |

### Functions MODIFIED (visual functionality preserved, data source changed)
| Lines | Function | Change |
|-------|----------|--------|
| 492-547 | `buildTree()` file grouping | Remove `stagedByFile` grouping. ADD: inject deleted ghost objects from `candidateBadges.deletedByFile` and created count from `candidateBadges.createdByFile` |
| 732-781 | `renderTreeItem()` | Replace `stagedObjectDeletions.has()` with `candidateBadges.deleted.has()`. Replace `stagedMoves.has()` with `candidateBadges.moved.has()`. ADD `candidateBadges.created.has()` check for `+` badge |
| 802-813 | `getStagedDisplayName()` | Simplify to return `obj.display_name` (server provides current name) |
| 347-348, 361-362 | Staging count calculations | Replace with `state.candidateDiff?.totalCount \|\| 0` |

### State references REMOVED
| Lines | Reference | Action |
|-------|-----------|--------|
| 28 | `stageObjectDeletions()` delegate | REMOVE |
| 29 | `stageNewObjectChanges()` delegate | REMOVE |
| Various | `data-staged-index` attributes | REMOVE (created objects use normal `data-index`) |
| Various | `selectedStagedIndices` management | REMOVE (normal selection handles all) |
| Various | `type: 'staged-creations'` drag data | REMOVE (normal drag data) |

### Staging poll/check logic REPLACED
| Line | Reference | Action |
|------|-----------|--------|
| 161-201 | `checkStagingChanges()` | REPLACE with candidate diff polling (delegates to `refreshCandidateDiff()` from L07-data-loading.md) |
| 170 | `fetch('/api/staging/info')` | REPLACE with `CandidateApi.getDiff()` via poll |
| 173 | `info.hasStaging` check | REPLACE with `state.candidateActive` |
| 174-183 | `info.lastModified` comparison | REPLACE with candidate diff timestamp |
| 185 | `hasStagedChanges() \|\| state.isEditingLocked` | REPLACE with `hasCandidateChanges()` |
| 186-196 | `resetStagingState()` path | REPLACE with candidate session clear |
| 210-211 | `await Explorer.loadStagedChanges()` | REPLACE with candidate diff load |
| 251 | `Explorer.startStagingPoll()` | REPLACE with `Explorer.startCandidatePoll()` |

## Changes

**1. Replace staging count calculations** (lines 347, 361):
```javascript
// BEFORE
const count = state.pendingEdits.size + state.stagedMoves.size + state.stagedCreations.length + state.stagedObjectDeletions.size + state.newFiles.size;
// AFTER
const count = state.candidateDiff?.totalCount || 0;
```

**2. Replace `stagedByFile` grouping with candidate badge data** (lines 492-547):

Remove the `stagedByFile` grouping of `state.stagedCreations`. Replace with injection of deleted ghost objects and created-object counts from `state.candidateBadges`:

```javascript
// BEFORE: Group staged creations by file
const stagedByFile = {};
state.stagedCreations.forEach((creation, idx) => { ... });

// Merge file lists
const allFilesSet = new Set([...Object.keys(objectsByFile), ...Object.keys(stagedByFile)]);

// AFTER: Get candidate badge data for files
const deletedByFile = state.candidateBadges?.deletedByFile || {};
const createdByFile = state.candidateBadges?.createdByFile || {};

// Merge file lists: existing files + files that only have deleted objects
const allFilesSet = new Set([...Object.keys(objectsByFile), ...Object.keys(deletedByFile)]);
```

**3. Render deleted ghost objects in tree** (replaces removal of deletion styling):

Within the file loop in `buildTree()`, after rendering normal objects, render ghost items for deleted objects:

```javascript
// After rendering normal objects for this file:
const deletedInFile = deletedByFile[file] || [];
const deletedHtml = deletedInFile.map(del => renderDeletedGhostItem(del)).join('');

// Folder count includes created count badge
const createdInFile = createdByFile[file] || [];
const createdCount = createdInFile.length;
const countHtml = `${objs.length}${createdCount > 0 ? ` <span class="staged-count">(+${createdCount})</span>` : ''}`;
```

**4. Add `renderDeletedGhostItem()` function** (replaces the deleted-object branch in `renderTreeItem()`):

```javascript
/**
 * Render a ghost tree item for an object deleted in the candidate.
 * Preserves the visual appearance of staged-for-deletion items:
 * strikethrough text, red − badge, Undo button.
 */
function renderDeletedGhostItem(deletedObj) {
    const displayName = deletedObj.display_name || deletedObj.name || '(unnamed)';
    const objType = deletedObj.object_type;
    const typeLabel = Explorer.getTypeBadge(objType, false);
    const badgeCompact = Explorer.getTypeBadgeTier(objType, false, 'compact');
    const badgeMedium = Explorer.getTypeBadgeTier(objType, false, 'medium');
    const badgeFull = Explorer.getTypeBadgeTier(objType, false, 'full');

    return `
        <div class="tree-item staged-for-deletion"
             data-deleted-key="${Explorer.escapeHtml(deletedObj.stable_key)}">
            <span class="tree-item-delete-badge" title="Staged for deletion">&#8722;</span>
            <span class="tree-item-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
            <span class="tree-item-type type-${objType}" title="${Explorer.escapeHtml(objType)}" data-badge-compact="${badgeCompact}" data-badge-medium="${badgeMedium}" data-badge-full="${badgeFull}">${typeLabel}</span>
            <button class="tree-item-undo-btn" onclick="event.stopPropagation(); Explorer.undoLastAction()" title="Undo deletion">Undo</button>
        </div>
    `;
}
```

**5. Modify `renderTreeItem()` to add creation and move badges from candidate diff** (lines 732-781):

```javascript
function renderTreeItem(obj, showType = false) {
    const key = Explorer.getObjectKey(obj);
    const selected = Explorer.isSelectedByIndex(obj.global_index) ? 'selected' : '';
    const isTemplate = isTreeItemTemplate(obj);
    const isOrphan = state.orphanIndices.has(obj.global_index);
    const hostListInfo = getHostListInfo(obj);
    const issue = getObjectIssue(obj);

    // Candidate diff badges (replaces staging state checks)
    const isCreated = state.candidateBadges?.created?.has(key) || false;
    const isMoved = state.candidateBadges?.moved?.has(key) || false;

    const orphanClass = isOrphan ? 'is-orphan' : '';
    const longListClass = hostListInfo.shouldGroup ? 'has-long-list' : '';
    const createdClass = isCreated ? 'staged-creation' : '';
    const movedClass = isMoved ? 'staged' : '';
    const typeLabel = Explorer.getTypeBadge(obj.object_type, isTemplate);
    const badgeCompact = Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'compact');
    const badgeMedium = Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'medium');
    const badgeFull = Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'full');
    const matchField = getSearchMatchField(obj);
    const displayName = obj.display_name;

    return `
        <div class="tree-item ${selected} ${orphanClass} ${longListClass} ${createdClass} ${movedClass}"
             data-index="${obj.global_index}"
             draggable="true"
             onclick="Explorer.handleItemClick(event, ${obj.global_index})"
             oncontextmenu="Explorer.handleContextMenu(event, ${obj.global_index})">
            <span class="tree-item-drag-handle" title="Drag to move to another file">${Explorer.getIcon('grip-vertical')}</span>
            ${issue ? `<span class="tree-item-issue-badge ${issue.severity}" title="${Explorer.escapeHtml(issue.message)}">${Explorer.getIssueIcon(issue)}</span>` : ''}
            ${hostListInfo.shouldGroup ? `<span class="tree-item-group-badge" title="Consider using a hostgroup (${hostListInfo.count} hosts)"><i class="fa-solid fa-list"></i></span>` : ''}
            ${isCreated ? '<span class="tree-item-staged-badge" title="Created in candidate session">+</span>' : ''}
            ${isMoved ? '<span class="tree-item-staged-badge" title="Moved in candidate session">&rarr;</span>' : ''}
            <span class="tree-item-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
            ${matchField ? `<span class="tree-item-match-field" title="Matched in ${Explorer.escapeHtml(matchField)}">${Explorer.escapeHtml(matchField)}</span>` : ''}
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}" title="${obj.object_type}" data-badge-compact="${badgeCompact}" data-badge-medium="${badgeMedium}" data-badge-full="${badgeFull}">${typeLabel}</span>`}
        </div>
    `;
}
```

**Key changes in `renderTreeItem()`:**
- REMOVED: `state.stagedObjectDeletions.has(obj.global_index)` check and entire deleted-item branch (deleted objects now rendered separately by `renderDeletedGhostItem()`)
- REMOVED: `state.stagedMoves.has(key)` -> REPLACED with `state.candidateBadges?.moved?.has(key)`
- ADDED: `state.candidateBadges?.created?.has(key)` check for green `+` badge
- PRESERVED: `staged-creation` CSS class on created objects
- PRESERVED: `staged` CSS class on moved objects
- PRESERVED: `tree-item-staged-badge` with `+` for created and `→` for moved
- REMOVED: `getStagedDisplayName()` call -> uses `obj.display_name` directly (server provides current name)

**6. Simplify `getStagedDisplayName()`** (lines 802-813):
```javascript
// BEFORE: checks state.pendingEdits.get() for edited name
// AFTER: returns obj.display_name directly (server provides current name)
function getStagedDisplayName(obj) {
    return obj.display_name;
}
```
This function can be inlined in callers and then removed entirely.

**7. Replace staging poll with candidate poll** (lines 161-201):
```javascript
// BEFORE: async function checkStagingChanges() { ... fetch('/api/staging/info') ... }
// AFTER: Delegate to Explorer.refreshCandidateDiff() (defined in L07-data-loading.md)
// The polling interval setup is in startCandidatePoll() (L07-data-loading.md)
```

**8. Remove staging delegate functions** (lines 28-29):
```javascript
// REMOVE
function stageObjectDeletions() { Explorer.stageObjectDeletions(); }
function stageNewObjectChanges() { Explorer.stageNewObjectChanges(); }
```

**9. Remove `renderStagedCreationTreeItem()` and related functions** (lines 549-701):

Remove these six functions entirely. Their visual functionality is migrated:
- Created objects appear in `allObjects` and get `+` badge via `candidateBadges.created` check in `renderTreeItem()`
- Created objects use normal click/context/drag handlers (no special staged handlers needed)
- Selection uses normal `selectedKeys` Set (no `selectedStagedIndices`)

**10. Update `handleItemClick()` click handling** (line 925-929):
```javascript
// REMOVE: staged creation selection clearing
// Created objects are now regular tree items, no special clearing needed
```

**11. Update shift-select range query** (line 939):
```javascript
// BEFORE: .tree-item:not(.staged-creation)
// AFTER: .tree-item
// Created objects are now regular tree items participating in normal selection
```

**12. Error handling for missing badge data**:
All `state.candidateBadges?.` accesses use optional chaining to handle the case where badge data is not yet populated (e.g., before first poll completes). The tree renders normally without badges, then updates when badge data arrives.

## CSS Classes Preserved (for L13-explorer-css.md)

The following CSS classes are STILL RENDERED by this plan and MUST NOT be removed in L13:
- `.staged-creation` — green tint on created objects
- `.staged-for-deletion` — strikethrough + red tint on deleted ghost objects
- `.staged` — move tint on moved objects
- `.staged-count` — `(+N)` badge in folder counts
- `.tree-item-staged-badge` — green `+` and `→` badges
- `.tree-item-delete-badge` — red `−` badge
- `.tree-item-undo-btn` — Undo button on deleted ghost items

**Impact on L13-explorer-css.md**: L13 must be revised to KEEP these CSS rules instead of deleting them. Only rename if the class names are truly misleading, but visual appearance must be identical.

## Change Tracking (Commandment 8)

| # | Change | Status |
|---|--------|--------|
| 1 | Replace staging count calculations (lines 347, 361) | [ ] |
| 2 | Replace `stagedByFile` grouping with candidate badge injection (lines 492-547) | [ ] |
| 3 | Add `renderDeletedGhostItem()` function | [ ] |
| 4 | Modify `renderTreeItem()` to use `candidateBadges` for creation/move badges | [ ] |
| 5 | Remove deleted-object branch from `renderTreeItem()` (moved to ghost items) | [ ] |
| 6 | Simplify/remove `getStagedDisplayName()` | [ ] |
| 7 | Replace staging poll with candidate poll | [ ] |
| 8 | Remove `stageObjectDeletions`/`stageNewObjectChanges` delegates | [ ] |
| 9 | Remove `renderStagedCreationTreeItem()` function | [ ] |
| 10 | Remove `handleStagedItemClick()` function | [ ] |
| 11 | Remove `updateStagedSelection()` function | [ ] |
| 12 | Remove `selectStagedCreationForEdit()` function | [ ] |
| 13 | Remove `handleStagedContextMenu()` function | [ ] |
| 14 | Remove `handleStagedDragStart()` function | [ ] |
| 15 | Update `handleItemClick()` to remove staged creation clearing | [ ] |
| 16 | Update shift-select range query to include all `.tree-item` | [ ] |
| 17 | Add error handling for missing badge data (optional chaining) | [ ] |
| 18 | Run `npm run lint:js` and fix any violations | [ ] |

## Verification

### Functional verification
- Tree renders correctly in candidate mode
- Created objects appear as tree items with green `+` badge and `staged-creation` class
- Deleted objects appear as ghost items with red `−` badge, strikethrough, and Undo button
- Moved objects appear with `→` badge and `staged` class
- Folder counts show `(+N)` for created objects in that file
- Staged count in nav bar shows correct total from `candidateDiff.totalCount`
- Normal objects (no changes) render without any badges
- Undo button on deleted ghost items calls `Explorer.undoLastAction()`
- Selection works normally for all objects (created objects use normal selection)
- Context menu works for created objects (no special staged context menu)
- Drag-and-drop works for created objects (no special staged drag handler)

### Visual parity verification (CRITICAL)
- Side-by-side comparison: tree appearance with staging system vs candidate system must be visually identical for:
  - A file with created objects (green badges, `(+N)` count)
  - A file with deleted objects (strikethrough, red badge, Undo)
  - A file with moved objects (arrow badge)
  - A file with a mix of all change types

### Linting (Commandment 10)
- `npm run lint:js` passes with zero errors
- No unused variables from removed staging references

### Playwright tests (Commandment 11)
Tree rendering is an excellent Playwright test target. The following selectors should be validated:

```javascript
// Created object badge
await expect(page.locator('.tree-item.staged-creation .tree-item-staged-badge')).toContainText('+');

// Deleted object ghost item
await expect(page.locator('.tree-item.staged-for-deletion .tree-item-delete-badge')).toContainText('−');
await expect(page.locator('.tree-item.staged-for-deletion .tree-item-undo-btn')).toBeVisible();

// Moved object badge
await expect(page.locator('.tree-item.staged .tree-item-staged-badge')).toContainText('→');

// Folder staged count
await expect(page.locator('.staged-count')).toContainText('(+');

// Staged count in nav
await expect(page.locator('[data-staged-count]')).not.toHaveText('0');
```

These tests should be added to the Playwright test suite as part of this layer's implementation.

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** This file is frontend-only tree rendering. No config writes occur. All mutations go through CandidateApi which writes only to the `.candidate/` directory.
- [x] **2. UI visual parity.** All visual indicators preserved: green `+` badge for created objects, `staged-creation` CSS class, red `−` badge and strikethrough for deleted objects, `→` badge for moved objects, `(+N)` folder counts, staged count display. Data source changes from client-side Maps/Sets to `state.candidateBadges` (populated from candidate diff). CSS classes are preserved, not renamed or removed.
- [x] **3. Full audit logging.** N/A for frontend tree rendering. Audit logging is handled by backend candidate routes (L03-routes-candidate.md). Frontend operations that trigger mutations (undo, etc.) go through CandidateApi which logs server-side.
- [x] **4. Proper error handling.** Optional chaining (`state.candidateBadges?.created?.has(key)`) prevents crashes when badge data is not yet loaded. Missing badge data degrades gracefully (no badges shown until poll completes).
- [x] **5. Dead code deletion.** Six functions removed: `renderStagedCreationTreeItem`, `handleStagedItemClick`, `updateStagedSelection`, `selectStagedCreationForEdit`, `handleStagedContextMenu`, `handleStagedDragStart`. Two delegates removed: `stageObjectDeletions`, `stageNewObjectChanges`. `getStagedDisplayName` simplified to passthrough.
- [x] **6. Full functionality migration.** All removed functions have their visual and interactive functionality migrated: created objects get badges in `renderTreeItem()`, deleted objects get ghost rendering via `renderDeletedGhostItem()`, moved objects get badges in `renderTreeItem()`, all objects participate in normal selection/context/drag.
- [x] **7. Palo Alto candidate model.** Tree reads from candidate objects (served by candidate API) and candidate diff (for badges). No client-side staging state.
- [x] **8. Change tracking document.** Change tracking table included with 18 tracked items.
- [x] **9. Complete planning before implementation.** This plan specifies all changes before any code is written. Dependencies on L07 plans are documented.
- [x] **10. Linting enforcement.** Verification includes `npm run lint:js` pass requirement.
- [x] **11. Playwright validation.** Specific Playwright test selectors provided for all visual indicators: creation badges, deletion ghost items, move badges, folder counts, nav staged count.
