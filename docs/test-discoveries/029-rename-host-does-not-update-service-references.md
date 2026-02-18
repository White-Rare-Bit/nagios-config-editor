# 029 — Rename Host Does Not Update Service References

**Phase:** 10 — Bulk Rename with References
**Severity:** Major
**Category:** Data Integrity / Reference Management

## Summary

Renaming a host via "Rename..." in the context menu only updates the host's own `host_name` field. It does NOT update references to that host in services, dependencies, hostgroups, or other objects. This leaves dangling references and creates broken configurations.

## Steps to Reproduce

1. Open Object Explorer (`/explorer`)
2. In `hosts.cfg`, right-click `web-prod-01` → **Rename...**
3. Change name to `web-prod-01-renamed` → click **Rename**
4. Navigate to the service "Application Health Check" in `services.cfg`

## Actual Behavior

- The host's `host_name` field is updated to `web-prod-01-renamed` ✓
- The service's `host_name` field still contains `web-prod-01,...` ✗
- The service immediately shows a **"BROKEN REFERENCE"** badge
- The rename stages **1 edit** (the host itself), leaving all referencing objects stale

## Expected Behavior

- Renaming a host should either:
  - **Automatically update** all objects referencing the old name (services, dependencies, escalations, hostgroups), OR
  - **Warn the user** before confirming which objects will break and offer to update them

## Additional Notes

- The API (`/api/apply-rename`) supports `updateReferences: true` which performs reference propagation — but this is not exposed in the Rename dialog
- The "BROKEN REFERENCE" badge IS correctly shown in the UI, indicating the detection layer works correctly
- The same issue applies to the "Bulk rename..." dialog for multi-selected objects

## Screenshots

- `screenshots/10-after-rename.png` — host renamed, "web-prod-01-renamed" shown in tree
- `screenshots/10-stale-service-reference.png` — service shows BROKEN REFERENCE badge after host rename
