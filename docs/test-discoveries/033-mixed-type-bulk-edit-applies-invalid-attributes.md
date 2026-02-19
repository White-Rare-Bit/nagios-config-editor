# Bug 033: Mixed-type bulk edit silently applies attributes to incompatible object types

**Phase:** 11 — Multi-Select Bulk Edit
**Severity:** Critical
**Screenshot:** screenshots/phase11-after-bulk-set.png

## Steps to Reproduce

1. Select all 198 objects (Select → Select all visible)
2. Right-click a selected item → Edit attributes...
3. Action: Set value, Attribute: max_check_attempts, Value: 10
4. Click OK
5. Commit badge shows 198 — all objects edited

## Actual Behavior

- `max_check_attempts: 10` is staged on every object type including:
  - `contact` (admin) — invalid, contacts have no `max_check_attempts`
  - `command` objects — invalid, commands have no `max_check_attempts`
  - `contactgroup`, `hostgroup`, `servicegroup` — all invalid
- No warning is shown before or after
- No indication in the autocomplete or UI that the attribute is type-specific
- Autocomplete for "check" shows host/service attributes without any label indicating which types they apply to

## Expected Behavior

- Mixed-type bulk edit should either:
  a) Warn: "max_check_attempts applies to 33 of 198 selected objects (hosts/services). Apply to those only?"
  b) Only apply the attribute to object types where it is a known valid field
  c) Show type-applicability in the autocomplete (e.g. "max_check_attempts — host, service")
- At minimum: post-edit summary should list how many objects of each type were affected

## Nagios Admin Impact

**Config-corrupting.** An admin selecting all objects to do a bulk compliance sweep (e.g. "standardize check intervals") will silently inject invalid attributes into contacts, commands, contactgroups, etc. When committed and applied, Nagios will reject the config or silently ignore the unknown directives depending on the directive and version. Either outcome is dangerous:
- Nagios config validation failure blocks all monitoring
- Silent ignore means the admin believes changes were applied when they weren't

## Verified In Staging

`contact.admin` (global_index 178) has `max_check_attempts: "10"` in pendingEdits — confirmed via `/api/staging`.
