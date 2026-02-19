# Bug 032: Bulk edit staged count doesn't match selection count — no explanation given

**Phase:** 11 — Multi-Select Bulk Edit
**Severity:** Minor
**Screenshot:** screenshots/phase11-after-bulk-set.png

## Steps to Reproduce

1. Use Select → Select by type → host (33 objects selected)
2. Right-click a selected host → Edit attributes...
3. Action: Set value, Attribute: max_check_attempts, Value: 5
4. Click OK
5. Observe Commit badge: shows 32, not 33

## Actual Behavior

- Commit badge shows 32 pending edits
- No toast or message explains the discrepancy
- The skipped object (`network-device`, a host template with `register: 0`) already had `max_check_attempts: 5`, so the edit was correctly a no-op and skipped
- The admin has no way to know which object(s) were not changed or why

## Expected Behavior

After bulk edit, a summary should indicate: "32 of 33 objects updated (1 already had the requested value)" or similar. Silent count mismatch erodes admin confidence — especially for large bulk operations where a missed object could mean a misconfigured production host.

## Nagios Admin Impact

An admin running a bulk compliance operation (e.g. "ensure all hosts have max_check_attempts=5") cannot confirm the operation was complete without manually cross-referencing staging state against selection count. In a fleet of hundreds of hosts, a silent skip is indistinguishable from a successful no-op vs a bug.
