# BUG 016 — Autocomplete Dropdown Hard-Capped at 20 Suggestions

**Phase:** 5 — Edit Attributes & Autocomplete
**Severity:** Minor
**Category:** Autocomplete UX

## Summary

The autocomplete dropdown shows a maximum of 20 suggestions regardless of how many objects match the typed query. When the sample config contains 30 commands beginning with `check_`, typing `check_` in a `check_command` field yields exactly 20 results — silently truncating the remaining 10 matches.

## Steps to Reproduce

1. Open a service object (e.g. "HTTP on web-servers")
2. Click the `check_command` field
3. Type `check_` to trigger autocomplete
4. Count the suggestions displayed

## Observed Behavior

- 20 suggestions are shown
- No scrollbar, "show more", or count indicator is present
- The remaining 10 matching commands (`check_nrpe`, `check_ping`, `check_redis`, `check_redis_mem`, `check_replication`, `check_snmp_uptime`, `check_ssh`, `check_vpn_tunnels`, `check_switch_ports`, `check_bandwidth`) are silently omitted

## Expected Behavior

Either:
- Show all matching suggestions (scrollable dropdown), or
- Show a truncated list **with a visible "and N more…" indicator** so the user knows results are incomplete

## Impact

Users editing `check_command` (or any high-cardinality reference field) may not see the correct command if its position falls outside the top 20 results. They may type an incorrect value or not know their command exists.

## Notes

- 30 `check_*` commands confirmed in `commands.cfg` via grep
- Autocomplete correctly limits suggestions to the right object type (commands for `check_command`) ✓
- The truncation is silent — no indication that results are cut off
