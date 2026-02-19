# 066 — "Add to Group" Drops Composite Tree Label (service loses "on {hostgroup}")

**Phase:** 22 — Context Menu
**Severity:** Major
**Screenshot:** `screenshots/phase22-add-to-group-result.png`

## Steps to Reproduce

1. Open Explorer, navigate to `HTTP on web-servers` in `services.cfg`
2. Right-click → **Add to group...**
3. Type "http", select **http-services**, click **Confirm**

## Actual Behavior

The tree item label immediately changes from `HTTP on web-servers` → `HTTP`. The `hostgroup_name` attribute is unchanged (`web-servers`); only `servicegroups: http-services` was added. After undo, the label reverts to `HTTP on web-servers` correctly.

## Expected Behavior

The tree item label should remain `HTTP on web-servers`. Adding a `servicegroups` attribute does not change the object's composite identity (`{service_description} on {hostgroup_name}`).

## Impact (Nagios Admin Perspective)

In a config with 50 services, losing the "on web-servers" suffix makes the item visually unidentifiable. If multiple services share the same `service_description` (e.g., "HTTP on web-servers" and "HTTP on linux-hosts"), both would display as "HTTP" after adding them to groups — making the tree ambiguous and unusable for distinguishing objects.

## Root Cause Hypothesis

When `Add to Group` creates a `pendingEdit`, the frontend likely re-derives the tree display name from the `edited` object snapshot. The snapshot may not include `hostgroup_name` in the label computation path, falling back to just `service_description`.

## Verification

- Before add-to-group: tree shows `HTTP on web-servers` ✓
- After add-to-group: tree shows `HTTP` ✗ (label regression)
- After Ctrl+Z undo: tree shows `HTTP on web-servers` ✓ (confirms the label is correct in the base state)
