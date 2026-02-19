# Cluster J — Staging System Integrity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 staging integrity bugs: staging state carries stale file paths when config is copied (001-staging), move-to-file dialog ignores object type compatibility (021), drag allowed to a staged-deleted file (025).

**Architecture:** The path pollution fix requires clearing the staged state on startup if the config directory doesn't match. The move dialog fix needs to filter target files by the object type being moved. The drag validation needs to check stagedFileDeletions before accepting a drop.

**Tech Stack:** Python/Flask, JavaScript. Key files: `staging_manager.py`, `static/js/explorer/file-operations.js`, `static/js/explorer/dialogs.js`.

---

### Task 1: Reproduce all 3 bugs with Playwright

**Files:**
- Read: `docs/test-discoveries/001-staging-state-path-pollution.md`
- Read: `docs/test-discoveries/021-move-to-file-ignores-object-type.md`
- Read: `docs/test-discoveries/025-drag-allowed-to-staged-deleted-file.md`

**Step 1: Start app**, navigate to http://localhost:8080

**Step 2: Reproduce 021 — move-to-file ignores object type**
1. Select a host object
2. Right-click → Move to File
3. Observe the target file list — it shows ALL .cfg files including service-only files
4. It should prefer/show files that typically contain hosts (hosts.cfg, templates.cfg)

**Step 3: Reproduce 025 — drag to staged-deleted file**
1. Stage a file for deletion (right-click file → Delete)
2. Try to drag an object to that staged-deleted file
3. Observe: drag is accepted (file shows as drop target) — should be rejected

---

### Task 2: Fix 001-staging — Staging state path pollution on startup

**Files:**
- Read + Modify: `staging_manager.py`
- Read + Modify: `app.py`

**Step 1: Find where staging.json is loaded on startup**
Read `app.py`. Find where `StagingManager` is initialized and where it loads the existing staging file.

**Step 2: Check if staged paths match current config directory**
After loading staging data, validate that the paths in `pendingEdits`, `stagedMoves`, etc. match the current config directory. If they don't (copied from another machine/path), clear the stale data:

```python
def validate_staging_paths(self, config_root: str) -> bool:
    """Returns False if staging data contains paths from a different config root."""
    data = self.get_staging()
    for edit in data.get('pendingEdits', {}).values():
        source_file = edit.get('object', {}).get('source_file', '')
        if source_file and not source_file.startswith(config_root):
            return False
    return True

def clear_if_stale(self, config_root: str):
    if not self.validate_staging_paths(config_root):
        logger.warning("Staging data contains paths from different config root — clearing stale state")
        self.clear_staging()
```

Call this in app startup.

**Step 3: Validate**
This is best tested by copying the config directory and verifying the staging state is cleared.

**Step 4: Run ruff**

**Step 5: Commit**
```bash
git add staging_manager.py app.py
git commit -m "fix: clear stale staging state when config directory path doesn't match

Fixes #001-staging — staging.json carried absolute paths from source
location; when config was copied, stale paths caused corrupt state.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 021 — Move-to-file shows type-compatible files first

**Files:**
- Read + Modify: `static/js/explorer/dialogs.js`

**Step 1: Find the move-to-file dialog**
Read `static/js/explorer/dialogs.js`. Search for the move-to-file dialog (likely `showMoveDialog` or similar). Find where the target file list is built.

**Step 2: Sort/filter by type compatibility**
Add logic to put type-appropriate files first:
```javascript
function getFilesForObjectType(objectType) {
    const allFiles = Explorer.getAvailableFiles();
    // Heuristic: files named after the object type (hosts.cfg, services.cfg)
    // or templates.cfg should appear first for templates
    const preferred = allFiles.filter(f => {
        const name = f.split('/').pop().toLowerCase();
        return name.includes(objectType) || (objectType.endsWith('template') && name.includes('template'));
    });
    const others = allFiles.filter(f => !preferred.includes(f));
    return [...preferred, ...others];
}
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 2. Move-to-file for a host should show hosts.cfg near the top of the list.

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/dialogs.js
git commit -m "fix: move-to-file dialog shows type-compatible files first

Fixes #021 — all files shown in alphabetical order regardless of object
type, making it easy to move to an incompatible file.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 025 — Reject drag to staged-deleted file

**Files:**
- Read + Modify: `static/js/explorer/file-operations.js`

**Step 1: Find the drag-over / drop handler**
Read `static/js/explorer/file-operations.js`. Find where drop targets are validated (likely in a `dragover` or `drop` event handler for file items in the tree).

**Step 2: Check stagedFileDeletions**
Before accepting a drop, check if the target file is staged for deletion:

```javascript
function isDropTargetValid(targetFilePath) {
    // Check if file is staged for deletion
    const stagedDeletions = state.stagedFileDeletions || new Set();
    if (stagedDeletions.has(targetFilePath)) {
        return false;
    }
    return true;
}

// In the drop handler:
if (!isDropTargetValid(targetFile)) {
    showToast('Cannot move to a file staged for deletion', 'error');
    return;
}
```

Also update the dragover visual feedback to not show the file as a valid drop target when it's staged for deletion (e.g., add a CSS class `staged-deleted` to such files and use `pointer-events: none` or show a no-drop cursor).

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 3. Dragging to a staged-deleted file should show no drop indicator and an error toast.

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/file-operations.js
git commit -m "fix: reject drag-and-drop to files staged for deletion

Fixes #025 — objects could be dragged to files that were staged for
deletion, creating invalid staged moves.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Final validation

Verify:
- [ ] Stale staging state cleared on startup when config is copied (001-staging)
- [ ] Move-to-file shows type-compatible files first (021)
- [ ] Drag to staged-deleted file is rejected with toast (025)

Run: `python3 -m pytest tests/ -v`
