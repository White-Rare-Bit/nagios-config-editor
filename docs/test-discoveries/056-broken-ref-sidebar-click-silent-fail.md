# Bug 056: Clicking Broken Reference Node in Graph Sidebar Silently Opens Explorer Without the Object

**Severity**: Medium
**Area**: Graph View — Sidebar Node Links
**Discovered**: 2026-02-19

## Description

Clicking any node entry in the Graph View sidebar navigates to the Object Explorer via `openNodeInExplorer(type, name)`, which goes to `/explorer?search=<name>&type=<type>`. For existing objects this works correctly. For broken reference nodes (`exists: false`, shown with ✗), the Explorer navigates to the page but cannot find the non-existent object — and silently falls back to displaying whatever was previously open, with no error, toast, or indication of failure.

## Steps to Reproduce

1. Open Graph View, add `web-prod-01` (host) via search
2. Apply Full Graph — `core-switch-01` ✗ appears in the NODES sidebar (broken reference, `web-prod-01.parents = core-switch-01`)
3. Click `core-switch-01 ✗` in the sidebar
4. Observe: page navigates to `/explorer` — but Explorer shows the **previously open object** (`web-prod-01`), not `core-switch-01`
5. No toast, no error banner, no "object not found" message

## Root Cause

`openNodeInExplorer(type, name)` in `dependencies.js:2413`:

```javascript
function openNodeInExplorer(type, name) {
    window.location.href = `/explorer?search=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}`;
}
```

The Explorer receives `?search=core-switch-01&type=host`, searches, finds nothing (the host doesn't exist in any config file), and falls back to the previous session state. No negative feedback is given.

The sidebar render at `dependencies.js:1311` calls `openNodeInExplorer` unconditionally for both existing and broken reference nodes:

```javascript
onclick="openNodeInExplorer('${escapeAttr(node.type)}', '${escapeAttr(node.label)}')"
```

## Expected Behaviour

When a broken reference node is clicked:
- **Option A**: Show a toast: *"'core-switch-01' is not defined in any config file — it cannot be opened in Explorer."*
- **Option B**: Disable the click / show cursor:default for broken reference sidebar items, and instead show a tooltip: *"Referenced but not defined — cannot open in Explorer"*
- **Option C**: Navigate to Explorer with a filter/highlight showing that the object is missing

## Additional Context

- Sidebar clicks for EXISTING nodes work correctly: `/explorer?search=web-prod-01&type=host` opens `web-prod-01` in the Editor panel
- Only `exists: false` nodes are affected
- The ✗ badge in the sidebar does tell the user the object is broken — but clicking it still silently navigates away from Graph View, which is confusing

## Screenshot

`screenshots/056-broken-ref-open-in-explorer-silent-fail.png` — Explorer shows `web-prod-01` after clicking `core-switch-01 ✗` in Graph View sidebar. No indication of failure.
