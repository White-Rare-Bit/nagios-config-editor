# 070 — Audit Log: Staging Undo (Pre-Apply) Generates No Audit Entry

**Phase:** 23 — Audit Log
**Severity:** Cosmetic (design gap)

## Steps to Reproduce

1. Edit an object attribute (e.g., `first_notification: 2→3`). Undo button becomes enabled.
2. Press Ctrl+Z to undo. Undo button becomes disabled again.
3. Navigate to `/logs`. Check the audit log.

## Actual Behavior

No new audit entry is created when staging changes are undone via Ctrl+Z. The audit log entry count remains the same. Confirmed via `GET /api/logs/audit` before and after: total entries unchanged (4→4).

Root cause: `routes/staging.py` undo handler calls no `log_audit()`. Only the `/api/staging/apply` path writes audit entries (plus git operations and backups).

## Expected Behavior (by design)

The audit log is intentionally limited to **disk writes** — operations that actually modified Nagios `.cfg` files. Staging undo reverts in-memory staging state without touching disk, so not logging it is consistent with the audit log's purpose.

## Admin Impact

Admins cannot reconstruct what staging changes were attempted-and-reverted before an apply. If an admin made 10 staging changes, undid 8 of them, and applied 2 — only the final 2 appear in the audit log. The 8 undone changes leave no trace.

This is a deliberate design tradeoff: simpler audit log vs. complete staging history. Worth documenting so admins understand the audit log shows "what changed on disk" not "what the user tried in staging."

A future improvement could be an optional staging activity log (separate from the audit log) that records all staging actions including undos.
