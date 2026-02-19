# 069 — Audit Log: Move Operations Store Absolute Filesystem Paths

**Phase:** 23 — Audit Log
**Severity:** Minor
**Screenshot:** screenshots/23-01-audit-log-initial.png

## Steps to Reproduce

1. Move an object from one file to another and Apply.
2. Call `GET /api/logs/audit` directly (or check browser network tab).
3. Inspect the `from` and `to` fields in the JSON response.

## Actual Behavior

Move log entries contain full absolute filesystem paths:

```json
{
  "action": "edit",
  "op": "move",
  "from": "/Users/ohm/Desktop/claude/nagios-bulk-editor/.worktrees/e2e-playwright/sample-config/hosts.cfg",
  "to": "/Users/ohm/Desktop/claude/nagios-bulk-editor/.worktrees/e2e-playwright/sample-config/templates.cfg"
}
```

The UI truncates these with `truncatePath()` so the rendered table shows `sample-config/hosts.cfg→sample-config/templates.cfg`, which is correct. However, the raw API response exposes the full server filesystem path including usernames, deployment structure, and project name.

Root cause: `routes/staging.py:882–883`:
```python
from_val=detail.get("from_file", ""),
to_val=detail.get("to_file", ""),
```
The `from_file`/`to_file` values from the staging system are absolute paths.

## Expected Behavior

The `from` and `to` fields in the audit log should store config-relative paths (e.g., `sample-config/hosts.cfg`) rather than absolute filesystem paths. The UI display is already correct — the fix should be applied at the logging layer.

## Admin Impact

Log files shipped to SIEM tools, log aggregators, or shared audit dashboards will expose the server's filesystem structure (`/Users/ohm/Desktop/...`), including deployment directory names and usernames. This is a minor information disclosure issue.
