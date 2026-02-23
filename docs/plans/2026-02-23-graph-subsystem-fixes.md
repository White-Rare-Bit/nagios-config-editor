# Graph Subsystem Bug Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 13 graph bugs (044–057, excluding 045) so quick views, search, and node rendering work correctly.

**Architecture:** Backend-first approach — fix data generation in `routes/analysis.py`, then frontend expansion/filter logic in `dependencies.js` + `dependencies-config.js`, then UX polish. Playwright verification after each layer.

**Tech Stack:** Python/Flask backend, vanilla JavaScript frontend, Cytoscape.js graph rendering.

**Design doc:** `docs/plans/2026-02-23-graph-subsystem-fixes-design.md`

---

## Task 1: Add `category` field to all graph edges (Bug 044)

**Files:**
- Modify: `routes/analysis.py:36-74` (add `_FIELD_TO_CATEGORY` near `_RELATIONSHIP_FIELDS`)
- Modify: `routes/analysis.py:241-244` (add category to edge dicts)

**Step 1: Add `_FIELD_TO_CATEGORY` dict after `_RELATIONSHIP_FIELDS`**

After `_RELATIONSHIP_FIELDS` (line 74), add:

```python
_FIELD_TO_CATEGORY = {
    "host_name": "dependencies",
    "hostgroup_name": "groups",
    "hostgroups": "groups",
    "hostgroup_members": "groups",
    "service_description": "dependencies",
    "dependent_service_description": "dependencies",
    "dependent_host_name": "dependencies",
    "dependent_hostgroup_name": "dependencies",
    "master_host_name": "dependencies",
    "master_hostgroup_name": "dependencies",
    "master_service_description": "dependencies",
    "servicegroup_name": "groups",
    "servicegroups": "groups",
    "servicegroup_members": "groups",
    "dependent_servicegroup_name": "dependencies",
    "contact_name": "contacts",
    "contacts": "contacts",
    "contact_groups": "contacts",
    "contactgroup_name": "contacts",
    "contactgroup_members": "contacts",
    "contactgroups": "contacts",
    "escalation_contacts": "contacts",
    "escalation_contact_groups": "contacts",
    "use": "templates",
    "members": "groups",
    "parents": "dependencies",
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

**Step 2: Add `category` to both edge emission sites**

In `_process_obj_relationships` (line 241-244), change both edge dicts:

```python
            if field in _REVERSE_EDGE_FIELDS:
                edges.append({"from": target_id, "to": node_id, "label": field, "arrows": "to",
                              "category": _FIELD_TO_CATEGORY.get(field, "dependencies")})
            else:
                edges.append({"from": node_id, "to": target_id, "label": field, "arrows": "to",
                              "category": _FIELD_TO_CATEGORY.get(field, "dependencies")})
```

**Step 3: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All 342 tests pass (no test touches graph API directly).

**Step 4: Verify with Playwright**

1. Navigate to `/dependencies`
2. Run in console: `window._graphDebug.allEdges.filter(e => e.category).length` — should be > 0
3. Run: `window._graphDebug.allEdges.filter(e => !e.category).length` — should be 0
4. Add a host node (e.g., `linux-server`), click "Inheritance" — verify nodes expand

**Step 5: Commit**

```bash
git add routes/analysis.py
git commit -m "fix(graph): add category field to all dependency edges (bug 044)"
```

---

## Task 2: Generate servicegroup member edges (Bug 049)

**Files:**
- Modify: `routes/analysis.py:206-244` (`_process_obj_relationships`)

**Step 1: Add servicegroup members special-case handling**

In `_process_obj_relationships`, after the `raw_value = resolved_attrs[field]` line (221) and before `targets = _parse_relationship_targets(...)` (222), add special handling for servicegroup `members`:

```python
        raw_value = resolved_attrs[field]

        # Servicegroup members use Nagios alternating-pair format: host1,svc1,host2,svc2
        if obj.object_type == "servicegroup" and field == "members":
            parts = [t.strip() for t in raw_value.split(",") if t.strip()]
            for i in range(0, len(parts) - 1, 2):
                host, svc = parts[i], parts[i + 1]
                target_id = f"service:{host}:{svc}"
                if target_id == node_id:
                    continue
                if target_id not in node_ids:
                    nodes.append({
                        "id": target_id,
                        "label": svc,
                        "type": "service",
                        "color": _TYPE_COLORS.get("service", "#999999"),
                        "exists": False,
                    })
                    node_ids.add(target_id)
                edges.append({"from": node_id, "to": target_id, "label": field, "arrows": "to",
                              "category": _FIELD_TO_CATEGORY.get(field, "groups")})
            continue

        targets = _parse_relationship_targets(field, target_type, raw_value)
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

