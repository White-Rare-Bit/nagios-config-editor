# Graph Subsystem Bug Fixes — Design

**Date:** 2026-02-23
**Scope:** 13 bugs from E2E test discoveries (044–057, excluding 045)
**Approach:** Backend-first — fix data generation, then frontend logic, then UX polish
**Deferred:** Bug 045 (staged objects in graph) — architectural change, separate effort

---

## Architecture Context

The graph subsystem is ~5,700 LOC across 5 files:

| File | Lines | Role |
|------|-------|------|
| `routes/analysis.py` | 1522 | Backend: builds `{nodes, edges}` from Nagios objects |
| `static/js/dependencies-config.js` | 668 | Edge categories, quick view presets, expansion rules |
| `static/js/dependencies.js` | 2452 | Frontend: Cytoscape rendering, search, interactions |
| `templates/dependencies.html` | 228 | HTML structure |
| `static/css/dependencies.css` | 820 | Styling |

**Data flow:** `/api/dependencies` → `{nodes[], edges[]}` → frontend stores in `allNodes`/`allEdges` → user adds nodes → `updateGraph()` filters → `renderGraph()` via Cytoscape.js

---

## Layer 1: Backend Data Fixes

### Bug 044 — Add `category` field to all edges (Critical)

**Root cause:** `_process_obj_relationships()` (analysis.py:244) emits edges as `{from, to, label, arrows}` with no `category` field. The frontend's `edgeCategories` in `dependencies-config.js` maps field names to categories, but the backend never populates this.

**Impact:** All 7 quick view presets filter edges by category. Since no edges have categories, every preset expands zero nodes. The graph's core feature is non-functional.

**Fix:**

Add a module-level `_FIELD_TO_CATEGORY` dict mapping every field in `_RELATIONSHIP_FIELDS` to its semantic category:

```python
_FIELD_TO_CATEGORY = {
    "parents": "dependencies",
    "host_name": "dependencies",
    "dependent_host_name": "dependencies",
    "dependent_hostgroup_name": "dependencies",
    "dependent_service_description": "dependencies",
    "service_description": "dependencies",
    "master_host_name": "dependencies",
    "master_hostgroup_name": "dependencies",
    "master_service_description": "dependencies",
    "dependent_servicegroup_name": "dependencies",
    "use": "templates",
    "hostgroups": "groups",
    "hostgroup_name": "groups",
    "servicegroups": "groups",
    "servicegroup_name": "groups",
    "members": "groups",
    "hostgroup_members": "groups",
    "servicegroup_members": "groups",
    "contacts": "contacts",
    "contact_name": "contacts",
    "contact_groups": "contacts",
    "contactgroup_name": "contacts",
    "contactgroup_members": "contacts",
    "contactgroups": "contacts",
    "escalation_contacts": "contacts",
    "escalation_contact_groups": "contacts",
    "check_command": "commands",
    "event_handler": "commands",
    "host_notification_commands": "commands",
    "service_notification_commands": "commands",
    "check_period": "schedules",
    "notification_period": "schedules",
    "host_notification_period": "schedules",
    "service_notification_period": "schedules",
    "escalation_period": "schedules",
    "dependency_period": "schedules",
    "exclude": "schedules",
}
```

In `_process_obj_relationships`, add `"category"` to edge dicts:

```python
edges.append({
    "from": node_id, "to": target_id, "label": field,
    "arrows": "to", "category": _FIELD_TO_CATEGORY.get(field, "dependencies")
})
```

Both edge emission sites (line 242 for reverse edges, line 244 for forward edges) need this.

**Files:** `routes/analysis.py`

---

### Bug 046 — Preserve `+` additive prefix + badge overlay

**Root cause:** `_parse_relationship_targets()` (line 169) strips `+` via `.lstrip("+")`. `_make_service_node_id()` (line 126) does the same. The `+` prefix in Nagios denotes additive inheritance (append to inherited value rather than replace).

**Fix — Backend:**

1. Remove `.lstrip("+")` from `_parse_relationship_targets()` (line 169)
2. Remove `.lstrip("+")` from `_make_service_node_id()` (line 126)
3. Remove `.lstrip("+")` from `_compute_target_node_id()` (lines 186-187, 197-198)
4. Add `"additive": True` flag to edge data when the raw target value started with `+`
5. Add `"additive": True` flag to node data when the node was reached via an additive reference

**Fix — Frontend:**

Add a green `+` badge overlay in `getNodeImageUrl()`, following the same pattern as the red `✗` orphan overlay:

```javascript
const additiveOverlay = isAdditive ? `
    <circle cx="40" cy="10" r="8" fill="#4CAF50"/>
    <text x="40" y="14" text-anchor="middle" fill="white" font-size="14" font-weight="bold">+</text>
` : '';
```

