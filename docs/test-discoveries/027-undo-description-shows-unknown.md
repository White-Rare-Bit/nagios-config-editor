# 027 — Undo entries for edits show "Edit object 'Unknown'"

**Phase:** 9 — Undo Stack Torture
**Severity:** Minor
**Category:** UX / Undo Stack

## Steps to Reproduce

1. Edit any attribute on a host, service, or contact in the center pane
2. Auto-save triggers (`stageCurrentChanges` → `POST /api/staging`)
3. Check the undo stack (via `GET /api/staging` → `staging.undoStack`)

## Actual Behavior

Undo entries for edit operations have description: `Edit object 'Unknown'`

```json
{ "type": "edit", "description": "Edit object 'Unknown'" }
```

## Expected Behavior

Description should identify the edited object: `Edit host 'web-prod-01'` or `Edit service 'HTTP' on 'web-prod-01'`.

## Technical Details

In `routes/staging.py` → `_create_undo_entries_for_edits`: the object name resolution fails and falls back to `'Unknown'`. The pending edit key format is `source_file|object_type|name` but the name extraction logic may not be correctly parsing it, or the object lookup by key is returning None.

## Impact

Users cannot identify what was undone from the toast message after pressing Ctrl+Z: *"Undone: Edit object 'Unknown'"* is not informative. Particularly confusing when multiple objects have been edited.
