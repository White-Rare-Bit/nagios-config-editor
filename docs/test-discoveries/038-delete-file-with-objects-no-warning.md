# 038 — Deleting a File With Objects Shows No Warning

**Phase:** 14 — File & Folder Operations
**Severity:** Critical
**Category:** Data Safety / Missing Confirmation

## Description

Clicking "Delete file" on a file containing objects silently stages the deletion with no warning, no confirmation dialog, and no object-count notice. An admin can accidentally stage the deletion of a file with dozens of critical objects in a single misclick.

## Steps to Reproduce

1. Open the Files tab in the Workspace panel
2. Hover over `commands.cfg` (35 objects)
3. Click the trash icon ("Delete file" button)
4. Observe: `commands.cfg` immediately shows a red strikethrough with "DEL" badge
5. No dialog appeared, no toast warning, no confirmation

**Screenshot:** `screenshots/task17-delete-commands-attempt.png`

## Code Evidence

`stageDeleteFile()` in `file-operations.js` (line 1468):
- Checks only for `stagedMoves` pointing to the file (warns if any)
- Does **not** check `state.allObjects.filter(o => o.source_file === filePath).length`
- No confirmation dialog for non-empty files
- Goes straight to `ApiClient.del('/api/files/...')` with no object count check

## Impact

An administrator managing production Nagios config could:
- Accidentally click "Delete file" on `commands.cfg` (35 commands referenced throughout the config)
- See only a DEL badge — no indication of the scope of what's being deleted
- Commit without noticing, wiping all command definitions from disk
- This would cause every service check in Nagios to fail

The existing warning for pending moves (staged object moves to the target file) is good, but the absence of a warning for existing objects is a critical omission.

## Expected

Before staging a file deletion that contains N objects, show a confirmation dialog:
> "commands.cfg contains 35 objects. Deleting this file will also stage the deletion of all its contents. Continue?"

This matches the existing pattern in `stageDeleteFolder()` which already shows a confirmation for pending moves.
