# Bug 057: "Expand Connections" Silent No-op After "Show Only Connections"

**Severity**: Medium
**Area**: Graph View — Context Menu Actions
**Discovered**: 2026-02-19

## Description

After using "Show only connections" to reduce a 71-node graph to 12 direct-neighbor nodes, immediately right-clicking the same node and choosing "Expand connections" produces zero new nodes — the graph stays at 12. The user's mental model is "expand these connections further," but the action fails silently (shows a blue "No new connections to add" info toast, then does nothing).

## Steps to Reproduce

1. Open Graph View, add `web-prod-01` (host)
2. Click Full Graph quick view → 71 nodes rendered
3. Right-click `web-prod-01` on canvas → "Show only connections" → 12 nodes remain
4. Right-click `web-prod-01` again → "Expand connections"
5. Observe: graph stays at 12 nodes — toast shows "No new connections to add"

## Root Cause

`contextExpandConnections()` at `dependencies.js:2227` calls `addAllConnectedRecursively(nodeId)` for each node in `contextMenuSelectedNodes`.

`addAllConnectedRecursively` at line 306 uses `collectNode()` (line 314) to add neighbors:

```javascript
function collectNode(nodeId) {
    if (addedNodeIds.size >= maxNodes || addedNodeIds.has(nodeId)) {return false;}
    addedNodeIds.add(nodeId);
    return true;
}
```

Recursion only continues into a neighbor when `collectNode` returns `true` (new node). If the neighbor is already in `addedNodeIds`, `collectNode` returns `false` and no further recursion happens.

After "Show only connections", `addedNodeIds` already contains all 12 of `web-prod-01`'s direct neighbors. When `addAllConnectedRecursively('host:web-prod-01')` is called:

1. Finds direct neighbors of `web-prod-01` (e.g., `hostgroup:linux-hosts`, `hostgroup:web-servers`, etc.)
2. `collectNode('hostgroup:linux-hosts')` → already in `addedNodeIds` → returns `false` → **no recursion into linux-hosts**
3. Same for all 11 other direct neighbors
4. `addedNodeIds.size` unchanged → `added = 0` → "No new connections to add"

The 2nd-degree connections (e.g., services inside `linux-hosts`, contacts inside `admins`) are never reached because the recursion is blocked by already-present direct neighbors.

## Confirmation

The action DOES work correctly from a 1-node graph:
- `clearGraph()` → `addNode('host:web-prod-01')` → right-click → "Expand connections" → 71 nodes added correctly
- In this case, all neighbors are NEW (not in `addedNodeIds`), so `collectNode` returns `true` for each, and recursion proceeds through the full graph.

## Expected Behaviour

"Expand connections" after "Show only connections" should bring the graph from 12 nodes back toward (or all the way to) the full 71-node graph. The user has a sub-graph view and wants to "open it up" again.

**Option A**: When "Expand connections" is invoked, call `addAllConnectedRecursively` for every node currently in `addedNodeIds` (not just the right-clicked node), so expansion proceeds from all existing nodes.

**Option B**: Add a separate "Expand all visible" button that re-runs full expansion from all current nodes.

**Option C**: Change `addAllConnectedRecursively` to recurse through already-added neighbors (without re-adding them) so it can reach 2nd-degree nodes. Requires `visited` set management to avoid performance issues.

## Additional Context

- The context menu header correctly shows "host: web-prod-01" in all cases — `contextMenuSelectedNodes` is always set to `[node.id()]` by the right-click handler (line 2041), so the action does execute; it just finds 0 new nodes.
- Contrast with the working case: on a 1-node graph, direct neighbors are ALL new → `collectNode` returns `true` → recursion reaches all 71 nodes.
- The "visited" set inside `addAllConnectedRecursively` prevents stack overflow but is separate from the `collectNode` issue; they work together to block re-expansion.
