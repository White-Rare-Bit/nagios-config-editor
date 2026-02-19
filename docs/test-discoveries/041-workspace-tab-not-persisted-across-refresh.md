# 041 — Workspace Panel Tab Selection Not Persisted Across Page Refresh

**Phase:** 17 — State Persistence  
**Severity:** Minor  
**Category:** UI / State Restoration

## Steps to Reproduce

1. In the right Workspace panel, click the **"Suggestions"** tab
2. Verify "Suggestions" tab is active
3. Refresh the page (F5)

## Actual Behavior

After refresh, the Workspace panel resets to the **"Files"** tab, ignoring the previously active "Suggestions" selection.

## Expected Behavior

The active workspace tab ("Suggestions", "Validation", or "Files") should be preserved across refresh, consistent with how the selected object and tree expansion state are persisted.

## Context

Other state IS persisted correctly:
- Selected object restored ✓
- Editor tabs (open objects) restored ✓
- Tree expansion state restored ✓
- Staging count restored ✓

The workspace tab selection is the only UI state component not preserved, making it inconsistent with the rest of the state restoration logic.