Add `isAdditive` parameter to `getNodeImageUrl()` and thread it through the node rendering in `updateGraph()`.

**Files:** `routes/analysis.py`, `static/js/dependencies.js`

---

### Bug 049 — Generate servicegroup member edges (Critical)

**Root cause:** Servicegroup `members` uses Nagios's alternating pair format: `host1,svc1,host2,svc2`. The current parser treats each comma-separated value as a single target, producing nonsensical node IDs.

**Fix:**

Add special handling in `_process_obj_relationships` when `obj.object_type == "servicegroup"` and `field == "members"`:

```python
if obj.object_type == "servicegroup" and field == "members":
    # Nagios format: host1,svc1,host2,svc2 (alternating pairs)
    parts = [t.strip() for t in raw_value.split(",") if t.strip()]
    for i in range(0, len(parts) - 1, 2):
        host, svc = parts[i], parts[i + 1]
        target_id = f"service:{host}:{svc}"
        # Create edge + target node...
    continue  # Skip normal processing
```

**Files:** `routes/analysis.py`

---

### Bug 050 — Contact "Notified By" traversal

**Root cause:** Two issues: (1) the `notifiedBy` expansion rules in `dependencies-config.js` already define backward traversal paths, but they can't work without edge categories (bug 044). (2) Multi-hop reverse traversal (contact ← contactgroup ← contact_groups ← host/service) may not reach source hosts/services.

**Fix:**

1. Fixing bug 044 (categories) should make the existing `notifiedBy` expansion rules functional
2. Verify during implementation — if the rules don't reach source objects, extend the `atType` rules for `contact.notifiedBy`:

```javascript
contact: {
    notifiedBy: {
        forward: ['contactgroups'],
        backward: ['contacts', 'members'],
        atType: {
            contactgroup: { backward: ['contact_groups'] },
            // If needed: continue traversal to find source hosts/services
            host: {},  // Stop here — we found the source
            service: {}
        },
        stopAt: []
    }
}
```

**Files:** `static/js/dependencies-config.js` (if rules need adjustment)

---

### Bug 052 — Typeable search for dependency/escalation objects

**Root cause:** `nagios_model.py:444` uses `→` (U+2192) in `get_name()` for servicedependency objects. This character can't be typed on standard keyboards, making these objects unsearchable in the graph.

**Impact on identity:** `get_name()` is used for stable keys (`source_file|object_type|name`) throughout the app. Changing it would break existing staging state.

**Fix:** Add a `search_label` field to graph nodes for dependency/escalation types that normalizes `→` to `->`. The graph search function (`performNodeSearch`) matches against `search_label` when present, falling back to `label`.

Backend (analysis.py): When building nodes for dependency/escalation types, add:
```python
if "→" in node_data["label"]:
    node_data["search_label"] = node_data["label"].replace("→", "->")
```

Frontend (dependencies.js): In `performNodeSearch`, check `search_label` too:
```javascript
const searchTarget = (node.search_label || node.label).toLowerCase();
if (searchTarget.includes(search)) { ... }
```

**Files:** `routes/analysis.py`, `static/js/dependencies.js`

---

## Layer 2: Frontend Expansion/Filter Logic

### Bug 047 — Search breaks on multi-word service names

**Root cause:** `performNodeSearch()` (dependencies.js:1159) matches `node.label.toLowerCase().includes(search)`. But `getNodeDisplayLabel()` (line 2144) formats service labels as `"HTTP on web-servers"` using the node ID, not the raw label. The search matches against the raw `label` (just "HTTP"), not the display label.

So the actual bug is different from what was reported — the search itself works fine for raw labels, but users search for the display format ("HTTP on web-servers") which doesn't match the raw label. The word "on" isn't a special delimiter; it just doesn't appear in the raw label.

**Fix:** Search against both `node.label` and the display label:

```javascript
function performNodeSearch(search) {
    const results = [];
    for (const node of allNodes) {
        const displayLabel = getNodeDisplayLabel(node.id, node.type, node.label);
        const searchTarget = node.search_label || displayLabel;
        if (searchTarget.toLowerCase().includes(search)) {
            results.push(node);
            if (results.length >= 30) break;
        }
    }
    displaySearchResults(results);
}
```

**Files:** `static/js/dependencies.js`

---

### Bug 048 — Service node labels show "Description / host"

**Root cause:** Backend `_add_or_update_node()` (analysis.py:145) sets `label: obj.get_name()` which for services is just the `service_description`. The host/hostgroup context is only embedded in the node ID, not the label.

**Fix:** In the backend, when building service nodes, set the label to include context:

```python
if obj.object_type == "service":
    target = obj.attributes.get("hostgroup_name") or obj.attributes.get("host_name", "")
    target = ",".join([t.strip() for t in target.split(",")
                       if t.strip() and not t.strip().startswith("!")])
    if target:
        label = f"{obj.get_name()} / {target}"
    else:
        label = obj.get_name()
```

