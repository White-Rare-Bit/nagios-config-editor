# Bug 044: All Graph Edges Missing `category` Field — All Quick View Presets Broken

## Severity
**Critical**

## Summary
All 765 edges in the dependency graph have `category: undefined`. Every quick view preset (Inheritance, Network, Notifications, Services, Monitoring, Escalations, Dependencies) filters by category to expand relevant connections from a root node. Since no edges match any category, every preset activates visually (button highlights, layout changes) but expands **zero** connected nodes. The graph is entirely non-functional for its core use case.

## Steps to Reproduce
1. Navigate to `/dependencies`
2. Search for any host (e.g. `linux-server`) and add it to the graph
3. Click any quick view button (e.g. "Services")
4. Observe: button becomes active, layout switches, but node count stays at 1

## Verification
In browser console:
```js
window._graphDebug.allEdges.filter(e => e.category).length
// Returns: 0  (out of 765 total edges)
```

## Actual Behavior
- Quick view buttons activate (CSS highlight + layout change) but no connected nodes are added
- `addedNodeIds` stays at 1 (root only) after any quick view
- Graph canvas shows isolated single node for all presets

## Expected Behavior
- "Services" quick view should expand `host:linux-server` → all services monitoring it (via `host_name` or `hostgroup_name` bindings)
- "Inheritance" quick view should expand `host:linux-server` → `host:generic-host` (via `use` edge)
- Each preset should filter edges by its declared categories and auto-expand from root

## Root Cause
The graph data API (`/api/graph` or equivalent) returns edges without the `category` field. The `dependencies-config.js` edge category definitions exist client-side but are never applied to the edge data returned by the server. The edge objects contain only `{from, to, label}` with no `category` property.

## Affected Presets (all broken)
| Preset | Categories Expected | Nodes Expanded |
|--------|---------------------|----------------|
| Inheritance | `['templates']` | 0 |
| Network | `['dependencies']` | 0 |
| Notifications | `['contacts', 'membership']` | 0 |
| Services | `['service-bindings', 'group-refs']` | 0 |
| Monitoring | `['commands', 'schedules']` | 0 |
| Escalations | `['escalations']` | 0 |
| Dependencies | `['dependencies']` | 0 |

## Screenshot
phase19-05-services-view.png (Services active but single node)

## Impact
The dependency graph's primary feature — context-sensitive quick views for Nagios administrators — is entirely non-functional. An admin trying to visualize "what services monitor this host" or "what is this host's template chain" gets no results, with no error message explaining why.