**Step 3: Verify with Playwright**

1. Navigate to `/dependencies`
2. Search for a servicegroup node and add it
3. Click "Members" quick view — should show service nodes connected
4. Console: `window._graphDebug.allEdges.filter(e => e.label === 'members' && e.from.startsWith('servicegroup:')).length` — should be > 0

**Step 4: Commit**

```bash
git add routes/analysis.py
git commit -m "fix(graph): generate servicegroup member edges with pair parsing (bug 049)"
```

---

## Task 3: Preserve `+` additive prefix + green badge overlay (Bug 046)

**Files:**
- Modify: `routes/analysis.py:123-131` (`_make_service_node_id`)
- Modify: `routes/analysis.py:164-170` (`_parse_relationship_targets`)
- Modify: `routes/analysis.py:173-203` (`_compute_target_node_id`)
- Modify: `routes/analysis.py:206-244` (`_process_obj_relationships` — add `additive` flag to edges)
- Modify: `static/js/dependencies.js:92-116` (`getNodeImageUrl` — add `+` badge)
- Modify: `static/js/dependencies.js:1862-1868` (pass `additive` to image function)

**Step 1: Remove `.lstrip("+")` from backend functions**

In `_make_service_node_id` (line 126), change:
```python
    target = ",".join([t.strip().lstrip("+").strip() for t in target.split(",")
                       if not t.strip().startswith("!")])
```
to:
```python
    target = ",".join([t.strip() for t in target.split(",")
                       if t.strip() and not t.strip().startswith("!")])
```

In `_parse_relationship_targets` (line 169), change:
```python
    return [t.strip().lstrip("+").strip() for t in raw_value.split(",")
            if t.strip() and not t.strip().startswith("!")]
```
to:
```python
    return [t.strip() for t in raw_value.split(",")
            if t.strip() and not t.strip().startswith("!")]
```

In `_compute_target_node_id` (lines 186-187 and 197-198), remove all `.lstrip("+")` calls. Change:
```python
        svc_context = ",".join([t.strip().lstrip("+").strip() for t in svc_context.split(",")
                                if not t.strip().startswith("!")])
```
to:
```python
        svc_context = ",".join([t.strip() for t in svc_context.split(",")
                                if t.strip() and not t.strip().startswith("!")])
```
(Both occurrences at lines 186-187 and 197-198.)

**Step 2: Add `additive` flag to edges**

In `_process_obj_relationships`, after parsing targets (line 222), track whether each target had a `+` prefix. Change the target loop:

```python
        for target in targets:
            if not target:
                continue
            is_additive = target.startswith("+")
            clean_target = target.lstrip("+").strip() if is_additive else target
            target_id, t_type = _compute_target_node_id(field, target_type, clean_target, obj, resolved_attrs)
            if target_id == node_id:
                continue

            if target_id not in node_ids:
                node_data = {
                    "id": target_id,
                    "label": clean_target,
                    "type": t_type,
                    "color": _TYPE_COLORS.get(t_type, "#999999"),
                    "exists": False,
                }
                if is_additive:
                    node_data["additive"] = True
                nodes.append(node_data)
                node_ids.add(target_id)

            edge_data = {"from": node_id, "to": target_id, "label": field, "arrows": "to",
                         "category": _FIELD_TO_CATEGORY.get(field, "dependencies")}
            if is_additive:
                edge_data["additive"] = True
            if field in _REVERSE_EDGE_FIELDS:
                edge_data["from"], edge_data["to"] = target_id, node_id
            edges.append(edge_data)
```

**Step 3: Add green `+` badge overlay to node SVG**

In `getNodeImageUrl` (dependencies.js:92), add `isAdditive` parameter and overlay:

