# Bug 054: Manually Added Nodes Silently Disappear from Canvas When No Edges Exist to Focus Node

**Severity**: High
**Area**: Graph View — Node Rendering
**Discovered**: 2026-02-19

## Description

When a user manually adds a second node via search that shares no edges with the existing focus node, the new node is added to the sidebar "NODES" list and the count increments — but the node **never appears on the canvas**. There is no warning, toast, or visual indication that the node is invisible.

## Steps to Reproduce

1. Open Graph View — start with `critical-services` (servicegroup) as the only node
2. Use the search box to find and add `linux-server` (host)
3. Observe: sidebar shows "NODES 2" with both `linux-server` and `critical-services` listed
4. Click "Fit to View"
5. Observe: canvas only shows `critical-services` — `linux-server` is invisible

## Root Cause

In `dependencies.js:1700` (`updateGraph()`), the rendering filter is:

```javascript
const displayNodes = allNodes.filter(n => {
    if (!typeFilteredNodeIds.has(n.id)) { return false; }
    if (n.id === focusNodeId) { return true; }        // focus always shows
    if (cy && cy.$id(n.id).selected()) { return true; } // selected always shows
    if (typeFilteredNodeIds.size === 1) { return true; } // only node shows
    return connectedNodeIds.has(n.id);  // must have edges to other added nodes
});
```

`connectedNodeIds` is built from `getEdgesInSubgraph(typeFilteredNodeIds)` — edges where **both** endpoints are in the current added set. Since `linux-server` and `critical-services` share no direct edges, `connectedNodeIds` is empty, and `linux-server` is excluded.

Only the **focus node** (the first node added, `critical-services`) is guaranteed to always render.

## Impact

- **Misleading feedback**: Sidebar says "NODES 2", canvas shows 1 — user thinks the node was added
- **Silent failure**: No toast, no badge, no "(hidden)" label on the sidebar entry
- **Fit to View ignores hidden nodes**: User clicks "Fit to View" and nothing changes
- **No way to tell which sidebar nodes are visible vs. invisible**
- **Breaks the manual exploration workflow**: A Nagios admin trying to compare two unrelated objects side-by-side (e.g., a host and a servicegroup) cannot do so

## Expected Behaviour

Any node explicitly added via search should always render on the canvas. The "only show connected" filter should apply to nodes added *automatically* via quick views/expansion — not to nodes the user manually placed.

Alternatively, sidebar entries for invisible nodes should show a visual indicator (e.g., dimmed, strikethrough, "(not shown — no connections)" label).

## Screenshot

`screenshots/054-invisible-node-bug.png` — Sidebar: "NODES 2" (linux-server + critical-services); Canvas: only critical-services rendered after Fit to View.