This produces labels like `"HTTP / web-servers"`.

The sidebar's `getNodeDisplayLabel()` already shows `"HTTP on web-servers"` — both formats are acceptable for different contexts (canvas vs sidebar).

**Files:** `routes/analysis.py`

---

### Bug 051 + 053 — Fix preset assignment per type

**Root cause:** `presetsByType` (dependencies.js:40) assigns `network` to escalation, dependency, and servicegroup types where it's meaningless.

**Fix:** Update `presetsByType` to only show relevant presets:

```javascript
const presetsByType = {
    host: ['inheritance', 'network', 'notifications', 'services', 'monitoring', 'escalations', 'dependencies', 'full'],
    hostgroup: ['inheritance', 'notifications', 'services', 'members', 'escalations', 'dependencies', 'full'],
    service: ['inheritance', 'network', 'notifications', 'monitoring', 'escalations', 'dependencies', 'full'],
    servicegroup: ['inheritance', 'members', 'full'],  // Removed network, notifications, escalations, dependencies
    contact: ['inheritance', 'notifiedBy', 'full'],
    contactgroup: ['inheritance', 'members', 'notifiedBy', 'full'],
    command: ['usedBy', 'full'],
    timeperiod: ['usedBy', 'full'],
    hostdependency: ['inheritance', 'dependencies', 'full'],        // Removed network, monitoring
    servicedependency: ['inheritance', 'dependencies', 'full'],     // Removed network, monitoring
    hostescalation: ['inheritance', 'escalations', 'full'],         // Removed network; escalations shows contacts+targets
    serviceescalation: ['inheritance', 'escalations', 'full'],      // Removed network; escalations shows contacts+targets
    default: ['inheritance', 'full']
};
```

Key changes:
- **servicegroup:** Only inheritance + members + full (no network/notification/escalation context)
- **hostdependency/servicedependency:** Only inheritance + dependencies + full (the `dependencies` preset already has rules to show dependent/master objects)
- **hostescalation/serviceescalation:** Only inheritance + escalations + full (the `escalations` preset shows contacts, targets, and time periods — everything relevant)

**Files:** `static/js/dependencies.js`

---

### Bug 054 — Manually added nodes always visible

**Root cause:** `updateGraph()` (dependencies.js:1718-1728) filters nodes to only show those with visible edges, plus the focus node and selected nodes. Manually added nodes with no edges to other added nodes are hidden — the sidebar says "NODES 2" but the canvas shows 1.

**Fix:** Track which nodes the user explicitly added via search. These always render regardless of connectivity.

Add a `manuallyAddedNodeIds` set alongside `addedNodeIds`:

```javascript
let manuallyAddedNodeIds = new Set();
```

In `addNode()`, add to both sets:
```javascript
addedNodeIds.add(nodeId);
manuallyAddedNodeIds.add(nodeId);
```

In `updateGraph()` filter, always show manually-added nodes:
```javascript
if (manuallyAddedNodeIds.has(n.id)) return true;  // Always show user-added nodes
```

Clear `manuallyAddedNodeIds` when clearing the graph or applying a quick view (those are programmatic additions, not user-initiated).

Persist `manuallyAddedNodeIds` in `saveGraphState()`/`loadGraphState()`.

**Files:** `static/js/dependencies.js`

---

### Bug 055 — Scope inheritance to direct chain

**Root cause:** The `inheritance` preset follows `use` edges bidirectionally (`forward: ['use'], backward: ['use']`). Once a shared ancestor template is reached, all descendants are pulled in — expanding to the entire config tree (32+ nodes instead of 3).

**Fix:** Change the inheritance expansion rules to be directional:
- **Forward** (upward): Follow `use` to find ancestors (unlimited depth)
- **Backward** (downward): Follow `use` to find direct children only (1 level)

Option A — Rule-based: Set `maxDepthBackward: 1` on the inheritance rules (requires adding depth-limited backward traversal to `expandWithRules`).

Option B — Post-expansion pruning: After expansion, prune nodes that aren't on a direct ancestor path from the root. Keep only: root → parent → grandparent → ... and direct children of each.

**Recommended: Option A** — it's cleaner and reusable for other presets that might need depth limits.

Add a `maxBackwardDepth` field to expansion rules:
```javascript
inheritance: {
    forward: ['use'],
    backward: ['use'],
    maxBackwardDepth: 1,  // Only show direct children, not full tree
    stopAt: []
}
```

In `_expandWithRulesImpl`, track backward depth per node and stop expanding backward when depth exceeds the limit.

**Files:** `static/js/dependencies-config.js`, `static/js/dependencies.js`

---

### Bug 056 — Broken ref click shows error feedback

**Root cause:** `openNodeInExplorer()` (dependencies.js:2413) navigates to `/explorer?search=...` unconditionally. For orphan nodes (`exists: false`), the Explorer finds nothing and silently falls back to previous session state.