```javascript
function getNodeImageUrl(type, color, isTemplate = false, exists = true, isAdditive = false) {
```

After the orphan overlay (line 106), add:
```javascript
        const additiveOverlay = isAdditive ? `
            <circle cx="40" cy="10" r="7" fill="#4CAF50"/>
            <text x="40" y="14" text-anchor="middle" fill="white" font-size="12" font-weight="bold">+</text>
        ` : '';
```

In the SVG template (line 113), add `${additiveOverlay}` next to `${orphanOverlay}`:
```javascript
            ${orphanOverlay}
            ${additiveOverlay}
```

**Step 4: Thread `additive` through node rendering**

In `renderGraph` (line 1862-1868), update the cache key and image call:

```javascript
            const isAdditive = n.additive || false;
            const cacheKey = `${n.type}:${n.color}:${isTemplate}:${exists}:${isAdditive}`;
            if (!nodeImageCache[cacheKey]) {
                nodeImageCache[cacheKey] = getNodeImageUrl(n.type, n.color, isTemplate, exists, isAdditive);
            }
```

**Step 5: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

**Step 6: Verify with Playwright**

1. Navigate to `/dependencies`, search for an object that uses additive hostgroup references (e.g., a service with `+hostgroup_name`)
2. Verify node has green `+` badge overlay
3. Verify non-additive nodes do NOT have the badge

**Step 7: Commit**

```bash
git add routes/analysis.py static/js/dependencies.js
git commit -m "fix(graph): preserve + additive prefix and add green badge overlay (bug 046)"
```

---

## Task 4: Service node labels show "Description / host" (Bug 048)

**Files:**
- Modify: `routes/analysis.py:133-161` (`_add_or_update_node`)

**Step 1: Set service node label to include host context**

In `_add_or_update_node`, after computing the label (line 145), add service-specific labeling:

```python
        label = obj.get_name()
        if obj.object_type == "service":
            target = obj.attributes.get("hostgroup_name") or obj.attributes.get("host_name", "")
            target = ",".join([t.strip().lstrip("+").strip() for t in target.split(",")
                               if t.strip() and not t.strip().startswith("!")])
            if target:
                label = f"{label} / {target}"

        node_data = {
            "id": node_id,
            "label": label,
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

**Step 3: Verify with Playwright**

1. Navigate to `/dependencies`, search for a service (e.g., "HTTP")
2. Service node label should show `HTTP / web-servers` (not just `HTTP`)
3. Sidebar display label should still show `HTTP on web-servers` (uses `getNodeDisplayLabel`)

**Step 4: Commit**

```bash
git add routes/analysis.py
git commit -m "fix(graph): include host context in service node labels (bug 048)"
```

---

## Task 5: Typeable search for dependency/escalation objects (Bug 052)

**Files:**
- Modify: `routes/analysis.py:133-161` (`_add_or_update_node` — add `search_label`)
- Modify: `static/js/dependencies.js:1159-1170` (`performNodeSearch` — check `search_label`)

**Step 1: Add `search_label` for nodes with untypeable characters**

In `_add_or_update_node`, after building `node_data`, add:

```python
        if "→" in label:
            node_data["search_label"] = label.replace("→", "->")
```

**Step 2: Update search to use `search_label`**

In `performNodeSearch` (dependencies.js:1159), change:

```javascript
    function performNodeSearch(search) {
        const results = [];
        for (const node of allNodes) {
            const searchTarget = (node.search_label || node.label).toLowerCase();
            if (searchTarget.includes(search)) {
                results.push(node);
                if (results.length >= 30) break;
            }
        }
        displaySearchResults(results);
    }
