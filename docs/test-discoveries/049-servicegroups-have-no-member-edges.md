# Bug 049: Servicegroups Have No Member Edges in Graph — Rendered as Stranded Nodes

## Severity
**Critical**

## Summary
The `/api/dependencies` graph data contains zero edges connecting services to their servicegroups. Servicegroup nodes appear in the graph but have no connections to member services, making the entire servicegroup feature of the graph non-functional.

## Evidence
```js
// In browser console:
window._graphDebug.allEdges.filter(e =>
  e.from.startsWith('service:') && e.label === 'servicegroups'
).length
// Returns: 0

window._graphDebug.allEdges.filter(e =>
  e.from.startsWith('servicegroup:') || e.to.startsWith('servicegroup:')
).length
// Returns: 2 — only servicegroup-to-servicegroup sub-group edges
```

When `servicegroup:critical-services` is added to the graph and Full Graph is applied, it expands to **1 node** (itself only).

## Root Cause
The `servicegroups` attribute on service objects is not represented as edges in the graph API response. Services reference servicegroups via:
1. `service.servicegroups = critical-services` attribute on the service
2. `servicegroup.members = HTTP,HTTPS,...` attribute on the servicegroup

Neither direction is included in the edge data.

## Contrast
Hostgroups work correctly — 147 edges involving hostgroups, with `hostgroup → host (members)` edges correctly populated.

## Impact
- "Members" quick view for servicegroups will show nothing (no edges to expand)
- "Services" quick view for servicegroups will show nothing
- Servicegroup nodes added to graph are isolated islands
- An admin trying to understand "what services are in my critical-services group?" gets no answer from the graph
- The "servicegroup" legend entry is misleading — servicegroups appear to exist in the graph but convey no useful relationship data
