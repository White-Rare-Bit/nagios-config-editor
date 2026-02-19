# 037 — No Rename Operation for Files or Folders

**Phase:** 14 — File & Folder Operations
**Severity:** Major
**Category:** Missing Feature / Workflow Gap

## Description

The workspace file panel has no rename operation for files or folders. The only operations available are: create, delete, and move (via drag-and-drop to another folder). There is no rename button, no double-click-to-rename, and no right-click context menu on files/folders.

## Steps to Reproduce

1. Open the Files tab in the Workspace panel
2. Hover over any `.cfg` file or folder
3. Observe the available controls: expand toggle, delete button (or Undo for staged items)
4. Right-click on a file — no context menu appears
5. Double-click on a filename — no inline edit triggers

## Code Evidence

`file-operations.js` exports 0 rename-related functions. The full export list includes create, move (immediate), delete/unstage operations, and drag-drop handlers — but nothing for rename. No rename API endpoint is called anywhere in the module.

## Impact

An admin who needs to rename a file (e.g. `dependencies.cfg` → `escalations.cfg` to better reflect its contents) must:
1. Create a new file with the desired name
2. Drag every object from the old file to the new one
3. Delete the old (now empty) file

This is a significant workflow gap for a tool whose primary purpose is config file management.

## Expected

A rename action should be available on files and folders — either via double-click inline edit, a rename button on hover, or a right-click context menu option.