```

**Step 3: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

**Step 4: Commit**

```bash
git add routes/analysis.py static/js/dependencies.js
git commit -m "fix(graph): add typeable search_label for dependency objects (bug 052)"
```

---

## Task 6: Playwright verification of Layer 1

**Step 1: Start the app and verify all backend fixes**

1. Run: `python3 app.py` (in background)
2. Navigate to `/dependencies`

**Step 2: Verify bug 044 — edge categories**
```js
window._graphDebug.allEdges.filter(e => e.category).length  // > 0
window._graphDebug.allEdges.filter(e => !e.category).length  // 0
```

**Step 3: Verify bug 049 — servicegroup edges**
Search for a servicegroup, add to graph, check edges exist to services.

**Step 4: Verify bug 048 — service labels**
Search for a service — label should show `HTTP / web-servers` format.

**Step 5: Verify bug 046 — additive prefix**
If sample config has `+` prefixes, verify green badge appears.

**Step 6: Test quick view expansion**
Add a host node → click each preset → verify nodes expand (not zero).
If presets still expand zero nodes, debug the expansion logic by stepping through `expandWithRules` in the browser console.

**Step 7: Document any issues found**

If quick views still don't expand, the root cause is in the frontend expansion logic (not categories). Note the actual failure for Layer 2 tasks.

---

## Task 7: Fix search to match display labels (Bug 047)

**Files:**
- Modify: `static/js/dependencies.js:1159-1170` (`performNodeSearch`)

**Step 1: Search against display label and search_label**

Change `performNodeSearch`:

```javascript
    function performNodeSearch(search) {
        const results = [];
        for (const node of allNodes) {
            const displayLabel = getNodeDisplayLabel(node.id, node.type, node.label);
            const searchTargets = [
                node.label.toLowerCase(),
                displayLabel.toLowerCase(),
            ];
            if (node.search_label) {
                searchTargets.push(node.search_label.toLowerCase());
            }
            if (searchTargets.some(t => t.includes(search))) {
                results.push(node);
                if (results.length >= 30) break;
            }
        }
        displaySearchResults(results);
    }
```

**Step 2: Verify with Playwright**

1. Navigate to `/dependencies`
2. Search for "HTTP on web" — should find the service node
3. Search for just "HTTP" — should also find it
4. Search for "MySQL->" — should find servicedependency nodes

**Step 3: Commit**

```bash
git add static/js/dependencies.js
git commit -m "fix(graph): search matches display labels and search_label (bugs 047, 052)"
```

---

## Task 8: Manually added nodes always visible (Bug 054)

**Files:**
- Modify: `static/js/dependencies.js:30` (add `manuallyAddedNodeIds`)
- Modify: `static/js/dependencies.js:1205-1228` (`addNode` — track manual adds)
- Modify: `static/js/dependencies.js:1700-1728` (`updateGraph` — always show manual nodes)
- Modify: `static/js/dependencies.js:1059-1090` (persist/restore `manuallyAddedNodeIds`)
- Modify: `static/js/dependencies.js:1270-1278` (`clearGraph` — clear manual set)
- Modify: `static/js/dependencies.js:1477-1479` (`applyQuickView` — clear manual set)

**Step 1: Add `manuallyAddedNodeIds` set**

After `let addedNodeIds = new Set();` (line 30), add:
```javascript
    let manuallyAddedNodeIds = new Set();
```

**Step 2: Track manual additions in `addNode`**

In `addNode` (line 1220), add:
```javascript
        addedNodeIds.add(nodeId);
        manuallyAddedNodeIds.add(nodeId);
```

**Step 3: Always show manually-added nodes in `updateGraph`**

In `updateGraph` (line 1718-1728), add a check before the edge-connectivity filter:

```javascript
        const displayNodes = allNodes.filter(n => {
            if (!typeFilteredNodeIds.has(n.id)) return false;
            if (n.id === focusNodeId) return true;
            if (cy && cy.$id(n.id).selected()) return true;
            if (manuallyAddedNodeIds.has(n.id)) return true;  // Bug 054: always show user-added nodes
            if (typeFilteredNodeIds.size === 1) return true;
            return connectedNodeIds.has(n.id);
        });
```

**Step 4: Clear on graph clear and quick view**

In `clearGraph` (around line 1272):
```javascript
        addedNodeIds.clear();
        manuallyAddedNodeIds.clear();
```

In `applyQuickView` (around line 1478):
```javascript
        addedNodeIds.clear();
        manuallyAddedNodeIds.clear();  // Quick view is programmatic, not manual
        addedNodeIds.add(rootNode);
```

**Step 5: Persist in save/load graph state**

In `saveGraphState` (around line 1061), add:
```javascript
            manuallyAddedNodeIds: Array.from(manuallyAddedNodeIds),
