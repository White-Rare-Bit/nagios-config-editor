# 065 — Context Menu "Delete" Has No Confirmation Dialog

**Phase:** 22 — Context Menu
**Severity:** Minor (staged; undo available)
**Screenshot:** `screenshots/phase22-delete-no-confirm.png`

## Steps to Reproduce

1. Open Explorer, navigate to any service (e.g., `HTTP on web-servers` in `services.cfg`)
2. Right-click the item in the object tree
3. Click **Delete** (red, no `...` suffix)

## Actual Behavior

The object is immediately staged for deletion with no confirmation dialog or "are you sure?" prompt. The open tab for that object closes, the view jumps to the next object in the tree, and the Undo button activates. The only feedback is the item disappearing from the tree.

## Expected Behavior

A confirmation dialog (or at minimum an inline toast with an "Undo" affordance) should appear before staging the deletion. Even in a staged system, a one-click-no-friction delete of a production service check is dangerous. A Nagios admin managing hundreds of services can easily misclick.

## Context

`003-delete-file-no-confirmation.md` documents the same pattern for file deletion. Object deletion is equally impactful — a service check definition represents years of tuning thresholds and notification logic. The `...` suffix convention used elsewhere (Rename..., Clone...) signals "will show a dialog"; Delete's lack of it is consistent with the immediate action, but the risk warrants at least a `Delete` → confirm flow or a prominent undo toast.

## Comparison

Note: `Move to file...` and `Rename...` both open dialogs. `Delete` does not — it is the single most destructive operation in the menu and the only one with no dialog.
