# Bug 050: Contact Full Graph Misses Template Node and Cannot Show Notification Sources

## Severity
**Major**

## Summary
Two compounding problems make the contact graph nearly useless to a Nagios administrator:

1. **Template not followed**: `contact:admin` uses `contact:generic-contact` via `use`, but the Full Graph expands to only 3 nodes (admin + 2 contactgroups). The template is not included.

2. **"Notified By" is structurally broken**: The most useful question for a contact — "what will page this person?" — cannot be answered. Services notify contactgroups, not contacts directly. There are no direct `service → contact` edges. Answering "notified by" requires two reverse hops: `contact ← members ← contactgroup ← contact_groups ← host/service`. The graph data and Full Graph expansion do not perform this traversal.

## Evidence
```js
// contact:admin edges
window._graphDebug.allEdges.filter(e =>
  e.from === 'contact:admin' || e.to === 'contact:admin'
)
// Returns 5 edges:
// admin → contactgroup:admins (contactgroups)
// admin → contactgroup:oncall (contactgroups)
// admin → contact:generic-contact (use) ← MISSING from Full Graph
// contactgroup:admins → admin (members, reverse)
// contactgroup:oncall → admin (members, reverse)

// Full Graph result: 3 nodes (admin, admins, oncall)
// Missing: generic-contact template
// Missing: any hosts/services that notify admin
```

## Expected Behavior
1. Full Graph should include `contact:generic-contact` (the template) when expanding from `contact:admin`
2. "Notified By" quick view should traverse: admin → contactgroups → (reverse) hosts/services that reference those contactgroups

## Impact
An on-call admin trying to audit "what alerts will I receive?" or "is admin correctly assigned to all critical services?" cannot use the graph to answer these questions. The contact view is a dead end.
