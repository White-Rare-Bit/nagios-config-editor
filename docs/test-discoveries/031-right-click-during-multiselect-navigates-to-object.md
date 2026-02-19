# Bug 031: Right-clicking during multi-select navigates to clicked object, breaking bulk operation flow

**Phase:** 11 — Multi-Select Bulk Edit
**Severity:** Major
**Screenshot:** screenshots/phase11-right-click-menu.png

## Steps to Reproduce

1. Select multiple objects (e.g. via Select → Select by type → host, yielding 33 selected)
2. Center pane shows "33 objects selected — Use the Actions menu for bulk operations"
3. Right-click on any tree item to open the context menu
4. Observe center pane: it immediately navigates to the right-clicked object, replacing the multi-select summary view
5. Attempt to click a bulk action (e.g. "Edit attributes...") — it fails because the element is no longer visible/active

## Actual Behavior

- Right-click simultaneously opens the context menu AND navigates to the clicked object
- The multi-select summary view is replaced by the single-object detail view
- Bulk actions in the context menu (Bulk rename..., Edit attributes...) become unavailable (not visible)
- The tab bar gains a new tab for the right-clicked object

## Expected Behavior

- Right-clicking a selected tree item should open the context menu without navigating away from the multi-select summary
- The center pane should remain in "N objects selected" state until the user explicitly clicks a single object or takes a bulk action
- Bulk actions (Edit attributes..., Bulk rename...) should be clickable from within the multi-select context

## Nagios Admin Impact

A Nagios administrator selecting 33 hosts to bulk-edit `max_check_attempts` cannot access the bulk edit dialog. Right-clicking to open the Actions menu immediately collapses the multi-select view, making the documented workflow ("Use the Actions menu for bulk operations") non-functional as described.

## Additional Notes

- The `Edit attributes...` menu item has class `multi-only` in the DOM, confirming it is intended for multi-select
- The DOM query returns items from multiple simultaneously-open menus (Select dropdown + context menu), creating confusing combined results
- The context menu successfully shows all expected bulk actions (Bulk rename, Edit attributes, Move to file, Add to group, Delete) when queried but the navigation side-effect prevents their use
