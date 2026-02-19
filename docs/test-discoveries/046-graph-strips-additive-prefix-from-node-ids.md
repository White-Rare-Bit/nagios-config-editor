# Bug 046: Graph Strips `+` Additive Prefix from Hostgroup Names in Service Node IDs

## Severity
**Minor**

## Summary
Services defined with additive hostgroup membership (`hostgroup_name: +database-servers,+cache-servers`) have the `+` prefix stripped in the graph node ID and sidebar label. The graph represents the service as if it had a plain (non-additive) hostgroup binding, hiding an important aspect of how the service was defined.

## Steps to Reproduce
1. Navigate to Graph View
2. Search for and add any host that is a member of `database-servers` or `cache-servers`
3. Use "Full Graph" to expand
4. Look at the "Replication Monitor" service node in the sidebar

## Actual Behavior
- Explorer tree displays: `"Replication Monitor on +database-servers,+cache-servers"`
- Graph node ID: `service:database-servers,cache-servers:Replication Monitor`
- Graph sidebar displays: `Replication Monitor on database-servers,cache-servers`
- The `+` additive operator is silently removed

## Expected Behavior
Either preserve the `+` prefix in the node label/ID, or add a visual indicator that this service uses additive hostgroup inheritance. Without it, an admin cannot distinguish between a service directly assigned to a hostgroup vs. one using additive template override syntax.

## Root Cause
The `/api/dependencies` endpoint strips leading `+` characters when constructing service node IDs from `hostgroup_name` values.

## Impact
Low — functional relationships are correct (the service still connects to the right hostgroups). However, an admin investigating "why does this host have this service?" may not realize the `+` additive override is in play, which is relevant to understanding template inheritance of `hostgroup_name`.
