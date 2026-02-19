# Bug 003: "Delete File" Button Has No Confirmation Dialog

**Phase:** 13 — Dialog Cancellation
**Severity:** Major
**Category:** Dialog Cancellation / State Pollution / Destructive Action

## Steps to Reproduce

1. Navigate to Object Explorer, workspace "Files" tab (right panel)
2. Hover over any file entry (e.g., `commands.cfg`)
3. Click the trash/delete icon button that appears

## Actual Behavior

- The file is **immediately staged for deletion** (count 38→39) with no confirmation dialog
- `commands.cfg` immediately shows strikethrough text in red in the workspace panel
- An "Undo deletion" button appears as the only recovery option
- There is no warning about how many objects will become orphaned or unreachable

## Expected Behavior

- A confirmation dialog should appear (similar to the object Delete confirmation which shows full impact analysis)
- The dialog should warn: how many objects are in the file, which objects reference those objects, and the total broken-reference count
- Only after confirming should the file be staged for deletion

## Contrast with Object Delete

Object deletion (right-click → Delete) shows an excellent confirmation dialog with:
- Full impact analysis listing all dependent objects
- "Total impact: N object(s) will have broken references"
- "Nagios may fail to start" warning
- "Cancel" and "Delete Anyway" buttons

The file Delete button bypasses all of this — yet deleting a file is *more* destructive (could delete 35+ objects at once).

## Impact

An admin accidentally hovering over a file and clicking the delete icon immediately stages removal of the entire file and all its objects. For a file like `commands.cfg` (35 objects), this would break every service/host that references those commands. The Undo path is non-obvious.

## Screenshot

`.playwright-mcp/screenshots/task16-bug-delete-file-no-confirm.png`
