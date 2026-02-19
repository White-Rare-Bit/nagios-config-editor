# 061 — Orphan Services Invisible to Both Orphan and Issues Filters

**Phase:** 21 — Search, Filter & Analysis
**Severity:** Major
**Screenshot:** screenshots/phase21-issues-bottom.png

## Steps to Reproduce

1. Enable the **Orphans** filter checkbox
2. Observe: services.cfg does not appear in the tree at all
3. Disable Orphans, enable the **Issues** filter checkbox
4. Observe: services.cfg shows only 1 entry ("Elasticsearch Cluster Health on log-server-01")

## Actual Behavior

The following 7 services that reference non-existent hosts (`orphan_service` API type) are invisible to BOTH the Orphan and Issues filters:
- Exchange Services on win-exchange-01
- Exchange Mail Queue on win-exchange-01
- Nagios Process on nagios-01
- Nagios Latency on nagios-01
- Elasticsearch on log-server-01
- Elasticsearch Cluster Health on log-server-01
- Orphan Service on nonexistent-server

These are confirmed via `GET /api/health-check` returning `type: "orphan_service"` for all 7.

Additionally, 6 services bound to empty hostgroups (`service_on_empty_hostgroup`) are also invisible to both filters:
- PING, CPU Load, Memory Usage, Disk C: (all on `windows-hosts` — empty group)
- AD Replication, DNS (on `domain-controllers` — empty group)

And 2 services with command argument mismatches (`command_arg_mismatch`) also do not appear in the Issues filter.

## Expected Behavior

- `orphan_service` objects should appear in the **Orphans** filter (services referencing non-existent hosts are definitionally orphaned)
- `service_on_empty_hostgroup` objects should appear in the **Issues** filter (services that will never execute are a configuration error)
- `command_arg_mismatch` objects should appear in the **Issues** filter

## Admin Impact

This is the most operationally significant bug in Phase 21. An admin auditing their config using the Orphan and Issues filters will completely miss:
- 7 services attached to hosts that don't exist (they will never run, generate no alerts)
- 6 services attached to hostgroups with no members (same problem)
- 2 services with incorrect check_command argument counts (checks will error at runtime)

These are exactly the problems a Nagios admin uses these filters to find. Missing them means false confidence in configuration health.
