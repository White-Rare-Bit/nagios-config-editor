# 073 — Commit Diff Preview Excludes External File Modifications

**Phase:** 24 — Conflict Detection & Backup
**Severity:** Major
**Category:** Data Integrity / UI Accuracy

## Summary

The commit dialog's diff preview shows only the changes stored in staging. When external modifications exist on disk, those changes are invisible in the diff preview — creating a false picture of what will actually be committed to disk and to git.

## Steps to Reproduce

1. Stage a single edit: change `alias` on `web-prod-01` from "Production Web Server 1" to "Production Web Server 1 - PHASE24TEST".
2. Externally insert 4 lines at the top of `hosts.cfg` while staging is active.
3. Open the commit dialog.

## Actual Behavior

The commit dialog shows:
- Header: **1 file changed ~1 modified**
- Diff shows only the alias change (`-` old value, `+` new value)
- No indication that `hosts.cfg` differs from what staging expected

The actual git commit writes: `1 file changed, 5 insertions(+), 1 deletion(-)`

The diff preview was off by 4 lines.

## Expected Behavior

The commit dialog diff should reflect the **actual** changes that will be written to disk and committed to git. When external modifications are present in a file, either:

1. Show the full diff including both staged and external changes (with visual distinction); or
2. Show an alert that the file has unsaved/untracked external changes and refuse to continue until resolved.

## Why This Matters (Nagios Admin Perspective)

The commit dialog is the admin's last checkpoint before config changes go to production. If the diff preview is inaccurate, the admin has no opportunity to catch unintended changes — they may approve a "1-line change" that is actually committing 10 or 100 modified lines from external sources. This makes the commit dialog a false safety net.

## Screenshot

`phase24-commit-dialog.png` — diff preview showing only alias change before clicking Apply.
`phase24-after-apply2.png` — git result confirming 5 insertions committed.

## Related

- #072 (no conflict detection) — this bug compounds that one: not only does the system not warn about external changes, it also doesn't show them in the diff preview.
