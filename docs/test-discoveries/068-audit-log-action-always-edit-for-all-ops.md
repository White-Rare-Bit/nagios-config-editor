# 068 — Audit Log: Action Column Always Shows "edit" for All Operation Types

**Phase:** 23 — Audit Log
**Severity:** Major
**Screenshot:** screenshots/23-01-audit-log-initial.png

## Steps to Reproduce

1. Create an object (e.g., clone a host), move an object between files, edit an attribute, then Apply all.
2. Navigate to `/logs`.
3. Inspect the **Action** column for each row.

## Actual Behavior

All staging apply operations emit `action="edit"` regardless of the actual operation type. The Action column shows:

| Operation | Action column | Details column |
|-----------|--------------|----------------|
| Object created (clone) | `edit` | `create` |
| Object attribute changed | `edit` | `max_check_attempts: 3→4` |
| Object moved between files | `edit` | `move hosts.cfg→templates.cfg` |
| Object deleted | `edit` | `delete` |

Root cause in `routes/staging.py:850–893`:
```python
elif audit_key == "object_creations":
    log_audit(action="edit", ...)   # should be action="create"
elif audit_key == "object_deletions":
    log_audit(action="edit", ...)   # should be action="delete"
elif audit_key == "object_moves":
    log_audit(action="edit", ...)   # should be action="move"
```
Every call uses `action="edit"` — only the `op` field varies.

## Expected Behavior

The Action column should reflect the actual operation type:
- Object created → `create`
- Attribute changed → `edit`
- Object moved → `move`
- Object deleted → `delete`

## Admin Impact

A Nagios administrator auditing "what happened to my config?" cannot distinguish at a glance between creation, deletion, or a simple attribute change. Every row says "edit", forcing them to read the Details column every time. For large logs this makes spotting critical events (deletions, moves) impossible without reading every entry.

## Secondary Effect

The "Edits" filter chip (which checks `op === 'modify'`) correctly filters to attribute modifications, but the action column still shows "edit" even for rows that do NOT represent attribute edits. The chip label and the column value are semantically decoupled, making the UI confusing.
