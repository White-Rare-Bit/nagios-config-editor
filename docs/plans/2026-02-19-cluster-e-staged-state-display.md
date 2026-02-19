# Cluster E — Staged State Not Reflected in UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 6 bugs where the UI shows stale (pre-staging) data: editor shows original values on reopen (039), status badges missing on restore (040), resolved attrs ignore staged template edits (019), warning badges not updated after cascade (017), broken reference badge persists after undo (002-badge), stale relationships panel on tab switch (003-relationships).

**Architecture:** The core issue is that the editor and related panels read from `state.allObjects` (disk values) rather than merging with `pendingEdits`. The fix requires: (1) the editor overlay function to check pending edits before rendering field values, (2) the badge/relationship panel to refresh on tab activation, (3) the inheritance resolution to incorporate staged template changes.

**Tech Stack:** JavaScript. Key files: `static/js/explorer/object-editor.js`, `static/js/explorer/tab-manager.js`, `static/js/explorer/relations-loader.js`, `static/js/explorer/badge-issues.js`.

---

### Task 1: Reproduce all 6 bugs with Playwright

**Files:**
- Read all 6 discovery files in docs/test-discoveries/ for bugs 039, 040, 019, 017, 002-badge, 003-relationships

**Step 1: Start app**, navigate to http://localhost:8080

**Step 2: Reproduce 039 — editor shows original on reopen**
1. Click `web-prod-01` host
2. Edit `alias` → change to "Production Web Server 1 [edited]"
3. Verify staged (Commit shows 1)
4. Refresh the page (F5) — object should auto-restore
5. Observe alias field: shows original "Production Web Server 1" not the staged value
6. Take screenshot: `.playwright-mcp/repro-039.png`

**Step 3: Reproduce 040 — status badges missing on restore**
1. Open `web-prod-01` — note the "NOTIFICATION UNREACHABLE" badge in breadcrumb
2. Refresh page (F5)
3. Observe breadcrumb: badge is gone after auto-restore
4. Take screenshot

**Step 4: Reproduce 003-relationships — stale panel on tab switch**
1. Open `app-prod-01` → expand Impact & Relationships → note "12 dependent services"
2. Click the `linux-server` link → opens in new tab
3. Expand Impact & Relationships for linux-server
4. Click back to `app-prod-01` tab
5. Observe: still shows linux-server's impact data (21), not app-prod-01's (12)

**Step 5: Reproduce 017/002-badge — stale badges after staging changes**
1. Open the PING service (has `hostgroup_name: linux-hosts`)
2. Right-click linux-hosts → Rename → `linux-hosts-renamed`
3. Observe PING service tab shows BROKEN REFERENCE badge ✓
4. Ctrl+Z to undo
5. Observe: BROKEN REFERENCE badge still shows on PING service tab ✗

---

