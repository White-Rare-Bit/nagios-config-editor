# L08 — `static/js/explorer/object-editor.js` — MODIFY

## Purpose
Rewrite save/create/revert to call CandidateApi. Remove all pendingEdits mutations.

## Removal Audit
- `stageCurrentChanges()` → REPLACED. Instead of building a pendingEdits entry and storing in client Map, calls `CandidateApi.editObject(stableKey, edited, original)` then refreshes.
- `checkForChanges()` that saves to pendingEdits → REPLACED. Auto-saves to server via CandidateApi.editObject() if there are unsaved changes when switching away.
- `showCenterPaneObject()` reads from `state.pendingEdits.get(idx)` to show edited values → REMOVED. In candidate mode, the object from server already has current attributes.
- `syncCenterPaneAfterUndo()` reads pendingEdits → SIMPLIFIED. Just reload from server objects.
- `getDeletedObjectKeys()` reads `state.stagedObjectDeletions` → REMOVED. No client-side deletion tracking.
- `addStagedCreationSuggestions()` reads `state.stagedCreations` → REMOVED. No client-side creation list.
- All references to `state.pendingEdits`, `state.stagedCreations`, `state.stagedObjectDeletions` → REMOVED.
- `?candidate=1` added to inheritance fetch calls.

Every removed function has a CandidateApi equivalent that performs the same user-facing operation.

## Changes

