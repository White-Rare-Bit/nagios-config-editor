# Impact & Relationships Shows Stale Data After Switching Tabs

**Phase**: Phase 2 — Object Inspection Stress
**Severity**: Major
**Category**: State Management

## What Was Tested

1. Opened `app-prod-01` (host) — expanded Impact & Relationships section
   - Correctly showed: "If host_name **app-prod-01** is Deleted/Renamed (12)"
2. Clicked the `linux-server` template link in Configuration Ancestry — opened in new tab
3. Clicked back on the `app-prod-01` tab
4. Expanded Impact & Relationships section again

## Expected Behavior

The Impact & Relationships panel should show data for the **currently active object** (app-prod-01), displaying:
- "If host_name **app-prod-01** is Deleted/Renamed (12)"
- "This Object Requires (4)"
- "Group Membership (4)"

## Actual Behavior

After switching back from `linux-server` tab to `app-prod-01` tab, the panel shows:
- "If host_name **linux-server** is Deleted/Renamed (21)"
- "This Object Requires (6)"
- "Group Membership (21)"

This is the relationship data for `linux-server`, not for `app-prod-01`. The panel retained the previous tab's data.

## Screenshot

`screenshots/03-stale-relationships.png`

## Impact

A Nagios administrator would see incorrect impact analysis for the object they're editing. If they relied on the displayed "12 dependent services" count to decide whether to rename a host, they would instead see "21" (the template's impact count) — leading to false confidence or false alarm. This is a data correctness issue in a critical decision-support feature.

## Root Cause (Hypothesis)

The Impact & Relationships component likely uses a shared/singleton expansion state. When `linux-server` was loaded and that tab's panel state was set, switching back to `app-prod-01` re-used the same DOM structure without re-fetching the relationships for `app-prod-01`.