### Task 2: Fix 039/040 — Editor loads staged values on restore

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js`

**Step 1: Find where editor is populated from object data**
Read `static/js/explorer/object-editor.js`. Search for the function that initializes the editor for a selected object (likely `selectObject` or `loadObject` or `renderCenterAttributes`). Find where `state.originalAttributes` and `state.editedObject.attributes` are set from the object.

**Step 2: Find where pendingEdits overlay should be applied**
After loading the base object, check if there's a pending edit for this object (by global_index or stable key). If so, overlay the staged values:

```javascript
function loadObjectIntoEditor(obj) {
    state.editedObject = { ...obj };
    state.originalAttributes = { ...obj.attributes };

    // Overlay staged pending edits if they exist
    const pendingEdit = state.pendingEdits.get(obj.global_index);
    if (pendingEdit) {
        state.editedObject.attributes = { ...pendingEdit.edited };
    }

    renderCenterAttributes();
    computeAndRenderBadges(obj); // Fix 040: always compute badges
}
```

**Step 3: Fix 040 — Ensure badge computation runs on restore**
Find where badges are computed (likely in `renderBreadcrumb` or similar). Ensure this function is called as part of `loadObjectIntoEditor`, not just on fresh selection. The bug is that auto-restore calls something that bypasses badge computation.

**Step 4: Validate with Playwright**
Reproduce Task 1 Steps 2 and 3:
- After refresh, editor should show "Production Web Server 1 [edited]"
- After refresh, "NOTIFICATION UNREACHABLE" badge should be present

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: overlay staged pending edits when loading object into editor

Fixes #039, #040 — editor loaded from allObjects (disk values), ignoring
pending staged edits. Status badges were also skipped during auto-restore.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 003-relationships — Refresh Impact panel on tab activation

**Files:**
- Read + Modify: `static/js/explorer/tab-manager.js`

**Step 1: Find tab activation handler**
Read `static/js/explorer/tab-manager.js`. Find the function that runs when a tab is clicked/activated (likely an `activateTab` or `selectTab` function).

**Step 2: Find where Impact & Relationships is loaded**
Read `static/js/explorer/relations-loader.js`. Find `loadImpactAndRelationships` (the function that fetches and renders the panel).

**Step 3: Call loadImpactAndRelationships on tab activation**
In the tab activation handler, after setting the current object, call `loadImpactAndRelationships` with the newly active object:

```javascript
function activateTab(tabKey) {
    // ... existing code to switch active tab ...

    // Refresh Impact & Relationships for the newly active object
    const obj = Explorer.findObjectByKey(tabKey);
    if (obj) {
        Explorer.loadImpactAndRelationships(obj);
    }
}
```

This ensures the panel always reflects the currently active tab, not the previous one.

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 4. Switching back to app-prod-01 tab should show app-prod-01's impact count (12), not linux-server's (21).

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/tab-manager.js
git commit -m "fix: refresh Impact & Relationships panel when switching tabs

Fixes #003-relationships — panel retained data from previously viewed tab
because loadImpactAndRelationships was not called on tab activation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 002-badge/017 — Refresh badges and resolved attrs on staging changes

**Files:**
- Read + Modify: `static/js/explorer/badge-issues.js`
- Read + Modify: `static/js/explorer/object-editor.js` (refreshAfterObjectChange)

**Step 1: Find refreshAfterObjectChange**
Read `static/js/explorer/object-editor.js`. Search for `refreshAfterObjectChange`. This function is called after staging changes. Check if it refreshes the breadcrumb badge for the currently-open tab.

**Step 2: Find where badge computation happens**
Read `static/js/explorer/badge-issues.js`. Understand the badge computation API. Find what function to call to re-check validity of an open tab.

**Step 3: After undo, revalidate open tabs**
Find where undo completion triggers a UI update. After the undo state is loaded, add a pass that re-validates all open tabs and updates their breadcrumb badges:

```javascript
// After undo completes and state is updated:
// Re-validate all open tabs
if (state.openTabs) {
    state.openTabs.forEach(tab => {
        const obj = Explorer.findObjectByKey(tab.key);
        if (obj) {
            const badges = Explorer.computeObjectBadges(obj);
            Explorer.updateTabBadges(tab.key, badges);
        }
    });
}
```

**Step 4: For 017 — warning badges after template edit**
After staging an edit to a template, call a function that re-checks warning badges for all objects that `use` the edited template. This may require traversing the template dependency tree.

**Step 5: Validate with Playwright**
Reproduce Task 1 Step 5:
- After Ctrl+Z undo, PING service tab should show no BROKEN REFERENCE badge

**Step 6: Run ESLint**

**Step 7: Commit**
```bash
git add static/js/explorer/badge-issues.js static/js/explorer/object-editor.js
git commit -m "fix: refresh breadcrumb badges on undo and template cascade

Fixes #002-badge, #017 — badges on open tabs were not re-evaluated after
undo operations or template inheritance chain changes.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix 019 — Resolved attributes show staged template edits

**Files:**
- Read + Modify: `static/js/explorer/relations-loader.js` OR `static/js/explorer/object-editor.js`

**Step 1: Find where resolved attributes are computed**
Read `static/js/explorer/object-editor.js` around the `renderInheritedAttributes` function. Find where the template inheritance chain is followed to compute resolved values.

**Step 2: Overlay pending edits on template chain**
When computing resolved attributes for a template in the chain, check if that template has a pending edit in `state.pendingEdits`. If it does, use the staged values instead of the disk values:

```javascript
function resolveAttributeFromChain(chain, attrName) {
    for (const template of chain) {
        // Check if template has pending edit
        const pendingEdit = state.pendingEdits.get(template.global_index);
        const attrs = pendingEdit ? pendingEdit.edited : template.attributes;
        if (attrs && attrName in attrs) {
            return { value: attrs[attrName], source: template.name };
        }
    }
    return null;
}
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 4 (from discovery 019):
1. Edit generic-host template, change `notifications_enabled` to `0`
2. Open linux-server → Impact & Relationships → resolved attrs
3. Should show `notifications_enabled: 0` (staged value), not `1` (disk value)

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: resolved attributes table incorporates pending staged template edits

Fixes #019 — inherited attribute resolution read from disk, ignoring staged
edits to parent templates, showing stale resolved values.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Final Playwright validation — all 6 bugs resolved

Verify:
- [ ] Editor shows staged values after page refresh (039)
- [ ] Status badges appear on auto-restore (040)
- [ ] Impact panel shows correct object's data on tab switch (003-relationships)
- [ ] BROKEN REFERENCE badge clears after undo (002-badge)
- [ ] Resolved attrs show staged template values (019)

Run: `python3 -m pytest tests/ -v`
