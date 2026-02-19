# 039 — Editor Shows Original Values (Not Staged) When Reopening Object

**Phase:** 17 — State Persistence  
**Severity:** Major  
**Category:** Staging / UX

## Steps to Reproduce

1. Open an object (e.g., `web-prod-01` host)
2. Edit an attribute (e.g., change `alias` from "Production Web Server 1" to "Production Web Server 1 [edited]")
3. Confirm edit is staged: Undo button shows badge "1", Commit shows "1"
4. Either:
   - Refresh the page (F5), OR
   - Navigate to another page (e.g., `/dependencies`) and back to `/explorer`
5. The object is auto-restored as the active tab — observe the `alias` field

## Actual Behavior

The `alias` field shows **"Production Web Server 1"** — the original disk value.  
The staged edit is silently invisible.

## Expected Behavior

The editor should show **"Production Web Server 1 [edited]"** — the staged pending value.  
Staging IS preserved server-side (`GET /api/staging` confirms `pendingEdits["31"]["edited"]["alias"] = "Production Web Server 1 [edited]"`), but the editor loads from the original object data, not from staging.

## Impact

An admin who edits a value, navigates away, and returns will see their original value displayed. They have no indication their edit survived unless they notice the Commit count badge. They may:
- Think their edit was lost and re-enter it (redundant)
- Not realize they have uncommitted work
- Accidentally undo the staged edit thinking nothing was changed

## Screenshots

- Before edit: `.playwright-mcp/phase17-01-web-prod-01-selected.png`
- After edit (correct): `.playwright-mcp/phase17-02-after-edit.png`
- After refresh (bug): `.playwright-mcp/phase17-03-after-refresh.png`
- After cross-page nav (bug): `.playwright-mcp/phase17-05-back-from-dependencies.png`
