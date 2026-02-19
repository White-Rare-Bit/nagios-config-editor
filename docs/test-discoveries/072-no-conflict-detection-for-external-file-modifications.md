# 072 — No Conflict Detection for External File Modifications

**Phase:** 24 — Conflict Detection & Backup
**Severity:** Critical
**Category:** Data Integrity / Conflict Detection

## Summary

When a config file is modified on disk by an external process while a staging session is active, the app detects no conflict. It silently applies staged changes on top of the external modifications and commits everything — including the unapproved external content — with no warning to the admin.

## Steps to Reproduce

1. Open the Object Explorer. Verify staging is empty (Undo/Commit disabled).
2. Click `web-prod-01` and edit the `alias` field to create 1 pending change (Commit badge shows "1").
3. While staging is held, externally modify `hosts.cfg` on disk (e.g., insert 4 comment lines at the top of the file).
4. Open the commit dialog via the Commit button.
5. Fill in a commit message and click **Apply Changes**.

## Actual Behavior

- The commit succeeds with no warning.
- The externally-added content (4 lines) is silently written to disk alongside the staged change.
- Git commit log confirms: `1 file changed, 5 insertions(+), 1 deletion(-)` — 4 unintended insertions from the external modification.
- The resulting `hosts.cfg` now contains the injected external lines that the admin never reviewed or approved.

## Expected Behavior

The app should detect that a tracked config file was modified on disk since the staging lock was acquired, and either:

1. **Block the commit** with an explicit error explaining which file(s) changed externally, and require the admin to reload and reconcile; or
2. **Warn prominently** in the commit dialog that external changes to `hosts.cfg` will be included, showing the full actual diff.

## Why This Is Critical (Nagios Admin Perspective)

A Nagios admin staging a targeted one-line change (alias edit) can unknowingly commit configuration written by another process — a cron job, another admin, a deployment script, or even an attacker with file access. The commit dialog diff preview reinforced this false sense of control (see #073). In production Nagios environments, an unexpected committed line in a host definition (e.g., a changed `check_command`, `notification_options`, or `max_check_attempts`) could silently disable alerting.

## Screenshot

`phase24-after-apply2.png` — git result overlay confirming successful commit with 5 insertions despite only 1 change staged.

## Notes

- The apply mechanism uses object-name-based lookup (stable keys) rather than line numbers — so it correctly finds the modified object even after line shifts. However, it performs no file-level freshness check (e.g., mtime or hash comparison) before writing.
- A previous test phase surfaced a `"Could not find define block at line N"` error in the application logs, suggesting the writer *does* use line numbers in some paths. This discrepancy should be investigated — conflict detection likely exists but is only triggered in edge cases.
