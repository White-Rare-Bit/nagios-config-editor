# 063 — Create Missing Host Defaults to services.cfg Target File

**Phase:** 21 — Search, Filter & Analysis
**Severity:** Minor
**Screenshot:** screenshots/phase21-create-missing-host.png

## Steps to Reproduce

1. Open the Suggestions panel (Workspace → Suggestions tab)
2. Under ERRORS, find a MISSING HOST entry (e.g., `win-exchange-01`)
3. Click the **Create** button
4. Observe the "Target File" pre-selected value in the dialog

## Actual Behavior

The "Create Missing host" dialog defaults the **Target File** to `services.cfg` — the file where the orphan service referencing the missing host lives.

Pre-filled attributes:
- host_name: win-exchange-01 ✓
- alias: win-exchange-01 ✓
- address: **127.0.0.1** (placeholder)

## Expected Behavior

- Target File should default to `hosts.cfg` — the canonical file for host definitions
- Alternatively, if the project has no hosts.cfg, offer the closest semantically appropriate file

## Admin Impact

Two risks:

1. **Wrong file**: An admin who clicks OK without inspecting the dialog will create a host definition inside services.cfg. While Nagios parses all .cfg files, mixing host definitions into services.cfg is disorganizing and confusing for future maintenance.

2. **Placeholder address**: `127.0.0.1` is a silent trap. An admin who accepts the default will create a host pointing to localhost. The host will appear healthy in Nagios (localhost is always reachable) but will never monitor the intended server. This could silently mask a production host going down.
