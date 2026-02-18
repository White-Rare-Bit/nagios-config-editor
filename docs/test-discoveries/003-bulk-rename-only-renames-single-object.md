# BUG-003: "Bulk Rename" Only Renames the Single Right-Clicked Object

**Phase:** Phase 10 — Bulk Rename with References
**Severity:** Major
**Date:** 2026-02-18

## Summary

The "Bulk rename..." context menu action presents a find/replace dialog suggesting it will
rename ALL objects whose names match the pattern. In practice, it only renames the single
object that was right-clicked. Other objects with matching names are ignored, and references
in other objects are not updated.

## Steps to Reproduce

1. Right-click `web-prod-01` in the object tree
2. Select "Bulk rename..."
3. Enter Find: `web-prod`, Replace with: `web-production`
4. Click "Rename"

## Actual Behavior

- `web-prod-01` is renamed to `web-production-01` ✓
- `web-prod-02` remains `web-prod-02` ✗
- `web-prod-03` remains `web-prod-03` ✗
- `Application Health Check` service with `host_name: web-prod-01,web-prod-02,...` is NOT
  updated ✗
- Staging shows exactly **1 pending edit** (global_index 31, only `web-prod-01`)

## Expected Behavior

"Bulk rename" with pattern `web-prod` → `web-production` should:
1. Rename ALL objects whose `host_name` (or equivalent name field) contains `web-prod`:
   - `web-prod-01` → `web-production-01`
   - `web-prod-02` → `web-production-02`
   - `web-prod-03` → `web-production-03`
2. Update ALL references to those names in other objects (e.g., `Application Health Check`
   service `host_name` field which lists all three hosts)
3. Bundle all those changes as a single undo step

## Additional Notes

- The dialog has no scope indicator — no text like "This will affect N objects" to
  set expectations
- No preview of what would change before confirming
- "Bulk rename" as accessed via right-click on a single object appears functionally
  identical to "Rename...", except it does a substring find/replace on the name instead
  of a full replacement. The "bulk" aspect (renaming many at once) does not function.

## Screenshots

- `screenshots/phase10-bulk-rename-dialog.png` — the dialog (no scope indicator)
- `screenshots/phase10-bulk-rename-result.png` — after rename: web-production-01 in tree,
  web-prod-02/03 still unchanged
