# 036 — Clone Dialog Has No Target File Selection

**Phase:** 12 — Cloning Adversarial
**Severity:** Minor
**Screenshot:** screenshots/12-clone-dialog.png

## Observed Behavior

The Clone dialog presents only a "New name" text field and Clone/Cancel buttons. There is no option to select a target file for the clone destination. The clone always lands in the same file as the original.

## Expected Behavior (Nagios Admin Perspective)

When cloning a host (e.g., to create a new server with similar config), the admin typically wants to place the clone in a specific file — for example, cloning `web-prod-01` into `new-servers.cfg`. The current flow requires a separate "Move to file" action after cloning.

## Workaround

Clone → then right-click the clone → Move to file...

## Notes

- This is a UX gap, not a data integrity issue.
- The Rename dialog also has no file selection, so this is consistent.
- The two-step workflow (clone + move) is functional but cumbersome for bulk provisioning workflows.