**Fix:** Check `exists` before navigating. The node data is available in the sidebar list rendering:

In the sidebar `onclick` handler (line 1311), pass `exists` to the function. In `openNodeInExplorer()`, check it:

```javascript
function openNodeInExplorer(type, name, exists = true) {
    if (!exists) {
        showToast(`"${name}" is not defined in any config file`, 'warning');
        return;
    }
    window.location.href = `/explorer?search=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}`;
}
```

Update the sidebar onclick to pass `node.exists !== false`:
```html
onclick="openNodeInExplorer('${type}', '${label}', ${node.exists !== false})"
```

Also update the context menu's "Open in Explorer" action to check `exists`.

**Files:** `static/js/dependencies.js`

---

### Bug 057 — Expand after show-only works

**Root cause:** After "show only connections" filters to direct neighbors (12 nodes), "expand connections" calls `addAllConnectedRecursively()` on the right-clicked node. But that function skips nodes already in `addedNodeIds`, so it can't recurse through direct neighbors to reach 2nd-degree connections.

**Fix:** In `contextExpandConnections()`, iterate ALL currently added nodes (not just the context menu selection) and attempt expansion from each:

```javascript
function contextExpandConnections() {
    hideContextMenu();
    const beforeCount = addedNodeIds.size;

    // Expand from all currently visible nodes, not just selected
    const nodesToExpand = contextMenuSelectedNodes.length > 0
        ? contextMenuSelectedNodes
        : [...addedNodeIds];

    // Set focus for layout
    if (contextMenuSelectedNodes.length > 0) {
        focusNodeId = contextMenuSelectedNodes[0];
    }

    for (const nodeId of nodesToExpand) {
        addAllConnectedRecursively(nodeId);
    }

    const added = addedNodeIds.size - beforeCount;
    // ... rest unchanged
}
```

Wait — the issue is that `addAllConnectedRecursively` skips already-added nodes during recursion. The fix should be: when expanding from right-click, for each currently-added node, try to add its direct neighbors (which may not be in `addedNodeIds` yet). The function already does this — it just stops at already-visited nodes. The real problem is that `addAllConnectedRecursively` checks `addedNodeIds.has(nodeId)` at the top and returns immediately for already-added nodes, preventing recursion through them.

**Better fix:** Separate the "visited" set from `addedNodeIds`. Use a local `visited` set for cycle detection, while still allowing recursion through already-added nodes to discover new 2nd-degree connections:

In `addAllConnectedRecursively`, change the guard from:
```javascript
if (addedNodeIds.has(nodeId)) return false;
```
to:
```javascript
if (visited.has(nodeId)) return false;
visited.add(nodeId);
addedNodeIds.add(nodeId);
```

Pass `visited` as a parameter (default to `new Set()`).

**Files:** `static/js/dependencies.js`

---

## Layer 3: Frontend UX

Bug 048 and Bug 056 are covered above (in Layers 1 and 2 respectively, since they overlap with other changes in those files).

---

## Execution Order

| # | Bug(s) | Layer | Description | Complexity |
|---|--------|-------|-------------|------------|
| 1 | 044 | Backend | Add `category` field to all edges | Low |
| 2 | 049 | Backend | Servicegroup member edge generation | Medium |
| 3 | 046 | Backend+Frontend | Preserve `+` prefix + badge overlay | Medium |
| 4 | 048 | Backend | Service node labels "Desc / host" | Low |
| 5 | 052 | Backend+Frontend | `search_label` for typeable search | Low |
| 6 | 050 | Frontend | Verify/fix contact "Notified By" traversal | Low-Medium |
| 7 | 047 | Frontend | Search against display labels | Low |
| 8 | 054 | Frontend | Manually added nodes always visible | Low |
| 9 | 051+053 | Frontend | Fix preset assignment per type | Low |
| 10 | 055 | Frontend | Scope inheritance to direct chain | Medium |
| 11 | 057 | Frontend | Separate visited set from addedNodeIds | Medium |
| 12 | 056 | Frontend | Broken ref click error feedback | Low |

---

## Validation

After each layer, verify with Playwright:

1. **After Layer 1:** Load graph, add a host node, apply "Network" quick view — should expand to show parent hosts and hostgroups. Apply "Services" — should show services. Check that servicegroup nodes have member edges.
2. **After Layer 2:** Search for "HTTP on web-servers" — should find the service. Add two unrelated nodes — both should render. Apply "Inheritance" on a host — should show 3-node chain, not 32-node tree. "Show only connections" then "Expand connections" — should add 2nd-degree nodes.
3. **After Layer 3:** Click orphan node in sidebar — should show toast warning, not navigate.

Run `python3 -m pytest tests/ -v` after each layer to catch regressions.