```

In `loadGraphState` (around line 1082), add:
```javascript
            if (state.manuallyAddedNodeIds && Array.isArray(state.manuallyAddedNodeIds)) {
                manuallyAddedNodeIds = new Set(state.manuallyAddedNodeIds);
            }
```

**Step 6: Verify with Playwright**

1. Add host node `linux-server`
2. Add servicegroup node (unrelated, no edges to host)
3. Both nodes should be visible on canvas — sidebar says "NODES 2", canvas shows 2

**Step 7: Commit**

```bash
git add static/js/dependencies.js
git commit -m "fix(graph): manually added nodes always visible on canvas (bug 054)"
```

---

## Task 9: Fix preset assignment per type (Bugs 051 + 053)

**Files:**
- Modify: `static/js/dependencies.js:40-56` (`presetsByType`)

**Step 1: Update `presetsByType`**

Replace lines 40-56:

```javascript
    const presetsByType = {
        host: ['inheritance', 'network', 'notifications', 'services', 'monitoring', 'escalations', 'dependencies', 'full'],
        hostgroup: ['inheritance', 'notifications', 'services', 'members', 'escalations', 'dependencies', 'full'],
        service: ['inheritance', 'network', 'notifications', 'monitoring', 'escalations', 'dependencies', 'full'],
        servicegroup: ['inheritance', 'members', 'full'],
        contact: ['inheritance', 'notifiedBy', 'full'],
        contactgroup: ['inheritance', 'members', 'notifiedBy', 'full'],
        command: ['usedBy', 'full'],
        timeperiod: ['usedBy', 'full'],
        hostdependency: ['inheritance', 'dependencies', 'full'],
        servicedependency: ['inheritance', 'dependencies', 'full'],
        hostescalation: ['inheritance', 'escalations', 'full'],
        serviceescalation: ['inheritance', 'escalations', 'full'],
        default: ['inheritance', 'full']
    };
```

**Step 2: Verify with Playwright**

1. Add a servicegroup → only see Inheritance, Members, Full Graph buttons
2. Add a hostescalation → only see Inheritance, Escalations, Full Graph buttons
3. Add a hostdependency → only see Inheritance, Dependencies, Full Graph buttons
4. Add a host → see all 8 buttons as before

**Step 3: Commit**

```bash
git add static/js/dependencies.js
git commit -m "fix(graph): assign relevant quick view presets per object type (bugs 051, 053)"
```

---

## Task 10: Scope inheritance to direct chain (Bug 055)

**Files:**
- Modify: `static/js/dependencies-config.js:208-212` (inheritance rules — add `maxBackwardDepth`)
- Modify: `static/js/dependencies.js:1554-1588` (`_expandWithRulesImpl` — enforce depth limit)

**Step 1: Add `maxBackwardDepth` to all inheritance rules**

In `dependencies-config.js`, add `maxBackwardDepth: 1` to every `inheritance` rule block. Example for `host`:

```javascript
            inheritance: {
                forward: ['use'],
                backward: ['use'],
                maxBackwardDepth: 1,
                stopAt: []
            },
```

Apply this to all 12 type entries that have an `inheritance` preset (host, hostgroup, service, servicegroup, contact, contactgroup, hostdependency, servicedependency, hostescalation, serviceescalation).

**Step 2: Enforce depth limit in `_expandWithRulesImpl`**

In `_expandWithRulesImpl` (dependencies.js:1554), track backward depth per node. Change the BFS to use `{nodeId, backwardDepth}` tuples:

```javascript
    function _expandWithRulesImpl(startNodeId, preset, nodes, edges, resultSet, exemptRootFromStopAt) {
        if (!edges || !nodes) return;

        const startNode = nodes.find(n => n.id === startNodeId);
        if (!startNode) return;

        const rules = expansionRules[startNode.type]?.[preset];
        if (!rules) return;

        const maxBackwardDepth = rules.maxBackwardDepth ?? Infinity;
        const visited = new Set();
        const toVisit = [{nodeId: startNodeId, backwardDepth: 0}];

        while (toVisit.length > 0) {
            const {nodeId, backwardDepth} = toVisit.pop();
            if (visited.has(nodeId)) continue;
            visited.add(nodeId);

            const currentNode = nodes.find(n => n.id === nodeId);
            if (!currentNode) continue;

            const shouldApplyStopAt = exemptRootFromStopAt ? (nodeId !== startNodeId) : true;
            if (shouldApplyStopAt && rules.stopAt?.includes(currentNode.type)) {
                continue;
            }

            resultSet.add(nodeId);

            const { forward, backward } = resolveApplicableRules(rules, currentNode.type);

            // Forward targets: always follow (depth = 0, these are ancestors)
            for (const targetId of collectForwardTargets(edges, nodeId, forward, visited, nodes)) {
                toVisit.push({nodeId: targetId, backwardDepth: 0});
            }

            // Backward targets: respect depth limit
            if (backwardDepth < maxBackwardDepth) {
                for (const targetId of collectBackwardTargets(edges, nodeId, backward, visited, nodes)) {
                    toVisit.push({nodeId: targetId, backwardDepth: backwardDepth + 1});
                }
            }
        }
    }
