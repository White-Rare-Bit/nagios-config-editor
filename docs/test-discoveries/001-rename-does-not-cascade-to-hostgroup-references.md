# BUG-001: Renaming a Hostgroup Does Not Update Service References

**Phase:** Phase 10 — Bulk Rename with References
**Severity:** Critical
**Date:** 2026-02-18

## Summary

Renaming a hostgroup via "Rename..." only updates the hostgroup object itself. Services that
reference the hostgroup by name via `hostgroup_name` (or `host_name`) are **not** updated,
leaving them with broken references.

## Steps to Reproduce

1. Open Explorer at `http://localhost:8080/explorer`
2. Right-click `linux-hosts` (HOSTGROUP in `hostgroups.cfg`)
3. Select "Rename..."
4. Enter new name: `linux-hosts-renamed`
5. Click "Rename"
6. Click any service that uses `hostgroup_name: linux-hosts` (e.g., "PING on linux-hosts")

## Actual Behavior

- The hostgroup object's `hostgroup_name` is updated to `linux-hosts-renamed` ✓
- **9 services** using `hostgroup_name: linux-hosts` are NOT updated ✗
- Those services display a red **BROKEN REFERENCE** badge
- Staging shows only 1 pending edit (the hostgroup itself); zero service edits

Affected services (all in `services.cfg`):
- PING on linux-hosts
- SSH on linux-hosts
- Disk Usage - Root on linux-hosts
- CPU Load on linux-hosts
- Memory Usage on linux-hosts
- Total Processes on linux-hosts
- Zombie Processes on linux-hosts
- Swap Usage on linux-hosts
- Security Updates on linux-hosts

## Expected Behavior

Renaming a hostgroup should either:
1. Automatically cascade the rename to all objects referencing it by name, OR
2. Show a warning/preview of affected references and let the user choose to update them

The Rename dialog has no "update references" option and no warning about breakage.

## Impact

Any hostgroup rename immediately breaks all services using that hostgroup, creating an
inconsistent configuration that would fail Nagios validation. The user has no in-dialog
warning that this will happen.

## Screenshots

- `screenshots/phase10-bug-rename-no-cascade.png` — after rename, shows updated hostgroup
- `screenshots/phase10-bug-broken-reference.png` — PING service with BROKEN REFERENCE badge and stale `hostgroup_name: linux-hosts`

## API Evidence

`GET /api/staging` after rename shows `pendingEdits` with only 1 entry (global_index `4`,
the hostgroup itself). No service edits present.
