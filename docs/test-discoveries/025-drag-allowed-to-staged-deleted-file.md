# 025 — Drag allowed to staged-deleted file

**Phase:** 8 — Drag & Drop Stress
**Severity:** Major
**Category:** State Integrity / Drag-and-Drop

## Steps to Reproduce

1. Stage a file for deletion (right-click a file → Delete file)
2. Without committing, drag an object from the tree onto the deleted file in the workspace panel

## Actual Behavior

The object is staged to move into the file that is slated for deletion. No warning or rejection is shown. The staging state now contains a move targeting a file that will be deleted on commit, creating a conflict.

## Expected Behavior

`handleFileDrop` should check whether `targetFile` is in `state.stagedFileDeletions` before accepting the drop. If the target file is staged for deletion, the drop should be rejected with a toast: *"Cannot move objects into a file staged for deletion."*

## Technical Details

In `file-operations.js` → `handleFileDrop(event, targetFile)`: no guard against `state.stagedFileDeletions.includes(targetFile)` before calling `processObject`.

## Impact

On commit, the backend receives a move to a file that is simultaneously being deleted. The resulting state is ambiguous and may silently discard the moved objects.