```

**Step 3: Verify with Playwright**

1. Add `linux-server` host → click "Inheritance"
2. Should show: `linux-server → generic-host` (ancestor chain) + direct children of `generic-host` (1 level down)
3. Should NOT show 32+ nodes (the full tree)

**Step 4: Run unit tests if any exist for expansion**

Check: `grep -r "expandWithRules\|_expandWithRulesImpl" tests/`

**Step 5: Commit**

```bash
git add static/js/dependencies-config.js static/js/dependencies.js
git commit -m "fix(graph): scope inheritance preset to direct chain with depth limit (bug 055)"
```

---

## Task 11: Fix expand-after-show-only (Bug 057)

**Files:**
- Modify: `static/js/dependencies.js:306-318` (`addAllConnectedRecursively` — separate visited from addedNodeIds)

**Step 1: Change `addAllConnectedRecursively` to use separate visited set**

The current guard at line 315 (`addedNodeIds.has(nodeId)`) prevents recursion through already-added nodes. Change `collectNode` to use the `visited` set for cycle detection:

```javascript
    function addAllConnectedRecursively(startNodeId, visited = new Set()) {
        if (visited.has(startNodeId)) return;
        visited.add(startNodeId);

        const maxNodes = MAX_NODES;
        const [startType, startName] = parseNodeId(startNodeId);

        function collectNode(nodeId) {
            if (addedNodeIds.size >= maxNodes) return false;
            if (addedNodeIds.has(nodeId)) return false;  // Already in graph, but still recurse through it
            addedNodeIds.add(nodeId);
            return true;
        }
```

Wait — the issue is that `collectNode` returns `false` for already-added nodes, and callers check the return value to decide whether to recurse deeper. We need callers to recurse even for already-added nodes.

Instead, restructure: always recurse through neighbors, only skip if in `visited`:

In the helper functions that call `collectNode` and then recurse (like `addTemplates`, `addObjectDependencies`), change them to recurse regardless of whether the node was newly added:

```javascript
        function addTemplates(nodeId) {
            const templateEdges = findEdges(null, nodeId, 'use');
            for (const edge of templateEdges) {
                addedNodeIds.add(edge.from);
                if (!visited.has(edge.from)) {
                    visited.add(edge.from);
                    addTemplates(edge.from);
                }
            }
        }
```

Apply the same pattern to all recursive helper functions (`addObjectDependencies`, `addHostgroups`, `addServicesForHost`, etc.) — use `visited` for cycle detection, `addedNodeIds.add()` for graph membership.

**Step 2: Verify with Playwright**

1. Add a host → right-click → "Expand connections" (should add many nodes)
2. Right-click → "Show only connections" (filters to direct neighbors)
3. Right-click any neighbor → "Expand connections" → should add 2nd-degree nodes
4. Should NOT show "No new connections to add" toast

**Step 3: Commit**

```bash
git add static/js/dependencies.js
git commit -m "fix(graph): separate visited set from addedNodeIds for re-expansion (bug 057)"
```

---

## Task 12: Broken ref click shows error feedback (Bug 056)

**Files:**
- Modify: `static/js/dependencies.js:1309-1317` (sidebar onclick — pass `exists`)
- Modify: `static/js/dependencies.js:2413-2414` (`openNodeInExplorer` — check exists)
- Modify: `static/js/dependencies.js:2405-2411` (context menu handler — pass exists)

**Step 1: Update `openNodeInExplorer` to check existence**

```javascript
    function openNodeInExplorer(type, name, exists) {
        if (exists === false) {
            showToast(`"${name}" is not defined in any config file`, 'warning');
            return;
        }
        window.location.href = `/explorer?search=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}`;
    }
```

**Step 2: Pass `exists` from sidebar node list**

In `updateAddedNodesList` (around line 1311), change the onclick:

```javascript
                <div class="dep-node-item ${!exists ? 'orphan' : ''}"
                     onclick="openNodeInExplorer('${escapeAttr(node.type)}', '${escapeAttr(node.label)}', ${node.exists !== false})">
```

**Step 3: Pass `exists` from context menu**

In the context menu handler (around line 2405-2411), find where `openNodeInExplorer` is called from the context menu and pass the node's `exists` value:

```javascript
            const node = allNodes.find(n => n.id === selectedNodeId);
            openNodeInExplorer(type, name, node ? node.exists !== false : true);
```

**Step 4: Verify with Playwright**

1. Add a node that references orphan objects
2. In sidebar, click an orphan node (red `✗` badge)
3. Should see toast: `"core-switch-01" is not defined in any config file`
4. Should NOT navigate away from graph page

**Step 5: Commit**

```bash
git add static/js/dependencies.js
git commit -m "fix(graph): show warning toast when clicking broken reference node (bug 056)"
```

---

## Task 13: Verify contact "Notified By" traversal (Bug 050)

**Files:**
- Possibly modify: `static/js/dependencies-config.js` (contact expansion rules)

**Step 1: Test with Playwright after all other fixes**

1. Add a contact node (e.g., `nagiosadmin`)
2. Click "Notified By" quick view
3. Check if hosts/services that notify this contact are shown
4. If they appear → bug 050 is resolved by bug 044 fix (categories enable the rules to work)
5. If they don't appear → debug and extend expansion rules

**Step 2: If rules need adjustment**

If "Notified By" doesn't reach source hosts/services, the expansion rules need extending. The current rules for `contact.notifiedBy` are:

```javascript
forward: ['contactgroups'],
backward: ['contacts', 'members'],
atType: {
    contactgroup: { backward: ['contact_groups'] }
}
```

This should work: contact → (backward: contacts) → host/service. But if the contact is only reached via a contactgroup:
contact → (forward: contactgroups) → contactgroup → (backward: contact_groups) → host/service.

If the BFS doesn't reach hosts because it doesn't continue backward from the contactgroup, add:
```javascript
atType: {
    contactgroup: { backward: ['contact_groups'] },
    host: {},  // Stop expansion at hosts (they're the source)
    service: {}  // Stop expansion at services
}
```

**Step 3: Commit (only if changes needed)**

```bash
git add static/js/dependencies-config.js
git commit -m "fix(graph): extend notifiedBy expansion rules for contact traversal (bug 050)"
```

---

## Task 14: Final Playwright validation pass

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All 342+ tests pass.

**Step 2: Verify each bug is fixed**

| Bug | Verification |
|-----|-------------|
| 044 | All edges have `category` field; quick views expand nodes |
| 046 | `+` prefix preserved; green badge on additive nodes |
| 047 | Search "HTTP on web-servers" finds the service |
| 048 | Service labels show `HTTP / web-servers` |
| 049 | Servicegroup "Members" view shows services |
| 050 | Contact "Notified By" shows source hosts/services |
| 051 | Servicegroup shows only Inheritance/Members/Full |
| 052 | Search `MySQL->` finds servicedependency |
| 053 | Presets match object type context |
| 054 | Two unrelated nodes both visible on canvas |
| 055 | Inheritance shows 3-node chain, not 32-node tree |
| 056 | Clicking orphan node shows toast, doesn't navigate |
| 057 | Expand after show-only adds 2nd-degree nodes |

**Step 3: Lint**

Run: `npx eslint static/js/dependencies.js static/js/dependencies-config.js` (fix any new issues)

**Step 4: Commit any lint fixes**

```bash
git add -A && git commit -m "style: lint fixes for graph subsystem"
```
