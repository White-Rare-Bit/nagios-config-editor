# 030 — Bulk Rename Dialog Has No "Update References" Option

**Phase:** 10 — Bulk Rename with References
**Severity:** Major
**Category:** Data Integrity / UX

## Summary

The "Bulk Rename..." dialog (multi-select, find/replace) renames only the primary name field of selected objects. It has no option to also update objects that reference those names. This is the same root cause as issue 029 (single rename), but affects multi-object pattern-based rename.

## Steps to Reproduce

1. Open Object Explorer (`/explorer`)
2. Select 3 hosts: web-prod-01, web-prod-02, web-prod-03 (Ctrl+click or Select by Type)
3. Right-click → **Bulk rename...**
4. Find: `web-prod` → Replace with: `web-prod-v2` → click **Rename**
5. Navigate to service "Application Health Check" in services.cfg

## Actual Behavior

- Hosts renamed: `web-prod-v2-01`, `web-prod-v2-02`, `web-prod-v2-03` ✓
- Service `host_name` still contains old names `web-prod-01,web-prod-02,web-prod-03,...` ✗
- Service immediately shows **"BROKEN REFERENCE"** badge
- The dialog stages exactly N edits (one per renamed object) — no reference updates staged
- No warning shown to user that N references will break

## Expected Behavior

The Bulk Rename dialog should either:
1. Include an **"Update references in other objects"** checkbox (like `/api/apply-rename` supports with `updateReferences: true`), OR
2. Show a **pre-rename warning** listing which other objects will have broken references after the rename

## Positive Behavior Observed

- **Undo works atomically**: a single Ctrl+Z undoes all N renames in one step ("Bulk edit N object(s)" in undo stack)
- Pattern-based find/replace correctly transforms all selected names
- BROKEN REFERENCE badge correctly appears on affected services

## API Capability Gap

`/api/apply-rename` supports `updateReferences: true` which correctly propagates name changes to all referencing objects across all field types. This capability is not surfaced in the Explorer UI dialogs.

## Screenshots

- `screenshots/10-bulk-rename-dialog.png` — dialog with find/replace fields
- `screenshots/10-bulk-rename-result.png` — hosts renamed, Commit shows 3 staged
- `screenshots/10-bulk-undo-result.png` — single Ctrl+Z reverts all 3 renames