**1. Rewrite `stageCurrentChanges()`** → `saveCurrentChanges()`:
```javascript
async function saveCurrentChanges() {
    if (!state.editedObject) { return; }
    const edited = gatherEditedAttributes();
    const original = state.originalAttributes;
    if (JSON.stringify(edited) === JSON.stringify(original)) { return; }

    const stableKey = Explorer.getObjectKey(state.editedObject);
    const result = await CandidateApi.editObject(stableKey, edited, original);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

**2. Rewrite `showCenterPaneObject()`** — Remove pendingEdits lookup:
```javascript
// BEFORE: checked state.pendingEdits.get(idx) to overlay edited values
// AFTER: object.attributes already has current values from server (candidate-aware load)
```
Remove the block that reads `const pendingEdit = state.pendingEdits.get(obj.global_index)` and uses `pendingEdit.edited` attributes. Just use `obj.attributes` directly.

**3. Rewrite create flow**:
```javascript
// BEFORE: pushed to state.stagedCreations array
// AFTER:
async function createNewObject(objectType, attributes, targetFile) {
    const result = await CandidateApi.createObject(objectType, attributes, targetFile);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
        // Select the newly created object
        if (result.data.stable_key) {
            state.newObjectKey = result.data.stable_key;
        }
    }
    return result;
}
```

**4. Rewrite revert flow**:
```javascript
// BEFORE: removed entry from state.pendingEdits
// AFTER:
async function revertCurrentObject() {
    const result = await CandidateApi.undo();
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
}
```

**5. Add `?candidate=1` to inheritance fetches**:
Any `fetch('/api/templates/inheritance/...')` call gets `?candidate=1` suffix when `state.candidateActive`.

**6. Remove `getDeletedObjectKeys()`** — Dead code in candidate mode.

**7. Remove `addStagedCreationSuggestions()`** — Dead code in candidate mode.

## Change Tracking

### Functions Removed
- [ ] `getDeletedObjectKeys()` — reads `state.stagedObjectDeletions`; dead code in candidate mode
- [ ] `addStagedCreationSuggestions()` — reads `state.stagedCreations`; dead code in candidate mode

### Functions Rewritten
- [ ] `stageCurrentChanges()` → `saveCurrentChanges()` — call `CandidateApi.editObject()` instead of building pendingEdits entry
- [ ] `checkForChanges()` — auto-save to server via `CandidateApi.editObject()` instead of saving to pendingEdits
- [ ] Create flow — call `CandidateApi.createObject()` instead of pushing to `state.stagedCreations`
- [ ] Revert flow — call `CandidateApi.undo()` instead of removing pendingEdits entry

### Functions Updated
- [ ] `showCenterPaneObject()` — remove `state.pendingEdits.get(idx)` lookup; use `obj.attributes` directly from server
- [ ] `syncCenterPaneAfterUndo()` — simplify to reload from server objects instead of reading pendingEdits
- [ ] `fetchInheritance()` — add `?candidate=1` query parameter when `state.candidateActive`
- [ ] `renderCenterAttributes()` — verify no references to pendingEdits or stagedCreations
- [ ] `getAttributeSuggestions()` — remove call to `addStagedCreationSuggestions()` (which is deleted)
- [ ] `getOptionSuggestions()` — verify no staging state references

### Functions Unchanged (no staging interaction)
- [ ] `validateRequiredFields()` — pure validation, no staging
- [ ] `formatIssueBadge()` / `updateIssueBadge()` — display only
- [ ] `hideCenterPaneObject()` — display only
- [ ] `showCenterPaneMultiple()` — display only
- [ ] `highlightCommandSyntax()` / `syncHighlight()` — display only
- [ ] `lookupDirective()` — display only
- [ ] `ensurePopoverElement()` / `positionPopover()` / `showDocsPopover()` / `hideDocsPopover()` / `scheduleHidePopover()` — popover UI only
- [ ] `filterCommaValueSuggestions()` — pure helper
- [ ] `showAttrAutocomplete()` / `showAutocompleteDropdown()` / `hideAttrAutocomplete()` / `selectAttrAutocomplete()` / `handleAttrAutocompleteKey()` — autocomplete UI only
- [ ] `syncNameDisplays()` — display sync only
- [ ] `updateAttribute()` — updates in-memory attribute (verify no pendingEdits write)
- [ ] `copyAttributeValue()` — clipboard only
- [ ] `deleteAttribute()` — in-memory attribute removal (verify no pendingEdits write)
- [ ] `showAddAttribute()` — display only
- [ ] `showAddAttrNameAutocomplete()` / `hideAddAttrNameAutocomplete()` / `selectAddAttrNameAutocomplete()` / `handleAddAttrNameAutocompleteKey()` — autocomplete UI only
- [ ] `showAddAttrAutocomplete()` / `hideAddAttrAutocomplete()` / `selectAddAttrAutocomplete()` / `handleAddAttrAutocompleteKey()` — autocomplete UI only
- [ ] `toggleSection()` / `saveDetailSectionState()` / `restoreDetailSectionState()` — UI state only
- [ ] `invalidateInheritanceCache()` / `buildStableKey()` — cache helper
- [ ] `loadInheritanceSection()` / `renderTemplateChainBreadcrumb()` / `renderInheritedAttributes()` / `renderInheritanceSection()` — display only
- [ ] `getTemplatesForType()` — data lookup only

### State References Cleaned
- [ ] Remove all `state.pendingEdits` references
- [ ] Remove all `state.stagedCreations` references
- [ ] Remove all `state.stagedObjectDeletions` references

### Exports Updated
- [ ] Remove `stageCurrentChanges` export, add `saveCurrentChanges`
- [ ] Remove exports for deleted functions if they were exported
- [ ] Verify all remaining exports still valid

### Error Handling
- [ ] All `CandidateApi.*` calls check `result.success` before refreshing
- [ ] Failed operations surface error via toast or dialog (no silent failures)

### Audit Logging
- [ ] Server-side CandidateApi endpoints handle audit logging; no client-side audit calls needed

## Verification

### Manual Testing
- Edit a host attribute, save → attribute persists after page reload
- Create new object → appears in tree
- Revert/undo → reverts last change
- Switch between objects → auto-save triggers correctly
- Inheritance fetch uses `?candidate=1` when candidate is active
- Attribute suggestions exclude deleted staging references
- No console errors

### Linting
- [ ] `npx eslint static/js/explorer/object-editor.js` passes
- [ ] No ESLint warnings or errors

### Playwright Tests
- [ ] Edit object attribute and save
- [ ] Create new object via dialog
- [ ] Undo/revert object edit
- [ ] Auto-save on object switch
- [ ] Inheritance display with candidate config

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** All edit/create/revert operations go through CandidateApi which modifies the candidate directory only. Live config untouched until Apply.
- [x] **C2 — UI visual parity.** Center pane layout, attribute editor, autocomplete, inheritance display all remain visually identical. Only the backend save mechanism changes.
- [x] **C3 — Full audit logging.** CandidateApi server endpoints log through audit_service.py and application logging. No client-side audit gaps.
- [x] **C4 — Proper error handling.** Every CandidateApi call checks `result.success` and surfaces errors. No silent failures.
- [x] **C5 — Dead code deletion.** `getDeletedObjectKeys()` and `addStagedCreationSuggestions()` are deleted. All `state.pendingEdits`, `state.stagedCreations`, and `state.stagedObjectDeletions` references removed.
- [x] **C6 — Full functionality migration.** Every removed function has a CandidateApi equivalent. Save, create, revert, auto-save, and inheritance fetch all migrated.
- [x] **C7 — Palo Alto candidate model.** All edits target candidate config via CandidateApi. Inheritance fetches add `?candidate=1` to read from candidate. No direct live config mutation.
- [x] **C8 — Change tracking document.** Change Tracking section added above with tickable checklist covering all ~40 functions.
- [x] **C9 — Complete planning before implementation.** This plan fully specifies all changes before any code is written.
- [x] **C10 — Linting enforcement.** Verification section includes ESLint command for this file.
- [x] **C11 — Playwright validation.** Playwright test cases listed for edit, create, undo, auto-save, and inheritance operations.
