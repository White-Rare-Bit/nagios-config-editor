# Same-File Drop Reorder Design

## Summary

Remove the restriction that skips same-file drops during drag-and-drop. When a user drags object(s) from the left panel and drops them at a position in the right panel within the same file, stage it as a move (reorder) just like any cross-file move.

## Current Behavior

- Dragging objects from the left panel to the right panel stages a move operation
- Same-file drops are silently skipped with `if (objData.source_file === targetFile) continue;`
- A toast reports skipped objects: "Staged 2 object(s) to move. 1 already in file."

## New Behavior

- Same-file drops are allowed and create a `stagedMove` where `originalFile === targetFile` with a new `insertPosition`
- This enables reordering objects within a file via drag-and-drop
- No visual distinction between same-file reorders and cross-file moves
- Same toast message: "Staged N object(s) to move"
- Same-position drops are allowed (no-op prevention not needed)

## Code Changes

All in `static/js/explorer/file-operations.js`:

1. **`handleObjectDrop`** — Remove the `if (objData.source_file === targetFile) continue;` check
2. **`handleFileDrop`** — Remove the same-file skip so dropping on the file header reorders to end
3. **`handleFolderDrop`** — Remove the same-file skip for consistency
4. **`alreadyInFile` counter logic** — Remove this tracking since same-file drops are now valid moves

## What Stays the Same

- Visual feedback (blue glow, drop zones, drag badge)
- Toast messages ("Staged N object(s) to move")
- Staging system (`stagedMoves` map, commit flow)
